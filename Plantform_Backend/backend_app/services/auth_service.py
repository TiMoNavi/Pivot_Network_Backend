from __future__ import annotations

from datetime import UTC, datetime

from backend_app.core.security import (
    expires_after_hours,
    hash_password,
    new_access_token,
    new_object_id,
    new_password_salt,
)
from backend_app.repositories.auth_repository import AuthRepository
from backend_app.schemas.auth import AuthSessionRead, LoginRequest, RegisterRequest, UserRead
from backend_app.storage.memory_store import AuthSessionRecord, InMemoryStore, UserRecord


class AuthService:
    def __init__(
        self,
        store: InMemoryStore | None = None,
        *,
        repository: AuthRepository | None = None,
        token_ttl_hours: int = 12,
    ) -> None:
        self.store = store
        self.repository = repository
        self.token_ttl_hours = token_ttl_hours

    def register(self, payload: RegisterRequest) -> AuthSessionRead:
        email = str(payload.email).lower()
        if payload.role not in {"seller", "buyer", "platform_admin"}:
            raise ValueError("Unsupported role.")
        if self.repository is not None:
            existing_user = self.repository.get_user_by_email(email)
        else:
            existing_user = None if self.store is None else self.store.users_by_email.get(email)
            if existing_user is not None and self.store is not None:
                existing_user = self.store.users[existing_user]
        if existing_user is not None:
            raise ValueError("A user with this email already exists.")

        now = datetime.now(UTC)
        salt = new_password_salt()
        user = UserRecord(
            id=new_object_id("user"),
            email=email,
            display_name=payload.display_name,
            password_salt=salt,
            password_hash=hash_password(payload.password, salt),
            role=payload.role,
            status="active",
            created_at=now,
            updated_at=now,
        )
        if self.repository is not None:
            self.repository.save_user(user)
            self.repository.commit()
        elif self.store is not None:
            self.store.users[user.id] = user
            self.store.users_by_email[email] = user.id
        return self._issue_session(user)

    def login(self, payload: LoginRequest) -> AuthSessionRead:
        email = str(payload.email).lower()
        if self.repository is not None:
            user = self.repository.get_user_by_email(email)
            if user is None:
                raise ValueError("Invalid email or password.")
        else:
            user_id = None if self.store is None else self.store.users_by_email.get(email)
            if user_id is None or self.store is None:
                raise ValueError("Invalid email or password.")
            user = self.store.users[user_id]
        if user.password_hash != hash_password(payload.password, user.password_salt):
            raise ValueError("Invalid email or password.")
        if user.status != "active":
            raise ValueError("User is not active.")
        return self._issue_session(user)

    def logout(self, token: str) -> None:
        if self.repository is not None:
            session = self.repository.get_auth_session_by_token(token)
        else:
            session = None if self.store is None else self.store.auth_sessions_by_token.get(token)
        if session is None:
            return
        session.revoked_at = datetime.now(UTC)
        if self.repository is not None:
            self.repository.save_auth_session(session)
            self.repository.commit()

    def get_user_by_token(self, token: str) -> UserRecord | None:
        if self.repository is not None:
            session = self.repository.get_auth_session_by_token(token)
        else:
            session = None if self.store is None else self.store.auth_sessions_by_token.get(token)
        if session is None:
            return None
        if session.revoked_at is not None:
            return None
        if session.expires_at <= datetime.now(UTC):
            return None
        if self.repository is not None:
            return self.repository.get_user_by_id(session.user_id)
        if self.store is None:
            return None
        return self.store.users.get(session.user_id)

    def _issue_session(self, user: UserRecord) -> AuthSessionRead:
        token = new_access_token()
        session = AuthSessionRecord(
            id=new_object_id("session"),
            user_id=user.id,
            token=token,
            scope="api_access",
            expires_at=expires_after_hours(self.token_ttl_hours),
            revoked_at=None,
            created_at=datetime.now(UTC),
        )
        if self.repository is not None:
            self.repository.save_auth_session(session)
            self.repository.commit()
        elif self.store is not None:
            self.store.auth_sessions_by_token[token] = session
        return AuthSessionRead(
            access_token=token,
            expires_at=session.expires_at,
            user=self._user_read(user),
        )

    @staticmethod
    def _user_read(user: UserRecord) -> UserRead:
        return UserRead(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=user.role,
            status=user.status,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )
