from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO


db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
socketio = SocketIO()


def init_extensions(app) -> None:
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db, compare_type=True)
    socketio.init_app(
        app,
        cors_allowed_origins=app.config.get("SOCKETIO_CORS_ORIGINS", "*"),
        async_mode=app.config.get("SOCKETIO_ASYNC_MODE"),
        message_queue=app.config.get("SOCKETIO_MESSAGE_QUEUE"),
        ping_interval=app.config.get("SOCKETIO_PING_INTERVAL", 25),
        ping_timeout=app.config.get("SOCKETIO_PING_TIMEOUT", 60),
        max_http_buffer_size=app.config.get("SOCKETIO_MAX_HTTP_BUFFER_SIZE", 1000000),
        manage_session=False,
    )
