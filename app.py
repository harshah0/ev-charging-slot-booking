from flask import Flask

from config import config_by_name
from extensions import db, login_manager, migrate
from routes import register_blueprints


def create_app(config_name: str = "default") -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_by_name[config_name])
    app.config.from_pyfile("config.py", silent=True)

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    register_blueprints(app)
    return app


app = create_app()


if __name__ == "__main__":
    app.run()
