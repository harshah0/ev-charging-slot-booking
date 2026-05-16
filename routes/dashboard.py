from __future__ import annotations

from flask import Blueprint, jsonify, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload
from sqlalchemy import func

from extensions import db
from models import Booking, ChargingStation, User
from models import Transaction
from models.transaction import TransactionType, TransactionStatus
from models.booking import BookingLifecycleStatus
from services.admin_analytics import build_admin_analytics_snapshot
from services.open_charge_map import get_open_charge_map_diagnostics
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
    analytics = build_admin_analytics_snapshot()
    ocm_diagnostics = get_open_charge_map_diagnostics()

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
        **analytics,
        recent_bookings=recent_bookings,
        station_shortcuts=station_shortcuts,
        ocm_diagnostics=ocm_diagnostics,
    )


@dashboard_bp.get("/admin/openchargemap-diagnostics")
@admin_required
def admin_openchargemap_diagnostics():
    return jsonify(get_open_charge_map_diagnostics())