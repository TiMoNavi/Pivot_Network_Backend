from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend_app.db.models.onboarding import SellerOnboardingSession


class SellerOnboardingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, **kwargs) -> SellerOnboardingSession:
        onboarding_session = SellerOnboardingSession(**kwargs)
        self.session.add(onboarding_session)
        self.session.flush()
        return onboarding_session

    def get_for_seller(self, session_id, seller_user_id) -> SellerOnboardingSession | None:
        statement = select(SellerOnboardingSession).where(
            SellerOnboardingSession.id == session_id,
            SellerOnboardingSession.seller_user_id == seller_user_id,
        )
        return self.session.scalar(statement)

    def save(self, onboarding_session: SellerOnboardingSession) -> SellerOnboardingSession:
        self.session.add(onboarding_session)
        self.session.flush()
        return onboarding_session
