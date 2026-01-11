# app/services/compare.py
from __future__ import annotations

import uuid
from typing import Iterable

COMPARE_SESSION_KEY = "compare_product_ids"
COMPARE_LIMIT = 10  # ограничение, чтобы не раздувать таблицу

def _normalize_uuid_str(value: str) -> str | None:
    try:
        return str(uuid.UUID(str(value)))
    except Exception:
        return None


def get_compare_ids(session: dict) -> list[str]:
    """
    Инвариант: в session храним list[str] UUID, без дублей, порядок = порядок добавления.
    """
    raw = session.get(COMPARE_SESSION_KEY)
    if not isinstance(raw, list):
        return []

    out: list[str] = []
    seen: set[str] = set()

    for item in raw:
        s = _normalize_uuid_str(str(item))
        if not s:
            continue
        if s in seen:
            continue
        out.append(s)
        seen.add(s)

    return out


def set_compare_ids(session: dict, ids: Iterable[str]) -> None:
    cleaned: list[str] = []
    seen: set[str] = set()

    for x in ids:
        s = _normalize_uuid_str(str(x))
        if not s:
            continue
        if s in seen:
            continue
        cleaned.append(s)
        seen.add(s)

        if len(cleaned) >= COMPARE_LIMIT:
            break

    session[COMPARE_SESSION_KEY] = cleaned


def add_to_compare(session: dict, product_id: uuid.UUID) -> None:
    ids = get_compare_ids(session)
    pid = str(product_id)

    if pid in ids:
        return

    ids.append(pid)
    set_compare_ids(session, ids)


def remove_from_compare(session: dict, product_id: uuid.UUID) -> None:
    ids = get_compare_ids(session)
    pid = str(product_id)

    ids = [x for x in ids if x != pid]
    set_compare_ids(session, ids)


def clear_compare(session: dict) -> None:
    session[COMPARE_SESSION_KEY] = []
