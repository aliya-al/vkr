# app/routers/public/catalog.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.category import Category
from app.models.product import Product
from app.utils.database import get_async_session
from app.utils.templates import templates

router = APIRouter()


def _calc_display_price(price: int, discount_percent: int | None) -> int:
    """
    Цена для показа в каталоге.
    Если скидки нет — показываем price.
    """
    if not discount_percent:
        return price
    pct = max(0, min(int(discount_percent), 100))
    return int(round(price * (100 - pct) / 100))


@router.get("/catalog/", response_class=HTMLResponse)
async def catalog_index(request: Request, session: AsyncSession = Depends(get_async_session)):
    """
    /catalog/ — список категорий (показываем дерево от корня).
    """
    res = await session.execute(
        select(Category)
        .where(Category.parent_id.is_(None))
        .options(selectinload(Category.children))
        .order_by(Category.name)
    )
    root_categories = res.scalars().all()

    return templates.TemplateResponse(
        "public/catalog/catalog.html",
        {"request": request, "root_categories": root_categories},
    )


@router.get("/catalog/{slug}", response_class=HTMLResponse)
async def catalog_category(slug: str, request: Request, session: AsyncSession = Depends(get_async_session)):
    """
    /catalog/<slug> — страница категории:
      - показывает подкатегории (если есть)
      - показывает товары текущей категории (обычно это лист, но поддерживаем и смешанный вывод)
    """
    res = await session.execute(
        select(Category)
        .where(Category.slug == slug)
        .options(selectinload(Category.children))
    )
    category = res.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404, detail="Категория не найдена")

    prod_res = await session.execute(
        select(Product)
        .where(Product.category_id == category.id, Product.is_active.is_(True))
        .options(selectinload(Product.images))
        .order_by(Product.name)
    )
    products = prod_res.scalars().all()

    product_cards = []
    for p in products:
        main_image = p.images[0].file_path if p.images else None  # главное уже первым по order_by в модели
        product_cards.append(
            {
                "id": str(p.id),
                "name": p.name,
                "price": p.price,
                "discount_percent": p.discount_percent,
                "display_price": _calc_display_price(p.price, p.discount_percent),
                "main_image": main_image,
            }
        )

    return templates.TemplateResponse(
        "public/catalog/category.html",
        {
            "request": request,
            "category": category,
            "subcategories": list(category.children or []),
            "products": product_cards,
        },
    )
