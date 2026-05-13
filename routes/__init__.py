from flask import Flask

from routes.auth import auth_bp
from routes.health import health_bp
from routes.home import home_bp


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(auth_bp)
    app.register_blueprint(home_bp)
    app.register_blueprint(health_bp)
