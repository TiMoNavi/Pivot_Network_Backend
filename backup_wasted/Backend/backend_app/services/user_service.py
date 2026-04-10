from pwdlib import PasswordHash

from backend_app.repositories.user_repository import UserRepository
from backend_app.schemas.user import UserCreate

password_hasher = PasswordHash.recommended()


class UserService:
    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository

    def list_users(self):
        return self.repository.list_users()

    def create_user(self, payload: UserCreate):
        existing_user = self.repository.get_by_email(str(payload.email))
        if existing_user is not None:
            raise ValueError("A user with this email already exists.")

        return self.repository.create(
            email=str(payload.email),
            password_hash=password_hasher.hash(payload.password),
            display_name=payload.display_name,
            role=payload.role,
        )

