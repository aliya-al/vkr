import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.brand import Brand
from app.models.category import Category
from app.models.product import Product
from app.utils.database import get_async_session
from app.utils.templates import templates

router = APIRouter()


@router.get("/products", response_class=HTMLResponse)
async def products_list(request: Request, session: AsyncSession = Depends(get_async_session)):
    result = await session.execute(
        select(Product)
        .options(selectinload(Product.category), selectinload(Product.brand))
        .order_by(Product.name)
    )
    products = result.scalars().all()
    return templates.TemplateResponse(
        "admin/catalog/products/products_list.html",
        {"request": request, "products": products},
    )


async def _get_form_choices(session: AsyncSession, current_category_id: uuid.UUID | None = None):
    categories_result = await session.execute(
        select(Category).options(selectinload(Category.children)).order_by(Category.name)
    )
    brands_result = await session.execute(select(Brand).order_by(Brand.name))
    categories = [
        category
        for category in categories_result.scalars().all()
        if not category.children or category.id == current_category_id
    ]
    return categories, brands_result.scalars().all()


@router.get("/products/create", response_class=HTMLResponse)
async def product_create_page(request: Request, session: AsyncSession = Depends(get_async_session)):
    categories, brands = await _get_form_choices(session)
    return templates.TemplateResponse(
        "admin/catalog/products/product_create.html",
        {"request": request, "categories": categories, "brands": brands},
    )


@router.post("/products/create")
async def product_create(
    name: str = Form(...),
    description: str | None = Form(None),
    category_id: str = Form(...),
    brand_id: str | None = Form(None),
    price: int = Form(...),
    volume_m3: float = Form(...),
    weight_kg: float = Form(...),
    is_active: bool = Form(False),
    discount_percent: str | None = Form(None),
    session: AsyncSession = Depends(get_async_session),
):
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
    await session.commit()
    return RedirectResponse("/admin/catalog/products", status_code=303)


@router.get("/products/{product_id}/edit", response_class=HTMLResponse)
async def product_edit_page(
    product_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    result = await session.execute(
        select(Product)
        .where(Product.id == product_id)
        .options(selectinload(Product.category), selectinload(Product.brand))
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404)

    categories, brands = await _get_form_choices(session, current_category_id=product.category_id)
    return templates.TemplateResponse(
        "admin/catalog/products/product_edit.html",
        {
            "request": request,
            "product": product,
            "categories": categories,
            "brands": brands,
        },
    )


@router.post("/products/{product_id}/edit")
async def product_edit(
    product_id: uuid.UUID,
    name: str = Form(...),
    description: str | None = Form(None),
    category_id: str = Form(...),
    brand_id: str | None = Form(None),
    price: int = Form(...),
    volume_m3: float = Form(...),
    weight_kg: float = Form(...),
    is_active: bool = Form(False),
    discount_percent: str | None = Form(None),
    session: AsyncSession = Depends(get_async_session),
):
    result = await session.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404)

    product.name = name
    product.description = description
    product.category_id = uuid.UUID(category_id)
    product.brand_id = uuid.UUID(brand_id) if brand_id else None
    product.price = price
    product.volume_m3 = volume_m3
    product.weight_kg = weight_kg
    product.is_active = is_active
    product.discount_percent = int(discount_percent) if discount_percent else None

    await session.commit()
    return RedirectResponse("/admin/catalog/products", status_code=303)


@router.post("/products/{product_id}/delete")
async def product_delete(product_id: uuid.UUID, session: AsyncSession = Depends(get_async_session)):
    result = await session.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404)

    await session.delete(product)
    await session.commit()
    return RedirectResponse("/admin/catalog/products", status_code=303)
