# app/routers/public/checkout.py
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import DeliveryType, Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.utils.database import get_async_session
from app.utils.templates import templates

router = APIRouter()


def _get_cart(session_obj: dict) -> dict[str, int]:
    """
    Корзина в сессии: {"<product_uuid>": qty}
    """
    cart = session_obj.get("cart")
    if not isinstance(cart, dict):
        cart = {}
        session_obj["cart"] = cart

    normalized: dict[str, int] = {}
    for k, v in cart.items():
        try:
            qty = int(v)
        except Exception:
            qty = 0
        if qty > 0:
            normalized[str(k)] = qty

    session_obj["cart"] = normalized
    return normalized


def _calc_display_price(price: int, discount_percent: int | None) -> int:
    if not discount_percent:
        return price
    pct = max(0, min(int(discount_percent), 100))
    return int(round(price * (100 - pct) / 100))


async def _load_cart_products(session: AsyncSession, cart: dict[str, int]) -> tuple[list[dict], int, float, float]:
    """
    Возвращает:
      items: [{product, qty, unit_price, line_total}]
      total_price, total_weight_kg, total_volume_m3
    """
    ids: list[uuid.UUID] = []
    for k in cart.keys():
        try:
            ids.append(uuid.UUID(k))
        except Exception:
            continue

    if not ids:
        return [], 0, 0.0, 0.0

    res = await session.execute(
        select(Product).where(Product.id.in_(ids), Product.is_active.is_(True))
    )
    products = res.scalars().all()
    by_id = {str(p.id): p for p in products}

    items: list[dict] = []
    total_price = 0
    total_weight = 0.0
    total_volume = 0.0

    for pid_str, qty in cart.items():
        p = by_id.get(pid_str)
        if not p:
            continue

        unit_price = _calc_display_price(p.price, p.discount_percent)
        line_total = unit_price * qty

        total_price += line_total
        total_weight += float(p.weight_kg) * qty
        total_volume += float(p.volume_m3) * qty

        items.append(
            {
                "product": p,
                "qty": qty,
                "unit_price": unit_price,
                "line_total": line_total,
            }
        )

    return items, total_price, total_weight, total_volume


@router.get("/checkout", response_class=HTMLResponse)
async def checkout_page(request: Request, session: AsyncSession = Depends(get_async_session)):
    cart = _get_cart(request.session)
    items, total_price, total_weight, total_volume = await _load_cart_products(session, cart)

    return templates.TemplateResponse(
        "public/checkout.html",
        {
            "request": request,
            "items": items,
            "total_price": total_price,
            "total_weight": total_weight,
            "total_volume": total_volume,
            "error": None,
            "form_data": {},
        },
    )

@router.post("/checkout")
async def checkout_submit(
    request: Request,
    customer_name: str = Form(...),
    customer_phone: str = Form(...),
    delivery_type: str = Form(...),  # "delivery" | "pickup"
    delivery_address: str | None = Form(None),
    comment: str | None = Form(None),
    session: AsyncSession = Depends(get_async_session),
):
    cart = _get_cart(request.session)
    items, total_price, total_weight, total_volume = await _load_cart_products(session, cart)

    # базовые проверки
    customer_name = customer_name.strip()
    customer_phone = customer_phone.strip()
    delivery_address = (delivery_address or "").strip()
    comment = (comment or "").strip() or None

    error = None
    if not items:
        error = "Корзина пуста или товары недоступны."
    elif not customer_name:
        error = "Укажи имя."
    elif not customer_phone:
        error = "Укажи номер телефона."
    elif delivery_type not in ("delivery", "pickup"):
        error = "Некорректный способ получения."
    elif delivery_type == "delivery" and not delivery_address:
        error = "Для доставки нужен адрес."

    if error:
        return templates.TemplateResponse(
            "public/checkout.html",
            {
                "request": request,
                "items": items,
                "total_price": total_price,
                "total_weight": total_weight,
                "total_volume": total_volume,
                "error": error,
                "form_data": {
                    "customer_name": customer_name,
                    "customer_phone": customer_phone,
                    "delivery_type": delivery_type,
                    "delivery_address": delivery_address,
                    "comment": comment or "",
                },
            },
            status_code=400,
        )

    try:
        order = Order(
            customer_name=customer_name,
            customer_phone=customer_phone,
            comment=comment,
            delivery_type=DeliveryType(delivery_type),
            delivery_address=delivery_address if delivery_type == "delivery" else None,
            pickup_address=None,  # самовывоз позже
            total_price=total_price,
            total_weight_kg=total_weight,
            total_volume_m3=total_volume,
            manager_id=None,  # менеджер назначается позже
        )
        session.add(order)
        await session.flush()  # получаем order.id

        for it in items:
            p: Product = it["product"]
            qty: int = it["qty"]
            unit_price: int = it["unit_price"]
            line_total: int = it["line_total"]

            session.add(
                OrderItem(
                    order_id=order.id,
                    product_id=p.id,
                    quantity=qty,
                    price_per_item=p.price,  # базовая цена на момент заказа
                    discount_percent=p.discount_percent,
                    total_price=line_total,  # по цене с учётом скидки

                    product_name=p.name,
                    product_slug=getattr(p, "slug", None),
                    weight_kg=float(p.weight_kg or 0.0),
                    volume_m3=float(p.volume_m3 or 0.0),
                )
            )

        await session.commit()

    except Exception:
        await session.rollback()
        return templates.TemplateResponse(
            "public/checkout.html",
            {
                "request": request,
                "items": items,
                "total_price": total_price,
                "total_weight": total_weight,
                "total_volume": total_volume,
                "error": "Не удалось создать заявку. Попробуй ещё раз.",
                "form_data": {
                    "customer_name": customer_name,
                    "customer_phone": customer_phone,
                    "delivery_type": delivery_type,
                    "delivery_address": delivery_address,
                    "comment": comment or "",
                },
            },
            status_code=500,
        )

    # очищаем корзину после успешного сохранения
    request.session["cart"] = {}
    request.session["last_order_id"] = str(order.id)

    return RedirectResponse("/checkout/success", status_code=303)

@router.get("/checkout/success", response_class=HTMLResponse)
async def checkout_success(request: Request):
    last_order_id = request.session.get("last_order_id")
    return templates.TemplateResponse(
        "public/order_success.html",
        {"request": request, "last_order_id": last_order_id},
    )
