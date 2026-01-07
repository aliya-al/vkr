import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.category import Category
from app.utils.database import get_async_session
from app.utils.strings import slugify
from app.utils.templates import templates

router = APIRouter()


@router.get("/admin/categories", response_class=HTMLResponse)
async def categories_list(request: Request, session: AsyncSession = Depends(get_async_session)):
    result = await session.execute(
        select(Category)
        .options(
            selectinload(Category.parent)
        )
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

    category.name = name
    category.slug = slugify(name)
    category.parent_id = uuid.UUID(parent_id) if parent_id else None

    await session.commit()
    return RedirectResponse("/admin/categories", status_code=303)


@router.post("/admin/categories/{category_id}/delete")
async def category_delete(category_id: uuid.UUID, session: AsyncSession = Depends(get_async_session)):
    result = await session.execute(select(Category).where(Category.id == category_id))
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404)

    await session.delete(category)
    await session.commit()
    return RedirectResponse("/admin/categories", status_code=303)
