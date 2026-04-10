from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend_app.api.deps import get_auth_service
from backend_app.api.security import get_current_user
from backend_app.schemas.auth import AuthSessionRead, LoginRequest, RegisterRequest, UserRead
from backend_app.services.auth_service import AuthService
from backend_app.storage.memory_store import UserRecord

router = APIRouter(prefix="/auth", tags=["auth"])
bearer_scheme = HTTPBearer(auto_error=False)


@router.post("/register", response_model=AuthSessionRead, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> AuthSessionRead:
    try:
        return auth_service.register(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/login", response_model=AuthSessionRead)
def login(
    payload: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> AuthSessionRead:
    try:
        return auth_service.login(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    user: UserRecord = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> None:
    del user
    if credentials and credentials.scheme.lower() == "bearer":
        auth_service.logout(credentials.credentials)
    return None


@router.get("/me", response_model=UserRead)
def me(user: UserRecord = Depends(get_current_user)) -> UserRead:
    return UserRead(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        status=user.status,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )
