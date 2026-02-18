from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy import or_, select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.order import DeliveryType, Order, OrderStatus
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.product_image import ProductImage
from app.models.user import AdminUser
from app.services.order_totals import fetch_orders_weight_volume
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

PICKUP_POINTS: list[str] = [
    "ул. Примерная, 1",
    "пр-т Другой, 10",
]


def _admin_id_uuid(admin: dict) -> uuid.UUID:
    try:
        return uuid.UUID(str(admin.get("id")))
    except Exception:
        raise HTTPException(status_code=404)


def _is_admin(admin: dict) -> bool:
    return str(admin.get("role")) == "admin"


def _can_manager_access_order(admin: dict, order: Order) -> bool:
    me = _admin_id_uuid(admin)
    return order.manager_id is None or order.manager_id == me


async def _load_managers_for_admin(session: AsyncSession, keep_ids: set[uuid.UUID]) -> list[AdminUser]:
    cond = (AdminUser.role == "manager") & (AdminUser.is_active.is_(True) | AdminUser.id.in_(keep_ids))
    res = await session.execute(
        select(AdminUser)
        .where(cond)
        .order_by(AdminUser.login)
    )
    return res.scalars().all()


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


def _calc_display_price(price: int, discount_percent: int | None) -> int:
    if not discount_percent:
        return price
    pct = max(0, min(int(discount_percent), 100))
    return int(round(price * (100 - pct) / 100))


def _normalize_phone_ru(phone: str) -> tuple[str, str | None]:
    s = (phone or "").strip()
    digits = "".join(ch for ch in s if ch.isdigit())
    if digits.startswith("9"):
        digits = "7" + digits
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    if not (len(digits) == 11 and digits.startswith("7")):
        return s, "Укажи телефон в формате +7 (999) 999-99-99."
    formatted = f"+7 ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"
    return formatted, None


async def _load_products_for_picker(session: AsyncSession) -> list[dict]:
    res = await session.execute(
        select(Product)
        .options(selectinload(Product.images))
        .where(Product.is_active.is_(True))
        .order_by(Product.name.asc())
    )
    products = list(res.scalars().all())

    out: list[dict] = []
    for p in products:
        img_url = None
        if getattr(p, "images", None):
            img0 = p.images[0]
            raw = (
                getattr(img0, "url", None)
                or getattr(img0, "image_url", None)
                or getattr(img0, "path", None)
                or getattr(img0, "file_path", None)
            )
            img_url = _normalize_media_path(raw)

        base_unit = int(p.price)
        unit = _calc_display_price(base_unit, p.discount_percent)

        out.append(
            {
                "id": str(p.id),
                "name": p.name,
                "unit_price": unit,
                "base_unit_price": base_unit,
                "discount_percent": p.discount_percent,
                "image_url": img_url,
                "weight_kg": float(p.weight_kg or 0.0),
                "volume_m3": float(p.volume_m3 or 0.0),
            }
        )
    return out


async def _load_order_items_for_ui(session: AsyncSession, order: Order) -> tuple[list[dict], int, int, float, float, dict[str, int]]:
    await session.refresh(order, attribute_names=["items"])
    res = await session.execute(
        select(OrderItem)
        .where(OrderItem.order_id == order.id)
        .options(selectinload(OrderItem.product))
    )
    rows = list(res.scalars().all())

    items: list[dict] = []
    total_price = 0
    total_base = 0
    total_weight = 0.0
    total_volume = 0.0
    req_cart: dict[str, int] = {}

    for it in rows:
        p = it.product
        if not p:
            continue

        qty = int(it.quantity or 0)
        if qty < 1:
            continue

        base_unit = int(getattr(it, "price_per_item", None) or getattr(p, "price", 0) or 0)
        unit_price = int(getattr(it, "final_price_per_item", None) or _calc_display_price(base_unit, p.discount_percent))
        img_url = _normalize_media_path(getattr(it, "product_image", None)) or _normalize_media_path(getattr(p, "image_url", None))

        w = float(getattr(it, "weight_kg", None) or float(p.weight_kg or 0.0))
        v = float(getattr(it, "volume_m3", None) or float(p.volume_m3 or 0.0))

        total_price += unit_price * qty
        total_base += base_unit * qty
        total_weight += w * qty
        total_volume += v * qty

        items.append(
            {
                "product": p,
                "qty": qty,
                "unit_price": unit_price,
                "base_unit_price": base_unit,
                "image_url": img_url,
                "weight_kg": w,
                "volume_m3": v,
            }
        )
        req_cart[str(p.id)] = qty

    return items, total_price, total_base, total_weight, total_volume, req_cart


async def _recalc_and_save_order_totals(session: AsyncSession, order: Order) -> None:
    res = await session.execute(
        select(OrderItem)
        .where(OrderItem.order_id == order.id)
    )
    rows = list(res.scalars().all())

    total_price = 0
    total_weight = 0.0
    total_volume = 0.0

    for it in rows:
        qty = int(it.quantity or 0)
        if qty < 1:
            continue
        unit_price = int(it.final_price_per_item or it.price_per_item or 0)
        total_price += unit_price * qty
        total_weight += float(it.weight_kg or 0.0) * qty
        total_volume += float(it.volume_m3 or 0.0) * qty

    order.total_price = total_price
    order.total_weight_kg = total_weight
    order.total_volume_m3 = total_volume
    session.add(order)


async def _get_order_or_404(session: AsyncSession, order_id: uuid.UUID) -> Order:
    res = await session.execute(
        select(Order)
        .where(Order.id == order_id)
        .options(selectinload(Order.manager))
    )
    order = res.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404)
    return order


from zoneinfo import ZoneInfo

_TZ_LOCAL = ZoneInfo("Europe/Berlin")


def _iso_dt_local(dt: datetime | None) -> str:
    if not dt:
        return ""
    x = dt
    if getattr(x, "tzinfo", None) is not None:
        x = x.astimezone(_TZ_LOCAL).replace(tzinfo=None)
    else:
        x = x.replace(tzinfo=None)
    return x.replace(second=0, microsecond=0).isoformat(timespec="minutes")



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
        res0 = await session.execute(stmt)
        orders = res0.scalars().all()

        keep_ids = {o.manager_id for o in orders if o.manager_id}
        managers = await _load_managers_for_admin(session, keep_ids)

        order_totals = await fetch_orders_weight_volume(session, [o.id for o in orders])
        status_choices = [(s.value, STATUS_LABELS[s]) for s in OrderStatus]

        return templates.TemplateResponse(
            "admin/requests/index.html",
            {
                "request": request,
                "admin": admin,
                "orders": orders,
                "status_choices": status_choices,
                "delivery_labels": DELIVERY_LABELS,
                "pickup_points": PICKUP_POINTS,

                "order_totals": order_totals,
                "managers": managers,
                "me_login": None,
            },
        )

    me = _admin_id_uuid(admin)
    stmt = stmt.where(or_(Order.manager_id.is_(None), Order.manager_id == me))

    me_res = await session.execute(select(AdminUser).where(AdminUser.id == me))
    me_user = me_res.scalar_one_or_none()
    me_login = me_user.login if me_user else None

    res = await session.execute(stmt)
    orders = res.scalars().all()

    order_totals = await fetch_orders_weight_volume(session, [o.id for o in orders])
    status_choices = [(s.value, STATUS_LABELS[s]) for s in OrderStatus]

    return templates.TemplateResponse(
        "admin/requests/index.html",
        {
            "request": request,
            "admin": admin,
            "orders": orders,
            "status_choices": status_choices,
            "delivery_labels": DELIVERY_LABELS,
            "order_totals": order_totals,
            "managers": managers,
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

    if not _is_admin(admin) and not _can_manager_access_order(admin, order):
        return JSONResponse({"ok": False, "error": "Нет доступа."}, status_code=404)

    if status:
        try:
            order.status = OrderStatus(status)
        except Exception:
            return JSONResponse({"ok": False, "error": "Некорректный статус."}, status_code=400)

    if manager_id is not None:
        manager_id = str(manager_id).strip()

        if _is_admin(admin):
            if manager_id == "":
                order.manager_id = None
            else:
                try:
                    mid = uuid.UUID(manager_id)
                except Exception:
                    return JSONResponse({"ok": False, "error": "Некорректный manager_id."}, status_code=400)

                m_res = await session.execute(
                    select(AdminUser).where(
                        AdminUser.id == mid,
                        AdminUser.role == "manager",
                    )
                )
                m = m_res.scalar_one_or_none()
                if not m:
                    return JSONResponse({"ok": False, "error": "Менеджер не найден."}, status_code=400)

                if (not m.is_active) and (order.manager_id != m.id):
                    return JSONResponse({"ok": False, "error": "Нельзя назначить неактивного менеджера."}, status_code=400)

                order.manager_id = m.id

        else:
            me = _admin_id_uuid(admin)

            if manager_id == "":
                if order.manager_id == me:
                    order.manager_id = None
                elif order.manager_id is None:
                    pass
                else:
                    return JSONResponse({"ok": False, "error": "Нет доступа."}, status_code=404)
            else:
                if manager_id != str(me):
                    return JSONResponse({"ok": False, "error": "Можно назначить только себя."}, status_code=403)
                order.manager_id = me

    await session.commit()

    status_value = order.status.value if order.status else "new"
    status_label = STATUS_LABELS.get(order.status, status_value)

    manager_login: str | None = None
    if order.manager_id:
        u = await session.get(AdminUser, order.manager_id)
        manager_login = u.login if u else None

    return JSONResponse(
        {
            "ok": True,
            "status": status_value,
            "status_label": status_label,
            "manager_login": manager_login,
        }
    )


@router.get("/admin/requests/new", response_class=HTMLResponse)
async def request_new_page(
    request: Request,
    admin: dict = Depends(require_admin_or_404),
    session: AsyncSession = Depends(get_async_session),
):
    cart = request.session.get("req_cart")
    if not isinstance(cart, dict):
        cart = {}
        request.session["req_cart"] = cart

    ids: list[uuid.UUID] = []
    for pid_str in list(cart.keys()):
        try:
            ids.append(uuid.UUID(str(pid_str)))
        except Exception:
            continue

    items = []
    total_price = 0
    total_base = 0
    total_weight = 0.0
    total_volume = 0.0

    if ids:
        res = await session.execute(
            select(Product)
            .options(selectinload(Product.images))
            .where(Product.id.in_(ids), Product.is_active.is_(True))
        )
        products_by_id = {str(p.id): p for p in res.scalars().all()}

        for pid_str, qty0 in cart.items():
            p = products_by_id.get(str(pid_str))
            if not p:
                continue
            qty = int(qty0 or 0)
            if qty < 1:
                continue

            img_url = None
            if getattr(p, "images", None):
                img0 = p.images[0]
                raw = (
                    getattr(img0, "url", None)
                    or getattr(img0, "image_url", None)
                    or getattr(img0, "path", None)
                    or getattr(img0, "file_path", None)
                )
                img_url = _normalize_media_path(raw)

            base_unit = int(p.price)
            unit_price = _calc_display_price(base_unit, p.discount_percent)

            total_price += unit_price * qty
            total_base += base_unit * qty
            total_weight += float(p.weight_kg or 0.0) * qty
            total_volume += float(p.volume_m3 or 0.0) * qty

            items.append(
                {
                    "product": p,
                    "qty": qty,
                    "unit_price": unit_price,
                    "base_unit_price": base_unit,
                    "image_url": img_url,
                    "weight_kg": float(p.weight_kg or 0.0),
                    "volume_m3": float(p.volume_m3 or 0.0),
                }
            )

    managers: list[AdminUser] = []
    if _is_admin(admin):
        managers = await _load_managers_for_admin(session, set())

    products = await _load_products_for_picker(session)

    draft = request.session.get("req_draft")
    if not isinstance(draft, dict):
        draft = {}
        request.session["req_draft"] = draft

    flash = request.session.pop("req_flash", None)
    error = None
    field_errors = {}
    if isinstance(flash, dict):
        error = flash.get("error")
        field_errors = flash.get("field_errors") or {}

    form_data = {
        "customer_name": draft.get("customer_name", ""),
        "customer_phone": draft.get("customer_phone", ""),
        "delivery_type": (draft.get("delivery_type", "pickup") or "pickup"),
        "pickup_address": draft.get("pickup_address", ""),
        "delivery_address": draft.get("delivery_address", ""),
        "comment": draft.get("comment", ""),
        "created_at": draft.get("created_at", ""),
        "status": (draft.get("status", "new") or "new"),
        "manager_id": draft.get("manager_id", ""),
    }

    return templates.TemplateResponse(
        "admin/requests/new.html",
        {
            "request": request,
            "admin": admin,
            "error": error,
            "field_errors": field_errors,
            "form_data": form_data,
            "managers": managers,
            "statuses": [(s.value, STATUS_LABELS[s]) for s in OrderStatus],
            "delivery_labels": DELIVERY_LABELS,
            "pickup_points": PICKUP_POINTS,

            "items": items,
            "total_price": total_price,
            "total_base": total_base,
            "total_weight": total_weight,
            "total_volume": total_volume,
            "products": products,
            "req_cart": {str(k): int(v or 0) for k, v in cart.items()} if isinstance(cart, dict) else {},
        },
    )


@router.post("/admin/requests/new")
async def request_new_submit(
    request: Request,
    admin: dict = Depends(require_admin_or_404),
    session: AsyncSession = Depends(get_async_session),

    customer_name: str | None = Form(None),
    customer_phone: str | None = Form(None),

    delivery_type: str | None = Form(None),
    pickup_address: str | None = Form(None),
    delivery_address: str | None = Form(None),

    comment: str | None = Form(None),

    created_at: str | None = Form(None),
    status: str | None = Form(None),
    manager_id: str | None = Form(None),
):
    cart = request.session.get("req_cart")
    if not isinstance(cart, dict):
        cart = {}
        request.session["req_cart"] = cart

    customer_name = (customer_name or "").strip()
    customer_phone, phone_err = _normalize_phone_ru(customer_phone or "")

    delivery_type = (delivery_type or "").strip()
    pickup_address = (pickup_address or "").strip() or None
    delivery_address = (delivery_address or "").strip() or None
    comment = (comment or "").strip() or None

    draft = request.session.get("req_draft")
    if not isinstance(draft, dict):
        draft = {}
    draft.update({
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "delivery_type": delivery_type,
        "pickup_address": pickup_address or "",
        "delivery_address": delivery_address or "",
        "comment": comment or "",
        "created_at": created_at or "",
        "status": status or "new",
        "manager_id": manager_id or "",
    })
    request.session["req_draft"] = draft

    created_at = (created_at or "").strip()
    created_at_dt: datetime | None = None
    if created_at:
        try:
            created_at_dt = datetime.fromisoformat(created_at)
        except Exception:
            created_at_dt = None

    err: str | None = None
    field_errors: dict[str, str] = {}

    if created_at and not created_at_dt:
        err = "Некорректная дата заявки."
        field_errors["created_at"] = "Проверь формат даты и времени."

    if not err:
        if not cart:
            err = "Добавь товары в заявку."
        elif not customer_name:
            err = "Заполните обязательные поля."
            field_errors["customer_name"] = "Имя обязательно."
        elif not customer_phone:
            err = "Заполните обязательные поля."
            field_errors["customer_phone"] = "Телефон обязателен."
        elif phone_err:
            err = phone_err
        elif delivery_type not in ("delivery", "pickup"):
            err = "Некорректный способ получения."
        elif delivery_type == "delivery" and not delivery_address:
            err = "Для доставки нужен адрес."
            field_errors["delivery_address"] = "Укажи адрес доставки."
        elif delivery_type == "pickup" and not pickup_address:
            err = "Для самовывоза нужен пункт."
            field_errors["pickup_address"] = "Укажи пункт самовывоза."
        else:
            try:
                OrderStatus(status or "new")
            except Exception:
                err = "Некорректный статус."

    if not err and created_at_dt:
        now_dt = datetime.now(created_at_dt.tzinfo) if created_at_dt.tzinfo else datetime.now()
        if created_at_dt > now_dt:
            err = "Дата заявки не может быть в будущем."
            field_errors["created_at"] = "Укажи дату и время не позже текущего момента."

    if not err and created_at and created_at_dt and created_at_dt > datetime.now(created_at_dt.tzinfo):
        err = "Дата заявки не может быть в будущем."
        field_errors["created_at"] = "Укажи дату и время не позже текущего момента."

    mid_uuid: uuid.UUID | None = None
    if not err and _is_admin(admin):
        mid_raw = (manager_id or "").strip()
        if mid_raw:
            try:
                mid_uuid = uuid.UUID(mid_raw)
            except Exception:
                err = "Некорректный менеджер."
            else:
                m_res = await session.execute(
                    select(AdminUser).where(
                        AdminUser.id == mid_uuid,
                        AdminUser.role == "manager",
                    )
                )
                m = m_res.scalar_one_or_none()
                if not m:
                    err = "Менеджер не найден."
                elif not m.is_active:
                    err = "Нельзя назначить неактивного менеджера."

    if err:
        request.session["req_flash"] = {"error": err, "field_errors": field_errors}
        return RedirectResponse("/admin/requests/new", status_code=303)

    ids: list[uuid.UUID] = []
    for pid_str in list(cart.keys()):
        try:
            ids.append(uuid.UUID(str(pid_str)))
        except Exception:
            continue

    if not ids:
        request.session["req_flash"] = {"error": "Добавь товары в заявку.", "field_errors": {}}
        return RedirectResponse("/admin/requests/new", status_code=303)

    res = await session.execute(
        select(Product)
        .options(selectinload(Product.images), selectinload(Product.category))
        .where(Product.id.in_(ids), Product.is_active.is_(True))
    )
    products_by_id = {str(p.id): p for p in res.scalars().all()}

    items_ui = []
    total_price = 0
    total_weight = 0.0
    total_volume = 0.0

    for pid_str, qty0 in cart.items():
        p = products_by_id.get(str(pid_str))
        if not p:
            continue
        qty = int(qty0 or 0)
        if qty < 1:
            continue

        img_url = None
        if getattr(p, "images", None):
            img0 = p.images[0]
            raw = (
                getattr(img0, "url", None)
                or getattr(img0, "image_url", None)
                or getattr(img0, "path", None)
                or getattr(img0, "file_path", None)
            )
            img_url = _normalize_media_path(raw)

        base_unit = int(p.price)
        unit_price = _calc_display_price(base_unit, p.discount_percent)

        total_price += unit_price * qty
        total_weight += float(p.weight_kg or 0.0) * qty
        total_volume += float(p.volume_m3 or 0.0) * qty

        items_ui.append((p, qty, unit_price, img_url))

    order = Order(
        customer_name=customer_name,
        customer_phone=customer_phone,
        comment=comment,
        delivery_type=DeliveryType(delivery_type),
        delivery_address=delivery_address if delivery_type == "delivery" else None,
        pickup_address=pickup_address if delivery_type == "pickup" else None,
        total_price=total_price,
        total_weight_kg=total_weight,
        total_volume_m3=total_volume,
        manager_id=mid_uuid,
        status=OrderStatus(status or "new"),
    )
    if created_at_dt:
        order.created_at = created_at_dt

    session.add(order)
    await session.flush()

    for p, qty, unit_price, img_url in items_ui:
        cat = getattr(p, "category", None)
        session.add(
            OrderItem(
                order_id=order.id,
                product_id=p.id,
                quantity=qty,
                price_per_item=p.price,
                final_price_per_item=unit_price,
                discount_percent=p.discount_percent,
                total_price=unit_price * qty,
                product_name=p.name,
                product_slug=getattr(p, "slug", None),
                weight_kg=float(p.weight_kg or 0.0),
                volume_m3=float(p.volume_m3 or 0.0),
                product_image=img_url,
                category_id=getattr(p, "category_id", None),
                category_name=getattr(cat, "name", None),
                category_slug=getattr(cat, "slug", None),
            )
        )

    await session.commit()

    request.session["req_cart"] = {}
    request.session.pop("req_draft", None)
    request.session.pop("req_flash", None)

    return RedirectResponse(f"/admin/requests/", status_code=303)


@router.get("/admin/requests/{order_id}/edit", response_class=HTMLResponse)
async def request_edit_page(
    order_id: uuid.UUID,
    request: Request,
    admin: dict = Depends(require_admin_or_404),
    session: AsyncSession = Depends(get_async_session),
):
    order = await _get_order_or_404(session, order_id)

    if not _is_admin(admin) and not _can_manager_access_order(admin, order):
        raise HTTPException(status_code=404)

    res_items = await session.execute(
        select(OrderItem)
        .where(OrderItem.order_id == order.id)
        .options(selectinload(OrderItem.product))
    )
    order_items = list(res_items.scalars().all())

    keep_ids: set[uuid.UUID] = set()
    managers: list[AdminUser] = []
    if _is_admin(admin):
        if order.manager_id:
            keep_ids.add(order.manager_id)
        managers = await _load_managers_for_admin(session, keep_ids)

    products = await _load_products_for_picker(session)
    items, total_price, total_base, total_weight, total_volume, req_cart = await _load_order_items_for_ui(session, order)

    flash_key = f"req_edit_flash:{order_id}"
    flash = request.session.pop(flash_key, None)
    error = None
    field_errors = {}
    if isinstance(flash, dict):
        error = flash.get("error")
        field_errors = flash.get("field_errors") or {}

    form_data = {
        "customer_name": order.customer_name or "",
        "customer_phone": order.customer_phone or "",
        "delivery_type": (order.delivery_type.value if order.delivery_type else "pickup"),
        "pickup_address": getattr(order, "pickup_address", None) or "",
        "delivery_address": getattr(order, "delivery_address", None) or "",
        "comment": order.comment or "",
        "created_at": _iso_dt_local(order.created_at),
        "status": (order.status.value if order.status else "new"),
        "manager_id": str(order.manager_id) if order.manager_id else "",
    }

    return templates.TemplateResponse(
        "admin/requests/edit.html",
        {
            "request": request,
            "admin": admin,
            "order_id": str(order.id),
            "error": error,
            "field_errors": field_errors,
            "form_data": form_data,
            "managers": managers,
            "statuses": [(s.value, STATUS_LABELS[s]) for s in OrderStatus],
            "delivery_labels": DELIVERY_LABELS,
            "pickup_points": PICKUP_POINTS,

            "items": items,
            "total_price": total_price,
            "total_base": total_base,
            "total_weight": total_weight,
            "total_volume": total_volume,
            "products": products,
            "req_cart": req_cart,
            "order_items_count": len(order_items),
        },
    )


@router.post("/admin/requests/{order_id}/edit")
async def request_edit_submit(
    order_id: uuid.UUID,
    request: Request,
    admin: dict = Depends(require_admin_or_404),
    session: AsyncSession = Depends(get_async_session),

    customer_name: str = Form(...),
    customer_phone: str = Form(...),

    delivery_type: str = Form(...),
    pickup_address: str | None = Form(None),
    delivery_address: str | None = Form(None),

    comment: str | None = Form(None),

    created_at: str | None = Form(None),
    status: str | None = Form(None),
    manager_id: str | None = Form(None),
):
    order = await _get_order_or_404(session, order_id)

    if not _is_admin(admin) and not _can_manager_access_order(admin, order):
        raise HTTPException(status_code=404)

    customer_name = (customer_name or "").strip()
    customer_phone, phone_err = _normalize_phone_ru(customer_phone or "")

    delivery_type = (delivery_type or "").strip()
    pickup_address = (pickup_address or "").strip() or None
    delivery_address = (delivery_address or "").strip() or None
    comment = (comment or "").strip() or None

    created_at = (created_at or "").strip()
    created_at_dt: datetime | None = None
    if created_at:
        try:
            created_at_dt = datetime.fromisoformat(created_at)
        except Exception:
            created_at_dt = None

    res_items = await session.execute(
        select(OrderItem).where(OrderItem.order_id == order.id)
    )
    order_items = list(res_items.scalars().all())

    err: str | None = None
    field_errors: dict[str, str] = {}

    if not order_items:
        err = "Добавь товары в заявку."
    elif not customer_name:
        err = "Укажи имя."
    elif phone_err:
        err = phone_err
    elif delivery_type not in ("delivery", "pickup"):
        err = "Некорректный способ получения."
    elif delivery_type == "delivery" and not delivery_address:
        err = "Для доставки нужен адрес."
        field_errors["delivery_address"] = "Укажи адрес доставки."
    elif delivery_type == "pickup" and not pickup_address:
        err = "Для самовывоза нужен пункт."
        field_errors["pickup_address"] = "Укажи пункт самовывоза."
    else:
        try:
            OrderStatus(status or "new")
        except Exception:
            err = "Некорректный статус."

    mid_uuid: uuid.UUID | None = None
    if not err:
        if _is_admin(admin):
            mid_raw = (manager_id or "").strip()
            if mid_raw:
                try:
                    mid_uuid = uuid.UUID(mid_raw)
                except Exception:
                    err = "Некорректный менеджер."
                else:
                    m_res = await session.execute(
                        select(AdminUser).where(
                            AdminUser.id == mid_uuid,
                            AdminUser.role == "manager",
                        )
                    )
                    m = m_res.scalar_one_or_none()
                    if not m:
                        err = "Менеджер не найден."
                    elif not m.is_active:
                        err = "Нельзя назначить неактивного менеджера."
        else:
            me = _admin_id_uuid(admin)
            mid_uuid = order.manager_id
            if manager_id is not None:
                raw = (manager_id or "").strip()
                if raw == "":
                    if order.manager_id == me:
                        mid_uuid = None
                    elif order.manager_id is None:
                        mid_uuid = None
                    else:
                        raise HTTPException(status_code=404)
                else:
                    if raw != str(me):
                        raise HTTPException(status_code=404)
                    mid_uuid = me

    if err:
        flash_key = f"req_edit_flash:{order_id}"
        request.session[flash_key] = {"error": err, "field_errors": field_errors}
        return RedirectResponse(f"/admin/requests/{order_id}/edit", status_code=303)

    order.customer_name = customer_name
    order.customer_phone = customer_phone
    order.comment = comment
    order.delivery_type = DeliveryType(delivery_type)
    order.delivery_address = delivery_address if delivery_type == "delivery" else None
    order.pickup_address = pickup_address if delivery_type == "pickup" else None
    order.status = OrderStatus(status or "new")
    order.manager_id = mid_uuid

    if created_at_dt:
        order.created_at = created_at_dt

    await _recalc_and_save_order_totals(session, order)
    await session.commit()

    return RedirectResponse(f"/admin/requests/", status_code=303)


@router.post("/admin/requests/{order_id:uuid}/cart/add")
async def request_edit_cart_add(
    order_id: uuid.UUID,
    request: Request,
    admin: dict = Depends(require_admin_or_404),
    session: AsyncSession = Depends(get_async_session),

    product_id: str = Form(...),
    qty: int = Form(1),
):
    order = await _get_order_or_404(session, order_id)
    if not _is_admin(admin) and not _can_manager_access_order(admin, order):
        raise HTTPException(status_code=404)

    try:
        pid = uuid.UUID(product_id)
    except Exception:
        raise HTTPException(status_code=400)

    res = await session.execute(
        select(Product)
        .options(selectinload(Product.images), selectinload(Product.category))
        .where(Product.id == pid, Product.is_active.is_(True))
    )

    product = res.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404)

    q = int(qty) if qty else 1
    if q < 1:
        q = 1

    res2 = await session.execute(
        select(OrderItem).where(OrderItem.order_id == order.id, OrderItem.product_id == pid)
    )
    it = res2.scalar_one_or_none()

    base_unit = int(product.price)
    unit_price = _calc_display_price(base_unit, product.discount_percent)

    if it:
        it.quantity = int(it.quantity or 0) + q
        it.final_price_per_item = unit_price
        it.price_per_item = base_unit
        it.discount_percent = product.discount_percent
        it.total_price = unit_price * int(it.quantity or 0)
        it.weight_kg = float(product.weight_kg or 0.0)
        it.volume_m3 = float(product.volume_m3 or 0.0)
        session.add(it)
        new_qty = int(it.quantity or 0)
    else:
        img_url = None
        if getattr(product, "images", None):
            img0 = product.images[0] if product.images else None
            if img0:
                raw = (
                    getattr(img0, "url", None)
                    or getattr(img0, "image_url", None)
                    or getattr(img0, "path", None)
                    or getattr(img0, "file_path", None)
                )
                img_url = _normalize_media_path(raw)

        cat = getattr(product, "category", None)
        it = OrderItem(
            order_id=order.id,
            product_id=pid,
            quantity=q,
            price_per_item=base_unit,
            final_price_per_item=unit_price,
            discount_percent=product.discount_percent,
            total_price=unit_price * q,
            product_name=product.name,
            product_slug=getattr(product, "slug", None),
            weight_kg=float(product.weight_kg or 0.0),
            volume_m3=float(product.volume_m3 or 0.0),
            product_image=img_url,
            category_id=getattr(product, "category_id", None),
            category_name=getattr(cat, "name", None),
            category_slug=getattr(cat, "slug", None),
        )
        session.add(it)
        new_qty = q

    await _recalc_and_save_order_totals(session, order)
    await session.commit()

    return {"ok": True, "qty": new_qty}


@router.post("/admin/requests/{order_id:uuid}/cart/update")
async def request_edit_cart_update(
    order_id: uuid.UUID,
    request: Request,
    admin: dict = Depends(require_admin_or_404),
    session: AsyncSession = Depends(get_async_session),

    product_id: str = Form(...),
    qty: int = Form(...),
):
    order = await _get_order_or_404(session, order_id)
    if not _is_admin(admin) and not _can_manager_access_order(admin, order):
        raise HTTPException(status_code=404)

    try:
        pid = uuid.UUID(product_id)
    except Exception:
        raise HTTPException(status_code=400)

    q = int(qty) if qty is not None else 1

    res2 = await session.execute(
        select(OrderItem).where(OrderItem.order_id == order.id, OrderItem.product_id == pid)
    )
    it = res2.scalar_one_or_none()

    if q < 1:
        if it:
            await session.delete(it)
    else:
        if not it:
            raise HTTPException(status_code=404)

        res_p = await session.execute(select(Product).where(Product.id == pid, Product.is_active.is_(True)))
        product = res_p.scalar_one_or_none()
        if not product:
            raise HTTPException(status_code=404)

        base_unit = int(product.price)
        unit_price = _calc_display_price(base_unit, product.discount_percent)

        it.quantity = q
        it.final_price_per_item = unit_price
        it.price_per_item = base_unit
        it.discount_percent = product.discount_percent
        it.total_price = unit_price * q
        it.weight_kg = float(product.weight_kg or 0.0)
        it.volume_m3 = float(product.volume_m3 or 0.0)
        session.add(it)

    await _recalc_and_save_order_totals(session, order)
    await session.commit()
    return {"ok": True}


@router.post("/admin/requests/{order_id:uuid}/cart/remove")
async def request_edit_cart_remove(
    order_id: uuid.UUID,
    request: Request,
    admin: dict = Depends(require_admin_or_404),
    session: AsyncSession = Depends(get_async_session),

    product_id: str = Form(...),
):
    order = await _get_order_or_404(session, order_id)
    if not _is_admin(admin) and not _can_manager_access_order(admin, order):
        raise HTTPException(status_code=404)

    try:
        pid = uuid.UUID(product_id)
    except Exception:
        raise HTTPException(status_code=400)

    res2 = await session.execute(
        select(OrderItem).where(OrderItem.order_id == order.id, OrderItem.product_id == pid)
    )
    it = res2.scalar_one_or_none()
    if it:
        await session.delete(it)

    await _recalc_and_save_order_totals(session, order)
    await session.commit()
    return {"ok": True}


@router.post("/admin/requests/{order_id:uuid}/cart/clear")
async def request_edit_cart_clear(
    order_id: uuid.UUID,
    request: Request,
    admin: dict = Depends(require_admin_or_404),
    session: AsyncSession = Depends(get_async_session),
):
    order = await _get_order_or_404(session, order_id)
    if not _is_admin(admin) and not _can_manager_access_order(admin, order):
        raise HTTPException(status_code=404)

    await session.execute(delete(OrderItem).where(OrderItem.order_id == order.id))
    await _recalc_and_save_order_totals(session, order)
    await session.commit()
    return {"ok": True}


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


@router.post("/admin/requests/new/cart/add")
async def request_new_cart_add(
    request: Request,
    product_id: str | None = Form(None),
    qty: int | None = Form(None),
):
    form = await request.form()
    pid_raw = (product_id or form.get("product_id") or "").strip()
    if not pid_raw:
        raise HTTPException(status_code=400, detail="product_id is required")

    try:
        pid = uuid.UUID(pid_raw)
    except Exception:
        raise HTTPException(status_code=400, detail="bad product_id")

    q_raw = qty if qty is not None else form.get("qty")
    try:
        q = int(q_raw) if q_raw is not None else 1
    except Exception:
        q = 1
    if q < 1:
        q = 1

    cart = request.session.get("req_cart")
    if not isinstance(cart, dict):
        cart = {}

    key = str(pid)
    cart[key] = int(cart.get(key, 0)) + q
    request.session["req_cart"] = cart
    return {"ok": True, "qty": cart[key]}


@router.post("/admin/requests/new/cart/update")
async def request_new_cart_update(
    request: Request,
    product_id: str | None = Form(None),
    qty: int | None = Form(None),
):
    form = await request.form()
    pid_raw = (product_id or form.get("product_id") or "").strip()
    if not pid_raw:
        raise HTTPException(status_code=400, detail="product_id is required")

    try:
        uuid.UUID(pid_raw)
    except Exception:
        raise HTTPException(status_code=400, detail="bad product_id")

    q_raw = qty if qty is not None else form.get("qty")
    try:
        q = int(q_raw) if q_raw is not None else 1
    except Exception:
        q = 1

    cart = request.session.get("req_cart")
    if not isinstance(cart, dict):
        cart = {}

    if q < 1:
        cart.pop(pid_raw, None)
    else:
        cart[pid_raw] = q

    request.session["req_cart"] = cart
    return {"ok": True}


@router.post("/admin/requests/new/cart/remove")
async def request_new_cart_remove(
    request: Request,
    product_id: str = Form(...),
):
    cart = request.session.get("req_cart")
    if not isinstance(cart, dict):
        cart = {}
    cart.pop(str(product_id), None)
    request.session["req_cart"] = cart
    return {"ok": True}


@router.post("/admin/requests/new/cart/clear")
async def request_new_cart_clear(request: Request):
    request.session["req_cart"] = {}
    return {"ok": True}
