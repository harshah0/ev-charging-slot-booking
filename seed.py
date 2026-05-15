from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import or_

from extensions import db
from models import ChargingStation, User
from models.user import UserRole


@dataclass(frozen=True)
class SeedAdmin:
    username: str = "admin"
    email: str = "admin@ev.com"
    password: str = "Admin123"


@dataclass(frozen=True)
class SeedStation:
    station_name: str
    address: str
    city: str
    state: str
    latitude: str
    longitude: str
    total_slots: int
    available_slots: int
    charging_type: str


ADMIN = SeedAdmin(
    username=os.getenv("SEED_ADMIN_USERNAME", "admin"),
    email=os.getenv("SEED_ADMIN_EMAIL", "admin@ev.com"),
    password=os.getenv("SEED_ADMIN_PASSWORD", "Admin123"),
)

DEMO_STATIONS: list[SeedStation] = [
    SeedStation(
        station_name="Central EV Hub",
        address="100 Main Street",
        city="Bengaluru",
        state="Karnataka",
        latitude="12.9716",
        longitude="77.5946",
        total_slots=8,
        available_slots=8,
        charging_type="DC Fast Charging",
    ),
    SeedStation(
        station_name="Northside Charge Point",
        address="42 Lake Road",
        city="Hyderabad",
        state="Telangana",
        latitude="17.3850",
        longitude="78.4867",
        total_slots=6,
        available_slots=6,
        charging_type="AC Fast Charging",
    ),
    SeedStation(
        station_name="Airport Rapid Charge",
        address="Terminal 2 Road",
        city="Chennai",
        state="Tamil Nadu",
        latitude="13.0827",
        longitude="80.2707",
        total_slots=10,
        available_slots=10,
        charging_type="DC Fast Charging",
    ),
]


def seed_admin_user() -> tuple[User, bool]:
    user_by_email = User.query.filter_by(email=ADMIN.email).one_or_none()
    user_by_username = User.query.filter_by(username=ADMIN.username).one_or_none()

    if user_by_email is not None and user_by_username is not None and user_by_email.id != user_by_username.id:
        raise ValueError(
            "Seed conflict: admin email and username are already assigned to different users."
        )

    user = user_by_email or user_by_username
    created = False

    if user is None:
        user = User(
            username=ADMIN.username,
            email=ADMIN.email,
            role=UserRole.ADMIN.value,
            wallet_balance=Decimal("0.00"),
        )
        user.set_password(ADMIN.password)
        db.session.add(user)
        created = True
    else:
        user.username = ADMIN.username
        user.email = ADMIN.email
        user.role = UserRole.ADMIN.value

    return user, created


def seed_demo_stations() -> tuple[int, int]:
    created_count = 0
    updated_count = 0

    for station_data in DEMO_STATIONS:
        station = ChargingStation.query.filter_by(station_name=station_data.station_name).one_or_none()

        if station is None:
            station = ChargingStation(
                station_name=station_data.station_name,
                address=station_data.address,
                city=station_data.city,
                state=station_data.state,
                latitude=station_data.latitude,
                longitude=station_data.longitude,
                total_slots=station_data.total_slots,
                available_slots=station_data.available_slots,
                charging_type=station_data.charging_type,
            )
            db.session.add(station)
            created_count += 1
            continue

        station.address = station_data.address
        station.city = station_data.city
        station.state = station_data.state
        station.latitude = station_data.latitude
        station.longitude = station_data.longitude
        station.total_slots = station_data.total_slots
        station.available_slots = min(station_data.available_slots, station_data.total_slots)
        station.charging_type = station_data.charging_type
        updated_count += 1

    return created_count, updated_count


def run_seed() -> dict[str, int]:
    with db.session.no_autoflush:
        admin_user, admin_created = seed_admin_user()
        station_created, station_updated = seed_demo_stations()

    db.session.commit()

    return {
        "admin_created": int(admin_created),
        "stations_created": station_created,
        "stations_updated": station_updated,
    }
