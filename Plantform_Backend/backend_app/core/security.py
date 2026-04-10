from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta


PASSWORD_ITERATIONS = 120_000


def hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_ITERATIONS,
    ).hex()


def new_password_salt() -> str:
    return secrets.token_hex(16)


def new_access_token() -> str:
    return secrets.token_urlsafe(32)


def new_object_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


def expires_after_hours(hours: int) -> datetime:
    return datetime.now(UTC) + timedelta(hours=hours)
