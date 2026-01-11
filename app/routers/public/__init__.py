# app/routers/public/__init__.py
from fastapi import APIRouter

from . import catalog, cart, checkout, compare, favorites

router = APIRouter()

router.include_router(catalog.router)
router.include_router(cart.router)
router.include_router(checkout.router)
router.include_router(compare.router)
router.include_router(favorites.router)