import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.news import News
from app.utils.uploads import UPLOADS_NEWS_DIR, normalize_news_media_path
from app.utils.database import get_async_session
from app.utils.deps import require_admin_or_404
from app.utils.templates import templates

router = APIRouter(dependencies=[Depends(require_admin_or_404)])

_UPLOAD_DIR = UPLOADS_NEWS_DIR
_WEB_PREFIX = "/static/img/uploads/news"

NEWS_TITLE_MAX_LEN = 30

def _safe_ext(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return ext
    return ""


async def _save_image(file: UploadFile) -> str:
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    ext = _safe_ext(file.filename or "")
    if not ext:
        raise ValueError("Недопустимый формат изображения. Разрешены: jpg, jpeg, png, webp, gif.")

    name = f"{uuid.uuid4().hex}{ext}"
    dst = _UPLOAD_DIR / name

    content = await file.read()
    if not content:
        raise ValueError("Файл изображения пустой.")
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
    for item in items:
        item.image_path = normalize_news_media_path(item.image_path)
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
    image: UploadFile | None = File(None),
    session: AsyncSession = Depends(get_async_session),
):
    title = title.strip()
    if len(title) > NEWS_TITLE_MAX_LEN:
        return templates.TemplateResponse(
            "admin/news/create.html",
            {"request": request, "error": f"Название должно быть не длиннее {NEWS_TITLE_MAX_LEN} символов.", "form_data": {"title": title}},
            status_code=400,
        )

    if not title:
        return templates.TemplateResponse(
            "admin/news/create.html",
            {"request": request, "error": "Название обязательно.", "form_data": {"title": title}},
            status_code=400,
        )

                      
    if not image or not image.filename:
        return templates.TemplateResponse(
            "admin/news/create.html",
            {"request": request, "error": "Фото обязательно. Загрузите изображение.", "form_data": {"title": title}},
            status_code=400,
        )

    try:
        image_path = await _save_image(image)
    except ValueError as e:
        return templates.TemplateResponse(
            "admin/news/create.html",
            {"request": request, "error": str(e), "form_data": {"title": title}},
            status_code=400,
        )

    item = News(title=title, image_path=image_path)
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

    item.image_path = normalize_news_media_path(item.image_path)

    return templates.TemplateResponse(
        "admin/news/edit.html",
        {"request": request, "news": item, "error": None},
    )


@router.post("/admin/news/{news_id}/edit")
async def news_edit(
    news_id: uuid.UUID,
    request: Request,
    title: str = Form(...),
    image: UploadFile | None = File(None),
    remove_image: bool = Form(False),
    session: AsyncSession = Depends(get_async_session),
):
    result = await session.execute(select(News).where(News.id == news_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404)

    title = title.strip()
    if len(title) > NEWS_TITLE_MAX_LEN:
        return templates.TemplateResponse(
            "admin/news/edit.html",
            {"request": request, "news": item,
             "error": f"Название должно быть не длиннее {NEWS_TITLE_MAX_LEN} символов."},
            status_code=400,
        )

    if not title:
        return templates.TemplateResponse(
            "admin/news/edit.html",
            {"request": request, "news": item, "error": "Название обязательно."},
            status_code=400,
        )

    has_new_image = bool(image and image.filename)

                                                                                   
    if remove_image and not has_new_image:
        msg = "Фото обязательно. Если удаляете текущее фото — загрузите новое."
                                                      
        if not item.image_path:
            msg = "Фото обязательно. Сейчас фото нет — загрузите изображение."
        return templates.TemplateResponse(
            "admin/news/edit.html",
            {"request": request, "news": item, "error": msg},
            status_code=400,
        )

                                                                                              
    if not item.image_path and not has_new_image:
        return templates.TemplateResponse(
            "admin/news/edit.html",
            {"request": request, "news": item, "error": "Фото обязательно. Загрузите изображение."},
            status_code=400,
        )

                         
    item.title = title

                                                              
    if has_new_image:
        try:
            new_path = await _save_image(image)  # type: ignore[arg-type]
        except ValueError as e:
            return templates.TemplateResponse(
                "admin/news/edit.html",
                {"request": request, "news": item, "error": str(e)},
                status_code=400,
            )

                                              
        _delete_image_if_local(item.image_path)
        item.image_path = new_path

                                                                               
                                       

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
