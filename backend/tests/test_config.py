from pathlib import Path

from app.core.config import BACKEND_ROOT, Settings


def test_default_database_url_is_backend_anchored() -> None:
    settings = Settings(_env_file=None)

    assert settings.database_url == f"sqlite:///{BACKEND_ROOT / 'directindex.db'}"
    assert Path(settings.database_url.removeprefix("sqlite:///")).is_absolute()
