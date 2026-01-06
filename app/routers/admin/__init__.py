from fastapi import APIRouter

from . import auth, brands, categories, dashboard, products

router = APIRouter(prefix="/admin")

router.include_router(auth.router)
router.include_router(dashboard.router)
router.include_router(categories.router)
router.include_router(brands.router)
router.include_router(products.router)
