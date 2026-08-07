from datetime import datetime
import os
from flask import Flask, jsonify
from flask_migrate import Migrate
from flask_login import LoginManager
from logging.config import dictConfig
from sqlalchemy import text


def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get("APP_ENV", "development")

    from config import config_map
    cfg = config_map.get(config_name, config_map["default"])

    app = Flask(__name__)
    app.config.from_object(cfg)

    dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"default": {
            "format": "[%(asctime)s] %(levelname)s in %(module)s: %(message)s",
        }},
        "handlers": {"wsgi": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
            "formatter": "default",
        }},
        "root": {
            "level": "DEBUG" if app.config.get("DEBUG") else "INFO",
            "handlers": ["wsgi"],
        },
    })

    from models import db, User
    Migrate(app, db)
    db.init_app(app)

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from blueprints.auth import auth_bp
    from blueprints.admin import admin_bp
    from blueprints.bar import bar_bp
    from blueprints.ranking import ranking_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(bar_bp)
    app.register_blueprint(ranking_bp)

    @app.template_filter("float_format")
    def float_format_filter(value):
        return "{:.2f}".format(value).replace(".", ",")

    @app.route("/healthz")
    def healthz():
        """Authoritative "can the system take bookings" signal.

        Unlike a bare TCP/HTTP check, this fails when the app is up but the
        database is not — the case the kiosk boot wait-loop actually needs
        to distinguish so Chromium never starts onto an error page.
        No auth: it leaks nothing. Excluded from access logs (see
        gunicorn.conf.py) since it's polled every few seconds.
        """
        from utils.version import get_version

        try:
            db.session.execute(text("SELECT 1"))
        except Exception:
            return jsonify(status="error"), 503
        return jsonify(status="ok", version=get_version()), 200

    @app.cli.command("create-admin")
    def create_admin_cmd():
        """Create the initial admin user if it doesn't exist."""
        admin_username = app.config["ADMIN_USERNAME"]
        admin_password = app.config["ADMIN_PASSWORD"]
        if not User.query.filter_by(username=admin_username).first():
            print(f"Creating admin user: {admin_username}")
            user = User(username=admin_username)
            user.set_password(admin_password)
            db.session.add(user)
            db.session.commit()
            print("Done.")
        else:
            print(f"Admin user '{admin_username}' already exists.")

    return app


def start_scheduler(app):
    """Start the background job scheduler.

    This must be called in exactly one process. Under gunicorn it is invoked
    from a post_fork hook gated to a single worker (see gunicorn.conf.py), so
    the scheduler's background thread lives inside a real, long-lived worker
    rather than in the arbiter (whose threads are not inherited across fork).
    """
    if app.config.get("TESTING"):
        return

    from blueprints.admin.aussendungen import cronjob as aussendungen_cronjob
    from utils.auto_aufbuchung import cronjob as auto_aufbuchung_cronjob
    from flask_apscheduler import APScheduler

    scheduler = APScheduler()
    scheduler.init_app(app)
    scheduler.add_job(
        id="aussendungen",
        func=lambda: aussendungen_cronjob(app),
        trigger="interval",
        seconds=60,
    )
    scheduler.add_job(
        id="auto_aufbuchung",
        func=lambda: auto_aufbuchung_cronjob(app),
        trigger="interval",
        seconds=60,
        next_run_time=datetime.now(),
    )
    scheduler.start()
    return scheduler


if __name__ == "__main__":
    app = create_app(os.environ.get("APP_ENV", "development"))
    # When the reloader is active, only start the scheduler in the reloaded
    # child process (WERKZEUG_RUN_MAIN is set there) to avoid running it twice.
    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        start_scheduler(app)
    app.run(host="0.0.0.0", debug=app.config["DEBUG"])
