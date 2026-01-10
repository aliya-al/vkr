# app/routers/public/__init__.py
from fastapi import APIRouter

from . import catalog, cart, checkout

router = APIRouter()

router.include_router(catalog.router)
router.include_router(cart.router)
router.include_router(checkout.router)
