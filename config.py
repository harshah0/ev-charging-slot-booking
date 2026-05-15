import os
from pathlib import Path
from datetime import timedelta

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def build_database_uri(default_path: str = "instance/app.db") -> str:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        if database_url.startswith("postgres://"):
            return database_url.replace("postgres://", "postgresql://", 1)
        return database_url

    return f"sqlite:///{(BASE_DIR / default_path).as_posix()}"


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
