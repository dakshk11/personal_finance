from datetime import UTC, datetime

from fastapi import Cookie, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings, local_test_account_password
from app.core.security import hash_password, hash_token
from app.db.session import get_db
from app.models.entities import User, UserSession


def _get_or_create_local_user(db: Session) -> User:
    settings = get_settings()
    email = settings.test_account_email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user:
        if not user.is_active:
            user.is_active = True
            db.commit()
            db.refresh(user)
        return user

    user = User(email=email, password_hash=hash_password(local_test_account_password(settings)), is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_current_user(
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias=get_settings().session_cookie_name),
) -> User:
    if not session_token:
        return _get_or_create_local_user(db)
    session = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(session_token)))
    if not session or session.expires_at <= datetime.now(UTC).replace(tzinfo=None):
        return _get_or_create_local_user(db)
    user = db.get(User, session.user_id)
    if not user or not user.is_active:
        return _get_or_create_local_user(db)
    return user
