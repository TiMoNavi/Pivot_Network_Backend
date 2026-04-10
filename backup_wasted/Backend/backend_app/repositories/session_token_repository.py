from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend_app.db.models.identity import SessionToken


class SessionTokenRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        user_id,
        token_hash: str,
        scope: str,
        expires_at: datetime,
    ) -> SessionToken:
        token = SessionToken(
            user_id=user_id,
            token_hash=token_hash,
            scope=scope,
            expires_at=expires_at,
        )
        self.session.add(token)
        self.session.commit()
        self.session.refresh(token)
        return token

    def get_active_by_hash(self, token_hash: str) -> SessionToken | None:
        statement = select(SessionToken).where(
            SessionToken.token_hash == token_hash,
            SessionToken.revoked_at.is_(None),
            SessionToken.expires_at > datetime.now(UTC),
        )
        return self.session.scalar(statement)

    def revoke(self, token: SessionToken) -> SessionToken:
        token.revoked_at = datetime.now(UTC)
        self.session.add(token)
        self.session.commit()
        self.session.refresh(token)
        return token
