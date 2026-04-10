from fastapi import APIRouter

from backend_app.api.routes import adapter_proxy, auth, buyer, health, platform, seller, users

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(adapter_proxy.router)
api_router.include_router(buyer.router)
api_router.include_router(platform.router)
api_router.include_router(seller.router)
api_router.include_router(users.router)
