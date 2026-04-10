from fastapi import APIRouter

from backend_app.api.v1.auth import router as auth_router
from backend_app.api.v1.files import router as files_router
from backend_app.api.v1.health import router as health_router
from backend_app.api.v1.nodes import router as nodes_router
from backend_app.api.v1.seller_capability_assessments import router as seller_capability_assessments_router
from backend_app.api.v1.seller_onboarding import router as seller_onboarding_router
from backend_app.api.v1.trade import router as trade_router

api_v1_router = APIRouter()
api_v1_router.include_router(auth_router)
api_v1_router.include_router(health_router)
api_v1_router.include_router(files_router)
api_v1_router.include_router(nodes_router)
api_v1_router.include_router(seller_capability_assessments_router)
api_v1_router.include_router(seller_onboarding_router)
api_v1_router.include_router(trade_router)
