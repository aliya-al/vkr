from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order, OrderStatus
from app.models.order_item import OrderItem
from app.models.product import Product

GroupBy = Literal["year", "month", "week", "day"]
Scope = Literal["recent", "all"]

MOSCOW_TZ_NAME = "Europe/Moscow"


@dataclass(frozen=True)
class KPI:
    orders_week_done: int
    orders_in_work: int
    orders_done_total: int
    revenue_30d_done: int


def default_periods(group: GroupBy) -> int:
    if group == "day":
        return 14
    if group == "week":
        return 12
    if group == "month":
        return 12
    return 5        


def compute_range(now: datetime, group: GroupBy, periods: int) -> tuple[datetime, datetime]:
    """
    Возвращает [start_dt, end_dt) как tz-aware datetimes.
    now должен быть tz-aware.
    """
    if periods <= 0:
        periods = default_periods(group)

    end_dt = now

    if group == "day":
        start_dt = now - timedelta(days=periods)
    elif group == "week":
        start_dt = now - timedelta(weeks=periods)
    elif group == "month":
        start_dt = now - timedelta(days=31 * periods)
    else:        
        start_dt = now - timedelta(days=365 * periods)

    return start_dt, end_dt


async def compute_range_scoped(
    session: AsyncSession,
    now: datetime,
    group: GroupBy,
    periods: int,
    scope: Scope,
) -> tuple[datetime, datetime]:
    """
    scope=recent -> как раньше (последние N периодов)
    scope=all -> всё время по выполненным заказам (DONE)
    """
    if scope == "recent":
        return compute_range(now=now, group=group, periods=periods)

                    
                                                          
    if group == "day":
                                                                    
                                                        
        raise ValueError("Для 'всё время' выбери group=week/month/year (day слишком тяжёлый).")

    min_dt = await session.scalar(
        select(func.min(Order.created_at)).where(Order.status == OrderStatus.done)
    )
    start_dt = min_dt or (now - timedelta(days=365))
    return start_dt, now


def _bucket_expr(group: GroupBy):
    created_msk = func.timezone(MOSCOW_TZ_NAME, Order.created_at)
    return func.date_trunc(group, created_msk)


async def fetch_kpis(session: AsyncSession, now: datetime) -> KPI:
    week_start = now - timedelta(days=7)
    month_start = now - timedelta(days=30)

    orders_week_done_stmt = select(func.count()).select_from(Order).where(
        Order.status == OrderStatus.done,
        Order.created_at >= week_start,
        Order.created_at < now,
    )
    orders_in_work_stmt = select(func.count()).select_from(Order).where(
        Order.status.in_([OrderStatus.new, OrderStatus.in_progress]),
    )
    orders_done_total_stmt = select(func.count()).select_from(Order).where(
        Order.status == OrderStatus.done,
    )
    revenue_30d_stmt = select(func.coalesce(func.sum(Order.total_price), 0)).select_from(Order).where(
        Order.status == OrderStatus.done,
        Order.created_at >= month_start,
        Order.created_at < now,
    )

    orders_week_done = int(await session.scalar(orders_week_done_stmt) or 0)
    orders_in_work = int(await session.scalar(orders_in_work_stmt) or 0)
    orders_done_total = int(await session.scalar(orders_done_total_stmt) or 0)
    revenue_30d_done = int(await session.scalar(revenue_30d_stmt) or 0)

    return KPI(
        orders_week_done=orders_week_done,
        orders_in_work=orders_in_work,
        orders_done_total=orders_done_total,
        revenue_30d_done=revenue_30d_done,
    )


async def fetch_sales_series(
    session: AsyncSession,
    start_dt: datetime,
    end_dt: datetime,
    group: GroupBy,
) -> list[dict]:
    """
    Выручка (revenue) по выполненным заказам (DONE), сгруппированная по периодам.
    """
    bucket = _bucket_expr(group).label("bucket")
    value = func.coalesce(func.sum(Order.total_price), 0).label("value")

    stmt = (
        select(bucket, value)
        .select_from(Order)
        .where(
            Order.status == OrderStatus.done,
            Order.created_at >= start_dt,
            Order.created_at < end_dt,
        )
        .group_by(bucket)
        .order_by(bucket)
    )

    rows = (await session.execute(stmt)).all()
    return [{"label": b.isoformat(), "value": int(v)} for (b, v) in rows]


def build_cumulative(series: list[dict]) -> list[dict]:
    total = 0
    out: list[dict] = []
    for p in series:
        total += int(p.get("value") or 0)
        out.append({"label": p.get("label"), "value": total})
    return out


async def fetch_top_products_total_qty(
    session: AsyncSession,
    start_dt: datetime,
    end_dt: datetime,
    limit: int = 5,
) -> list[dict]:
    """
    Топ товаров по количеству (DONE) только по валидным актуальным товарам.
    """
    total_qty = func.coalesce(func.sum(OrderItem.quantity), 0).label("total_qty")
    unique_orders = func.count(distinct(OrderItem.order_id)).label("unique_orders")
    revenue = func.coalesce(func.sum(OrderItem.total_price), 0).label("revenue")

    image = func.max(OrderItem.product_image).label("product_image")

    stmt = (
        select(
            Product.id.label("product_id"),
            Product.name.label("product_name"),
            Product.slug.label("product_slug"),
            image,
            total_qty,
            unique_orders,
            revenue,
        )
        .select_from(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .join(Product, Product.id == OrderItem.product_id)
        .where(
            Order.status == OrderStatus.done,
            Order.created_at >= start_dt,
            Order.created_at < end_dt,
            Product.slug.is_not(None),
            Product.slug != "",
        )
        .group_by(Product.id, Product.name, Product.slug)
        .order_by(total_qty.desc(), revenue.desc())
        .limit(limit)
    )

    rows = (await session.execute(stmt)).mappings().all()
    return [
        {
            "product_id": str(r["product_id"]),
            "name": r["product_name"],
            "slug": r["product_slug"],
            "image": r["product_image"],
            "total_qty": int(r["total_qty"] or 0),
            "unique_orders": int(r["unique_orders"] or 0),
            "revenue": int(r["revenue"] or 0),
        }
        for r in rows
    ]


async def fetch_category_breakdown(
    session: AsyncSession,
    start_dt: datetime,
    end_dt: datetime,
    limit: int = 12,
) -> list[dict]:
    """
    Продаваемые категории (pie) по метрике unique orders:
    - считаем количество уникальных заказов, где встречалась категория
    - группируем по snapshot OrderItem.category_*
    """
    orders_cnt = func.count(distinct(OrderItem.order_id)).label("orders_cnt")

    stmt = (
        select(
            OrderItem.category_id.label("category_id"),
            OrderItem.category_name.label("category_name"),
            orders_cnt,
        )
        .select_from(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            Order.status == OrderStatus.done,
            Order.created_at >= start_dt,
            Order.created_at < end_dt,
            OrderItem.category_name.is_not(None),
        )
        .group_by(OrderItem.category_id, OrderItem.category_name)
        .order_by(orders_cnt.desc())
        .limit(limit)
    )

    rows = (await session.execute(stmt)).mappings().all()
    return [
        {
            "category_id": str(r["category_id"]) if r["category_id"] else None,
            "name": r["category_name"],
            "value": int(r["orders_cnt"] or 0),
        }
        for r in rows
    ]
