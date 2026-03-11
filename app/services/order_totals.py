
from __future__ import annotations

import uuid
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order_item import OrderItem


async def fetch_orders_weight_volume(
    session: AsyncSession,
    order_ids: Iterable[uuid.UUID],
) -> dict[uuid.UUID, dict[str, float]]:
    """Считает итоговый вес/объём по нескольким заявкам одним запросом.

    Используем поля-снапшоты из ``OrderItem``: если товар уже удалён из каталога,
    значения ``weight_kg``/``volume_m3`` всё равно должны корректно учитываться
    по сохранённому составу заявки.
    """
    ids = list(order_ids)
    if not ids:
        return {}

    stmt = (
        select(
            OrderItem.order_id.label("order_id"),
            func.coalesce(func.sum(OrderItem.quantity * OrderItem.weight_kg), 0.0).label("weight_kg"),
            func.coalesce(func.sum(OrderItem.quantity * OrderItem.volume_m3), 0.0).label("volume_m3"),
        )
        .where(OrderItem.order_id.in_(ids))
        .group_by(OrderItem.order_id)
    )

    res = await session.execute(stmt)

    out: dict[uuid.UUID, dict[str, float]] = {}
    for order_id, weight_kg, volume_m3 in res.all():
        out[order_id] = {
            "weight_kg": float(weight_kg or 0.0),
            "volume_m3": float(volume_m3 or 0.0),
        }

                                            
    for oid in ids:
        out.setdefault(oid, {"weight_kg": 0.0, "volume_m3": 0.0})

    return out
