from __future__ import annotations

from sqlalchemy.orm import Session

from backend_app.core.config import get_settings
from backend_app.core.security import expires_after, generate_session_token, hash_password, hash_token, verify_password
from backend_app.db.models.identity import BuyerProfile, SellerProfile
from backend_app.repositories.session_token_repository import SessionTokenRepository
from backend_app.repositories.user_repository import UserRepository
from backend_app.schemas.auth import AuthSessionRead, LoginRequest, RegisterRequest
from backend_app.schemas.user import UserRead


class AuthService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.user_repository = UserRepository(session)
        self.session_token_repository = SessionTokenRepository(session)
        self.settings = get_settings()

    def register(self, payload: RegisterRequest) -> AuthSessionRead:
        if payload.role not in {"seller", "buyer", "platform_admin"}:
            raise ValueError("Unsupported role.")
        existing = self.user_repository.get_by_email(str(payload.email))
        if existing is not None:
            raise ValueError("A user with this email already exists.")

        user = self.user_repository.create(
            email=str(payload.email),
            password_hash=hash_password(payload.password),
            display_name=payload.display_name,
            role=payload.role,
        )

        if payload.role == "seller":
            self.session.add(
                SellerProfile(user_id=user.id, display_name=payload.display_name, status="active")
            )
        elif payload.role == "buyer":
            self.session.add(
                BuyerProfile(user_id=user.id, display_name=payload.display_name, status="active")
            )
        self.session.commit()

        return self._issue_session(user)

    def login(self, payload: LoginRequest) -> AuthSessionRead:
        user = self.user_repository.get_by_email(str(payload.email))
        if user is None or not verify_password(payload.password, user.password_hash):
            raise ValueError("Invalid email or password.")
        if user.status != "active":
            raise ValueError("User is not active.")
        return self._issue_session(user)

    def logout(self, raw_token: str) -> None:
        token = self.session_token_repository.get_active_by_hash(hash_token(raw_token))
        if token is None:
            return
        self.session_token_repository.revoke(token)

    def get_user_by_token(self, raw_token: str):
        token = self.session_token_repository.get_active_by_hash(hash_token(raw_token))
        if token is None:
            return None
        return self.user_repository.get_by_id(token.user_id)

    def _issue_session(self, user) -> AuthSessionRead:
        raw_token = generate_session_token()
        expires_at = expires_after(self.settings.session_token_ttl_hours)
        self.session_token_repository.create(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            scope="api_access",
            expires_at=expires_at,
        )
        return AuthSessionRead(
            access_token=raw_token,
            expires_at=expires_at,
            user=UserRead.model_validate(user),
        )
