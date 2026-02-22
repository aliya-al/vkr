from __future__ import annotations

from pathlib import Path

UPLOADS_ROOT_IMG = Path("app/static/img/uploads")
UPLOADS_NEWS_DIR = UPLOADS_ROOT_IMG / "news"
UPLOADS_PRODUCTS_DIR = UPLOADS_ROOT_IMG / "products"
UPLOADS_CATEGORIES_DIR = Path("app/static/uploads/categories")

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_STATIC_ROOT = _PROJECT_ROOT / "app" / "static"


def _is_external(url: str) -> bool:
    return url.startswith(("http://", "https://", "//"))


def _static_url_to_file(url: str) -> Path | None:
    if not url.startswith("/static/"):
        return None
    rel = url.removeprefix("/static/")
    if not rel:
        return None
    return _STATIC_ROOT / rel


def _url_exists(url: str) -> bool:
    fpath = _static_url_to_file(url)
    return bool(fpath and fpath.is_file())


def _pick_existing(candidates: list[str]) -> str | None:
    seen: set[str] = set()
    ordered: list[str] = []
    for c in candidates:
        if not c or c in seen:
            continue
        seen.add(c)
        ordered.append(c)

    for c in ordered:
        if _url_exists(c):
            return c
    return ordered[0] if ordered else None


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
    elif p.startswith("static/"):
        candidates.append("/" + p)
    else:
        raw = p.lstrip("/")
        if raw.startswith("img/uploads/products/"):
            candidates.append("/static/" + raw)
        elif raw.startswith("uploads/products/"):
            candidates.append("/static/" + raw)
            candidates.append("/static/img/uploads/products/" + raw.removeprefix("uploads/products/"))
        elif raw.startswith("products/"):
            tail = raw.removeprefix("products/")
            candidates.append("/static/uploads/products/" + tail)
            candidates.append("/static/img/uploads/products/" + tail)
        else:
            candidates.append("/static/uploads/products/" + raw)
            candidates.append("/static/img/uploads/products/" + raw)

    if candidates:
        raw0 = candidates[0].removeprefix("/static/")
        if raw0.startswith("img/uploads/products/"):
            tail = raw0.removeprefix("img/uploads/products/")
            candidates.append("/static/uploads/products/" + tail)
        elif raw0.startswith("uploads/products/"):
            tail = raw0.removeprefix("uploads/products/")
            candidates.append("/static/img/uploads/products/" + tail)

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
    elif p.startswith("static/"):
        candidates.append("/" + p)
    else:
        raw = p.lstrip("/")
        if raw.startswith("img/uploads/news/"):
            candidates.append("/static/" + raw)
        elif raw.startswith("uploads/news/"):
            candidates.append("/static/" + raw)
            candidates.append("/static/img/uploads/news/" + raw.removeprefix("uploads/news/"))
        elif raw.startswith("news/"):
            tail = raw.removeprefix("news/")
            candidates.append("/static/uploads/news/" + tail)
            candidates.append("/static/img/uploads/news/" + tail)
        else:
            candidates.append("/static/uploads/news/" + raw)
            candidates.append("/static/img/uploads/news/" + raw)

    if candidates:
        raw0 = candidates[0].removeprefix("/static/")
        if raw0.startswith("img/uploads/news/"):
            tail = raw0.removeprefix("img/uploads/news/")
            candidates.append("/static/uploads/news/" + tail)
        elif raw0.startswith("uploads/news/"):
            tail = raw0.removeprefix("uploads/news/")
            candidates.append("/static/img/uploads/news/" + tail)

    return _pick_existing(candidates)
