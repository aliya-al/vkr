from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from app.utils.templates import templates
from app.utils.deps import require_admin_or_404

router = APIRouter()

@router.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_home(request: Request, admin=Depends(require_admin_or_404)):
    return templates.TemplateResponse("admin/dashboard.html",
                                      {"request": request, "admin": admin})
