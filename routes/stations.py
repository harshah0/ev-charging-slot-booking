from __future__ import annotations

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import login_required

from extensions import db
from models import ChargingStation
from utils.station_validation import VALID_CHARGING_TYPES, validate_station_payload
from utils.csrf import validate_csrf_token
from utils.decorators import admin_required
from utils.geospatial import parse_coordinate, parse_radius_km, with_distance, SUPPORTED_RADIUS_KM
from services.open_charge_map import fetch_nearby_public_stations

stations_bp = Blueprint("stations", __name__, url_prefix="/stations")


def _serialize_station_for_map(station: ChargingStation, *, distance_km: float | None = None) -> dict:
    payload = {
        "id": station.id,
        "station_name": station.station_name,
        "location": f"{station.address}, {station.city}, {station.state}",
        "address": f"{station.address}, {station.city}, {station.state}",
        "operator": "Platform-managed station",
        "charging_type": station.charging_type,
        "available_slots": station.available_slots,
        "total_slots": station.total_slots,
        "latitude": float(station.latitude),
        "longitude": float(station.longitude),
        "source": "local",
        "bookable": True,
    }
    if distance_km is not None:
        payload["distance_km"] = round(distance_km, 2)
    return payload


def _combine_station_points(
    local_stations: list[ChargingStation],
    *,
    user_lat: float | None = None,
    user_lon: float | None = None,
    radius_km: float | None = None,
) -> tuple[list[dict], list[dict], list[dict], str | None]:
    local_points = [_serialize_station_for_map(station) for station in local_stations]
    public_points: list[dict] = []
    public_error: str | None = None

    if user_lat is not None and user_lon is not None and radius_km is not None:
        local_points = with_distance(
            local_points,
            user_lat=user_lat,
            user_lon=user_lon,
            radius_km=radius_km,
        )
        public_points, public_error = fetch_nearby_public_stations(
            latitude=user_lat,
            longitude=user_lon,
            radius_km=radius_km,
        )

    combined_points = local_points + public_points
    if user_lat is not None and user_lon is not None:
        combined_points.sort(key=lambda station: station.get("distance_km") or 0)
    return combined_points, local_points, public_points, public_error


@stations_bp.get("")
def list_stations():
    stations = ChargingStation.query.order_by(ChargingStation.created_at.desc()).all()
    return render_template("stations/list.html", stations=stations)


@stations_bp.get("/map")
def station_map():
    latitude_raw = request.args.get("lat")
    longitude_raw = request.args.get("lon")
    radius_raw = request.args.get("radius_km")

    user_location: dict | None = None
    radius_km = 10
    if latitude_raw is not None and longitude_raw is not None:
        try:
            user_lat = parse_coordinate(latitude_raw, "latitude")
            user_lon = parse_coordinate(longitude_raw, "longitude")
            radius_km = parse_radius_km(radius_raw, default=10)
            user_location = {
                "latitude": user_lat,
                "longitude": user_lon,
                "radius_km": radius_km,
            }
        except ValueError:
            user_location = None

    stations = ChargingStation.query.order_by(ChargingStation.station_name.asc()).all()
    station_points, _, _, public_error = _combine_station_points(
        stations,
        user_lat=user_location["latitude"] if user_location else None,
        user_lon=user_location["longitude"] if user_location else None,
        radius_km=user_location["radius_km"] if user_location else None,
    )

    return render_template(
        "stations/map.html",
        stations=station_points,
        supported_radius_km=SUPPORTED_RADIUS_KM,
        initial_radius_km=radius_km,
        user_location=user_location,
        public_station_error=public_error,
    )


@stations_bp.get("/nearby")
def nearby_stations():
    try:
        user_lat = parse_coordinate(request.args.get("lat"), "latitude")
        user_lon = parse_coordinate(request.args.get("lon"), "longitude")
        radius_km = parse_radius_km(request.args.get("radius_km"), default=10)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    stations = ChargingStation.query.order_by(ChargingStation.station_name.asc()).all()
    nearby, local_stations, public_stations, public_error = _combine_station_points(
        stations,
        user_lat=user_lat,
        user_lon=user_lon,
        radius_km=radius_km,
    )
    return jsonify(
        {
            "center": {"latitude": user_lat, "longitude": user_lon},
            "radius_km": radius_km,
            "count": len(nearby),
            "stations": nearby,
            "local_stations": local_stations,
            "public_stations": public_stations,
            "public_error": public_error,
        }
    )


@stations_bp.get("/new")
@admin_required
def new_station():
    return render_template("stations/form.html", station=None, charging_types=VALID_CHARGING_TYPES, form=None)


@stations_bp.post("")
@admin_required
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
@admin_required
def edit_station(station_id: int):
    station = ChargingStation.query.get_or_404(station_id)
    return render_template("stations/form.html", station=station, charging_types=VALID_CHARGING_TYPES, form=None)


@stations_bp.post("/<int:station_id>/update")
@admin_required
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
@admin_required
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
