from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from extensions import db
from models import ChargingStation
from utils.station_validation import VALID_CHARGING_TYPES, validate_station_payload
from utils.csrf import validate_csrf_token

stations_bp = Blueprint("stations", __name__, url_prefix="/stations")


def _serialize_station_for_map(station: ChargingStation) -> dict:
    return {
        "id": station.id,
        "station_name": station.station_name,
        "location": f"{station.address}, {station.city}, {station.state}",
        "charging_type": station.charging_type,
        "available_slots": station.available_slots,
        "total_slots": station.total_slots,
        "latitude": float(station.latitude),
        "longitude": float(station.longitude),
    }


@stations_bp.get("")
def list_stations():
    stations = ChargingStation.query.order_by(ChargingStation.created_at.desc()).all()
    return render_template("stations/list.html", stations=stations)


@stations_bp.get("/map")
def station_map():
    stations = ChargingStation.query.order_by(ChargingStation.station_name.asc()).all()
    station_points = [_serialize_station_for_map(station) for station in stations]
    return render_template("stations/map.html", stations=station_points)


@stations_bp.get("/new")
@login_required
def new_station():
    return render_template("stations/form.html", station=None, charging_types=VALID_CHARGING_TYPES, form=None)


@stations_bp.post("")
@login_required
def create_station():
    if not validate_csrf_token(request.form.get("csrf_token")):
        flash("Your session has expired. Please try again.", "danger")
        return redirect(url_for("stations.list_stations"))

    errors = validate_station_payload(request.form)
    if errors:
        for error in errors:
            flash(error, "danger")
        return render_template(
            "stations/form.html",
            station=None,
            charging_types=VALID_CHARGING_TYPES,
            form=request.form,
        ), 400

    station = ChargingStation(
        station_name=request.form.get("station_name", "").strip(),
        address=request.form.get("address", "").strip(),
        city=request.form.get("city", "").strip(),
        state=request.form.get("state", "").strip(),
        latitude=request.form.get("latitude"),
        longitude=request.form.get("longitude"),
        total_slots=int(request.form.get("total_slots", 0)),
        available_slots=int(request.form.get("total_slots", 0)),
        charging_type=request.form.get("charging_type", "").strip(),
    )

    db.session.add(station)
    db.session.commit()

    flash("Charging station created successfully.", "success")
    return redirect(url_for("stations.list_stations"))


@stations_bp.get("/<int:station_id>/edit")
@login_required
def edit_station(station_id: int):
    station = ChargingStation.query.get_or_404(station_id)
    return render_template("stations/form.html", station=station, charging_types=VALID_CHARGING_TYPES, form=None)


@stations_bp.post("/<int:station_id>/update")
@login_required
def update_station(station_id: int):
    station = ChargingStation.query.get_or_404(station_id)
    if not validate_csrf_token(request.form.get("csrf_token")):
        flash("Your session has expired. Please try again.", "danger")
        return redirect(url_for("stations.edit_station", station_id=station_id))

    errors = validate_station_payload(request.form)
    if errors:
        for error in errors:
            flash(error, "danger")
        return render_template(
            "stations/form.html",
            station=station,
            charging_types=VALID_CHARGING_TYPES,
            form=request.form,
        ), 400

    station.station_name = request.form.get("station_name", "").strip()
    station.address = request.form.get("address", "").strip()
    station.city = request.form.get("city", "").strip()
    station.state = request.form.get("state", "").strip()
    station.latitude = request.form.get("latitude")
    station.longitude = request.form.get("longitude")
    station.total_slots = int(request.form.get("total_slots", 0))
    station.available_slots = min(station.available_slots, station.total_slots)
    station.charging_type = request.form.get("charging_type", "").strip()

    db.session.commit()
    flash("Charging station updated successfully.", "success")
    return redirect(url_for("stations.list_stations"))


@stations_bp.post("/<int:station_id>/delete")
@login_required
def delete_station(station_id: int):
    station = ChargingStation.query.get_or_404(station_id)
    if not validate_csrf_token(request.form.get("csrf_token")):
        flash("Your session has expired. Please try again.", "danger")
        return redirect(url_for("stations.list_stations"))

    if station.bookings:
        flash("This station cannot be deleted because bookings already exist.", "danger")
        return redirect(url_for("stations.list_stations"))

    db.session.delete(station)
    db.session.commit()
    flash("Charging station deleted successfully.", "info")
    return redirect(url_for("stations.list_stations"))
