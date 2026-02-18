                                      

from fastapi import Request, HTTPException, status


def require_admin_or_404(request: Request) -> dict:
    admin_user_id = request.session.get("admin_user_id")
    if not admin_user_id:
                                         
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    return {
        "id": admin_user_id,
        "role": request.session.get("admin_user_role"),
    }


def require_superadmin_or_404(request: Request) -> dict:
    """
    Только админ (role=admin). Менеджер и неавторизованный получат 404.
    """
    admin = require_admin_or_404(request)
    if admin.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return admin
