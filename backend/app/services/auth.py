from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.identity import NodeRegistrationToken, SellerProfile, SessionToken, User
from app.models.platform import BuyerWallet


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 390000)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    salt, stored_digest = password_hash.split("$", maxsplit=1)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 390000)
    return hmac.compare_digest(digest.hex(), stored_digest)


def create_user(db: Session, email: str, password: str, display_name: str | None) -> User:
    user = User(email=email.lower().strip(), password_hash=hash_password(password), display_name=display_name)
    user.seller_profile = SellerProfile()
    user.buyer_wallet = BuyerWallet(balance_cny_credits=settings.DEFAULT_TEST_BALANCE_CNY_CREDITS)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_user_by_email(db: Session, email: str) -> User | None:
    statement = select(User).where(User.email == email.lower().strip())
    return db.scalar(statement)


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = get_user_by_email(db, email)
    if user is None:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def issue_session_token(db: Session, user: User, expires_hours: int = 24) -> SessionToken:
    token = SessionToken(
        user_id=user.id,
        token=secrets.token_urlsafe(32),
        expires_at=utcnow() + timedelta(hours=expires_hours),
    )
    db.add(token)
    db.commit()
    db.refresh(token)
    return token


def issue_node_registration_token(
    db: Session, user: User, label: str | None, expires_hours: int
) -> NodeRegistrationToken:
    token = NodeRegistrationToken(
        user_id=user.id,
        token=secrets.token_urlsafe(48),
        label=label,
        expires_at=utcnow() + timedelta(hours=expires_hours),
    )
    db.add(token)
    db.commit()
    db.refresh(token)
    return token


def get_user_from_session_token(db: Session, raw_token: str) -> User | None:
    statement = select(SessionToken).where(SessionToken.token == raw_token, SessionToken.revoked.is_(False))
    session_token = db.scalar(statement)
    expires_at = _coerce_utc(session_token.expires_at) if session_token is not None else None
    if session_token is None or expires_at is None or expires_at < utcnow():
        return None
    return session_token.user


def get_node_registration_token(db: Session, raw_token: str) -> NodeRegistrationToken | None:
    statement = select(NodeRegistrationToken).where(
        NodeRegistrationToken.token == raw_token,
        NodeRegistrationToken.revoked.is_(False),
    )
    node_token = db.scalar(statement)
    expires_at = _coerce_utc(node_token.expires_at) if node_token is not None else None
    if node_token is None or expires_at is None or expires_at < utcnow():
        return None
    return node_token
