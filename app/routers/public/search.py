from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.category import Category
from app.models.product import Product
from app.services.compare import get_compare_ids
from app.services.favorites import get_favorite_ids
from app.utils.database import get_async_session
from app.utils.templates import templates

router = APIRouter()


def _calc_display_price(price: int, discount_percent: int | None) -> int:
    if not discount_percent:
        return price
    pct = max(0, min(int(discount_percent), 100))
    return int(round(price * (100 - pct) / 100))


@router.get("/search", response_class=HTMLResponse)
@router.get("/search/", response_class=HTMLResponse)
async def search_page(
    request: Request,
    q: str = "",
    session: AsyncSession = Depends(get_async_session),
):
    query = (q or "").strip()
    products: list[dict] = []

    if query:
        stmt = (
            select(Product)
            .join(Category, Product.category_id == Category.id)
            .where(
                Product.is_active.is_(True),
                or_(
                    Product.name.ilike(f"%{query}%"),
                    Category.name.ilike(f"%{query}%"),
                ),
            )
            .options(selectinload(Product.images))
            .order_by(Product.name.asc())
        )
        res = await session.execute(stmt)
        rows = res.scalars().all()

        for p in rows:
            main_image = p.images[0].file_path if p.images else None
            products.append(
                {
                    "id": str(p.id),
                    "slug": p.slug,
                    "name": p.name,
                    "price": p.price,
                    "discount_percent": p.discount_percent,
                    "display_price": _calc_display_price(p.price, p.discount_percent),
                    "main_image": main_image,
                }
            )

    fav_ids = [str(x) for x in (get_favorite_ids(request.session) or [])]
    cmp_ids = [str(x) for x in (get_compare_ids(request.session) or [])]

    return templates.TemplateResponse(
        "public/catalog/search.html",
        {
            "request": request,
            "q": query,
            "products": products,
            "show_prompt": not bool(query),
            "fav_ids": fav_ids,
            "cmp_ids": cmp_ids,
            "fav_ids_set": set(fav_ids),
            "cmp_ids_set": set(cmp_ids),
        },
    )


@router.get("/search/suggest", response_class=JSONResponse)
async def search_suggest(
    q: str = Query(default="", max_length=120),
    session: AsyncSession = Depends(get_async_session),
):
    query = (q or "").strip()
    if not query:
        return {"items": []}

    cat_stmt = (
        select(Category)
        .join(Product, Product.category_id == Category.id)
        .where(
            Product.is_active.is_(True),
            Category.name.ilike(f"%{query}%"),
        )
        .distinct()
        .order_by(Category.name.asc())
        .limit(3)
    )
    categories = (await session.execute(cat_stmt)).scalars().all()

    prod_stmt = (
        select(Product)
        .join(Category, Product.category_id == Category.id)
        .where(
            Product.is_active.is_(True),
            or_(
                Product.name.ilike(f"%{query}%"),
                Category.name.ilike(f"%{query}%"),
            ),
        )
        .order_by(Product.name.asc())
        .limit(6)
    )
    products = (await session.execute(prod_stmt)).scalars().all()

    items: list[dict] = []
    for category in categories:
        items.append(
            {
                "type": "category",
                "title": category.name,
                "subtitle": "Категория",
                "url": f"/catalog/{category.slug}/",
            }
        )

    for product in products:
        if len(items) >= 6:
            break
        items.append(
            {
                "type": "product",
                "title": product.name,
                "subtitle": "Товар",
                "url": f"/product/{product.slug}/",
            }
        )

    return {"items": items[:6]}
