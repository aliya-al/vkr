from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.utils.templates import templates

from app.utils.database import get_async_session
from app.utils.security import verify_password
from app.models.user import AdminUser

router = APIRouter()

@router.get("/admin/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("admin/login.html", {"request": request, "error": None})

@router.post("/admin/login")
async def login_action(
    request: Request,
    login: str = Form(...),
    password: str = Form(...),
    session: AsyncSession = Depends(get_async_session),
):
    """ Обработка входа. Проверяет пользователя и пишет данные в сессию."""
    result = await session.execute(select(AdminUser).where(AdminUser.login == login))
    user = result.scalar_one_or_none()

    if not user or not user.is_active or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "admin/login.html",
            {"request": request, "error": "Неверный логин или пароль."},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    request.session["admin_user_id"] = str(user.id)
    request.session["admin_user_role"] = user.role

    return RedirectResponse(url="/admin/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/admin/logout")
async def logout_action(request: Request):
    request.session.clear()
    resp = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    resp.delete_cookie("session", path="/")
    return resp