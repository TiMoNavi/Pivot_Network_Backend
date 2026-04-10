from __future__ import annotations

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings, get_settings
from app.errors import AdapterHTTPException

bearer_scheme = HTTPBearer(auto_error=False)


def require_adapter_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> str:
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or credentials.credentials != settings.adapter_token
    ):
        raise AdapterHTTPException(
            status_code=401,
            detail="adapter_auth_failed",
            error_code="adapter_auth_failed",
        )
    return credentials.credentials
