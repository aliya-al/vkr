from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import case, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.category import Category
from app.models.product import Product
from app.services.compare import get_compare_ids
from app.services.favorites import get_favorite_ids
from app.utils.database import get_async_session
from app.utils.templates import templates


router = APIRouter()


def _normalize_query(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.split())


def _calc_display_price(price: int, discount_percent: int | None) -> int:
    if not discount_percent:
        return price
    pct = max(0, min(int(discount_percent), 100))
    return int(round(price * (100 - pct) / 100))


async def _find_products(session: AsyncSession, q: str) -> tuple[list[Product], bool]:
    pattern = f"%{q}%"
    prefix = f"{q}%"

    relevance = case(
        (Product.name.ilike(prefix), 0),
        (Category.name.ilike(prefix), 1),
        (Product.name.ilike(pattern), 2),
        else_=3,
    )

    base_stmt = (
        select(Product)
        .join(Category, Product.category_id == Category.id)
        .where(
            Product.is_active.is_(True),
            or_(Product.name.ilike(pattern), Category.name.ilike(pattern)),
        )
        .options(selectinload(Product.images))
        .order_by(relevance.asc(), Product.name.asc())
        .limit(120)
    )

    products = (await session.execute(base_stmt)).scalars().all()
    if products:
        return products, False

    tokens = [token for token in q.split() if len(token) >= 2]
    if not tokens:
        return [], False

    token_conds = []
    for token in tokens:
        token_pattern = f"%{token}%"
        token_conds.append(Product.name.ilike(token_pattern))
        token_conds.append(Category.name.ilike(token_pattern))

    fallback_stmt = (
        select(Product)
        .join(Category, Product.category_id == Category.id)
        .where(Product.is_active.is_(True), or_(*token_conds))
        .options(selectinload(Product.images))
        .order_by(Product.name.asc())
        .limit(120)
    )
    fallback_products = (await session.execute(fallback_stmt)).scalars().all()
    return fallback_products, bool(fallback_products)


@router.get("/search", response_class=HTMLResponse)
async def search_page(
    request: Request,
    q: str = Query(default=""),
    session: AsyncSession = Depends(get_async_session),
):
    normalized_q = _normalize_query(q)

    product_cards: list[dict] = []
    used_fallback = False

    if normalized_q:
        products, used_fallback = await _find_products(session, normalized_q)

        for product in products:
            main_image = product.images[0].file_path if product.images else None
            product_cards.append(
                {
                    "id": str(product.id),
                    "slug": product.slug,
                    "name": product.name,
                    "price": product.price,
                    "discount_percent": product.discount_percent,
                    "display_price": _calc_display_price(product.price, product.discount_percent),
                    "main_image": main_image,
                }
            )

    fav_ids = [str(x) for x in (get_favorite_ids(request.session) or [])]
    cmp_ids = [str(x) for x in (get_compare_ids(request.session) or [])]

    return templates.TemplateResponse(
        "public/search/results.html",
        {
            "request": request,
            "q": normalized_q,
            "products": product_cards,
            "used_fallback": used_fallback,
            "fav_ids": fav_ids,
            "cmp_ids": cmp_ids,
            "fav_ids_set": set(fav_ids),
            "cmp_ids_set": set(cmp_ids),
        },
    )


@router.get("/search/suggest", response_class=JSONResponse)
async def search_suggestions(
    q: str = Query(default="", max_length=120),
    session: AsyncSession = Depends(get_async_session),
):
    normalized_q = _normalize_query(q)
    if len(normalized_q) < 2:
        return JSONResponse({"items": []})

    pattern = f"%{normalized_q}%"
    prefix = f"{normalized_q}%"

    category_rank = case((Category.name.ilike(prefix), 0), else_=1)
    product_rank = case((Product.name.ilike(prefix), 0), else_=1)

    categories = (
        (
            await session.execute(
                select(Category)
                .where(Category.name.ilike(pattern))
                .order_by(category_rank.asc(), Category.name.asc())
                .limit(3)
            )
        )
        .scalars()
        .all()
    )

    products = (
        (
            await session.execute(
                select(Product)
                .join(Category, Product.category_id == Category.id)
                .where(Product.is_active.is_(True), Product.name.ilike(pattern))
                .order_by(product_rank.asc(), Product.name.asc())
                .limit(3)
            )
        )
        .scalars()
        .all()
    )

    items: list[dict] = []

    for category in categories:
        items.append(
            {
                "type": "category",
                "label": category.name,
                "url": f"/catalog/{category.slug}/",
            }
        )

    for product in products:
        items.append(
            {
                "type": "product",
                "label": product.name,
                "url": f"/product/{product.slug}/",
            }
        )

    return JSONResponse({"items": items[:6]})
