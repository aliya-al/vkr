# app/services/favorites.py
from __future__ import annotations

import uuid
from typing import Iterable

FAVORITES_SESSION_KEY = "favorites"
FAVORITES_LIMIT = 50  # чтобы не раздувать cookie-сессию


def _normalize_uuid_str(value: str) -> str | None:
    try:
        return str(uuid.UUID(str(value)))
    except Exception:
        return None


def get_favorite_ids(session: dict) -> list[str]:
    """
    Инвариант: в session храним list[str] UUID, без дублей, порядок = порядок добавления.
    """
    raw = session.get(FAVORITES_SESSION_KEY)
    if not isinstance(raw, list):
        return []

    out: list[str] = []
    seen: set[str] = set()

    for item in raw:
        s = _normalize_uuid_str(str(item))
        if not s or s in seen:
            continue
        out.append(s)
        seen.add(s)

    return out


def set_favorite_ids(session: dict, ids: Iterable[str]) -> None:
    cleaned: list[str] = []
    seen: set[str] = set()

    for x in ids:
        s = _normalize_uuid_str(str(x))
        if not s or s in seen:
            continue
        cleaned.append(s)
        seen.add(s)

        if len(cleaned) >= FAVORITES_LIMIT:
            break

    session[FAVORITES_SESSION_KEY] = cleaned


def add_to_favorites(session: dict, product_id: uuid.UUID) -> None:
    ids = get_favorite_ids(session)
    pid = str(product_id)
    if pid in ids:
        return
    ids.append(pid)
    set_favorite_ids(session, ids)


def remove_from_favorites(session: dict, product_id: uuid.UUID) -> None:
    ids = get_favorite_ids(session)
    pid = str(product_id)
    ids = [x for x in ids if x != pid]
    set_favorite_ids(session, ids)


def clear_favorites(session: dict) -> None:
    session[FAVORITES_SESSION_KEY] = []
