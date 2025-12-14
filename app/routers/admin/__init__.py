from fastapi import APIRouter
from . import auth, pages
from .catalog import router as catalog_router

router = APIRouter(prefix="/admin")

router.include_router(auth.router)
router.include_router(catalog_router)
router.include_router(pages.router)
