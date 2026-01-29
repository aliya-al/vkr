# app/routers/public/favorites.py
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.product import Product
from app.services.favorites import (
    add_to_favorites,
    clear_favorites,
    get_favorite_ids,
    remove_from_favorites,
)
from app.utils.database import get_async_session
from app.utils.templates import templates

router = APIRouter()


@router.get("/favorites", response_class=HTMLResponse)
async def favorites_page(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    ids_str = get_favorite_ids(request.session)
    if not ids_str:
        return templates.TemplateResponse(
            "public/favorites.html",
            {"request": request, "products": []},
        )

    ids: list[uuid.UUID] = []
    for s in ids_str:
        try:
            ids.append(uuid.UUID(s))
        except Exception:
            continue

    if not ids:
        return templates.TemplateResponse(
            "public/favorites.html",
            {"request": request, "products": []},
        )

    result = await session.execute(
        select(Product)
        .where(Product.id.in_(ids))
        .options(selectinload(Product.images))
    )
    products = result.scalars().all()

    # сохранить порядок из session
    by_id = {p.id: p for p in products}
    ordered_products = [by_id[i] for i in ids if i in by_id]

    return templates.TemplateResponse(
        "public/favorites.html",
        {"request": request, "products": ordered_products},
    )


@router.post("/favorites/add/{product_id}")
async def favorites_add(
    product_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    # проверяем, что товар существует
    exists = await session.execute(select(Product.id).where(Product.id == product_id))
    if not exists.scalar_one_or_none():
        raise HTTPException(status_code=404)

    add_to_favorites(request.session, product_id)

    back = request.headers.get("referer")
    return RedirectResponse(back or "/favorites", status_code=303)

@router.post("/favorites/toggle")
async def favorites_toggle(
    request: Request,
    product_id: uuid.UUID = Form(...),
    session: AsyncSession = Depends(get_async_session),
):
    # проверяем, что товар существует
    exists = await session.execute(select(Product.id).where(Product.id == product_id))
    if not exists.scalar_one_or_none():
        raise HTTPException(status_code=404)

    ids_str = get_favorite_ids(request.session)
    ids_set = set(ids_str or [])

    if str(product_id) in ids_set:
        remove_from_favorites(request.session, product_id)
    else:
        add_to_favorites(request.session, product_id)

    back = request.headers.get("referer")
    return RedirectResponse(back or "/favorites", status_code=303)

@router.post("/favorites/remove/{product_id}")
async def favorites_remove(product_id: uuid.UUID, request: Request):
    remove_from_favorites(request.session, product_id)

    back = request.headers.get("referer")
    return RedirectResponse(back or "/favorites", status_code=303)


@router.post("/favorites/clear")
async def favorites_clear(request: Request):
    clear_favorites(request.session)
    return RedirectResponse("/favorites", status_code=303)
