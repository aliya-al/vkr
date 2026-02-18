from fastapi import APIRouter, Depends

from app.utils.deps import require_admin_or_404
from . import brands, categories, products, attributes, requests, products_import

router = APIRouter(dependencies=[Depends(require_admin_or_404)])

router.include_router(categories.router)
router.include_router(brands.router)
router.include_router(products.router)
router.include_router(attributes.router)
router.include_router(requests.router)
router.include_router(products_import.router)
