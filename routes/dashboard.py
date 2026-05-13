from __future__ import annotations

from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from extensions import db
from models import Booking, ChargingStation, User
from utils.decorators import admin_required

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

    active_bookings = (
        Booking.query.options(joinedload(Booking.station))
        .filter_by(user_id=current_user.id, booking_status="confirmed")
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
    total_users = db.session.query(func.count(User.id)).scalar() or 0
    total_stations = db.session.query(func.count(ChargingStation.id)).scalar() or 0
    total_bookings = db.session.query(func.count(Booking.id)).scalar() or 0
    active_bookings = (
        db.session.query(func.count(Booking.id)).filter(Booking.booking_status == "confirmed").scalar() or 0
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

    return render_template(
        "dashboard/admin.html",
        total_users=total_users,
        total_stations=total_stations,
        total_bookings=total_bookings,
        active_bookings=active_bookings,
        total_slots=total_slots,
        available_slots=available_slots,
        occupied_slots=occupied_slots,
        slot_utilization=slot_utilization,
        recent_bookings=recent_bookings,
        station_shortcuts=station_shortcuts,
    )