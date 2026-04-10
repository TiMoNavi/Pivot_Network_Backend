from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend_app.db.models.buyer_client import BuyerRuntimeClientSession


class BuyerRuntimeClientRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_for_runtime_session(self, runtime_session_id, buyer_user_id) -> BuyerRuntimeClientSession | None:
        statement = select(BuyerRuntimeClientSession).where(
            BuyerRuntimeClientSession.runtime_session_id == runtime_session_id,
            BuyerRuntimeClientSession.buyer_user_id == buyer_user_id,
        )
        return self.session.scalar(statement)

    def upsert(self, runtime_session_id, buyer_user_id, **kwargs) -> BuyerRuntimeClientSession:
        client_session = self.get_for_runtime_session(runtime_session_id, buyer_user_id)
        if client_session is None:
            client_session = BuyerRuntimeClientSession(
                runtime_session_id=runtime_session_id,
                buyer_user_id=buyer_user_id,
                **kwargs,
            )
            self.session.add(client_session)
            self.session.flush()
            return client_session

        for key, value in kwargs.items():
            setattr(client_session, key, value)
        self.session.add(client_session)
        self.session.flush()
        return client_session
