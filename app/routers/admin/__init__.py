from fastapi import APIRouter

from . import auth, dashboard, managers, news
from .catalog_crud import router as catalog_router

router = APIRouter()

router.include_router(auth.router)
router.include_router(dashboard.router)
router.include_router(managers.router)
router.include_router(news.router)

router.include_router(catalog_router)
