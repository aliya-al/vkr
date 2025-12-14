import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.utils.database import get_async_session
from app.utils.templates import templates

from .utils import slugify

router = APIRouter()


@router.get("/brands", response_class=HTMLResponse)
async def brands_list(request: Request, session: AsyncSession = Depends(get_async_session)):
    result = await session.execute(select(Brand).order_by(Brand.name))
    brands = result.scalars().all()
    return templates.TemplateResponse(
        "admin/catalog/brands/brands_list.html",
        {"request": request, "brands": brands},
    )


@router.get("/brands/create", response_class=HTMLResponse)
async def brand_create_page(request: Request):
    return templates.TemplateResponse(
        "admin/catalog/brands/brand_create.html",
        {"request": request},
    )


@router.post("/brands/create")
async def brand_create(
    name: str = Form(...),
    session: AsyncSession = Depends(get_async_session),
):
    brand = Brand(name=name, slug=slugify(name))
    session.add(brand)
    await session.commit()
    return RedirectResponse("/admin/catalog/brands", status_code=303)


@router.get("/brands/{brand_id}/edit", response_class=HTMLResponse)
async def brand_edit_page(brand_id: uuid.UUID, request: Request, session: AsyncSession = Depends(get_async_session)):
    result = await session.execute(select(Brand).where(Brand.id == brand_id))
    brand = result.scalar_one_or_none()
    if not brand:
        raise HTTPException(status_code=404)

    return templates.TemplateResponse(
        "admin/catalog/brands/brand_edit.html",
        {"request": request, "brand": brand},
    )


@router.post("/brands/{brand_id}/edit")
async def brand_edit(
    brand_id: uuid.UUID,
    name: str = Form(...),
    session: AsyncSession = Depends(get_async_session),
):
    result = await session.execute(select(Brand).where(Brand.id == brand_id))
    brand = result.scalar_one_or_none()
    if not brand:
        raise HTTPException(status_code=404)

    brand.name = name
    brand.slug = slugify(name)
    await session.commit()
    return RedirectResponse("/admin/catalog/brands", status_code=303)


@router.post("/brands/{brand_id}/delete")
async def brand_delete(brand_id: uuid.UUID, session: AsyncSession = Depends(get_async_session)):
    result = await session.execute(select(Brand).where(Brand.id == brand_id))
    brand = result.scalar_one_or_none()
    if not brand:
        raise HTTPException(status_code=404)

    await session.delete(brand)
    await session.commit()
    return RedirectResponse("/admin/catalog/brands", status_code=303)
