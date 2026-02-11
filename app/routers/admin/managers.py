import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import AdminUser
from app.utils.database import get_async_session
from app.utils.security import hash_password
from app.utils.templates import templates
from app.utils.deps import require_superadmin_or_404

router = APIRouter(
    dependencies=[Depends(require_superadmin_or_404) ]
)

LOGIN_MAX_LEN = 15

@router.get("/admin/managers", response_class=HTMLResponse)
async def managers_list(request: Request, session: AsyncSession = Depends(get_async_session)):
    result = await session.execute(
        select(AdminUser)
        .where(AdminUser.role == "manager")
        .order_by(AdminUser.login)
    )
    managers = result.scalars().all()
    return templates.TemplateResponse(
        "admin/managers/index.html",
        {"request": request, "managers": managers},
    )


@router.get("/admin/managers/new", response_class=HTMLResponse)
async def manager_create_page(request: Request):
    return templates.TemplateResponse(
        "admin/managers/create.html",
        {"request": request, "error": None, "login": "", "is_active": True},
    )


@router.post("/admin/managers/new", response_class=HTMLResponse)
async def manager_create(
    request: Request,
    login: str = Form(...),
    password: str = Form(...),
    is_active: bool = Form(False),
    session: AsyncSession = Depends(get_async_session),
):
    login = login.strip()

    if len(login) > LOGIN_MAX_LEN:
        return templates.TemplateResponse(
            "admin/managers/create.html",
            {"request": request, "error": "Логин должен быть не длиннее 15 символов.", "login": login,
             "is_active": is_active},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if not login:
        return templates.TemplateResponse(
            "admin/managers/create.html",
            {"request": request, "error": "Логин не может быть пустым.", "login": login, "is_active": is_active},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if not password or len(password) < 6:
        return templates.TemplateResponse(
            "admin/managers/create.html",
            {"request": request, "error": "Пароль должен быть минимум 6 символов.", "login": login, "is_active": is_active},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    existing = await session.execute(select(AdminUser).where(AdminUser.login == login))
    if existing.scalar_one_or_none():
        return templates.TemplateResponse(
            "admin/managers/create.html",
            {"request": request, "error": "Такой логин уже существует.", "login": login, "is_active": is_active},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    manager = AdminUser(
        login=login,
        password_hash=hash_password(password),
        role="manager",
        is_active=is_active,
    )
    session.add(manager)
    await session.commit()

    return RedirectResponse("/admin/managers", status_code=303)


@router.get("/admin/managers/{manager_id}/edit", response_class=HTMLResponse)
async def manager_edit_page(
    manager_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    result = await session.execute(
        select(AdminUser)
        .where(AdminUser.id == manager_id, AdminUser.role == "manager")
    )
    manager = result.scalar_one_or_none()
    if not manager:
        raise HTTPException(status_code=404)

    return templates.TemplateResponse(
        "admin/managers/edit.html",
        {"request": request, "manager": manager, "error": None},
    )


@router.post("/admin/managers/{manager_id}/edit", response_class=HTMLResponse)
async def manager_edit(
    manager_id: uuid.UUID,
    request: Request,
    login: str = Form(...),
    password: str | None = Form(None),  # если пусто — пароль не меняем
    is_active: bool = Form(False),
    session: AsyncSession = Depends(get_async_session),
):
    result = await session.execute(
        select(AdminUser)
        .where(AdminUser.id == manager_id, AdminUser.role == "manager")
    )
    manager = result.scalar_one_or_none()
    if not manager:
        raise HTTPException(status_code=404)

    login = login.strip()

    if len(login) > LOGIN_MAX_LEN:
        return templates.TemplateResponse(
            "admin/managers/edit.html",
            {"request": request, "manager": manager, "error": "Логин должен быть не длиннее 15 символов."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if not login:
        return templates.TemplateResponse(
            "admin/managers/edit.html",
            {"request": request, "manager": manager, "error": "Логин не может быть пустым."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # проверка уникальности логина, если меняем
    if login != manager.login:
        existing = await session.execute(select(AdminUser).where(AdminUser.login == login))
        if existing.scalar_one_or_none():
            return templates.TemplateResponse(
                "admin/managers/edit.html",
                {"request": request, "manager": manager, "error": "Такой логин уже существует."},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

    manager.login = login
    manager.is_active = is_active

    if password is not None and password.strip():
        if len(password.strip()) < 6:
            return templates.TemplateResponse(
                "admin/managers/edit.html",
                {"request": request, "manager": manager, "error": "Новый пароль должен быть минимум 6 символов."},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        manager.password_hash = hash_password(password.strip())

    await session.commit()
    return RedirectResponse("/admin/managers", status_code=303)


@router.post("/admin/managers/{manager_id}/delete")
async def manager_delete(manager_id: uuid.UUID, session: AsyncSession = Depends(get_async_session)):
    result = await session.execute(
        select(AdminUser)
        .where(AdminUser.id == manager_id, AdminUser.role == "manager")
    )
    manager = result.scalar_one_or_none()
    if not manager:
        raise HTTPException(status_code=404)

    await session.delete(manager)
    await session.commit()
    return RedirectResponse("/admin/managers", status_code=303)
