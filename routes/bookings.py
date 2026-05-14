from __future__ import annotations

from datetime import timedelta, timezone
from decimal import Decimal

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload

from extensions import db
from models import Booking, ChargingStation, Transaction
from models.transaction import TransactionStatus, TransactionType
from utils.booking_validation import validate_booking_payload
from utils.csrf import validate_csrf_token
from utils.payment import calculate_booking_cost, format_currency, validate_wallet_balance

bookings_bp = Blueprint("bookings", __name__, url_prefix="/bookings")


@bookings_bp.get("")
@login_required
def history():
    bookings = (
        Booking.query.options(joinedload(Booking.station))
        .filter_by(user_id=current_user.id)
        .order_by(Booking.created_at.desc())
        .all()
    )
    return render_template("bookings/history.html", bookings=bookings)


@bookings_bp.get("/new/<int:station_id>")
@login_required
def new_booking(station_id: int):
    station = ChargingStation.query.get_or_404(station_id)
    return render_template("bookings/new.html", station=station)


@bookings_bp.post("")
@login_required
def create_booking():
    if not validate_csrf_token(request.form.get("csrf_token")):
        flash("Your session has expired. Please try again.", "danger")
        return redirect(url_for("stations.list_stations"))

    station_id = request.form.get("station_id", type=int)
    station = (
        db.session.query(ChargingStation)
        .filter(ChargingStation.id == station_id)
        .with_for_update()
        .one_or_none()
    )
    if station is None:
        flash("Charging station not found.", "danger")
        return redirect(url_for("stations.list_stations"))

    errors, booking_time, charging_duration = validate_booking_payload(request.form)
    if errors:
        for error in errors:
            flash(error, "danger")
        return render_template("bookings/new.html", station=station, form=request.form), 400

    if station.available_slots <= 0:
        flash("No slots are currently available at this station.", "danger")
        return render_template("bookings/new.html", station=station, form=request.form), 409

    duplicate_booking = Booking.query.filter(
        Booking.user_id == current_user.id,
        Booking.station_id == station.id,
        Booking.booking_status == "confirmed",
    ).first()
    if duplicate_booking:
        flash("You already have an active booking for this station.", "danger")
        return render_template("bookings/new.html", station=station, form=request.form), 409

    # Calculate booking cost
    booking_cost = calculate_booking_cost(charging_duration)

    # Validate wallet balance
    is_valid, error_msg = validate_wallet_balance(
        Decimal(current_user.wallet_balance), booking_cost
    )
    if not is_valid:
        flash(error_msg, "danger")
        return redirect(url_for("payment.recharge"))

    try:
        # Create booking
        booking = Booking(
            user_id=current_user.id,
            station_id=station.id,
            booking_time=booking_time,
            charging_duration=charging_duration,
            booking_status="confirmed",
        )

        # Deduct from wallet (atomic operation)
        current_user.wallet_balance = Decimal(current_user.wallet_balance) - booking_cost
        station.available_slots = station.available_slots - 1

        # Record transaction
        transaction = Transaction(
            user_id=current_user.id,
            booking_id=None,  # Will be set after booking is created
            transaction_type=TransactionType.BOOKING.value,
            amount=-booking_cost,  # Negative for debit
            status=TransactionStatus.COMPLETED.value,
            description=f"Booking at {station.station_name} for {charging_duration} minutes",
            balance_after=Decimal(current_user.wallet_balance),
        )

        db.session.add(booking)
        db.session.flush()  # Get booking ID before committing
        transaction.booking_id = booking.id
        db.session.add(transaction)
        db.session.commit()

        flash(
            f"Your booking was created successfully. Charged: {format_currency(booking_cost)}. Remaining balance: {format_currency(Decimal(current_user.wallet_balance))}",
            "success",
        )
        return redirect(url_for("bookings.history"))

    except Exception as e:
        db.session.rollback()
        flash("An error occurred while creating your booking. Please try again.", "danger")
        return render_template("bookings/new.html", station=station, form=request.form), 500


@bookings_bp.post("/<int:booking_id>/cancel")
@login_required
def cancel_booking(booking_id: int):
    if not validate_csrf_token(request.form.get("csrf_token")):
        flash("Your session has expired. Please try again.", "danger")
        return redirect(url_for("bookings.history"))

    booking = Booking.query.filter_by(id=booking_id, user_id=current_user.id).first_or_404()
    if booking.booking_status == "cancelled":
        flash("Booking is already cancelled.", "info")
        return redirect(url_for("bookings.history"))

    station = (
        db.session.query(ChargingStation)
        .filter(ChargingStation.id == booking.station_id)
        .with_for_update()
        .one_or_none()
    )
    if station is None:
        flash("Charging station no longer exists.", "danger")
        return redirect(url_for("bookings.history"))

    booking.booking_status = "cancelled"
    station.available_slots = min(station.available_slots + 1, station.total_slots)

    db.session.commit()
    flash("Booking cancelled successfully.", "info")
    return redirect(url_for("bookings.history"))
