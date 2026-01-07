# Dependency: “нет админ-сессии → 404”

from fastapi import Request, HTTPException, status

def require_admin_or_404(request: Request) -> dict:
    admin_user_id = request.session.get("admin_user_id")
    if not admin_user_id:
        # цель: не показывать существвование админки клиентам. будто маршрута нет.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    return {
        "id": admin_user_id,
        "role": request.session.get("admin_user_role"),
    }

def require_superadmin_or_404(request: Request):
    """
    Проверка админа. Менеджер получит 404.
    """
    role = request.session.get("admin_user_role")
    if role != "admin":
        # 404 чтобы не светить существование раздела
        raise HTTPException(status_code=404)