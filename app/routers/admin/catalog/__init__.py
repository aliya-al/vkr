from fastapi import APIRouter, Depends

from app.routers.admin.deps import require_admin_or_404
from . import brands, categories, products

router = APIRouter(
    prefix="/catalog",
    dependencies=[Depends(require_admin_or_404)],
)

router.include_router(categories.router)
router.include_router(brands.router)
router.include_router(products.router)
