from __future__ import annotations

from decimal import Decimal

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload

from extensions import db
from models import Booking, ChargingStation, Transaction
from models.booking import BookingLifecycleStatus
from models.transaction import TransactionStatus, TransactionType
from services.booking_lifecycle import (
    booking_expires_at,
    cancel_booking as cancel_booking_lifecycle,
    complete_booking as complete_booking_lifecycle,
    sync_booking_lifecycle,
)
from services.realtime import emit_live_booking_event
from utils.booking_validation import validate_booking_payload
from utils.csrf import validate_csrf_token
from utils.datetime_utils import utc_now
from utils.payment import calculate_booking_cost, format_currency, validate_wallet_balance

bookings_bp = Blueprint("bookings", __name__, url_prefix="/bookings")


@bookings_bp.get("")
@login_required
def history():
    bookings = Booking.query.options(joinedload(Booking.station)).filter_by(user_id=current_user.id).order_by(Booking.created_at.desc()).all()
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
        Booking.booking_status == BookingLifecycleStatus.ACTIVE.value,
        Booking.expires_at > utc_now(),
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
        expires_at = booking_expires_at(booking_time, charging_duration)

        # Create booking
        booking = Booking(
            user_id=current_user.id,
            station_id=station.id,
            booking_time=booking_time,
            charging_duration=charging_duration,
            booking_status=BookingLifecycleStatus.ACTIVE.value,
            activated_at=utc_now(),
            expires_at=expires_at,
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

        emit_live_booking_event(
            action="created",
            booking=booking,
            station=station,
            message=f"New booking created for {station.station_name}.",
        )

        flash(
            f"Your booking was created successfully. Charged: {format_currency(booking_cost)}. Remaining balance: {format_currency(Decimal(current_user.wallet_balance))}",
            "success",
        )
        return redirect(url_for("bookings.history"))

    except Exception as e:
        db.session.rollback()
        flash("An error occurred while creating your booking. Please try again.", "danger")
        return render_template("bookings/new.html", station=station, form=request.form), 500


@bookings_bp.post("/<int:booking_id>/complete")
@login_required
def complete_booking(booking_id: int):
    if not validate_csrf_token(request.form.get("csrf_token")):
        flash("Your session has expired. Please try again.", "danger")
        return redirect(url_for("bookings.history"))

    booking = (
        Booking.query.options(joinedload(Booking.station))
        .filter_by(id=booking_id, user_id=current_user.id)
        .with_for_update()
        .one_or_none()
    )
    if booking is None:
        flash("Booking not found.", "danger")
        return redirect(url_for("bookings.history"))

    sync_booking_lifecycle(booking)
    if booking.booking_status != BookingLifecycleStatus.ACTIVE.value:
        flash("Only active bookings can be completed.", "info")
        return redirect(url_for("bookings.history"))

    if booking.station is None:
        flash("Charging station no longer exists.", "danger")
        return redirect(url_for("bookings.history"))

    if not complete_booking_lifecycle(booking):
        flash("Unable to complete this booking.", "danger")
        return redirect(url_for("bookings.history"))

    db.session.commit()
    emit_live_booking_event(
        action="completed",
        booking=booking,
        station=booking.station,
        message="Booking completed and slot released.",
    )
    flash("Booking marked as completed.", "success")
    return redirect(url_for("bookings.history"))


@bookings_bp.post("/<int:booking_id>/cancel")
@login_required
def cancel_booking(booking_id: int):
    if not validate_csrf_token(request.form.get("csrf_token")):
        flash("Your session has expired. Please try again.", "danger")
        return redirect(url_for("bookings.history"))

    booking = (
        Booking.query.options(joinedload(Booking.station))
        .filter_by(id=booking_id, user_id=current_user.id)
        .with_for_update()
        .one_or_none()
    )
    if booking is None:
        flash("Booking not found.", "danger")
        return redirect(url_for("bookings.history"))

    sync_booking_lifecycle(booking)
    if booking.booking_status == BookingLifecycleStatus.CANCELLED.value:
        flash("Booking is already cancelled.", "info")
        return redirect(url_for("bookings.history"))

    if booking.booking_status != BookingLifecycleStatus.ACTIVE.value:
        flash("Only active bookings can be cancelled.", "info")
        return redirect(url_for("bookings.history"))

    station = booking.station
    if station is None:
        flash("Charging station no longer exists.", "danger")
        return redirect(url_for("bookings.history"))

    if not cancel_booking_lifecycle(booking):
        flash("Unable to cancel this booking.", "danger")
        return redirect(url_for("bookings.history"))

    db.session.commit()
    emit_live_booking_event(
        action="cancelled",
        booking=booking,
        station=booking.station,
        message="Booking cancelled and slot released.",
    )
    flash("Booking cancelled successfully.", "info")
    return redirect(url_for("bookings.history"))
