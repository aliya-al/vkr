from fastapi import APIRouter

from app.routers.admin import router as admin_router
from app.routers.public import router as public_router

routers = APIRouter()

# Публичная часть
routers.include_router(public_router)

# Админка
routers.include_router(admin_router)
