from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from app.utils.templates import templates
from app.routers.admin.deps import require_admin_or_404

router = APIRouter()


@router.get("/dashboard", response_class=HTMLResponse)
async def admin_home(request: Request, admin=Depends(require_admin_or_404)):
    return templates.TemplateResponse("admin/home.html",
                                      {"request": request, "admin": admin})
