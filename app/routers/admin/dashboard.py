# app/routers/admin/dashboard.py
from __future__ import annotations

from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.templates import templates
from app.utils.deps import require_admin_or_404
from app.utils.database import get_async_session

from app.services.analytics import (
    compute_range,
    default_periods,
    fetch_kpis,
    fetch_top_products_total_qty,
    fetch_sales_series,
    build_cumulative,
    fetch_category_breakdown,
)

router = APIRouter()

GroupByQuery = Literal["year", "month", "week", "day"]
MOSCOW_TZ = ZoneInfo("Europe/Moscow")


@router.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    admin=Depends(require_admin_or_404),
    session: AsyncSession = Depends(get_async_session),

    # каждый блок управляется отдельно
    sales_group: GroupByQuery = Query("month"),
    growth_group: GroupByQuery = Query("month"),
    categories_group: GroupByQuery = Query("month"),
    top_group: GroupByQuery = Query("month"),
):
    # ориентируемся на Москву (как твой moscow_dt)
    now = datetime.now(MOSCOW_TZ)

    # KPI
    kpis = await fetch_kpis(session, now=now)

    # Sales
    sales_start, sales_end = compute_range(now=now, group=sales_group, periods=default_periods(sales_group))
    sales = await fetch_sales_series(session, start_dt=sales_start, end_dt=sales_end, group=sales_group)

    # Growth
    growth_start, growth_end = compute_range(now=now, group=growth_group, periods=default_periods(growth_group))
    growth_base = await fetch_sales_series(session, start_dt=growth_start, end_dt=growth_end, group=growth_group)
    growth = build_cumulative(growth_base)

    # Categories pie
    cat_start, cat_end = compute_range(now=now, group=categories_group, periods=default_periods(categories_group))
    categories = await fetch_category_breakdown(session, start_dt=cat_start, end_dt=cat_end, limit=12)

    # Top products
    top_start, top_end = compute_range(now=now, group=top_group, periods=default_periods(top_group))
    top_products = await fetch_top_products_total_qty(
        session,
        start_dt=top_start,
        end_dt=top_end,
        limit=5,
    )

    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "admin": admin,

            "sales_group": sales_group,
            "growth_group": growth_group,
            "categories_group": categories_group,
            "top_group": top_group,

            # передаём datetime, чтобы в шаблоне применять |moscow_dt
            "sales_range_start": sales_start,
            "sales_range_end": sales_end,
            "growth_range_start": growth_start,
            "growth_range_end": growth_end,
            "categories_range_start": cat_start,
            "categories_range_end": cat_end,
            "top_range_start": top_start,
            "top_range_end": top_end,

            # можно оставить как dict (как у тебя), но без JSON-строк
            "kpis": kpis.__dict__,
            "top_products": top_products,

            # передаём списки как есть
            "sales": sales,
            "growth": growth,
            "categories": categories,
        },
    )
