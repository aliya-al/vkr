from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse

from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.templates import templates
from app.utils.database import get_async_session

from app.models.news import News
from app.models.category import Category
from app.models.product import Product

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home_index(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    # Новости: по дате (новые первые)
    res_news = await session.execute(
        select(News).order_by(desc(News.created_at)).limit(12)
    )
    news = res_news.scalars().all()

    # Категории: верхнего уровня (если parent_id используется)
    res_cats = await session.execute(
        select(Category).where(Category.parent_id.is_(None)).limit(30)
    )
    categories = res_cats.scalars().all()

    # Акции: товары со скидкой (discount_percent > 0)
    res_promo = await session.execute(
        select(Product)
        .options(selectinload(Product.images))
        .where(Product.is_active.is_(True))
        .where(Product.discount_percent.is_not(None))
        .where(Product.discount_percent > 0)
        .limit(20)
    )
    promo_products = res_promo.scalars().all()

    # Товары: ограничим ради производительности
    res_products = await session.execute(
        select(Product)
        .options(selectinload(Product.images))
        .where(Product.is_active.is_(True))
        .limit(60)
    )
    products = res_products.scalars().all()

    return templates.TemplateResponse(
        "public/home.html",
        {
            "request": request,
            "news": news,
            "categories": categories,
            "promo_products": promo_products,
            "products": products,
        },
    )
