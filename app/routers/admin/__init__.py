from fastapi import APIRouter
from . import auth, pages

router = APIRouter(prefix="/admin")

router.include_router(auth.router)
router.include_router(pages.router)
