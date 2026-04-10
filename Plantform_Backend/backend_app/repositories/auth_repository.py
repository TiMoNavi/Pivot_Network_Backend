from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend_app.db.models.auth_trade import AuthSessionModel, UserModel
from backend_app.storage.memory_store import AuthSessionRecord, UserRecord


class AuthRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def commit(self) -> None:
        self.session.commit()

    def get_user_by_email(self, email: str) -> UserRecord | None:
        model = self.session.scalar(select(UserModel).where(UserModel.email == email))
        if model is None:
            return None
        return self._user_record(model)

    def get_user_by_id(self, user_id: str) -> UserRecord | None:
        model = self.session.get(UserModel, user_id)
        if model is None:
            return None
        return self._user_record(model)

    def save_user(self, record: UserRecord) -> UserRecord:
        model = self.session.get(UserModel, record.id)
        if model is None:
            model = UserModel(id=record.id)
            self.session.add(model)
        model.email = record.email
        model.display_name = record.display_name
        model.password_salt = record.password_salt
        model.password_hash = record.password_hash
        model.role = record.role
        model.status = record.status
        model.created_at = self._ensure_utc_datetime(record.created_at)
        model.updated_at = self._ensure_utc_datetime(record.updated_at)
        self.session.flush()
        return self._user_record(model)

    def get_auth_session_by_token(self, token: str) -> AuthSessionRecord | None:
        model = self.session.scalar(select(AuthSessionModel).where(AuthSessionModel.token == token))
        if model is None:
            return None
        return self._session_record(model)

    def save_auth_session(self, record: AuthSessionRecord) -> AuthSessionRecord:
        model = self.session.get(AuthSessionModel, record.id)
        if model is None:
            model = AuthSessionModel(id=record.id)
            self.session.add(model)
        model.user_id = record.user_id
        model.token = record.token
        model.scope = record.scope
        model.expires_at = self._ensure_utc_datetime(record.expires_at)
        model.revoked_at = self._ensure_utc_datetime(record.revoked_at)
        model.created_at = self._ensure_utc_datetime(record.created_at)
        self.session.flush()
        return self._session_record(model)

    @staticmethod
    def _user_record(model: UserModel) -> UserRecord:
        return UserRecord(
            id=model.id,
            email=model.email,
            display_name=model.display_name,
            password_salt=model.password_salt,
            password_hash=model.password_hash,
            role=model.role,
            status=model.status,
            created_at=AuthRepository._ensure_utc_datetime(model.created_at),
            updated_at=AuthRepository._ensure_utc_datetime(model.updated_at),
        )

    @staticmethod
    def _session_record(model: AuthSessionModel) -> AuthSessionRecord:
        return AuthSessionRecord(
            id=model.id,
            user_id=model.user_id,
            token=model.token,
            scope=model.scope,
            expires_at=AuthRepository._ensure_utc_datetime(model.expires_at),
            revoked_at=AuthRepository._ensure_utc_datetime(model.revoked_at),
            created_at=AuthRepository._ensure_utc_datetime(model.created_at),
        )

    @staticmethod
    def _ensure_utc_datetime(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
