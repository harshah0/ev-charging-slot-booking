from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from flask import request

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PASSWORD_PATTERN = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,72}$")


def is_safe_next_url(target: str | None) -> bool:
    if not target:
        return False

    host_url = urlparse(request.host_url)
    redirect_url = urlparse(urljoin(request.host_url, target))

    return redirect_url.scheme in {"http", "https"} and host_url.netloc == redirect_url.netloc


def validate_registration_data(username: str, email: str, password: str, confirm_password: str) -> list[str]:
    errors: list[str] = []

    username = username.strip()
    email = email.strip().lower()
    password = password or ""
    confirm_password = confirm_password or ""

    if not username:
        errors.append("Username is required.")
    elif len(username) < 3:
        errors.append("Username must be at least 3 characters long.")
    elif len(username) > 80:
        errors.append("Username must not exceed 80 characters.")

    if not email:
        errors.append("Email is required.")
    elif len(email) > 255 or not EMAIL_PATTERN.match(email):
        errors.append("Enter a valid email address.")

    if not password:
        errors.append("Password is required.")
    elif len(password) < 8:
        errors.append("Password must be at least 8 characters long.")
    elif len(password) > 72:
        errors.append("Password must not exceed 72 characters.")
    elif not PASSWORD_PATTERN.match(password):
        errors.append("Password must include at least one letter and one number.")

    if password and password != confirm_password:
        errors.append("Passwords do not match.")

    return errors


def validate_login_data(email: str, password: str) -> list[str]:
    errors: list[str] = []

    email = email.strip().lower()
    password = password or ""

    if not email:
        errors.append("Email is required.")
    elif len(email) > 255 or not EMAIL_PATTERN.match(email):
        errors.append("Enter a valid email address.")

    if not password:
        errors.append("Password is required.")
    elif len(password) > 72:
        errors.append("Password is too long.")

    return errors
