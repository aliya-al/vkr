# app/routers/public/compare.py
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.product import Product
from app.models.product_characteristic_value import ProductCharacteristicValue
from app.services.compare import (
    add_to_compare,
    clear_compare,
    get_compare_ids,
    remove_from_compare,
)
from app.utils.database import get_async_session
from app.utils.templates import templates

router = APIRouter()


def _format_value(v: ProductCharacteristicValue) -> str | None:
    ch = getattr(v, "characteristic", None)
    if not ch:
        return None

    # value_type хранится в GlobalCharacteristic (Enum CharacteristicType) :contentReference[oaicite:1]{index=1}
    vt = getattr(ch, "value_type", None)

    if str(vt) == "CharacteristicType.number" or getattr(vt, "value", None) == "number":
        if v.value_number is None:
            return None
        s = f"{v.value_number}".rstrip("0").rstrip(".")
        unit = getattr(ch, "unit", None)
        return f"{s} {unit}".strip() if unit else s

    # string
    if not v.value_string:
        return None
    return str(v.value_string).strip()


@router.get("/compare", response_class=HTMLResponse)
async def compare_page(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Таблица сравнения:
      - колонки: товары
      - строки: характеристики (объединение характеристик по товарам)
    """
    ids_str = get_compare_ids(request.session)
    if not ids_str:
        return templates.TemplateResponse(
            "public/catalog/compare.html",
            {
                "request": request,
                "products": [],
                "rows": [],
            },
        )

    # UUID list
    ids: list[uuid.UUID] = []
    for s in ids_str:
        try:
            ids.append(uuid.UUID(s))
        except Exception:
            continue

    if not ids:
        return templates.TemplateResponse(
            "public/catalog/compare.html",
            {"request": request, "products": [], "rows": []},
        )

    # Подгружаем товары + значения характеристик + сами характеристики (без N+1)
    result = await session.execute(
        select(Product)
        .where(Product.id.in_(ids))
        .options(
            selectinload(Product.images),
            selectinload(Product.characteristics_values).selectinload(ProductCharacteristicValue.characteristic),
        )
    )
    products = result.scalars().all()

    # Важно: сохраняем порядок из session
    by_id = {p.id: p for p in products}
    ordered_products = [by_id[i] for i in ids if i in by_id]

    # Собираем матрицу: characteristic_id -> {product_id -> value_str}
    # Плюс метаданные строки (name/unit/value_type)
    row_meta: dict[int, dict[str, Any]] = {}
    matrix: dict[int, dict[uuid.UUID, str]] = {}

    for p in ordered_products:
        for v in (p.characteristics_values or []):
            ch = getattr(v, "characteristic", None)
            if not ch:
                continue

            cid = int(v.characteristic_id)
            row_meta.setdefault(
                cid,
                {
                    "characteristic_id": cid,
                    "name": getattr(ch, "name", ""),
                    "unit": getattr(ch, "unit", None),
                    "value_type": getattr(ch, "value_type", None),
                },
            )

            value_str = _format_value(v)
            if value_str is None:
                continue

            matrix.setdefault(cid, {})
            matrix[cid][p.id] = value_str

    # Ряды в стабильном порядке: по имени характеристики
    def _row_sort_key(item: dict[str, Any]) -> str:
        return (item.get("name") or "").lower()

    rows: list[dict[str, Any]] = []
    for cid, meta in row_meta.items():
        values_by_product_id = matrix.get(cid, {})
        rows.append(
            {
                "characteristic_id": cid,
                "name": meta.get("name", ""),
                # ключи UUID-строки, значения - готовые строки для отображения
                "cells": {str(p.id): values_by_product_id.get(p.id, "—") for p in ordered_products},
            }
        )

    rows.sort(key=_row_sort_key)

    return templates.TemplateResponse(
        "public/catalog/compare.html",
        {
            "request": request,
            "products": ordered_products,
            "rows": rows,
        },
    )


@router.post("/compare/add/{product_id}")
async def compare_add(
    product_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    # Проверка: товар существует (и можно добавить только активный, если нужно)
    exists = await session.execute(select(Product.id).where(Product.id == product_id))
    if not exists.scalar_one_or_none():
        raise HTTPException(status_code=404)

    add_to_compare(request.session, product_id)

    back = request.headers.get("referer")
    return RedirectResponse(back or "/compare", status_code=303)


@router.post("/compare/remove/{product_id}")
async def compare_remove(product_id: uuid.UUID, request: Request):
    remove_from_compare(request.session, product_id)

    back = request.headers.get("referer")
    return RedirectResponse(back or "/compare", status_code=303)


@router.post("/compare/clear")
async def compare_clear(request: Request):
    clear_compare(request.session)
    return RedirectResponse("/compare", status_code=303)
