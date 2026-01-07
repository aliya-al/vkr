import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.utils.database import get_async_session
from app.utils.strings import slugify
from app.utils.templates import templates

router = APIRouter()

@router.get("/admin/brands", response_class=HTMLResponse)
async def brands_list(request: Request, session: AsyncSession = Depends(get_async_session)):
    result = await session.execute(select(Brand).order_by(Brand.name))
    brands = result.scalars().all()
    return templates.TemplateResponse(
        "admin/brands/index.html",
        {"request": request, "brands": brands},
    )

@router.get("/admin/brands/new", response_class=HTMLResponse)
async def brand_create_page(request: Request):
    return templates.TemplateResponse(
        "admin/brands/create.html",
        {"request": request},
    )

@router.post("/admin/brands/new")
async def brand_create(
    name: str = Form(...),
    session: AsyncSession = Depends(get_async_session),
):
    brand = Brand(name=name, slug=slugify(name))
    session.add(brand)
    await session.commit()
    return RedirectResponse("/admin/brands", status_code=303)

@router.get("/admin/brands/{brand_id}/edit", response_class=HTMLResponse)
async def brand_edit_page(brand_id: uuid.UUID, request: Request, session: AsyncSession = Depends(get_async_session)):
    result = await session.execute(select(Brand).where(Brand.id == brand_id))
    brand = result.scalar_one_or_none()
    if not brand:
        raise HTTPException(status_code=404)

    return templates.TemplateResponse(
        "admin/brands/edit.html",
        {"request": request, "brand": brand},
    )

@router.post("/admin/brands/{brand_id}/edit")
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
    return RedirectResponse("/admin/brands", status_code=303)


@router.post("/admin/brands/{brand_id}/delete")
async def brand_delete(brand_id: uuid.UUID, session: AsyncSession = Depends(get_async_session)):
    result = await session.execute(select(Brand).where(Brand.id == brand_id))
    brand = result.scalar_one_or_none()
    if not brand:
        raise HTTPException(status_code=404)

    await session.delete(brand)
    await session.commit()
    return RedirectResponse("/admin/brands", status_code=303)
