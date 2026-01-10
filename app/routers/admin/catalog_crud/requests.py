# app/routers/admin/catalog_crud/requests.py
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.order import Order, OrderStatus
from app.models.order_item import OrderItem
from app.models.user import AdminUser
from app.utils.database import get_async_session
from app.utils.deps import require_admin_or_404
from app.utils.templates import templates

router = APIRouter(dependencies=[Depends(require_admin_or_404)])


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


def _admin_id_uuid(admin: dict) -> uuid.UUID:
    try:
        return uuid.UUID(str(admin.get("id")))
    except Exception:
        raise HTTPException(status_code=404)


def _is_admin(admin: dict) -> bool:
    return str(admin.get("role")) == "admin"


def _can_manager_access_order(admin: dict, order: Order) -> bool:
    """
    Менеджер видит:
    - свои заявки
    - неприкреплённые
    """
    me = _admin_id_uuid(admin)
    return order.manager_id is None or order.manager_id == me


async def _load_active_managers(session: AsyncSession) -> list[AdminUser]:
    res = await session.execute(
        select(AdminUser)
        .where(AdminUser.role == "manager", AdminUser.is_active.is_(True))
        .order_by(AdminUser.login)
    )
    return res.scalars().all()


@router.get("/admin/requests", response_class=HTMLResponse)
async def requests_list(
    request: Request,
    admin: dict = Depends(require_admin_or_404),
    session: AsyncSession = Depends(get_async_session),
):
    stmt = (
        select(Order)
        .options(selectinload(Order.manager))
        .order_by(Order.created_at.desc())
    )

    me_login: str | None = None
    managers: list[AdminUser] = []

    if _is_admin(admin):
        managers = await _load_active_managers(session)
    else:
        me = _admin_id_uuid(admin)
        stmt = stmt.where(or_(Order.manager_id.is_(None), Order.manager_id == me))

        me_res = await session.execute(select(AdminUser).where(AdminUser.id == me))
        me_user = me_res.scalar_one_or_none()
        me_login = me_user.login if me_user else None

    res = await session.execute(stmt)
    orders = res.scalars().all()

    status_choices = [(s.value, STATUS_LABELS[s]) for s in OrderStatus]

    return templates.TemplateResponse(
        "admin/requests/index.html",
        {
            "request": request,
            "admin": admin,
            "orders": orders,
            "status_choices": status_choices,
            "delivery_labels": DELIVERY_LABELS,
            "managers": managers,      # только для админа (active)
            "me_login": me_login,      # только для менеджера
        },
    )


@router.get("/admin/requests/{order_id}/edit", response_class=HTMLResponse)
async def request_edit_page(
    order_id: uuid.UUID,
    request: Request,
    admin: dict = Depends(require_admin_or_404),
    session: AsyncSession = Depends(get_async_session),
):
    res = await session.execute(
        select(Order)
        .where(Order.id == order_id)
        .options(
            selectinload(Order.manager),
            selectinload(Order.items).selectinload(OrderItem.product),
        )
    )
    order = res.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404)

    if not _is_admin(admin) and not _can_manager_access_order(admin, order):
        raise HTTPException(status_code=404)

    managers: list[AdminUser] = []
    if _is_admin(admin):
        managers = await _load_active_managers(session)

    return templates.TemplateResponse(
        "admin/requests/edit.html",
        {
            "request": request,
            "admin": admin,
            "order": order,
            "managers": managers,
            "statuses": [s.value for s in OrderStatus],
            "error": None,
        },
    )


@router.post("/admin/requests/{order_id}/edit", response_class=HTMLResponse)
async def request_edit(
    order_id: uuid.UUID,
    request: Request,
    admin: dict = Depends(require_admin_or_404),
    status: str | None = Form(None),
    manager_id: str | None = Form(None),  # теперь используется и админом, и менеджером (в списке)
    action: str | None = Form(None),      # совместимость со старыми кнопками take/drop
    session: AsyncSession = Depends(get_async_session),
):
    res = await session.execute(
        select(Order)
        .where(Order.id == order_id)
        .options(
            selectinload(Order.manager),
            selectinload(Order.items).selectinload(OrderItem.product),
        )
    )
    order = res.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404)

    if not _is_admin(admin) and not _can_manager_access_order(admin, order):
        raise HTTPException(status_code=404)

    error: str | None = None

    # 1) статус
    if status:
        try:
            order.status = OrderStatus(status)
        except Exception:
            error = "Некорректный статус."

    # 2) менеджер
    if not error:
        if _is_admin(admin):
            # админ: выбрать любого активного менеджера или снять
            if manager_id is not None:
                manager_id = manager_id.strip()
                if manager_id == "":
                    order.manager_id = None
                else:
                    try:
                        mid = uuid.UUID(manager_id)
                    except Exception:
                        error = "Некорректный manager_id."
                    else:
                        m_res = await session.execute(
                            select(AdminUser).where(
                                AdminUser.id == mid,
                                AdminUser.role == "manager",
                                AdminUser.is_active.is_(True),
                            )
                        )
                        m = m_res.scalar_one_or_none()
                        if not m:
                            error = "Менеджер не найден."
                        else:
                            order.manager_id = m.id
        else:
            # менеджер: dropdown "нет" или "я"
            me = _admin_id_uuid(admin)

            if manager_id is not None:
                manager_id = manager_id.strip()
                if manager_id == "":
                    # снять с себя можно только если заявка у меня
                    if order.manager_id == me:
                        order.manager_id = None
                    elif order.manager_id is None:
                        pass
                    else:
                        raise HTTPException(status_code=404)
                else:
                    # назначить можно только себя
                    if manager_id != str(me):
                        raise HTTPException(status_code=404)
                    order.manager_id = me

            # совместимость со старым UI (take/drop), если где-то осталось
            if action == "take":
                if order.manager_id is None:
                    order.manager_id = me
                elif order.manager_id != me:
                    raise HTTPException(status_code=404)
            elif action == "drop":
                if order.manager_id == me:
                    order.manager_id = None
                else:
                    raise HTTPException(status_code=404)

    if not error:
        await session.commit()
        # редиректим назад: если пришли со списка — вернёмся на список, иначе на edit
        referer = request.headers.get("referer") or ""
        if "/admin/requests" in referer and "/edit" not in referer:
            return RedirectResponse("/admin/requests", status_code=303)
        return RedirectResponse(f"/admin/requests/{order_id}/edit", status_code=303)

    managers: list[AdminUser] = []
    if _is_admin(admin):
        managers = await _load_active_managers(session)

    return templates.TemplateResponse(
        "admin/requests/edit.html",
        {
            "request": request,
            "admin": admin,
            "order": order,
            "managers": managers,
            "statuses": [s.value for s in OrderStatus],
            "error": error,
        },
        status_code=400,
    )


@router.post("/admin/requests/{order_id}/delete")
async def request_delete(
    order_id: uuid.UUID,
    admin: dict = Depends(require_admin_or_404),
    session: AsyncSession = Depends(get_async_session),
):
    if not _is_admin(admin):
        raise HTTPException(status_code=404)

    order = await session.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404)

    await session.delete(order)
    await session.commit()
    return RedirectResponse("/admin/requests", status_code=303)
