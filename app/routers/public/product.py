from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.models.product import Product
from app.models.category import Category
from app.models.product_characteristic_value import ProductCharacteristicValue
from app.utils.database import get_async_session
from app.utils.templates import templates
from app.routers.public.favorites import get_favorite_ids
from app.routers.public.compare import get_compare_ids

router = APIRouter()


def _normalize_media_path(path: str | None) -> str | None:

    if not path:
        return None

    p = path.strip()
    if not p:
        return None

                    
    if p.startswith(("http://", "https://", "//")):
        return p

                                   
    if p.startswith("/static/"):
        return p

                                      
    if p.startswith("static/"):
        return "/" + p

                       
    p = p.lstrip("/")

                                                             
                                                 
    if p.startswith("img/uploads/products/"):
        return "/static/" + p

                                                 
                            
    p = p.removeprefix("products/")

    return "/static/img/uploads/products/" + p



def _format_price_rub(value: int | None) -> str:
    if value is None:
        return ""
               
    return f"{int(value):,}".replace(",", " ")


def _calc_final_price(price: int, discount_percent: int | None) -> int:
    if not discount_percent:
        return price
    pct = max(0, min(int(discount_percent), 100))
                                       
    return int(round(price * (100 - pct) / 100))


async def _build_category_chain(session: AsyncSession, leaf: Category) -> list[Category]:
    """
    Строим цепочку категорий от корня до leaf.
    Делается отдельными точечными запросами по parent_id (глубина маленькая),
    зато без тяжелых join/cte и без сюрпризов.
    """
    chain: list[Category] = []
    seen: set[str] = set()
    cur: Category | None = leaf

                         
    for _ in range(30):
        if not cur:
            break
        cur_id = str(cur.id)
        if cur_id in seen:
            break
        seen.add(cur_id)
        chain.append(cur)

        if not cur.parent_id:
            break

        parent_res = await session.execute(
            select(Category).where(Category.id == cur.parent_id)
        )
        cur = parent_res.scalar_one_or_none()

    chain.reverse()
    return chain


def _extract_characteristics(product: Product) -> list[dict]:
    """
    PV -> [{name, value, unit}]
    Числа типа 2.0 -> 2
    """
    out: list[dict] = []
    for pv in (product.characteristics_values or []):
        ch = pv.characteristic
        if not ch:
            continue

        val = None
        if pv.value_string is not None and pv.value_string != "":
            val = pv.value_string
        elif pv.value_number is not None:
            n = float(pv.value_number)
            val = int(n) if n.is_integer() else pv.value_number

        if val is None:
            continue

        out.append({"name": ch.name, "value": val, "unit": getattr(ch, "unit", None)})
    return out


def _build_gallery(product: Product) -> dict:
    """
    На основе relationship order_by (is_main desc, id asc) получаем:
    - main
    - thumbs
    - all
    """
    imgs = []
    for img in (product.images or []):
        src = _normalize_media_path(getattr(img, "file_path", None))
        if not src:
            continue
        imgs.append({"src": src, "is_main": bool(getattr(img, "is_main", False))})

    main = imgs[0] if imgs else None
    thumbs = imgs[1:] if len(imgs) > 1 else []
    return {"main": main, "thumbs": thumbs, "all": imgs}


def _product_card_dict(
    p: Product,
    fav_ids: set[str],
    cmp_ids: set[str],
) -> dict:
    final_price = _calc_final_price(p.price, p.discount_percent)
    main_img = None
    if p.images:
        main_img = _normalize_media_path(p.images[0].file_path)

    pid = str(p.id)
    return {
        "id": pid,
        "slug": p.slug,
        "name": p.name,
        "price": p.price,
        "discount_percent": p.discount_percent,
        "final_price": final_price,
        "has_discount": bool(p.discount_percent),
        "price_fmt": _format_price_rub(p.price),
        "final_price_fmt": _format_price_rub(final_price),
        "main_image": main_img,
        "is_favorite": pid in fav_ids,
        "is_compared": pid in cmp_ids,
    }


@router.get("/product/{product_slug}/", response_class=HTMLResponse)
async def product_detail(
    product_slug: str,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    fav_ids = get_favorite_ids(request.session)
    cmp_ids = get_compare_ids(request.session)

                      
    res = await session.execute(
        select(Product)
        .where(Product.slug == product_slug, Product.is_active.is_(True))
        .options(
                                                              
            joinedload(Product.brand),
            joinedload(Product.category),
                                        
            selectinload(Product.images),
            selectinload(Product.characteristics_values).selectinload(
                ProductCharacteristicValue.characteristic
            ),
        )
    )
    product = res.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")

                    
    final_price = _calc_final_price(product.price, product.discount_percent)
    pricing = {
        "price": product.price,
        "discount_percent": product.discount_percent,
        "final_price": final_price,
        "has_discount": bool(product.discount_percent),
        "price_fmt": _format_price_rub(product.price),
        "final_price_fmt": _format_price_rub(final_price),
    }

                
    gallery = _build_gallery(product)

                       
    characteristics = _extract_characteristics(product)

                                            
    breadcrumbs = []
    if product.category:
        chain = await _build_category_chain(session, product.category)
        breadcrumbs = [
            {
                "title": c.name,
                "url": request.url_for("category_detail", category_slug=c.slug)
                if "category_detail" in request.app.router.routes.__str__()                 
                else f"/catalog/{c.slug}/",
            }
            for c in chain
        ]
    breadcrumbs.append({"title": product.name, "url": str(request.url)})

                                                         
    related_res = await session.execute(
        select(Product)
        .where(
            Product.is_active.is_(True),
            Product.category_id == product.category_id,
            Product.id != product.id,
        )
        .options(selectinload(Product.images))
        .order_by(Product.name.asc())
        .limit(10)
    )
    related_db = related_res.scalars().all()
    related = [_product_card_dict(p, fav_ids, cmp_ids) for p in related_db]

                                     
    pid = str(product.id)
    ui = {
        "fav_ids": fav_ids,
        "cmp_ids": cmp_ids,
        "is_favorite": pid in fav_ids,
        "is_compared": pid in cmp_ids,
    }

    product_id_str = str(product.id)

    return templates.TemplateResponse(
        "public/catalog/product_detail.html",
        {
            "request": request,
            "product": product,
            "pricing": pricing,
            "gallery": gallery,
            "breadcrumbs": breadcrumbs,
            "characteristics": characteristics,
            "related": related,
            "ui": ui,
        },
    )
