import uuid
from pathlib import Path

import anyio
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.brand import Brand
from app.models.category import Category
from app.models.product import Product
from app.models.product_image import ProductImage
from app.utils.database import get_async_session
from app.utils.templates import templates
from app.utils.delete_product_image import delete_product_image_if_local

router = APIRouter()

# Папка хранения файлов и web-путь (отсюда отдаем в <img src="...">)
_PRODUCTS_UPLOAD_DIR = Path("app/static/img/uploads/products")
_PRODUCTS_WEB_PREFIX = "/static/img/uploads/products"

# Разрешённые расширения
_ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

# Размер чанка при записи (чтобы не держать весь файл в RAM)
_CHUNK_SIZE = 1024 * 1024  # 1MB


def _ext_or_empty(filename: str) -> str:
    """Достаём расширение и проверяем, что оно разрешено."""
    ext = Path(filename).suffix.lower()
    return ext if ext in _ALLOWED_EXT else ""


async def _save_product_image(file: UploadFile) -> str:
    """
    Асинхронно сохранить картинку чанками и вернуть web-path.
    не блокируем event loop и не читаем файл целиком в память.
    """
    # создаём папку, если её ещё нет
    _PRODUCTS_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # проверяем расширение
    ext = _ext_or_empty(file.filename or "")
    if not ext:
        raise ValueError("Неподдерживаемый формат изображения.")

    # генерируем безопасное имя файла
    name = f"{uuid.uuid4().hex}{ext}"
    dst = _PRODUCTS_UPLOAD_DIR / name

    # пишем в файл чанками
    try:
        async with await anyio.open_file(dst, "wb") as out:
            while True:
                chunk = await file.read(_CHUNK_SIZE)
                if not chunk:
                    break
                await out.write(chunk)
    finally:
        # освобождаем ресурсы UploadFile (временный файл/дескриптор)
        try:
            await file.close()
        except Exception:
            pass

    # возвращаем путь для шаблонов
    return f"{_PRODUCTS_WEB_PREFIX}/{name}"

def _only_leaf_categories(
    categories: list[Category], current_category_id: uuid.UUID | None = None
) -> list[Category]:
    leaves: list[Category] = []
    current_category: Category | None = None

    for category in categories:
        if not category.children:
            leaves.append(category)
        if current_category_id and category.id == current_category_id:
            current_category = category

    if current_category and current_category not in leaves:
        leaves.append(current_category)

    return leaves


async def _get_form_choices(session: AsyncSession, current_category_id: uuid.UUID | None = None):
    """Подгружаем категории и бренды для форм create/edit."""
    categories_result = await session.execute(
        select(Category).options(selectinload(Category.children)).order_by(Category.name)
    )
    brands_result = await session.execute(select(Brand).order_by(Brand.name))

    categories = _only_leaf_categories(categories_result.scalars().all(), current_category_id)
    brands = brands_result.scalars().all()
    return categories, brands


def _sort_images(images: list[ProductImage]) -> list[ProductImage]:
    """Сортировка для отображения/логики: сначала главное (is_main=True), затем по id."""
    return sorted(images, key=lambda x: (not bool(getattr(x, "is_main", False)), x.id))


def _pick_next_main_after_delete(remaining: list[ProductImage], deleted_main_id: int | None) -> ProductImage | None:
    """
    Выбор нового главного, когда главное удалили.
    """
    if not remaining:
        return None

    remaining_sorted = sorted(remaining, key=lambda x: x.id)

    if deleted_main_id is not None:
        for img in remaining_sorted:
            if img.id > deleted_main_id:
                return img

    return remaining_sorted[0]


@router.get("/admin/products", response_class=HTMLResponse)
async def products_list(request: Request, session: AsyncSession = Depends(get_async_session)):
    # Важно: подгружаем images, чтобы index.html мог показывать фото без дополнительных запросов
    result = await session.execute(
        select(Product)
        .options(selectinload(Product.category), selectinload(Product.brand), selectinload(Product.images))
        .order_by(Product.name)
    )
    products = result.scalars().all()
    return templates.TemplateResponse("admin/products/index.html", {"request": request, "products": products})


@router.get("/admin/products/new", response_class=HTMLResponse)
async def product_create_page(request: Request, session: AsyncSession = Depends(get_async_session)):
    categories, brands = await _get_form_choices(session)
    return templates.TemplateResponse(
        "admin/products/create.html",
        {"request": request, "categories": categories, "brands": brands, "error": None},
    )


@router.post("/admin/products/new")
async def product_create(
    name: str = Form(...),
    description: str | None = Form(None),
    category_id: str = Form(...),
    main_image: UploadFile = File(...),  # главное фото обязательно в create
    extra_images: list[UploadFile] | None = File(None),  # доп. фото (0..N)
    brand_id: str | None = Form(None),
    price: int = Form(...),
    volume_m3: float = Form(...),
    weight_kg: float = Form(...),
    is_active: bool = Form(False),
    discount_percent: str | None = Form(None),
    session: AsyncSession = Depends(get_async_session),
):
    new_files: list[str] = []
    # old_files_to_delete: что удаляем ПОСЛЕ commit
    old_files_to_delete: list[str] = []

    try:
        async with session.begin():
            product = Product(
                name=name,
                description=description,
                category_id=uuid.UUID(category_id),
                brand_id=uuid.UUID(brand_id) if brand_id else None,
                price=price,
                volume_m3=volume_m3,
                weight_kg=weight_kg,
                is_active=is_active,
                discount_percent=int(discount_percent) if discount_percent else None,
            )
            session.add(product)
            # flush нужен, чтобы получить product.id до вставки картинок
            await session.flush()

            # главное фото
            if not main_image or not main_image.filename:
                raise HTTPException(status_code=400, detail="Главное фото обязательно.")
            try:
                main_path = await _save_product_image(main_image)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

            new_files.append(main_path)
            session.add(ProductImage(product_id=product.id, file_path=main_path, is_main=True))

            # дополнительные фото
            for f in (extra_images or []):
                if not f or not f.filename:
                    continue
                try:
                    p = await _save_product_image(f)
                except ValueError:
                    continue
                new_files.append(p)
                session.add(ProductImage(product_id=product.id, file_path=p, is_main=False))

        # commit уже прошёл — можно удалять старые файлы (если бы они были)
        for p in old_files_to_delete:
            delete_product_image_if_local(p)

    except HTTPException:
        for p in new_files:
            delete_product_image_if_local(p)
        raise
    except Exception:
        for p in new_files:
            delete_product_image_if_local(p)
        raise

    return RedirectResponse("/admin/products", status_code=303)


@router.get("/admin/products/{product_id}/edit", response_class=HTMLResponse)
async def product_edit_page(
    product_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    result = await session.execute(
        select(Product)
        .where(Product.id == product_id)
        .options(
            selectinload(Product.category),
            selectinload(Product.brand),
            selectinload(Product.images),
        )
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404)

    categories, brands = await _get_form_choices(session, product.category_id)
    return templates.TemplateResponse(
        "admin/products/edit.html",
        {"request": request, "product": product, "categories": categories, "brands": brands, "error": None},
    )


@router.post("/admin/products/{product_id}/edit")
async def product_edit(
    product_id: uuid.UUID,
    request: Request,
    name: str = Form(...),
    description: str | None = Form(None),
    category_id: str = Form(...),
    brand_id: str | None = Form(None),
    price: int = Form(...),
    volume_m3: float = Form(...),
    weight_kg: float = Form(...),
    is_active: bool = Form(False),
    new_images: list[UploadFile] | None = File(None),
    discount_percent: str | None = Form(None),
    session: AsyncSession = Depends(get_async_session),
):
    new_files: list[str] = []
    old_files_to_delete: list[str] = []

    form = await request.form()

    set_main_id_raw = form.get("set_main_id")

    try:
        async with session.begin():
            # достаём товар вместе с картинками
            result = await session.execute(
                select(Product).where(Product.id == product_id).options(selectinload(Product.images))
            )
            product = result.scalar_one_or_none()
            if not product:
                raise HTTPException(status_code=404)

            # обновляем поля товара
            product.name = name
            product.description = description
            product.category_id = uuid.UUID(category_id)
            product.brand_id = uuid.UUID(brand_id) if brand_id else None
            product.price = price
            product.volume_m3 = volume_m3
            product.weight_kg = weight_kg
            product.is_active = is_active
            product.discount_percent = int(discount_percent) if discount_percent else None

            # сортируем текущие картинки (главная первой)
            images_sorted = _sort_images(list(product.images or []))

            if not images_sorted:
                main_fallback = form.get("main_image_fallback")  # UploadFile или None
                if main_fallback and getattr(main_fallback, "filename", ""):
                    try:
                        p = await _save_product_image(main_fallback)
                    except ValueError as e:
                        raise HTTPException(status_code=400, detail=str(e))

                    new_files.append(p)
                    session.add(ProductImage(product_id=product.id, file_path=p, is_main=True))
                    await session.flush()

                    # перечитаем изображения, чтобы дальше работать единообразно
                    result2 = await session.execute(
                        select(Product).where(Product.id == product_id).options(selectinload(Product.images))
                    )
                    product = result2.scalar_one()
                    images_sorted = _sort_images(list(product.images or []))

            set_main_id: int | None = None
            if set_main_id_raw:
                try:
                    set_main_id = int(str(set_main_id_raw))
                except Exception:
                    set_main_id = None

            if set_main_id is not None and images_sorted:
                # 1) проверяем, что выбранное фото существует
                target = next((img for img in images_sorted if img.id == set_main_id), None)
                if not target:
                    raise HTTPException(status_code=400, detail="Выбранное главное фото не найдено.")

                # 2) шаг 1: снимаем главного у всех
                for img in images_sorted:
                    img.is_main = False
                await session.flush()  # гарантирует, что в БД теперь 0 главных

                # 3) шаг 2: назначаем выбранное главным и снова flush
                target.is_main = True
                await session.flush()

                # пересортируем для дальнейшей логики
                images_sorted = _sort_images(list(images_sorted))

            to_delete: list[ProductImage] = []

            # запомним id удалённого главного (если удаляем)
            deleted_main_id: int | None = None

            for img in images_sorted:
                replace_file = form.get(f"replace_{img.id}")
                remove_flag = form.get(f"remove_{img.id}")

                if replace_file and getattr(replace_file, "filename", ""):
                    try:
                        new_path = await _save_product_image(replace_file)
                    except ValueError:
                        continue

                    new_files.append(new_path)
                    old_files_to_delete.append(img.file_path)
                    img.file_path = new_path

                if remove_flag:
                    if getattr(img, "is_main", False):
                        deleted_main_id = img.id  # главное удаляют
                    old_files_to_delete.append(img.file_path)
                    to_delete.append(img)

            for img in to_delete:
                await session.delete(img)

            for f in (new_images or []):
                if not f or not f.filename:
                    continue
                try:
                    p = await _save_product_image(f)
                except ValueError:
                    continue
                new_files.append(p)
                session.add(ProductImage(product_id=product.id, file_path=p, is_main=False))

            await session.flush()

            result_imgs = await session.execute(
                select(Product).where(Product.id == product_id).options(selectinload(Product.images))
            )
            product = result_imgs.scalar_one()
            remaining = list(product.images or [])

            # Если картинок не осталось — ничего не назначаем.
            if not remaining:
                # ничего не делаем
                pass
            else:
                # если осталось >0 картинок — гарантируем, что главное ровно одно
                current_mains = [img for img in remaining if img.is_main]

                if len(current_mains) == 1:
                    pass
                else:
                    # шаг 1: снять флаг у всех и flush
                    for img in remaining:
                        img.is_main = False
                    await session.flush()

                    # шаг 2: назначить нового главного и flush
                    new_main = _pick_next_main_after_delete(remaining, deleted_main_id)
                    if new_main:
                        new_main.is_main = True
                        await session.flush()

        for p in old_files_to_delete:
            delete_product_image_if_local(p)

    except HTTPException:
        for p in new_files:
            delete_product_image_if_local(p)
        raise
    except Exception:
        for p in new_files:
            delete_product_image_if_local(p)
        raise

    return RedirectResponse("/admin/products", status_code=303)


@router.post("/admin/products/{product_id}/delete")
async def product_delete(product_id: uuid.UUID, session: AsyncSession = Depends(get_async_session)):
    # файлы удаляем после commit, чтобы при ошибке не потерять данные
    old_files_to_delete: list[str] = []

    try:
        async with session.begin():
            result = await session.execute(
                select(Product).where(Product.id == product_id).options(selectinload(Product.images))
            )
            product = result.scalar_one_or_none()
            if not product:
                raise HTTPException(status_code=404)

            for img in (product.images or []):
                old_files_to_delete.append(img.file_path)
            await session.delete(product)

        for p in old_files_to_delete:
            delete_product_image_if_local(p)

    except HTTPException:
        raise

    return RedirectResponse("/admin/products", status_code=303)
