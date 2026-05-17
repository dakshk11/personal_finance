from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import UserSession


password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left, right)


def create_session(db: Session, user_id: int) -> str:
    settings = get_settings()
    token = secrets.token_urlsafe(48)
    db.add(
        UserSession(
            user_id=user_id,
            token_hash=hash_token(token),
            expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=settings.session_ttl_seconds),
        )
    )
    db.commit()
    return token


def password_meets_policy(password: str) -> bool:
    if len(password) < 12:
        return False
    return any(char.isdigit() for char in password) and any(char.isalpha() for char in password)
