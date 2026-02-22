from __future__ import annotations

from pathlib import Path

UPLOADS_ROOT_DIR = Path("app/static/uploads")
UPLOADS_WEB_PREFIX = "/static/uploads"
LEGACY_UPLOADS_WEB_PREFIX = "/static/img/uploads"


def upload_dir(*parts: str) -> Path:
    target = UPLOADS_ROOT_DIR.joinpath(*parts)
    target.mkdir(parents=True, exist_ok=True)
    return target


def upload_web_prefix(*parts: str) -> str:
    cleaned = [p.strip("/") for p in parts if p and p.strip("/")]
    if not cleaned:
        return UPLOADS_WEB_PREFIX
    return f"{UPLOADS_WEB_PREFIX}/{'/'.join(cleaned)}"


def upload_web_path(*parts: str) -> str:
    cleaned = [p.strip("/") for p in parts if p is not None and p.strip("/")]
    return upload_web_prefix(*cleaned)


def normalize_upload_web_path(path: str | None) -> str | None:
    if not path:
        return None

    p = path.strip()
    if not p:
        return None

    if p.startswith(("http://", "https://", "//")):
        return p

    if p.startswith(LEGACY_UPLOADS_WEB_PREFIX + "/"):
        suffix = p.removeprefix(LEGACY_UPLOADS_WEB_PREFIX + "/")
        return upload_web_path(suffix)

    if p.startswith("/static/"):
        return p

    if p.startswith("static/"):
        p = "/" + p
        if p.startswith(LEGACY_UPLOADS_WEB_PREFIX + "/"):
            suffix = p.removeprefix(LEGACY_UPLOADS_WEB_PREFIX + "/")
            return upload_web_path(suffix)
        return p

    p = p.lstrip("/")
    if p.startswith("img/uploads/"):
        return upload_web_path(p.removeprefix("img/uploads/"))
    if p.startswith("uploads/"):
        return upload_web_path(p.removeprefix("uploads/"))

    return p


def normalize_product_media_path(path: str | None) -> str | None:
    p = normalize_upload_web_path(path)
    if not p:
        return None
    if p.startswith(("http://", "https://", "//", "/static/")):
        if p.startswith("/static/uploads/"):
            if p.startswith("/static/uploads/products/"):
                return p
            return upload_web_path("products", p.removeprefix("/static/uploads/"))
        return p

    p = p.removeprefix("products/")
    return upload_web_path("products", p)
