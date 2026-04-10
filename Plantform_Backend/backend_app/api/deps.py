from functools import lru_cache

from fastapi import Depends
from sqlalchemy.orm import Session

from backend_app.clients.adapter_client import AdapterClient
from backend_app.core.config import get_settings
from backend_app.db.session import get_db, init_database
from backend_app.repositories.auth_repository import AuthRepository
from backend_app.repositories.seller_onboarding_repository import SellerOnboardingRepository
from backend_app.repositories.trade_repository import TradeRepository
from backend_app.services.auth_service import AuthService
from backend_app.services.capability_assessment_service import CapabilityAssessmentService
from backend_app.services.file_service import FileService
from backend_app.services.node_service import NodeService
from backend_app.services.offer_commercialization_service import OfferCommercializationService
from backend_app.services.seller_onboarding_service import SellerOnboardingService
from backend_app.services.trade_service import TradeService
from backend_app.storage.memory_store import InMemoryStore


@lru_cache
def get_adapter_client() -> AdapterClient:
    settings = get_settings()
    return AdapterClient(
        base_url=settings.adapter_base_url,
        token=settings.adapter_token,
        timeout_seconds=settings.adapter_timeout_seconds,
    )


def get_node_service() -> NodeService:
    return NodeService(get_adapter_client())


def get_file_service() -> FileService:
    settings = get_settings()
    settings.download_root.mkdir(parents=True, exist_ok=True)
    return FileService(settings.download_root)


@lru_cache
def get_store() -> InMemoryStore:
    return InMemoryStore()


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    init_database()
    return AuthService(repository=AuthRepository(db))


def get_trade_service(db: Session = Depends(get_db)) -> TradeService:
    init_database()
    settings = get_settings()
    settings.download_root.mkdir(parents=True, exist_ok=True)
    return TradeService(
        None,
        download_root=settings.download_root,
        seller_onboarding_repository=SellerOnboardingRepository(db),
        trade_repository=TradeRepository(db),
    )


def get_capability_assessment_service(db: Session = Depends(get_db)) -> CapabilityAssessmentService:
    init_database()
    onboarding_repository = SellerOnboardingRepository(db)
    trade_repository = TradeRepository(db)
    commercialization_service = OfferCommercializationService(trade_repository)
    return CapabilityAssessmentService(
        onboarding_repository,
        trade_repository,
        get_adapter_client(),
        commercialization_service,
    )


def get_seller_onboarding_service(db: Session = Depends(get_db)) -> SellerOnboardingService:
    init_database()
    onboarding_repository = SellerOnboardingRepository(db)
    trade_repository = TradeRepository(db)
    commercialization_service = OfferCommercializationService(trade_repository)
    capability_assessment_service = CapabilityAssessmentService(
        onboarding_repository,
        trade_repository,
        get_adapter_client(),
        commercialization_service,
    )
    return SellerOnboardingService(
        onboarding_repository,
        get_adapter_client(),
        capability_assessment_service,
    )
