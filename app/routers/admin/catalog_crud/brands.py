import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.utils.database import get_async_session
from app.utils.strings import slugify, ensure_unique_slug
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

@router.post("/admin/brands/new", response_class=HTMLResponse)
async def brand_create(
    request: Request,
    name: str = Form(...),
    session: AsyncSession = Depends(get_async_session),
):
    name_clean = (name or "").strip()
    if not name_clean:
        return templates.TemplateResponse(
            "admin/brands/create.html",
            {"request": request, "error": "Название обязательно.", "name_value": ""},
            status_code=400,
        )

    # (опционально, но удобно) ранняя проверка дубля имени (без 500)
    exists_stmt = select(Brand.id).where(func.lower(Brand.name) == name_clean.lower())
    if (await session.execute(exists_stmt)).first():
        return templates.TemplateResponse(
            "admin/brands/create.html",
            {"request": request, "error": "Такой бренд уже существует.", "name_value": name_clean},
            status_code=400,
        )

    base = slugify(name_clean)
    slug = await ensure_unique_slug(session, Brand, base)

    brand = Brand(name=name_clean, slug=slug)
    session.add(brand)

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return templates.TemplateResponse(
            "admin/brands/create.html",
            {"request": request, "error": "Такой бренд уже существует.", "name_value": name_clean},
            status_code=400,
        )

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

@router.post("/admin/brands/{brand_id}/edit", response_class=HTMLResponse)
async def brand_edit(
    brand_id: uuid.UUID,
    request: Request,
    name: str = Form(...),
    session: AsyncSession = Depends(get_async_session),
):
    brand = (await session.execute(select(Brand).where(Brand.id == brand_id))).scalar_one_or_none()
    if not brand:
        raise HTTPException(status_code=404)

    name_clean = (name or "").strip()
    if not name_clean:
        return templates.TemplateResponse(
            "admin/brands/edit.html",
            {"request": request, "brand": brand, "error": "Название обязательно."},
            status_code=400,
        )

    # проверка дубля имени (кроме самой себя)
    exists_stmt = select(Brand.id).where(
        func.lower(Brand.name) == name_clean.lower(),
        Brand.id != brand_id,
    )
    if (await session.execute(exists_stmt)).first():
        brand.name = name_clean
        return templates.TemplateResponse(
            "admin/brands/edit.html",
            {"request": request, "brand": brand, "error": "Такой бренд уже существует."},
            status_code=400,
        )

    base = slugify(name_clean)
    slug = await ensure_unique_slug(session, Brand, base, exclude_id=brand_id)

    brand.name = name_clean
    brand.slug = slug

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return templates.TemplateResponse(
            "admin/brands/edit.html",
            {"request": request, "brand": brand, "error": "Такой бренд уже существует."},
            status_code=400,
        )

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
