from __future__ import annotations

from pathlib import Path

UPLOADS_ROOT = Path("app/static/uploads")
UPLOADS_ROOT_IMG = Path("app/static/img/uploads")

UPLOADS_NEWS_DIR = UPLOADS_ROOT / "news"
UPLOADS_PRODUCTS_DIR = UPLOADS_ROOT / "products"
UPLOADS_CATEGORIES_DIR = UPLOADS_ROOT / "categories"

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_STATIC_ROOT = _PROJECT_ROOT / "app" / "static"


def _is_external(url: str) -> bool:
    return url.startswith(("http://", "https://", "//"))


def _static_url_to_file(url: str) -> Path | None:
    if not url.startswith("/static/"):
        return None
    rel = url.removeprefix("/static/")
    return (_STATIC_ROOT / rel) if rel else None


def _url_exists(url: str) -> bool:
    fpath = _static_url_to_file(url)
    return bool(fpath and fpath.is_file())


def _pick_existing(candidates: list[str]) -> str | None:
    uniq: list[str] = []
    seen: set[str] = set()
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            uniq.append(c)

    for c in uniq:
        if _url_exists(c):
            return c
    return uniq[0] if uniq else None


def normalize_product_media_path(path: str | None) -> str | None:
    if not path:
        return None
    p = path.strip()
    if not p:
        return None
    if _is_external(p):
        return p

    candidates: list[str] = []
    if p.startswith("/static/"):
        candidates.append(p)
        raw = p.removeprefix("/static/")
        if raw.startswith("img/uploads/products/"):
            tail = raw.removeprefix("img/uploads/products/")
            candidates.append("/static/uploads/products/" + tail)
        elif raw.startswith("uploads/products/"):
            tail = raw.removeprefix("uploads/products/")
            candidates.append("/static/img/uploads/products/" + tail)
    elif p.startswith("static/"):
        normalized = "/" + p
        candidates.append(normalized)
        raw = normalized.removeprefix("/static/")
        if raw.startswith("img/uploads/products/"):
            tail = raw.removeprefix("img/uploads/products/")
            candidates.append("/static/uploads/products/" + tail)
        elif raw.startswith("uploads/products/"):
            tail = raw.removeprefix("uploads/products/")
            candidates.append("/static/img/uploads/products/" + tail)
    else:
        raw = p.lstrip("/")
        if raw.startswith("uploads/products/"):
            tail = raw.removeprefix("uploads/products/")
            candidates.append("/static/uploads/products/" + tail)
            candidates.append("/static/img/uploads/products/" + tail)
        elif raw.startswith("img/uploads/products/"):
            tail = raw.removeprefix("img/uploads/products/")
            candidates.append("/static/uploads/products/" + tail)
            candidates.append("/static/img/uploads/products/" + tail)
        elif raw.startswith("products/"):
            tail = raw.removeprefix("products/")
            candidates.append("/static/uploads/products/" + tail)
            candidates.append("/static/img/uploads/products/" + tail)
        else:
            candidates.append("/static/uploads/products/" + raw)
            candidates.append("/static/img/uploads/products/" + raw)

    return _pick_existing(candidates)


def normalize_news_media_path(path: str | None) -> str | None:
    if not path:
        return None
    p = path.strip()
    if not p:
        return None
    if _is_external(p):
        return p

    candidates: list[str] = []
    if p.startswith("/static/"):
        candidates.append(p)
        raw = p.removeprefix("/static/")
        if raw.startswith("img/uploads/news/"):
            tail = raw.removeprefix("img/uploads/news/")
            candidates.append("/static/uploads/news/" + tail)
        elif raw.startswith("uploads/news/"):
            tail = raw.removeprefix("uploads/news/")
            candidates.append("/static/img/uploads/news/" + tail)
    elif p.startswith("static/"):
        normalized = "/" + p
        candidates.append(normalized)
        raw = normalized.removeprefix("/static/")
        if raw.startswith("img/uploads/news/"):
            tail = raw.removeprefix("img/uploads/news/")
            candidates.append("/static/uploads/news/" + tail)
        elif raw.startswith("uploads/news/"):
            tail = raw.removeprefix("uploads/news/")
            candidates.append("/static/img/uploads/news/" + tail)
    else:
        raw = p.lstrip("/")
        if raw.startswith("uploads/news/"):
            tail = raw.removeprefix("uploads/news/")
            candidates.append("/static/uploads/news/" + tail)
            candidates.append("/static/img/uploads/news/" + tail)
        elif raw.startswith("img/uploads/news/"):
            tail = raw.removeprefix("img/uploads/news/")
            candidates.append("/static/uploads/news/" + tail)
            candidates.append("/static/img/uploads/news/" + tail)
        elif raw.startswith("news/"):
            tail = raw.removeprefix("news/")
            candidates.append("/static/uploads/news/" + tail)
            candidates.append("/static/img/uploads/news/" + tail)
        else:
            candidates.append("/static/uploads/news/" + raw)
            candidates.append("/static/img/uploads/news/" + raw)

    return _pick_existing(candidates)
