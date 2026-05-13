from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = "auth.login"


@login_manager.user_loader
def load_user(user_id: str):
	return None


def init_extensions(app) -> None:
	db.init_app(app)
	login_manager.init_app(app)
	migrate.init_app(app, db, compare_type=True)
