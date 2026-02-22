from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse

from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.templates import templates
from app.utils.database import get_async_session
from app.utils.category_image import find_category_image_url

from app.models.news import News
from app.models.category import Category
from app.models.product import Product

from app.services.favorites import get_favorite_ids
from app.services.compare import get_compare_ids
from app.utils.uploads import normalize_news_media_path, normalize_product_media_path


router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home_index(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
                                     
    res_news = await session.execute(
        select(News).order_by(desc(News.created_at)).limit(12)
    )
    news = res_news.scalars().all()
    for item in news:
        item.image_path = normalize_news_media_path(item.image_path)

                                                              
    res_cats = await session.execute(
        select(Category)
        .where(Category.parent_id.is_(None))
        .order_by(Category.name)
        .limit(30)
    )
    cats = res_cats.scalars().all()

    categories = [
        {
            "id": str(c.id),
            "name": c.name,
            "slug": c.slug,
            "image_url": find_category_image_url(str(c.id)),
        }
        for c in cats
    ]

                                                     
    res_promo = await session.execute(
        select(Product)
        .options(selectinload(Product.images))
        .where(Product.is_active.is_(True))
        .where(Product.discount_percent.is_not(None))
        .where(Product.discount_percent > 0)
        .limit(20)
    )
    promo_products = res_promo.scalars().all()
    for p in promo_products:
        if p.images:
            p.images[0].file_path = normalize_product_media_path(p.images[0].file_path)

                                               
    res_products = await session.execute(
        select(Product)
        .options(selectinload(Product.images))
        .where(Product.is_active.is_(True))
        .limit(60)
    )
    products = res_products.scalars().all()
    for p in products:
        if p.images:
            p.images[0].file_path = normalize_product_media_path(p.images[0].file_path)

    fav_ids = [str(x) for x in (get_favorite_ids(request.session) or [])]
    cmp_ids = [str(x) for x in (get_compare_ids(request.session) or [])]

    fav_ids_set = set(fav_ids)
    cmp_ids_set = set(cmp_ids)

    return templates.TemplateResponse(
        "public/home.html",
        {
            "request": request,
            "news": news,
            "categories": categories,
            "promo_products": promo_products,
            "products": products,
            "fav_ids_set": fav_ids_set,
            "cmp_ids_set": cmp_ids_set,
        },
    )

