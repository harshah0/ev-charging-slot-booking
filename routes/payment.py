"""Wallet and payment operations routes."""
from __future__ import annotations

from decimal import Decimal

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from models import Transaction
from models.transaction import TransactionStatus, TransactionType
from services.realtime import emit_recharge_analytics_update, emit_wallet_update
from utils.csrf import validate_csrf_token
from utils.payment import format_currency

payment_bp = Blueprint("payment", __name__, url_prefix="/payment")


@payment_bp.get("/transactions")
@login_required
def transaction_history():
    """Display user's transaction history."""
    transactions = (
        Transaction.query.filter_by(user_id=current_user.id)
        .order_by(Transaction.created_at.desc())
        .all()
    )
    return render_template("payment/transactions.html", transactions=transactions)


@payment_bp.get("/recharge")
@login_required
def recharge():
    """Show wallet recharge form."""
    return render_template("payment/recharge.html")


@payment_bp.post("/recharge")
@login_required
def recharge_post():
    """Process wallet recharge."""
    if not validate_csrf_token(request.form.get("csrf_token")):
        flash("Your session has expired. Please try again.", "danger")
        return redirect(url_for("payment.recharge"))

    amount_str = request.form.get("amount", "").strip()
    if not amount_str:
        flash("Please enter a recharge amount.", "danger")
        return render_template("payment/recharge.html", form=request.form), 400

    try:
        amount = Decimal(amount_str)
    except Exception:
        flash("Invalid amount format.", "danger")
        return render_template("payment/recharge.html", form=request.form), 400

    if amount <= 0:
        flash("Recharge amount must be greater than zero.", "danger")
        return render_template("payment/recharge.html", form=request.form), 400

    if amount > Decimal("100000.00"):
        flash("Recharge amount cannot exceed ₹100,000.", "danger")
        return render_template("payment/recharge.html", form=request.form), 400

    # Round to 2 decimal places for currency consistency
    amount = round(amount, 2)

    try:
        # Update user wallet balance
        current_user.wallet_balance = (
            Decimal(current_user.wallet_balance) + amount
        )

        # Record transaction
        transaction = Transaction(
            user_id=current_user.id,
            booking_id=None,
            transaction_type=TransactionType.RECHARGE.value,
            amount=amount,
            status=TransactionStatus.COMPLETED.value,
            description=f"Wallet recharge of {format_currency(amount)}",
            balance_after=Decimal(current_user.wallet_balance),
        )

        db.session.add(transaction)
        db.session.commit()

        emit_wallet_update(
            user=current_user,
            transaction=transaction,
            message=f"Wallet recharged with {format_currency(amount)}.",
        )

        # Broadcast a compact analytics event for admin dashboards only.
        # This keeps analytics realtime without relying on connect/sync flows.
        emit_recharge_analytics_update(user=current_user, amount=amount)

        flash(
            f"Wallet recharged successfully with {format_currency(amount)}. New balance: {format_currency(Decimal(current_user.wallet_balance))}",
            "success",
        )
        return redirect(url_for("dashboard.entry"))

    except Exception as e:
        db.session.rollback()
        flash("An error occurred while processing your recharge.", "danger")
        return render_template("payment/recharge.html", form=request.form), 500
