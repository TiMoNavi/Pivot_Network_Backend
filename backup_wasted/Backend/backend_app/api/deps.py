from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend_app.clients.adapter.client import AdapterClient
from backend_app.core.config import get_settings
from backend_app.db.session import get_db_session
from backend_app.services.auth_service import AuthService

bearer_scheme = HTTPBearer(auto_error=False)


def get_adapter_client() -> AdapterClient:
    settings = get_settings()
    return AdapterClient(
        base_url=settings.adapter_base_url,
        token=settings.adapter_token,
        timeout_seconds=settings.adapter_timeout_seconds,
    )


def get_auth_service(session: Session = Depends(get_db_session)) -> AuthService:
    return AuthService(session)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    auth_service: AuthService = Depends(get_auth_service),
):
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")
    user = auth_service.get_user_by_token(credentials.credentials)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token.")
    return user


def require_roles(*roles: str):
    def _require_role(user=Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied.")
        return user

    return _require_role
