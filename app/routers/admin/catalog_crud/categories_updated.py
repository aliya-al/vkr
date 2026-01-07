import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, delete, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.category import Category
from app.models.product import Product
from app.models.product_image import ProductImage

from app.utils.database import get_async_session
from app.utils.strings import slugify
from app.utils.templates import templates
from app.utils.delete_product_image import delete_product_image_if_local


router = APIRouter()


async def _get_subtree_category_ids(session: AsyncSession, root_id: uuid.UUID) -> list[uuid.UUID]:
    """Вернуть id категории root + всех её потомков. Используем UNION (не UNION ALL), чтобы не зависнуть при цикле."""
    q = text(
        """
        WITH RECURSIVE subcats AS (
            SELECT id
            FROM categories
            WHERE id = :root_id
            UNION
            SELECT c.id
            FROM categories c
            JOIN subcats s ON c.parent_id = s.id
        )
        SELECT id FROM subcats;
        """
    )
    rows = (await session.execute(q, {"root_id": root_id})).all()
    return [r[0] for r in rows]


async def _ensure_no_cycle(session: AsyncSession, category_id: uuid.UUID, new_parent_id: uuid.UUID | None) -> None:
    """
    Защита от циклов в дереве категорий:
    - нельзя назначить родителем саму себя
    - нельзя назначить родителем своего потомка
    """
    if not new_parent_id:
        return
    if new_parent_id == category_id:
        raise HTTPException(status_code=400, detail="Нельзя выбрать категорию саму себе родителем.")

    # Получаем всех потомков текущей категории; родитель не может быть среди них.
    descendants = await _get_subtree_category_ids(session, category_id)
    if new_parent_id in descendants:
        raise HTTPException(status_code=400, detail="Нельзя выбрать потомка в качестве родителя (получится цикл).")


@router.get("/admin/categories", response_class=HTMLResponse)
async def categories_list(request: Request, session: AsyncSession = Depends(get_async_session)):
    result = await session.execute(
        select(Category)
        .options(selectinload(Category.parent))
        .order_by(Category.name)
    )
    categories = result.scalars().all()
    return templates.TemplateResponse(
        "admin/categories/index.html",
        {"request": request, "categories": categories},
    )


@router.get("/admin/categories/new", response_class=HTMLResponse)
async def category_create_page(request: Request, session: AsyncSession = Depends(get_async_session)):
    result = await session.execute(select(Category).order_by(Category.name))
    categories = result.scalars().all()
    return templates.TemplateResponse(
        "admin/categories/create.html",
        {"request": request, "categories": categories},
    )


@router.post("/admin/categories/new")
async def category_create(
    name: str = Form(...),
    parent_id: str | None = Form(None),
    session: AsyncSession = Depends(get_async_session),
):
    # на create цикл невозможен (категории ещё нет), но запрещаем parent_id == None/uuid корректно
    category = Category(
        name=name,
        slug=slugify(name),
        parent_id=uuid.UUID(parent_id) if parent_id else None,
    )
    session.add(category)
    await session.commit()
    return RedirectResponse("/admin/categories", status_code=303)


@router.get("/admin/categories/{category_id}/edit", response_class=HTMLResponse)
async def category_edit_page(
    category_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    result = await session.execute(select(Category).where(Category.id == category_id))
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404)

    categories_result = await session.execute(
        select(Category).where(Category.id != category_id).order_by(Category.name)
    )
    categories = categories_result.scalars().all()

    return templates.TemplateResponse(
        "admin/categories/edit.html",
        {"request": request, "category": category, "categories": categories},
    )


@router.post("/admin/categories/{category_id}/edit")
async def category_edit(
    category_id: uuid.UUID,
    name: str = Form(...),
    parent_id: str | None = Form(None),
    session: AsyncSession = Depends(get_async_session),
):
    result = await session.execute(select(Category).where(Category.id == category_id))
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404)

    new_parent_id = uuid.UUID(parent_id) if parent_id else None
    await _ensure_no_cycle(session, category_id, new_parent_id)

    category.name = name
    category.slug = slugify(name)
    category.parent_id = new_parent_id

    await session.commit()
    return RedirectResponse("/admin/categories", status_code=303)


@router.post("/admin/categories/{category_id}/delete")
async def category_delete(category_id: uuid.UUID, session: AsyncSession = Depends(get_async_session)):
    """
    Удаление категории вместе со всем деревом потомков и всеми товарами внутри.
    """
    files_to_delete: list[str] = []

    async with session.begin():
        # 1) Собираем все категории в поддереве (эта + потомки).
        category_ids = await _get_subtree_category_ids(session, category_id)
        if not category_ids:
            raise HTTPException(status_code=404)

        # 2) Собираем пути картинок всех товаров в этих категориях (чтобы удалить их в конце роута).
        img_rows = await session.execute(
            select(ProductImage.file_path)
            .join(Product, ProductImage.product_id == Product.id)
            .where(Product.category_id.in_(category_ids))
        )
        files_to_delete = [r[0] for r in img_rows.all()]

        # 3) Удаляем товары (картинки в БД удалятся каскадом по FK product_images.product_id).
        await session.execute(
            delete(Product).where(Product.category_id.in_(category_ids))
        )

        # 4) Удаляем категории одним запросом (включая потомков).
        await session.execute(
            delete(Category).where(Category.id.in_(category_ids))
        )

    # 5) Коммит прошёл (вышли из session.begin) — теперь удаляем файлы с диска.
    for p in files_to_delete:
        try:
            delete_product_image_if_local(p)
        except Exception:
            # удаление файлов не должно ломать удаление категории
            pass

    return RedirectResponse("/admin/categories", status_code=303)
