from fastapi import APIRouter

from . import catalog, cart, checkout, compare, favorites, product, search

router = APIRouter()

router.include_router(catalog.router)
router.include_router(cart.router)
router.include_router(checkout.router)
router.include_router(compare.router)
router.include_router(favorites.router)
router.include_router(product.router)
router.include_router(search.router)