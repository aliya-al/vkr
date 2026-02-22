from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select, func, case, cast, Integer, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.category import Category
from app.models.product import Product
from app.models.brand import Brand
from app.utils.database import get_async_session
from app.utils.templates import templates
from app.utils.category_image import find_category_image_url
from app.services.favorites import get_favorite_ids
from app.services.compare import get_compare_ids
from app.utils.uploads import normalize_product_media_path


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

    categories = [
        {
            "id": str(c.id),
            "name": c.name,
            "slug": c.slug,
            "image_url": find_category_image_url(str(c.id)),
        }
        for c in root_categories
    ]

    return templates.TemplateResponse(
        "public/catalog/catalog.html",
        {"request": request, "categories": categories},
    )


@router.get("/catalog/{slug}/", response_class=HTMLResponse)
async def catalog_category(slug: str, request: Request, session: AsyncSession = Depends(get_async_session)):
    res = await session.execute(
        select(Category)
        .where(Category.slug == slug)
        .options(selectinload(Category.children))
    )
    category = res.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404, detail="Категория не найдена")

    qp = request.query_params

    children = list(category.children or [])
    tree_ids = [category.id] + [c.id for c in children]

    promo_on = qp.get("promo")
    sort = (qp.get("sort") or "").strip()

    sub_mode = qp.get("sub_mode")
    sub_slugs = qp.getlist("sub")
    child_by_slug = {c.slug: c for c in children}

    if children:
        if sub_slugs:
            selected_sub_slugs = [s for s in sub_slugs if s in child_by_slug]
        else:
            selected_sub_slugs = [c.slug for c in children] if sub_mode is None else []
        selected_child_ids = [child_by_slug[s].id for s in selected_sub_slugs]
        category_ids_selected = [category.id] + selected_child_ids
    else:
        selected_sub_slugs = []
        category_ids_selected = [category.id]

    promo_cond = (Product.discount_percent.isnot(None)) & (Product.discount_percent > 0)
    display_price_expr = case(
        (
            promo_cond,
            cast(func.round(Product.price * (100 - Product.discount_percent) / 100.0), Integer),
        ),
        else_=Product.price,
    )

    brands_res = await session.execute(
        select(Brand)
        .join(Product, Product.brand_id == Brand.id)
        .where(
            Product.is_active.is_(True),
            Product.category_id.in_(tree_ids),
            Product.brand_id.isnot(None),
        )
        .distinct()
        .order_by(Brand.name)
    )
    brands_db = brands_res.scalars().all()
    brand_by_slug = {b.slug: b for b in brands_db}

    brand_mode = qp.get("brand_mode")
    brand_slugs = qp.getlist("brand")
    if brands_db:
        if brand_slugs:
            selected_brand_slugs = [s for s in brand_slugs if s in brand_by_slug]
        else:
            selected_brand_slugs = [b.slug for b in brands_db] if brand_mode is None else []
        selected_brand_ids = [brand_by_slug[s].id for s in selected_brand_slugs]
    else:
        selected_brand_slugs = []
        selected_brand_ids = []

    bounds_res = await session.execute(
        select(func.min(display_price_expr), func.max(display_price_expr)).where(
            Product.is_active.is_(True),
            Product.category_id.in_(tree_ids),
        )
    )
    abs_min, abs_max = bounds_res.first() or (None, None)
    abs_min = int(abs_min or 0)
    abs_max = int(abs_max or 0)
    if abs_min > abs_max:
        abs_min, abs_max = abs_max, abs_min

    def _to_int(x: str | None) -> int | None:
        if x is None or x == "":
            return None
        try:
            return int(float(x))
        except Exception:
            return None

    min_q = _to_int(qp.get("min"))
    max_q = _to_int(qp.get("max"))

    if min_q is not None:
        min_q = max(abs_min, min(min_q, abs_max))
    if max_q is not None:
        max_q = max(abs_min, min(max_q, abs_max))
    if min_q is not None and max_q is not None and min_q > max_q:
        min_q, max_q = max_q, min_q

    stmt = (
        select(Product)
        .where(
            Product.is_active.is_(True),
            Product.category_id.in_(category_ids_selected),
        )
        .options(selectinload(Product.images))
    )

    if children and sub_mode is not None and not sub_slugs:
        stmt = stmt.where(Product.id.is_(None))

    if promo_on:
        stmt = stmt.where(promo_cond)

    if brands_db:
        if selected_brand_ids:
            stmt = stmt.where(Product.brand_id.in_(selected_brand_ids))
        elif brand_mode is not None and not brand_slugs:
            stmt = stmt.where(Product.id.is_(None))

    if min_q is not None:
        stmt = stmt.where(display_price_expr >= min_q)
    if max_q is not None:
        stmt = stmt.where(display_price_expr <= max_q)

    if sort == "price_asc":
        stmt = stmt.order_by(display_price_expr.asc(), Product.name.asc())
    elif sort == "price_desc":
        stmt = stmt.order_by(display_price_expr.desc(), Product.name.asc())
    else:
        stmt = stmt.order_by(Product.name.asc())

    prod_res = await session.execute(stmt)
    products = prod_res.scalars().all()

    product_cards = []
    for p in products:
        main_image = normalize_product_media_path(p.images[0].file_path) if p.images else None
        product_cards.append(
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

    subcategories = [
        {
            "id": str(sc.id),
            "name": sc.name,
            "slug": sc.slug,
            "image_url": find_category_image_url(str(sc.id)),
        }
        for sc in children
    ]

    brands = [
        {"id": str(b.id), "name": b.name, "slug": b.slug}
        for b in brands_db
    ]

    fav_ids = [str(x) for x in (get_favorite_ids(request.session) or [])]
    cmp_ids = [str(x) for x in (get_compare_ids(request.session) or [])]

    fav_ids_set = set(fav_ids)
    cmp_ids_set = set(cmp_ids)

    return templates.TemplateResponse(
        "public/catalog/category_detail.html",
        {
            "request": request,
            "category": category,
            "subcategories": subcategories,
            "selected_subs": selected_sub_slugs,
            "brands": brands,
            "selected_brands": selected_brand_slugs,
            "abs_min": abs_min,
            "abs_max": abs_max,
            "products": product_cards,
            "fav_ids": fav_ids,
            "cmp_ids": cmp_ids,
            "fav_ids_set": fav_ids_set,
            "cmp_ids_set": cmp_ids_set,
        },
    )


@router.get("/search", response_class=HTMLResponse)
async def catalog_search(
    request: Request,
    q: str = Query(default=""),
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
        prod_res = await session.execute(stmt)
        products_db = prod_res.scalars().all()

        products = [
            {
                "id": str(p.id),
                "slug": p.slug,
                "name": p.name,
                "price": p.price,
                "discount_percent": p.discount_percent,
                "display_price": _calc_display_price(p.price, p.discount_percent),
                "main_image": normalize_product_media_path(p.images[0].file_path) if p.images else None,
            }
            for p in products_db
        ]

    fav_ids = [str(x) for x in (get_favorite_ids(request.session) or [])]
    cmp_ids = [str(x) for x in (get_compare_ids(request.session) or [])]

    return templates.TemplateResponse(
        "public/catalog/search.html",
        {
            "request": request,
            "q": query,
            "products": products,
            "results_count": len(products),
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
        return JSONResponse({"items": []})

    products_res = await session.execute(
        select(Product)
        .where(
            Product.is_active.is_(True),
            Product.name.ilike(f"%{query}%"),
        )
        .order_by(Product.name.asc())
        .limit(6)
    )
    products = products_res.scalars().all()

    categories_res = await session.execute(
        select(Category)
        .join(Product, Product.category_id == Category.id)
        .where(
            Product.is_active.is_(True),
            Category.name.ilike(f"%{query}%"),
        )
        .distinct()
        .order_by(Category.name.asc())
        .limit(6)
    )
    categories = categories_res.scalars().all()

    items = [
        {
            "type": "product",
            "name": p.name,
            "url": f"/product/{p.slug}/",
        }
        for p in products
    ]
    items.extend(
        {
            "type": "category",
            "name": c.name,
            "url": f"/catalog/{c.slug}/",
        }
        for c in categories
    )

    return JSONResponse({"items": items[:6]})
