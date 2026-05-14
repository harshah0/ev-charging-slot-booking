"""Add booking lifecycle fields

Revision ID: c9d4e5f6a7b8
Revises: b8c3d4e5f6a7
Create Date: 2026-05-14 00:00:00.000000

"""
from datetime import datetime, timedelta, timezone

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c9d4e5f6a7b8"
down_revision = "b8c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()

    if connection.dialect.name == "sqlite":
        op.execute(sa.text("DROP TABLE IF EXISTS _alembic_tmp_bookings"))

    inspector = sa.inspect(connection)
    existing_columns = {column["name"] for column in inspector.get_columns("bookings")}

    columns_to_add = [
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("slot_released_at", sa.DateTime(timezone=True), nullable=True),
    ]

    for column in columns_to_add:
        if column.name not in existing_columns:
            op.add_column("bookings", column)

    existing_indexes = {index["name"] for index in inspector.get_indexes("bookings")}
    if "ix_bookings_status_expires_at" not in existing_indexes:
        op.create_index(
            "ix_bookings_status_expires_at",
            "bookings",
            ["booking_status", "expires_at"],
            unique=False,
        )

    _backfill_booking_lifecycle_data()


def _backfill_booking_lifecycle_data() -> None:
    connection = op.get_bind()
    bookings = sa.table(
        "bookings",
        sa.column("id", sa.Integer),
        sa.column("booking_time", sa.DateTime(timezone=True)),
        sa.column("charging_duration", sa.Integer),
        sa.column("booking_status", sa.String(length=20)),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("activated_at", sa.DateTime(timezone=True)),
        sa.column("expires_at", sa.DateTime(timezone=True)),
        sa.column("completed_at", sa.DateTime(timezone=True)),
        sa.column("expired_at", sa.DateTime(timezone=True)),
        sa.column("cancelled_at", sa.DateTime(timezone=True)),
        sa.column("slot_released_at", sa.DateTime(timezone=True)),
    )

    rows = connection.execute(
        sa.select(
            bookings.c.id,
            bookings.c.booking_time,
            bookings.c.charging_duration,
            bookings.c.booking_status,
            bookings.c.created_at,
        )
    ).fetchall()

    for row in rows:
        booking_time = row.booking_time or row.created_at or datetime.now(timezone.utc)
        if booking_time.tzinfo is None:
            booking_time = booking_time.replace(tzinfo=timezone.utc)
        else:
            booking_time = booking_time.astimezone(timezone.utc)

        expires_at = booking_time + timedelta(minutes=row.charging_duration)
        normalized_status = (row.booking_status or "active").strip().lower()
        if normalized_status == "confirmed":
            normalized_status = "active"

        update_values = {
            "booking_status": normalized_status,
            "activated_at": booking_time,
            "expires_at": expires_at,
        }

        if normalized_status == "cancelled":
            update_values["cancelled_at"] = row.created_at or booking_time
            update_values["slot_released_at"] = row.created_at or booking_time
        elif normalized_status == "completed":
            update_values["completed_at"] = row.created_at or booking_time
            update_values["slot_released_at"] = row.created_at or booking_time
        elif normalized_status == "expired":
            update_values["expired_at"] = row.created_at or booking_time
            update_values["slot_released_at"] = row.created_at or booking_time

        connection.execute(
            sa.update(bookings)
            .where(bookings.c.id == row.id)
            .values(**update_values)
        )


def downgrade():
    with op.batch_alter_table("bookings", schema=None) as batch_op:
        batch_op.drop_index("ix_bookings_status_expires_at")
        batch_op.alter_column(
            "booking_status",
            existing_type=sa.String(length=20),
            server_default=sa.text("'confirmed'"),
        )
        batch_op.drop_column("slot_released_at")
        batch_op.drop_column("cancelled_at")
        batch_op.drop_column("expired_at")
        batch_op.drop_column("completed_at")
        batch_op.drop_column("expires_at")
        batch_op.drop_column("activated_at")
