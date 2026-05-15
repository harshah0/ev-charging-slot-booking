from __future__ import annotations

from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from sqlalchemy import cast, Date
from datetime import timedelta

from extensions import db
from models import Booking, ChargingStation, User
from models import Transaction
from models.transaction import TransactionType, TransactionStatus
from models.booking import BookingLifecycleStatus
from utils.decorators import admin_required
from utils.datetime_utils import utc_now

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


def _build_nearby_station_query(active_bookings):
    reference_station = active_bookings[0].station if active_bookings else None
    query = ChargingStation.query

    if reference_station is not None:
        query = query.filter(
            (ChargingStation.city == reference_station.city)
            | (ChargingStation.state == reference_station.state)
        )

    stations = (
        query.order_by(ChargingStation.available_slots.desc(), ChargingStation.station_name.asc())
        .limit(6)
        .all()
    )

    if stations:
        return stations

    return ChargingStation.query.order_by(ChargingStation.created_at.desc()).limit(6).all()


@dashboard_bp.get("")
@login_required
def entry():
    if current_user.is_admin():
        return redirect(url_for("dashboard.admin_dashboard"))
    return redirect(url_for("dashboard.user_dashboard"))


@dashboard_bp.get("/user")
@login_required
def user_dashboard():
    if current_user.is_admin():
        return redirect(url_for("dashboard.admin_dashboard"))

    now = utc_now()

    active_bookings = (
        Booking.query.options(joinedload(Booking.station))
        .filter(
            Booking.user_id == current_user.id,
            Booking.booking_status == BookingLifecycleStatus.ACTIVE.value,
            Booking.expires_at > now,
        )
        .order_by(Booking.booking_time.asc())
        .all()
    )
    recent_history = (
        Booking.query.options(joinedload(Booking.station))
        .filter_by(user_id=current_user.id)
        .order_by(Booking.created_at.desc())
        .limit(5)
        .all()
    )
    total_bookings = (
        db.session.query(func.count(Booking.id)).filter(Booking.user_id == current_user.id).scalar() or 0
    )

    return render_template(
        "dashboard/user.html",
        active_bookings=active_bookings,
        recent_history=recent_history,
        nearby_stations=_build_nearby_station_query(active_bookings),
        total_bookings=total_bookings,
    )


@dashboard_bp.get("/admin")
@admin_required
def admin_dashboard():
    now = utc_now()
    total_users = db.session.query(func.count(User.id)).scalar() or 0
    total_stations = db.session.query(func.count(ChargingStation.id)).scalar() or 0
    total_bookings = db.session.query(func.count(Booking.id)).scalar() or 0
    active_bookings = (
        db.session.query(func.count(Booking.id))
        .filter(
            Booking.booking_status == BookingLifecycleStatus.ACTIVE.value,
            Booking.expires_at > now,
        )
        .scalar()
        or 0
    )
    completed_bookings = (
        db.session.query(func.count(Booking.id))
        .filter(Booking.booking_status == BookingLifecycleStatus.COMPLETED.value)
        .scalar()
        or 0
    )
    expired_bookings = (
        db.session.query(func.count(Booking.id))
        .filter(Booking.booking_status == BookingLifecycleStatus.EXPIRED.value)
        .scalar()
        or 0
    )
    cancelled_bookings = (
        db.session.query(func.count(Booking.id))
        .filter(Booking.booking_status == BookingLifecycleStatus.CANCELLED.value)
        .scalar()
        or 0
    )

    total_slots, available_slots = db.session.query(
        func.coalesce(func.sum(ChargingStation.total_slots), 0),
        func.coalesce(func.sum(ChargingStation.available_slots), 0),
    ).one()
    total_slots = int(total_slots or 0)
    available_slots = int(available_slots or 0)
    occupied_slots = max(total_slots - available_slots, 0)
    slot_utilization = round((occupied_slots / total_slots) * 100, 1) if total_slots else 0.0

    recent_bookings = (
        Booking.query.options(joinedload(Booking.station), joinedload(Booking.user))
        .order_by(Booking.created_at.desc())
        .limit(8)
        .all()
    )
    station_shortcuts = (
        ChargingStation.query.order_by(ChargingStation.available_slots.asc(), ChargingStation.station_name.asc())
        .limit(6)
        .all()
    )

    # Analytics: bookings per day (last 30 days)
    days = 30
    start_date = (now - timedelta(days=days - 1)).date()
    day_col = func.date(Booking.booking_time)
    bookings_per_day_rows = (
        db.session.query(day_col.label('day'), func.count(Booking.id))
        .filter(Booking.booking_time >= start_date)
        .group_by(day_col)
        .order_by(day_col)
        .all()
    )
    bookings_per_day_map = {str(r[0]): int(r[1]) for r in bookings_per_day_rows}
    bookings_per_day_labels = []
    bookings_per_day_counts = []
    for i in range(days):
        d = start_date + timedelta(days=i)
        key = str(d)
        bookings_per_day_labels.append(d.isoformat())
        bookings_per_day_counts.append(int(bookings_per_day_map.get(key, 0)))

    # Recharge trends (last 30 days)
    trans_day_col = func.date(Transaction.created_at)
    recharge_rows = (
        db.session.query(trans_day_col.label('day'), func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            Transaction.transaction_type == TransactionType.RECHARGE.value,
            Transaction.status == TransactionStatus.COMPLETED.value,
            Transaction.created_at >= start_date,
        )
        .group_by(trans_day_col)
        .order_by(trans_day_col)
        .all()
    )
    recharge_map = {str(r[0]): float(r[1]) for r in recharge_rows}
    recharge_labels = bookings_per_day_labels
    recharge_values = [float(recharge_map.get(d, 0.0)) for d in recharge_labels]

    # Booking status distribution
    status_rows = (
        db.session.query(Booking.booking_status, func.count(Booking.id))
        .group_by(Booking.booking_status)
        .all()
    )
    status_labels = [r[0].title() for r in status_rows]
    status_counts = [int(r[1]) for r in status_rows]

    # Most-used stations
    station_usage_rows = (
        db.session.query(ChargingStation.station_name, func.count(Booking.id).label('cnt'))
        .join(Booking, Booking.station_id == ChargingStation.id)
        .group_by(ChargingStation.id)
        .order_by(func.count(Booking.id).desc())
        .limit(10)
        .all()
    )
    top_stations = [r[0] for r in station_usage_rows]
    top_station_counts = [int(r[1]) for r in station_usage_rows]

    # Total wallet revenue from bookings (sum of booking charges)
    total_wallet_revenue = (
        db.session.query(func.coalesce(func.sum(-Transaction.amount), 0))
        .filter(
            Transaction.transaction_type == TransactionType.BOOKING.value,
            Transaction.status == TransactionStatus.COMPLETED.value,
        )
        .scalar()
        or 0
    )

    return render_template(
        "dashboard/admin.html",
        total_users=total_users,
        total_stations=total_stations,
        total_bookings=total_bookings,
        active_bookings=active_bookings,
        completed_bookings=completed_bookings,
        expired_bookings=expired_bookings,
        cancelled_bookings=cancelled_bookings,
        total_slots=total_slots,
        available_slots=available_slots,
        occupied_slots=occupied_slots,
        slot_utilization=slot_utilization,
        recent_bookings=recent_bookings,
        station_shortcuts=station_shortcuts,
        # Analytics payloads
        bookings_per_day_labels=bookings_per_day_labels,
        bookings_per_day_counts=bookings_per_day_counts,
        recharge_labels=recharge_labels,
        recharge_values=recharge_values,
        status_labels=status_labels,
        status_counts=status_counts,
        top_stations=top_stations,
        top_station_counts=top_station_counts,
        total_wallet_revenue=total_wallet_revenue,
    )