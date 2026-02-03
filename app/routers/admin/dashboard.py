from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.order import Order, OrderStatus
from app.models.user import AdminUser
from app.utils.templates import templates
from app.utils.deps import require_admin_or_404, require_superadmin_or_404
from app.utils.database import get_async_session
from app.services.analytics import (
    default_periods,
    fetch_kpis,
    fetch_sales_series,
    build_cumulative,
    fetch_category_breakdown,
    fetch_top_products_total_qty,
)

router = APIRouter()

GroupByQuery = Literal["year", "month", "week", "day"]
ScopeQuery = Literal["recent", "all"]

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


STATUS_LABELS: dict[OrderStatus, str] = {
    OrderStatus.new: "новый",
    OrderStatus.in_progress: "в работе",
    OrderStatus.done: "выполнен",
    OrderStatus.canceled: "отменён",
}

DELIVERY_LABELS: dict[str, str] = {
    "delivery": "Доставка",
    "pickup": "Самовывоз",
}


def _is_admin(admin: dict) -> bool:
    return str(admin.get("role")) == "admin"


def _admin_id_uuid(admin: dict) -> uuid.UUID:
    try:
        return uuid.UUID(str(admin.get("id")))
    except Exception:
        raise HTTPException(status_code=404)


async def _rolling_range_scoped(
    session: AsyncSession,
    now: datetime,
    group: GroupByQuery,
    periods: int,
    scope: ScopeQuery,
) -> tuple[datetime, datetime]:
    """
    Rolling-диапазоны (как ты описала):
    - week: последние 7 дней * periods (не календарная неделя)
    - month: последние N месяцев * periods (relativedelta)
    - year: последние N лет * periods
    - day: последние N дней * periods

    scope=all: от самой ранней заявки до now.
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=MOSCOW_TZ)

    end_dt = now

    if scope == "all":
        min_res = await session.execute(select(func.min(Order.created_at)))
        min_dt = min_res.scalar_one_or_none()
        if not min_dt:
            # если заказов нет — просто recent-окно
            scope = "recent"
        else:
            if min_dt.tzinfo is None:
                min_dt = min_dt.replace(tzinfo=timezone.utc).astimezone(MOSCOW_TZ)
            else:
                min_dt = min_dt.astimezone(MOSCOW_TZ)
            return min_dt, end_dt

    if periods <= 0:
        periods = default_periods(group)

    if group == "day":
        start_dt = end_dt - timedelta(days=periods)
    elif group == "week":
        start_dt = end_dt - timedelta(days=7 * periods)
    elif group == "month":
        start_dt = end_dt - relativedelta(months=periods)
    elif group == "year":
        start_dt = end_dt - relativedelta(years=periods)
    else:
        raise ValueError("Bad group")

    return start_dt, end_dt

async def _load_active_managers(session: AsyncSession) -> list[AdminUser]:
    res = await session.execute(
        select(AdminUser)
        .where(
            AdminUser.role == "manager",
            AdminUser.is_active.is_(True),
        )
        .order_by(AdminUser.login.asc())
    )
    return res.scalars().all()

@router.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard_page(
    request: Request,
    admin: dict = Depends(require_admin_or_404),
    session: AsyncSession = Depends(get_async_session),
):
    # последние 6 заявок на дашборде
    stmt = (
        select(Order)
        .options(selectinload(Order.manager))
        .order_by(Order.created_at.desc())
        .limit(7)
    )

    me_login: str | None = None
    if not _is_admin(admin):
        me = _admin_id_uuid(admin)
        stmt = stmt.where(or_(Order.manager_id.is_(None), Order.manager_id == me))

        me_res = await session.execute(select(AdminUser).where(AdminUser.id == me))
        me_user = me_res.scalar_one_or_none()
        me_login = me_user.login if me_user else None

    res = await session.execute(stmt)
    dash_orders = res.scalars().all()

    tpl = "admin/dashboard_admin.html" if _is_admin(admin) else "admin/dashboard_manager.html"

    dash_managers: list[AdminUser] | None = None
    if _is_admin(admin):
        dash_managers = await _load_active_managers(session)

    return templates.TemplateResponse(
        tpl,
        {
            "request": request,
            "admin": admin,
            "dash_managers": dash_managers,
            "dash_orders": dash_orders,
            "status_labels": STATUS_LABELS,
            "delivery_labels": DELIVERY_LABELS,
            "me_login": me_login,
        },
    )


@router.post("/admin/requests/{order_id}/inline")
async def request_inline_update(
    order_id: uuid.UUID,
    request: Request,
    admin: dict = Depends(require_admin_or_404),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    status: str | None = payload.get("status")
    manager_id: str | None = payload.get("manager_id")

    res = await session.execute(
        select(Order)
        .where(Order.id == order_id)
        .options(selectinload(Order.manager))
    )
    order = res.scalar_one_or_none()
    if not order:
        return JSONResponse({"ok": False, "error": "Заявка не найдена."}, status_code=404)

    # менеджеру разрешаем менять только то, что он видит,
    # но всё равно проверим
    if not _is_admin(admin):
        me = _admin_id_uuid(admin)
        if not (order.manager_id is None or order.manager_id == me):
            return JSONResponse({"ok": False, "error": "Нет доступа."}, status_code=404)

    # обновляем статус
    if status is not None:
        try:
            order.status = OrderStatus(status)
        except Exception:
            return JSONResponse({"ok": False, "error": "Некорректный статус."}, status_code=400)

    if manager_id is not None:
        if not _is_admin(admin):
            return JSONResponse({"ok": False, "error": "Только админ может менять менеджера."}, status_code=403)

        s = str(manager_id).strip()
        if s == "":
            order.manager_id = None
        else:
            try:
                mid = uuid.UUID(s)
            except Exception:
                return JSONResponse({"ok": False, "error": "Некорректный manager_id."}, status_code=400)

            m_res = await session.execute(
                select(AdminUser).where(
                    AdminUser.id == mid,
                    AdminUser.role == "manager",
                    AdminUser.is_active.is_(True),
                )
            )
            m = m_res.scalar_one_or_none()
            if not m:
                return JSONResponse({"ok": False, "error": "Менеджер не найден."}, status_code=400)

            order.manager_id = m.id

    await session.commit()

    # ответ для JS
    status_value = order.status.value if order.status else "new"
    return JSONResponse({"ok": True, "status": status_value})


@router.get("/admin/api/analytics/kpis", dependencies=[Depends(require_superadmin_or_404)])
async def api_kpis(session: AsyncSession = Depends(get_async_session)):
    now = datetime.now(MOSCOW_TZ)
    week_start = now - timedelta(days=7)

    orders_week = await session.scalar(
        select(func.count()).select_from(Order).where(
            Order.status == OrderStatus.done,
            Order.created_at >= week_start,
            Order.created_at < now,
        )
    )

    in_progress = await session.scalar(
        select(func.count()).select_from(Order).where(
            Order.status.in_([OrderStatus.new, OrderStatus.in_progress])
        )
    )

    done = await session.scalar(
        select(func.count()).select_from(Order).where(Order.status == OrderStatus.done)
    )

    return {
        "orders_week": int(orders_week or 0),
        "in_progress": int(in_progress or 0),
        "done": int(done or 0),
    }


@router.get("/admin/api/analytics/sales", dependencies=[Depends(require_superadmin_or_404)])
async def api_sales_series(
    session: AsyncSession = Depends(get_async_session),
    group: GroupByQuery = Query("month"),
    scope: ScopeQuery = Query("recent"),
    periods: int = Query(0, ge=0, le=200),
):
    now = datetime.now(MOSCOW_TZ)
    if periods <= 0:
        periods = default_periods(group)

    start_dt, end_dt = await _rolling_range_scoped(session, now, group, periods, scope)

    series = await fetch_sales_series(session, start_dt=start_dt, end_dt=end_dt, group=group)  # type: ignore[arg-type]
    return {"group": group, "scope": scope, "start": start_dt.isoformat(), "end": end_dt.isoformat(), "series": series}


@router.get("/admin/api/analytics/cumulative", dependencies=[Depends(require_superadmin_or_404)])
async def api_cumulative_series(
    session: AsyncSession = Depends(get_async_session),
    group: GroupByQuery = Query("month"),
    scope: ScopeQuery = Query("recent"),
    periods: int = Query(0, ge=0, le=200),
):
    now = datetime.now(MOSCOW_TZ)
    if periods <= 0:
        periods = default_periods(group)

    start_dt, end_dt = await _rolling_range_scoped(session, now, group, periods, scope)

    base = await fetch_sales_series(session, start_dt=start_dt, end_dt=end_dt, group=group)  # type: ignore[arg-type]
    return {"group": group, "scope": scope, "start": start_dt.isoformat(), "end": end_dt.isoformat(), "series": build_cumulative(base)}


@router.get("/admin/api/analytics/categories", dependencies=[Depends(require_superadmin_or_404)])
async def api_categories_breakdown(
    session: AsyncSession = Depends(get_async_session),
    group: GroupByQuery = Query("month"),
    scope: ScopeQuery = Query("recent"),
    periods: int = Query(0, ge=0, le=200),
    limit: int = Query(12, ge=1, le=50),
):
    now = datetime.now(MOSCOW_TZ)
    if periods <= 0:
        periods = default_periods(group)

    start_dt, end_dt = await _rolling_range_scoped(session, now, group, periods, scope)

    data = await fetch_category_breakdown(session, start_dt=start_dt, end_dt=end_dt, limit=limit)
    return {"group": group, "scope": scope, "start": start_dt.isoformat(), "end": end_dt.isoformat(), "data": data}


@router.get("/admin/api/analytics/top-products", dependencies=[Depends(require_superadmin_or_404)])
async def api_top_products(
    session: AsyncSession = Depends(get_async_session),
    group: GroupByQuery = Query("month"),
    scope: ScopeQuery = Query("recent"),
    periods: int = Query(0, ge=0, le=200),
    limit: int = Query(4, ge=1, le=50),
):
    now = datetime.now(MOSCOW_TZ)
    if periods <= 0:
        periods = default_periods(group)

    start_dt, end_dt = await _rolling_range_scoped(session, now, group, periods, scope)

    data = await fetch_top_products_total_qty(session, start_dt=start_dt, end_dt=end_dt, limit=limit)
    return {"group": group, "scope": scope, "start": start_dt.isoformat(), "end": end_dt.isoformat(), "data": data}
