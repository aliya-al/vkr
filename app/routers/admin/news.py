import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.news import News
from app.utils.database import get_async_session
from app.utils.deps import require_admin_or_404
from app.utils.templates import templates

router = APIRouter(dependencies=[Depends(require_admin_or_404)])

_UPLOAD_DIR = Path("app/static/img/uploads/news")
_WEB_PREFIX = "/static/img/uploads/news"


def _safe_ext(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return ext
    return ""


async def _save_image(file: UploadFile) -> str:
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    ext = _safe_ext(file.filename or "")
    name = f"{uuid.uuid4().hex}{ext}"
    dst = _UPLOAD_DIR / name

    content = await file.read()
    dst.write_bytes(content)

    return f"{_WEB_PREFIX}/{name}"

def _delete_image_if_local(web_path: str | None) -> None:
    if not web_path:
        return
    if not web_path.startswith(_WEB_PREFIX + "/"):
        return
    filename = web_path.removeprefix(_WEB_PREFIX + "/")
    fpath = _UPLOAD_DIR / filename
    try:
        if fpath.exists():
            fpath.unlink()
    except OSError:
        pass


@router.get("/admin/news", response_class=HTMLResponse)
async def news_list(request: Request, session: AsyncSession = Depends(get_async_session)):
    result = await session.execute(select(News).order_by(News.created_at.desc()))
    items = result.scalars().all()
    return templates.TemplateResponse(
        "admin/news/index.html",
        {"request": request, "news": items},
    )

@router.get("/admin/news/new", response_class=HTMLResponse)
async def news_create_page(request: Request):
    return templates.TemplateResponse(
        "admin/news/create.html",
        {"request": request, "error": None},
    )

@router.post("/admin/news/new")
async def news_create(
    request: Request,
    title: str = Form(...),
    description: str = Form(...),
    image: UploadFile | None = File(None),
    session: AsyncSession = Depends(get_async_session),
):
    title = title.strip()
    description = description.strip()

    if not title or not description:
        return templates.TemplateResponse(
            "admin/news/create.html",
            {"request": request, "error": "Название и описание обязательны."},
            status_code=400,
        )

    image_path = None
    if image and image.filename:
        image_path = await _save_image(image)

    item = News(title=title, description=description, image_path=image_path)
    session.add(item)
    await session.commit()

    return RedirectResponse("/admin/news", status_code=303)


@router.get("/admin/news/{news_id}/edit", response_class=HTMLResponse)
async def news_edit_page(
    news_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    result = await session.execute(select(News).where(News.id == news_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404)

    return templates.TemplateResponse(
        "admin/news/edit.html",
        {"request": request, "news": item, "error": None},
    )


@router.post("/admin/news/{news_id}/edit")
async def news_edit(
    news_id: uuid.UUID,
    request: Request,
    title: str = Form(...),
    description: str = Form(...),
    image: UploadFile | None = File(None),
    remove_image: bool = Form(False),
    session: AsyncSession = Depends(get_async_session),
):
    result = await session.execute(select(News).where(News.id == news_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404)

    title = title.strip()
    description = description.strip()
    if not title or not description:
        return templates.TemplateResponse(
            "admin/news/edit.html",
            {"request": request, "news": item, "error": "Название и описание обязательны."},
            status_code=400,
        )

    item.title = title
    item.description = description

    # удалить фото по чекбоксу
    if remove_image and item.image_path:
        _delete_image_if_local(item.image_path)
        item.image_path = None

    # заменить фото, если загрузили новое
    if image and image.filename:
        _delete_image_if_local(item.image_path)
        item.image_path = await _save_image(image)

    await session.commit()
    return RedirectResponse("/admin/news", status_code=303)


@router.post("/admin/news/{news_id}/delete")
async def news_delete(news_id: uuid.UUID, session: AsyncSession = Depends(get_async_session)):
    result = await session.execute(select(News).where(News.id == news_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404)

    _delete_image_if_local(item.image_path)

    await session.delete(item)
    await session.commit()

    return RedirectResponse("/admin/news", status_code=303)
