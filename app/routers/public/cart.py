# app/routers/public/cart.py
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.utils.database import get_async_session
from app.utils.templates import templates

router = APIRouter()


def _get_cart(session_obj: dict) -> dict[str, int]:
    """
    Корзина живет в сессии: {"<product_uuid>": qty}
    """
    cart = session_obj.get("cart")
    if not isinstance(cart, dict):
        cart = {}
        session_obj["cart"] = cart
    # нормализуем qty
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


@router.post("/cart/add")
async def cart_add(
    request: Request,
    product_id: str = Form(...),
    qty: int = Form(1),
    session: AsyncSession = Depends(get_async_session),
):
    # валидация id
    try:
        pid = uuid.UUID(product_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Некорректный product_id")

    # проверим товар существует и активен
    res = await session.execute(select(Product).where(Product.id == pid))
    product = res.scalar_one_or_none()
    if not product or not product.is_active:
        raise HTTPException(status_code=404, detail="Товар не найден")

    qty = int(qty) if qty else 1
    if qty < 1:
        qty = 1

    cart = _get_cart(request.session)
    key = str(pid)
    cart[key] = int(cart.get(key, 0)) + qty
    request.session["cart"] = cart

    # возвращаемся туда, откуда пришли, если возможно
    referer = request.headers.get("referer")
    return RedirectResponse(referer or "/cart", status_code=303)


@router.get("/cart", response_class=HTMLResponse)
async def cart_page(request: Request, session: AsyncSession = Depends(get_async_session)):
    cart = _get_cart(request.session)
    if not cart:
        return templates.TemplateResponse(
            "public/cart.html",
            {"request": request, "items": [], "total": 0},
        )

    # грузим товары одним запросом
    ids: list[uuid.UUID] = []
    for k in cart.keys():
        try:
            ids.append(uuid.UUID(k))
        except Exception:
            continue

    if not ids:
        request.session["cart"] = {}
        return templates.TemplateResponse(
            "public/cart.html",
            {"request": request, "items": [], "total": 0},
        )

    res = await session.execute(select(Product).where(Product.id.in_(ids)))
    products = res.scalars().all()
    by_id = {str(p.id): p for p in products}

    items = []
    total = 0

    for pid_str, qty in cart.items():
        p = by_id.get(pid_str)
        if not p:
            continue

        unit = _calc_display_price(p.price, p.discount_percent)
        line_total = unit * qty
        total += line_total

        items.append(
            {
                "id": pid_str,
                "name": p.name,
                "qty": qty,
                "unit_price": unit,
                "line_total": line_total,
            }
        )

    return templates.TemplateResponse(
        "public/cart.html",
        {"request": request, "items": items, "total": total},
    )


@router.post("/cart/remove")
async def cart_remove(request: Request, product_id: str = Form(...)):
    cart = _get_cart(request.session)
    cart.pop(str(product_id), None)
    request.session["cart"] = cart
    return RedirectResponse("/cart", status_code=303)


@router.post("/cart/clear")
async def cart_clear(request: Request):
    request.session["cart"] = {}
    return RedirectResponse("/cart", status_code=303)
