from fastapi import APIRouter

from . import catalog, cart, checkout, compare, favorites, product

router = APIRouter()

router.include_router(catalog.router)
router.include_router(cart.router)
router.include_router(checkout.router)
router.include_router(compare.router)
router.include_router(favorites.router)
router.include_router(product.router)