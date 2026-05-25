from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings, local_test_account_password
from app.core.security import hash_password
from app.models.entities import User


def seed_local_test_account(db: Session) -> None:
    settings = get_settings()
    if not settings.seed_test_account:
        return

    email = settings.test_account_email.strip().lower()
    password = local_test_account_password(settings)
    user = db.scalar(select(User).where(User.email == email))
    if user:
        user.password_hash = hash_password(password)
        user.is_active = True
    else:
        user = User(email=email, password_hash=hash_password(password), is_active=True)
        db.add(user)
    db.commit()
