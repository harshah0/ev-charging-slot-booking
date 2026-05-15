from __future__ import annotations

from datetime import datetime, timedelta, time, timezone

from sqlalchemy import func

from extensions import db
from models import Booking, ChargingStation, Transaction, User
from models.booking import BookingLifecycleStatus
from models.transaction import TransactionStatus, TransactionType
from utils.datetime_utils import ensure_utc_datetime, utc_now


def _start_of_day_utc(reference_time: datetime, days: int = 30) -> datetime:
    current_time = ensure_utc_datetime(reference_time) or utc_now()
    start_date = (current_time - timedelta(days=days - 1)).date()
    return datetime.combine(start_date, time.min, tzinfo=timezone.utc)


def build_admin_analytics_snapshot(reference_time: datetime | None = None) -> dict:
    now = ensure_utc_datetime(reference_time) or utc_now()
    start_dt = _start_of_day_utc(now, days=30)
    start_date = start_dt.date()

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

    total_wallet_revenue = (
        db.session.query(func.coalesce(func.sum(-Transaction.amount), 0))
        .filter(
            Transaction.transaction_type == TransactionType.BOOKING.value,
            Transaction.status == TransactionStatus.COMPLETED.value,
        )
        .scalar()
        or 0
    )

    day_col = func.date(Booking.booking_time)
    bookings_per_day_rows = (
        db.session.query(day_col.label("day"), func.count(Booking.id))
        .filter(Booking.booking_time >= start_dt)
        .group_by(day_col)
        .order_by(day_col)
        .all()
    )
    bookings_per_day_map = {str(row[0]): int(row[1]) for row in bookings_per_day_rows}
    bookings_per_day_labels = []
    bookings_per_day_counts = []
    for offset in range(30):
        day_value = start_date + timedelta(days=offset)
        bookings_per_day_labels.append(day_value.isoformat())
        bookings_per_day_counts.append(int(bookings_per_day_map.get(str(day_value), 0)))

    trans_day_col = func.date(Transaction.created_at)
    recharge_rows = (
        db.session.query(trans_day_col.label("day"), func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            Transaction.transaction_type == TransactionType.RECHARGE.value,
            Transaction.status == TransactionStatus.COMPLETED.value,
            Transaction.created_at >= start_dt,
        )
        .group_by(trans_day_col)
        .order_by(trans_day_col)
        .all()
    )
    recharge_map = {str(row[0]): float(row[1]) for row in recharge_rows}
    recharge_labels = list(bookings_per_day_labels)
    recharge_values = [float(recharge_map.get(day_label, 0.0)) for day_label in recharge_labels]

    status_rows = (
        db.session.query(Booking.booking_status, func.count(Booking.id))
        .group_by(Booking.booking_status)
        .all()
    )
    status_labels = [row[0].title() for row in status_rows]
    status_counts = [int(row[1]) for row in status_rows]

    station_usage_rows = (
        db.session.query(ChargingStation.station_name, func.count(Booking.id).label("cnt"))
        .join(Booking, Booking.station_id == ChargingStation.id)
        .group_by(ChargingStation.id)
        .order_by(func.count(Booking.id).desc())
        .limit(10)
        .all()
    )
    top_stations = [row[0] for row in station_usage_rows]
    top_station_counts = [int(row[1]) for row in station_usage_rows]

    return {
        "total_users": int(total_users),
        "total_stations": int(total_stations),
        "total_bookings": int(total_bookings),
        "active_bookings": int(active_bookings),
        "completed_bookings": int(completed_bookings),
        "expired_bookings": int(expired_bookings),
        "cancelled_bookings": int(cancelled_bookings),
        "total_slots": total_slots,
        "available_slots": available_slots,
        "occupied_slots": occupied_slots,
        "slot_utilization": slot_utilization,
        "total_wallet_revenue": float(total_wallet_revenue),
        "bookings_per_day_labels": bookings_per_day_labels,
        "bookings_per_day_counts": bookings_per_day_counts,
        "recharge_labels": recharge_labels,
        "recharge_values": recharge_values,
        "status_labels": status_labels,
        "status_counts": status_counts,
        "top_stations": top_stations,
        "top_station_counts": top_station_counts,
    }
