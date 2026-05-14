from __future__ import annotations

from decimal import Decimal
from enum import Enum

from sqlalchemy import func, text

from extensions import db


class TransactionType(str, Enum):
    """Transaction type enumeration."""
    RECHARGE = "recharge"
    BOOKING = "booking"
    REFUND = "refund"


class TransactionStatus(str, Enum):
    """Transaction status enumeration."""
    COMPLETED = "completed"
    PENDING = "pending"
    FAILED = "failed"


class Transaction(db.Model):
    __tablename__ = "transactions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("bookings.id"), nullable=True, index=True)
    transaction_type = db.Column(
        db.String(20),
        nullable=False,
        index=True,
    )
    amount = db.Column(
        db.Numeric(10, 2),
        nullable=False,
    )
    status = db.Column(
        db.String(20),
        nullable=False,
        default=TransactionStatus.COMPLETED.value,
        server_default=TransactionStatus.COMPLETED.value,
        index=True,
    )
    description = db.Column(db.String(255), nullable=True)
    balance_after = db.Column(
        db.Numeric(10, 2),
        nullable=False,
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    user = db.relationship("User", foreign_keys=[user_id])
    booking = db.relationship("Booking", foreign_keys=[booking_id])

    @property
    def is_completed(self) -> bool:
        """Check if transaction is completed."""
        return self.status == TransactionStatus.COMPLETED.value

    @property
    def is_debit(self) -> bool:
        """Check if transaction is a debit (negative amount)."""
        return self.amount < 0

    @property
    def is_credit(self) -> bool:
        """Check if transaction is a credit (positive amount)."""
        return self.amount > 0

    def __repr__(self) -> str:
        return (
            f"Transaction(id={self.id!r}, user_id={self.user_id!r}, "
            f"transaction_type={self.transaction_type!r}, amount={self.amount!r})"
        )
