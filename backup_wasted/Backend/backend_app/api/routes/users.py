from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend_app.db.session import get_db_session
from backend_app.repositories.user_repository import UserRepository
from backend_app.schemas.user import UserCreate, UserRead
from backend_app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])


def get_user_service(session: Session = Depends(get_db_session)) -> UserService:
    return UserService(UserRepository(session))


@router.get("/", response_model=list[UserRead])
def list_users(service: UserService = Depends(get_user_service)) -> list[UserRead]:
    return service.list_users()


@router.post("/", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    service: UserService = Depends(get_user_service),
) -> UserRead:
    try:
        return service.create_user(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

