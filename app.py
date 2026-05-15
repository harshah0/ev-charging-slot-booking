import os

import click
from flask import Flask
from flask_login import current_user

from config import config_by_name
from extensions import db, socketio
from extensions import init_extensions
from routes import register_blueprints
from services.booking_lifecycle import expire_due_bookings
from seed import run_seed
from services.realtime import register_socketio_events
from services.realtime import emit_live_booking_event


def create_app(config_name: str = "default") -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_by_name[config_name])
    app.config.from_pyfile("config.py", silent=True)

    init_extensions(app)

    import models  # noqa: F401

    register_blueprints(app)

    # In production, serve static files efficiently using WhiteNoise if available
    try:
        if not app.debug and os.getenv("USE_WHITENOISE", "true").lower() == "true":
            from whitenoise import WhiteNoise

            static_root = app.static_folder or "static"
            app.wsgi_app = WhiteNoise(app.wsgi_app, root=static_root, prefix="/static/")
    except Exception:
        # Do not break startup if whitenoise is not available; platform may serve static files instead
        pass

    @app.before_request
    def reconcile_booking_lifecycle():
        if not current_user.is_authenticated:
            return None

        expired_bookings = expire_due_bookings()
        if expired_bookings:
            db.session.commit()
            for booking in expired_bookings:
                emit_live_booking_event(action="expired", booking=booking, message="Booking expired and slot released.")
        return None

    @app.cli.command("sweep-bookings")
    def sweep_bookings_command() -> None:
        expired_bookings = expire_due_bookings()
        db.session.commit()
        print(f"Expired {len(expired_bookings)} booking(s).")

    @app.cli.group("seed")
    def seed_group() -> None:
        """Seed the database with safe demo data."""

    @seed_group.command("run")
    def seed_run_command() -> None:
        database_backend = db.engine.url.get_backend_name()
        if database_backend != "sqlite" and os.getenv("ALLOW_PRODUCTION_SEEDING", "false").lower() != "true":
            raise click.ClickException(
                "Refusing to seed a production database. Set ALLOW_PRODUCTION_SEEDING=true to confirm."
            )

        result = run_seed()
        print(
            "Seed completed: "
            f"admin_created={result['admin_created']}, "
            f"stations_created={result['stations_created']}, "
            f"stations_updated={result['stations_updated']}"
        )

    register_socketio_events()
    return app


app = create_app()


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=app.debug)
