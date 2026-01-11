from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order, OrderStatus
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.category import Category

GroupBy = Literal["year", "month", "week", "day"]

MOSCOW_TZ_NAME = "Europe/Moscow"


@dataclass(frozen=True)
class KPI:
    orders_week_done: int
    orders_in_work: int
    orders_done_total: int
    revenue_30d_done: int


def default_periods(group: GroupBy) -> int:
    # сколько “столбиков” показываем по умолчанию
    if group == "day":
        return 14
    if group == "week":
        return 12
    if group == "month":
        return 12
    return 5  # year


def compute_range(now: datetime, group: GroupBy, periods: int) -> tuple[datetime, datetime]:
    """
    Возвращает [start_dt, end_dt) как tz-aware datetimes.
    now должен быть tz-aware (в твоём dashboard.py он уже Moscow tz).
    """
    if periods <= 0:
        periods = default_periods(group)

    # end_dt — “сейчас”
    end_dt = now

    # start_dt — назад на N периодов (приблизительно; точная “нарезка” делается SQL date_trunc)
    if group == "day":
        start_dt = now - timedelta(days=periods)
    elif group == "week":
        start_dt = now - timedelta(weeks=periods)
    elif group == "month":
        start_dt = now - timedelta(days=31 * periods)
    else:  # year
        start_dt = now - timedelta(days=365 * periods)

    return start_dt, end_dt


def _bucket_expr(group: GroupBy):
    """
    SQL выражение для группировки по периоду в московском времени.
    Возвращает timestamp (начало bucket-а).
    """
    created_msk = func.timezone(MOSCOW_TZ_NAME, Order.created_at)
    return func.date_trunc(group, created_msk)


async def fetch_kpis(session: AsyncSession, now: datetime) -> KPI:
    """
    Мини-показатели:
    - заказов за неделю (DONE)
    - заявок/заказов в работе (NEW + IN_PROGRESS)
    - выполненные заказы (DONE, всего)
    - выручка за 30 дней (DONE)
    """
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
    Используем Order.total_price (снимок), не Product.price.
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
    """
    Накопительный рост выручки по уже агрегированной серии.
    На входе: [{"label": "...", "value": 100}, ...]
    На выходе value становится cumulative.
    """
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
    Топ товаров по количеству (DONE заказы):
    - total_qty: сумма quantity
    - unique_orders: количество уникальных заказов
    - revenue: сумма OrderItem.total_price (снимок по строкам)
    """
    total_qty = func.coalesce(func.sum(OrderItem.quantity), 0).label("total_qty")
    unique_orders = func.count(distinct(OrderItem.order_id)).label("unique_orders")
    revenue = func.coalesce(func.sum(OrderItem.total_price), 0).label("revenue")

    stmt = (
        select(
            Product.id.label("product_id"),
            Product.name.label("product_name"),
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
        )
        .group_by(Product.id, Product.name)
        .order_by(total_qty.desc(), revenue.desc())
        .limit(limit)
    )

    rows = (await session.execute(stmt)).mappings().all()
    return [
        {
            "product_id": str(r["product_id"]),
            "name": r["product_name"],
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
    Доли по категориям (pie):
    считаем выручку по сумме OrderItem.total_price (DONE), группируем по Category.
    """
    revenue = func.coalesce(func.sum(OrderItem.total_price), 0).label("revenue")

    stmt = (
        select(
            Category.id.label("category_id"),
            Category.name.label("category_name"),
            revenue,
        )
        .select_from(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .join(Product, Product.id == OrderItem.product_id)
        .join(Category, Category.id == Product.category_id)
        .where(
            Order.status == OrderStatus.done,
            Order.created_at >= start_dt,
            Order.created_at < end_dt,
        )
        .group_by(Category.id, Category.name)
        .order_by(revenue.desc())
        .limit(limit)
    )

    rows = (await session.execute(stmt)).mappings().all()
    return [
        {
            "category_id": str(r["category_id"]),
            "name": r["category_name"],
            "value": int(r["revenue"] or 0),
        }
        for r in rows
    ]
