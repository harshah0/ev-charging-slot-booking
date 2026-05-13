from __future__ import annotations

import hmac
import secrets

from flask import session

CSRF_SESSION_KEY = "csrf_token"


def generate_csrf_token() -> str:
    token = session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
    return token


def validate_csrf_token(submitted_token: str | None) -> bool:
    stored_token = session.get(CSRF_SESSION_KEY)
    if not stored_token or not submitted_token:
        return False
    return hmac.compare_digest(stored_token, submitted_token)
