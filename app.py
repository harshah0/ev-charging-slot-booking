from flask import Flask
from flask_login import current_user

from config import config_by_name
from extensions import db
from extensions import init_extensions
from routes import register_blueprints
from services.booking_lifecycle import expire_due_bookings


def create_app(config_name: str = "default") -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_by_name[config_name])
    app.config.from_pyfile("config.py", silent=True)

    init_extensions(app)

    import models  # noqa: F401

    register_blueprints(app)

    @app.before_request
    def reconcile_booking_lifecycle():
        if not current_user.is_authenticated:
            return None

        expired_count = expire_due_bookings()
        if expired_count > 0:
            db.session.commit()
        return None

    @app.cli.command("sweep-bookings")
    def sweep_bookings_command() -> None:
        expired_count = expire_due_bookings()
        db.session.commit()
        print(f"Expired {expired_count} booking(s).")

    return app


app = create_app()


if __name__ == "__main__":
    app.run()
