from fastapi import APIRouter
from app.routers.admin import router as admin_router

routers = APIRouter()
routers.include_router(admin_router)
