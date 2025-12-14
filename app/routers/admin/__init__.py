from fastapi import APIRouter
from . import auth, catalog, pages

router = APIRouter(prefix="/admin")

router.include_router(auth.router)
router.include_router(catalog.router)
router.include_router(pages.router)
