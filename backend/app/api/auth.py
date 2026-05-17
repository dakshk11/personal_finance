from datetime import UTC, datetime

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.core.rate_limit import auth_rate_limiter
from app.core.security import create_session, hash_password, hash_token, password_meets_policy, verify_password
from app.db.session import get_db
from app.models.entities import User, UserSession
from app.schemas.common import AuthRequest, UserOut


router = APIRouter(prefix="/auth", tags=["auth"])


def _rate_key(request: Request, email: str) -> str:
    host = request.client.host if request.client else "unknown"
    return f"{host}:{email.lower()}"


def _set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.session_cookie_name,
        token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        max_age=settings.session_ttl_seconds,
        path="/",
    )


@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def signup(payload: AuthRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> User:
    email = payload.email.strip().lower()
    if not auth_rate_limiter.allow(_rate_key(request, email)):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many auth attempts")
    if not password_meets_policy(payload.password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password must be at least 12 characters and include letters and numbers")
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    user = User(email=email, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_session(db, user.id)
    _set_session_cookie(response, token)
    return user


@router.post("/login", response_model=UserOut)
def login(payload: AuthRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> User:
    email = payload.email.strip().lower()
    if not auth_rate_limiter.allow(_rate_key(request, email)):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many auth attempts")
    user = db.scalar(select(User).where(User.email == email))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    token = create_session(db, user.id)
    _set_session_cookie(response, token)
    return user


@router.post("/logout")
def logout(
    response: Response,
    session_token: str | None = Cookie(default=None, alias=get_settings().session_cookie_name),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    settings = get_settings()
    if session_token:
        session = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(session_token)))
        if session:
            db.delete(session)
            db.commit()
    response.delete_cookie(settings.session_cookie_name, path="/")
    return {"status": "ok"}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.delete("/sessions/expired")
def prune_expired_sessions(db: Session = Depends(get_db)) -> dict[str, int]:
    sessions = db.scalars(select(UserSession).where(UserSession.expires_at <= datetime.now(UTC).replace(tzinfo=None))).all()
    count = len(sessions)
    for session in sessions:
        db.delete(session)
    db.commit()
    return {"deleted": count}
