from sqlalchemy import select
from sqlalchemy.orm import Session

from backend_app.db.models.user import User


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_users(self) -> list[User]:
        statement = select(User).order_by(User.created_at.desc())
        return list(self.session.scalars(statement))

    def get_by_email(self, email: str) -> User | None:
        statement = select(User).where(User.email == email)
        return self.session.scalar(statement)

    def get_by_id(self, user_id) -> User | None:
        statement = select(User).where(User.id == user_id)
        return self.session.scalar(statement)

    def create(
        self,
        *,
        email: str,
        password_hash: str,
        display_name: str,
        role: str,
    ) -> User:
        user = User(
            email=email,
            password_hash=password_hash,
            display_name=display_name,
            role=role,
        )
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user
