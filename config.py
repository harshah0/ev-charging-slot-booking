import os
import tempfile
from pathlib import Path
from datetime import timedelta

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _is_ci_or_test_mode() -> bool:
    """Detect CI/test contexts that should avoid workspace-bound sqlite paths."""
    return any(
        os.getenv(flag, "").lower() in {"1", "true", "yes"}
        for flag in ("CI", "GITHUB_ACTIONS", "PYTEST_CURRENT_TEST", "CI_SMOKE_TEST")
    )


def _normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql://", 1)
    return database_url


def _ensure_sqlite_parent_dir(database_uri: str) -> str:
    """Create parent directory for sqlite file databases on all platforms.

    CI runners and some local shells do not guarantee pre-created relative
    directories (for example "instance/"). If that directory is missing,
    sqlite cannot create the database and SQLAlchemy fails with
    "unable to open database file" during db.create_all().
    """
    if not database_uri.startswith("sqlite:///"):
        return database_uri

    sqlite_target = database_uri.replace("sqlite:///", "", 1)
    if sqlite_target in {":memory:", ""} or sqlite_target.startswith("file:"):
        return database_uri

    sqlite_path = Path(sqlite_target)
    if not sqlite_path.is_absolute():
        sqlite_path = BASE_DIR / sqlite_path
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{sqlite_path.as_posix()}"


def build_database_uri(default_path: str = "instance/app.db") -> str:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return _ensure_sqlite_parent_dir(_normalize_database_url(database_url))

    if _is_ci_or_test_mode():
        ci_db_path = Path(tempfile.gettempdir()) / "ev-charging-slot-booking" / "ci-smoke.db"
        ci_db_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{ci_db_path.as_posix()}"

    return _ensure_sqlite_parent_dir(f"sqlite:///{(BASE_DIR / default_path).as_posix()}")


def build_engine_options(database_uri: str) -> dict:
    if database_uri.startswith("sqlite"):
        return {}

    # Read optional pool tuning values from environment for production
    pool_size = int(os.getenv("SQLALCHEMY_POOL_SIZE", "10"))
    max_overflow = int(os.getenv("SQLALCHEMY_MAX_OVERFLOW", "20"))
    pool_pre_ping = os.getenv("SQLALCHEMY_POOL_PRE_PING", "true").lower() == "true"
    pool_recycle = int(os.getenv("SQLALCHEMY_POOL_RECYCLE", "300"))

    return {
        "pool_pre_ping": pool_pre_ping,
        "pool_recycle": pool_recycle,
        "pool_size": pool_size,
        "max_overflow": max_overflow,
    }


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_DATABASE_URI = build_database_uri()
    SQLALCHEMY_ENGINE_OPTIONS = build_engine_options(SQLALCHEMY_DATABASE_URI)
    SOCKETIO_ASYNC_MODE = os.getenv("SOCKETIO_ASYNC_MODE", "eventlet")
    SOCKETIO_CORS_ORIGINS = os.getenv("SOCKETIO_CORS_ORIGINS", "*")
    SOCKETIO_MESSAGE_QUEUE = os.getenv("SOCKETIO_MESSAGE_QUEUE")
    SOCKETIO_PING_INTERVAL = int(os.getenv("SOCKETIO_PING_INTERVAL", "25"))
    SOCKETIO_PING_TIMEOUT = int(os.getenv("SOCKETIO_PING_TIMEOUT", "60"))
    SOCKETIO_MAX_HTTP_BUFFER_SIZE = int(os.getenv("SOCKETIO_MAX_HTTP_BUFFER_SIZE", "1000000"))
    OPENCHARGEMAP_ENABLED = os.getenv("OPENCHARGEMAP_ENABLED", "true").lower() == "true"
    OPENCHARGEMAP_API_KEY = os.getenv("OPENCHARGEMAP_API_KEY")
    OPENCHARGEMAP_ENDPOINT = os.getenv("OPENCHARGEMAP_ENDPOINT", "https://api.openchargemap.io/v3/poi/")
    OPENCHARGEMAP_TIMEOUT_SECONDS = int(os.getenv("OPENCHARGEMAP_TIMEOUT_SECONDS", "6"))
    OPENCHARGEMAP_CACHE_TTL_SECONDS = int(os.getenv("OPENCHARGEMAP_CACHE_TTL_SECONDS", "300"))
    OPENCHARGEMAP_MAX_RESULTS = int(os.getenv("OPENCHARGEMAP_MAX_RESULTS", "25"))
    PERMANENT_SESSION_LIFETIME = timedelta(days=int(os.getenv("SESSION_LIFETIME_DAYS", "7")))
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.getenv("TEST_DATABASE_URL", "sqlite:///:memory:")


class ProductionConfig(Config):
    DEBUG = False
    # In production, secret key must be explicitly provided
    SECRET_KEY = os.getenv("SECRET_KEY") or Config.SECRET_KEY


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
