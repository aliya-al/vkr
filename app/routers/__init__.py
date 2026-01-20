from fastapi import APIRouter

from . import home
from app.routers.admin import router as admin_router
from app.routers.public import router as public_router

routers = APIRouter()

routers.include_router(home.router)
routers.include_router(public_router)
routers.include_router(admin_router)
