from __future__ import annotations

from decimal import Decimal

from flask_login import UserMixin
from sqlalchemy import func, text
from sqlalchemy.orm import validates
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db, login_manager


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False, unique=True, index=True)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    wallet_balance = db.Column(
        db.Numeric(10, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default=text("0.00"),
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @validates("username")
    def validate_username(self, key: str, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Username is required.")
        if len(value) < 3:
            raise ValueError("Username must be at least 3 characters long.")
        return value

    @validates("email")
    def validate_email(self, key: str, value: str) -> str:
        value = value.strip().lower()
        if not value:
            raise ValueError("Email is required.")
        if "@" not in value:
            raise ValueError("Email must be valid.")
        return value

    @validates("wallet_balance")
    def validate_wallet_balance(self, key: str, value) -> Decimal:
        if value is None:
            return Decimal("0.00")
        if Decimal(value) < 0:
            raise ValueError("Wallet balance cannot be negative.")
        return value

    def __repr__(self) -> str:
        return f"User(id={self.id!r}, username={self.username!r}, email={self.email!r})"


@login_manager.user_loader
def load_user(user_id: str):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None
