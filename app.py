from flask import Flask

from config import config_by_name
from extensions import init_extensions
from routes import register_blueprints


def create_app(config_name: str = "default") -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_by_name[config_name])
    app.config.from_pyfile("config.py", silent=True)

    init_extensions(app)

    register_blueprints(app)
    return app


app = create_app()


if __name__ == "__main__":
    app.run()
