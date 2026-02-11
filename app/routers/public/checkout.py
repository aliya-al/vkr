from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import DeliveryType, Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.utils.database import get_async_session
from app.utils.templates import templates

router = APIRouter()

def _normalize_media_path(path: str | None) -> str | None:

    if not path:
        return None

    p = path.strip()
    if not p:
        return None

    # внешние ссылки
    if p.startswith(("http://", "https://", "//")):
        return p

    # уже корректный публичный путь
    if p.startswith("/static/"):
        return p

    # если кто-то записал "static/..."
    if p.startswith("static/"):
        return "/" + p

    # нормализуем слэши
    p = p.lstrip("/")

    # если в БД уже лежит полный относительный путь от static
    #    например: "img/uploads/products/abc.jpg"
    if p.startswith("img/uploads/products/"):
        return "/static/" + p

    # если в БД лежит только имя файла: "abc.jpg"
    # или "products/abc.jpg"
    p = p.removeprefix("products/")

    return "/static/img/uploads/products/" + p

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


async def _load_cart_products(
    session: AsyncSession, cart: dict[str, int]
) -> tuple[list[dict], int, int, float, float]:
    """
    Возвращает:
      items: [{product, qty, unit_price, base_unit_price, line_total, line_total_base}]
      total_price, total_base, total_weight_kg, total_volume_m3
    """
    if not cart:
        return [], 0, 0, 0.0, 0.0

    # приводим ключи корзины к uuid
    ids: list[uuid.UUID] = []
    for pid_str in cart.keys():
        try:
            ids.append(uuid.UUID(pid_str))
        except Exception:
            continue

    if not ids:
        return [], 0, 0, 0.0, 0.0

    res = await session.execute(
        select(Product)
        .options(
            selectinload(Product.images),
            selectinload(Product.category),
        )
        .where(Product.id.in_(ids), Product.is_active.is_(True))
    )

    products = list(res.scalars().all())
    by_id = {str(p.id): p for p in products}

    items: list[dict] = []
    total_price = 0
    total_base = 0
    total_weight = 0.0
    total_volume = 0.0

    for pid_str, qty in cart.items():
        p = by_id.get(pid_str)
        if not p:
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

        line_total = unit_price * qty
        line_total_base = base_unit * qty

        total_price += line_total
        total_base += line_total_base
        total_weight += float(p.weight_kg or 0.0) * qty
        total_volume += float(p.volume_m3 or 0.0) * qty

        items.append(
            {
                "product": p,
                "qty": qty,
                "unit_price": unit_price,
                "base_unit_price": base_unit,
                "line_total": line_total,
                "line_total_base": line_total_base,
                "image_url": img_url,
            }
        )

    return items, total_price, total_base, total_weight, total_volume


@router.get("/checkout", response_class=HTMLResponse)
async def checkout_page(request: Request, session: AsyncSession = Depends(get_async_session)):
    cart = _get_cart(request.session)
    items, total_price, total_base, total_weight, total_volume = await _load_cart_products(session, cart)

    return templates.TemplateResponse(
        "public/checkout.html",
        {
            "total_base": total_base,
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
    pickup_address: str | None = Form(None),
    delivery_address: str | None = Form(None),
    comment: str | None = Form(None),
    session: AsyncSession = Depends(get_async_session),
):

    cart = _get_cart(request.session)
    items, total_price, total_base, total_weight, total_volume = await _load_cart_products(session, cart)

    # базовые проверки
    customer_name = customer_name.strip()
    customer_phone = customer_phone.strip()
    digits = "".join(ch for ch in customer_phone if ch.isdigit())

    # 9XXXXXXXXX -> 7XXXXXXXXXX
    if digits.startswith("9"):
        digits = "7" + digits
    # 8XXXXXXXXXX -> 7XXXXXXXXXX
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]

    # строгая проверка
    if not (len(digits) == 11 and digits.startswith("7")):
        error = "Укажи телефон в формате +7 (999) 999-99-99."
    else:
        # сохраняем в одном нормальном виде
        customer_phone = f"+7 ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"

    delivery_address = (delivery_address or "").strip()
    pickup_address = (pickup_address or "").strip()

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
    elif delivery_type == "pickup" and not pickup_address:
        error = "Для самовывоза нужен пункт самовывоза."
    elif delivery_type == "delivery" and not delivery_address:
        error = "Для доставки нужен адрес."

    if error:
        return templates.TemplateResponse(
            "public/checkout.html",
            {
                "request": request,
                "pickup_address": pickup_address,

                "items": items,
                "total_base": total_base,
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
            pickup_address=pickup_address if delivery_type == "pickup" else None,

            total_price=total_price,
            total_weight_kg=total_weight,
            total_volume_m3=total_volume,
            manager_id=None,
        )
        session.add(order)
        await session.flush()  # получаем order.id

        for it in items:
            p: Product = it["product"]
            qty: int = it["qty"]
            unit_price: int = it["unit_price"]
            line_total: int = it["line_total"]

            cat = getattr(p, "category", None)

            session.add(
                OrderItem(
                    order_id=order.id,
                    product_id=p.id,
                    quantity=qty,
                    price_per_item=p.price,
                    final_price_per_item=unit_price,
                    discount_percent=p.discount_percent,
                    total_price=line_total,

                    product_name=p.name,
                    product_slug=getattr(p, "slug", None),
                    weight_kg=float(p.weight_kg or 0.0),
                    volume_m3=float(p.volume_m3 or 0.0),
                    product_image=it.get("image_url"),

                    category_id=getattr(p, "category_id", None),
                    category_name=getattr(cat, "name", None),
                    category_slug=getattr(cat, "slug", None),
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
                "total_base": total_base,
                "total_volume": total_volume,
                "pickup_address": pickup_address,

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
