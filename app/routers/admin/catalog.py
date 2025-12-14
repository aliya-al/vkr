import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.brand import Brand
from app.models.category import Category
from app.models.product import Product
from app.models.product_image import ProductImage
from app.routers.admin.deps import require_admin_or_404
from app.utils.database import get_async_session
from app.utils.templates import templates

router = APIRouter(
    prefix="/catalog",
    dependencies=[Depends(require_admin_or_404)],
)


@router.get("/categories", response_class=HTMLResponse)
async def categories_list(request: Request, session: AsyncSession = Depends(get_async_session)):
    result = await session.execute(
        select(Category)
        .options(selectinload(Category.parent))
        .order_by(Category.name)
    )
    categories = result.scalars().all()
    return templates.TemplateResponse(
        "admin/catalog/categories/list.html",
        {"request": request, "categories": categories},
    )


@router.get("/categories/create", response_class=HTMLResponse)
async def category_create_page(request: Request, session: AsyncSession = Depends(get_async_session)):
    result = await session.execute(select(Category).order_by(Category.name))
    categories = result.scalars().all()
    return templates.TemplateResponse(
        "admin/catalog/categories/form.html",
        {
            "request": request,
            "category": None,
            "categories": categories,
            "action_url": "/admin/catalog/categories/create",
            "title": "Создать категорию",
        },
    )


@router.post("/categories/create")
async def category_create(
    name: str = Form(...),
    slug: str = Form(...),
    parent_id: str | None = Form(None),
    session: AsyncSession = Depends(get_async_session),
):
    category = Category(
        name=name,
        slug=slug,
        parent_id=uuid.UUID(parent_id) if parent_id else None,
    )
    session.add(category)
    await session.commit()
    return RedirectResponse("/admin/catalog/categories", status_code=303)


@router.get("/categories/{category_id}/edit", response_class=HTMLResponse)
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
        "admin/catalog/categories/form.html",
        {
            "request": request,
            "category": category,
            "categories": categories,
            "action_url": f"/admin/catalog/categories/{category_id}/edit",
            "title": "Редактировать категорию",
        },
    )


@router.post("/categories/{category_id}/edit")
async def category_edit(
    category_id: uuid.UUID,
    name: str = Form(...),
    slug: str = Form(...),
    parent_id: str | None = Form(None),
    session: AsyncSession = Depends(get_async_session),
):
    result = await session.execute(select(Category).where(Category.id == category_id))
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404)

    new_parent_id = uuid.UUID(parent_id) if parent_id else None
    category.name = name
    category.slug = slug
    category.parent_id = new_parent_id

    await session.commit()
    return RedirectResponse("/admin/catalog/categories", status_code=303)


@router.post("/categories/{category_id}/delete")
async def category_delete(category_id: uuid.UUID, session: AsyncSession = Depends(get_async_session)):
    result = await session.execute(select(Category).where(Category.id == category_id))
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404)

    await session.delete(category)
    await session.commit()
    return RedirectResponse("/admin/catalog/categories", status_code=303)


@router.get("/brands", response_class=HTMLResponse)
async def brands_list(request: Request, session: AsyncSession = Depends(get_async_session)):
    result = await session.execute(select(Brand).order_by(Brand.name))
    brands = result.scalars().all()
    return templates.TemplateResponse(
        "admin/catalog/brands/list.html",
        {"request": request, "brands": brands},
    )


@router.get("/brands/create", response_class=HTMLResponse)
async def brand_create_page(request: Request):
    return templates.TemplateResponse(
        "admin/catalog/brands/form.html",
        {
            "request": request,
            "brand": None,
            "action_url": "/admin/catalog/brands/create",
            "title": "Создать бренд",
        },
    )


@router.post("/brands/create")
async def brand_create(
    name: str = Form(...),
    slug: str = Form(...),
    session: AsyncSession = Depends(get_async_session),
):
    brand = Brand(name=name, slug=slug)
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
        "admin/catalog/brands/form.html",
        {
            "request": request,
            "brand": brand,
            "action_url": f"/admin/catalog/brands/{brand_id}/edit",
            "title": "Редактировать бренд",
        },
    )


@router.post("/brands/{brand_id}/edit")
async def brand_edit(
    brand_id: uuid.UUID,
    name: str = Form(...),
    slug: str = Form(...),
    session: AsyncSession = Depends(get_async_session),
):
    result = await session.execute(select(Brand).where(Brand.id == brand_id))
    brand = result.scalar_one_or_none()
    if not brand:
        raise HTTPException(status_code=404)

    brand.name = name
    brand.slug = slug
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


@router.get("/products", response_class=HTMLResponse)
async def products_list(request: Request, session: AsyncSession = Depends(get_async_session)):
    result = await session.execute(
        select(Product)
        .options(selectinload(Product.category), selectinload(Product.brand))
        .order_by(Product.name)
    )
    products = result.scalars().all()
    return templates.TemplateResponse(
        "admin/catalog/products/list.html",
        {"request": request, "products": products},
    )


async def _get_form_choices(session: AsyncSession):
    categories_result = await session.execute(select(Category).order_by(Category.name))
    brands_result = await session.execute(select(Brand).order_by(Brand.name))
    return categories_result.scalars().all(), brands_result.scalars().all()


@router.get("/products/create", response_class=HTMLResponse)
async def product_create_page(request: Request, session: AsyncSession = Depends(get_async_session)):
    categories, brands = await _get_form_choices(session)
    return templates.TemplateResponse(
        "admin/catalog/products/form.html",
        {
            "request": request,
            "product": None,
            "categories": categories,
            "brands": brands,
            "action_url": "/admin/catalog/products/create",
            "title": "Создать товар",
            "images": [],
        },
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
        .options(selectinload(Product.category), selectinload(Product.brand), selectinload(Product.images))
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404)

    categories, brands = await _get_form_choices(session)
    return templates.TemplateResponse(
        "admin/catalog/products/form.html",
        {
            "request": request,
            "product": product,
            "categories": categories,
            "brands": brands,
            "action_url": f"/admin/catalog/products/{product_id}/edit",
            "title": "Редактировать товар",
            "images": product.images,
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


@router.post("/products/{product_id}/images")
async def product_image_create(
    product_id: uuid.UUID,
    file_path: str = Form(...),
    session: AsyncSession = Depends(get_async_session),
):
    result = await session.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404)

    image = ProductImage(product_id=product_id, file_path=file_path)
    session.add(image)
    await session.commit()
    return RedirectResponse(f"/admin/catalog/products/{product_id}/edit", status_code=303)


@router.post("/products/{product_id}/images/{image_id}/delete")
async def product_image_delete(
    product_id: uuid.UUID,
    image_id: int,
    session: AsyncSession = Depends(get_async_session),
):
    result = await session.execute(
        select(ProductImage).where(
            ProductImage.id == image_id, ProductImage.product_id == product_id
        )
    )
    image = result.scalar_one_or_none()
    if not image:
        raise HTTPException(status_code=404)

    await session.delete(image)
    await session.commit()
    return RedirectResponse(f"/admin/catalog/products/{product_id}/edit", status_code=303)
