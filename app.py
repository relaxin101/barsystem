from datetime import datetime
import logging
import os
from flask import Flask, jsonify
from flask_migrate import Migrate
from flask_login import LoginManager
from logging.config import dictConfig
from sqlalchemy import text
from sqlalchemy.engine import make_url


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

    if not app.config.get("DEBUG") and not app.config.get("TESTING"):
        from utils.config_check import validate_production_config

        for warning in validate_production_config(app.config):
            logging.getLogger(__name__).warning(warning)

    # Session-Zeitzone: damit rechnet Postgres timestamptz-Spalten auch in
    # gespeicherten Berichten (DATE, TO_CHAR, Datumsliterale) in Ortszeit.
    if make_url(app.config["SQLALCHEMY_DATABASE_URI"]).get_backend_name() == "postgresql":
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "connect_args": {"options": f"-c timezone={app.config['APP_TIMEZONE']}"}
        }

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

    @app.template_filter("local_time")
    def local_time_filter(value, fmt="%d.%m.%Y %H:%M"):
        from utils.zeit import LOCAL_TZ

        return value.astimezone(LOCAL_TZ).strftime(fmt) if value else ""

    from utils.einstellungen import einstellung
    app.jinja_env.globals["einstellung"] = einstellung

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

    @app.cli.command("sync-report-role")
    def sync_report_role_cmd():
        """Legt die Datenbank-Rolle für Berichte an bzw. bringt sie auf den Sollzustand."""
        from utils.bericht_engine import REPORT_ROLE, sync_report_role

        if db.engine.dialect.name != "postgresql":
            print("Skipped: only needed on Postgres.")
            return
        sync_report_role(db.engine, app.config["SECRET_KEY"])
        print(f"Report role '{REPORT_ROLE}' is up to date.")

    @app.cli.command("backup")
    def backup_cmd():
        """Write a verified, gzip'd pg_dump to BACKUP_DIR.

        Mirrors the host-side backup script's completeness check, so host
        cron shrinks to one line calling this instead of reimplementing
        `docker compose exec db pg_dump` per installation.
        """
        from utils.backup import create_backup

        output_dir = os.environ.get("BACKUP_DIR", "/app/backups")
        try:
            path = create_backup(app.config["SQLALCHEMY_DATABASE_URI"], output_dir)
        except RuntimeError as e:
            print(f"Backup failed: {e}")
            raise SystemExit(1)
        print(f"Backup written to {path}")

    return app


SCHEDULER_LOCK_ID = 727272  # arbitrary app-wide Postgres advisory-lock key

_scheduler_lock_conn = None  # held open for the process lifetime


def _acquire_scheduler_lock(app):
    """Try to become the one scheduler process via a session-level advisory lock.

    The lock lives as long as the dedicated connection; if the owning worker
    dies, Postgres releases it and the next worker that calls
    start_scheduler (e.g. its respawn) wins. Non-Postgres DBs have no lock.
    """
    global _scheduler_lock_conn
    from models import db

    with app.app_context():
        engine = db.engine
        if engine.dialect.name != "postgresql":
            return True
        conn = engine.connect()
        got = conn.exec_driver_sql(
            "SELECT pg_try_advisory_lock(%s)" % SCHEDULER_LOCK_ID
        ).scalar()
        if not got:
            conn.close()
            return False
        _scheduler_lock_conn = conn
        return True


def start_scheduler(app):
    """Start the background job scheduler, unless another process already runs it.

    Safe to call from every gunicorn worker (see gunicorn.conf.py): a Postgres
    advisory lock guarantees only one of them actually starts the scheduler,
    and it is called from post_worker_init so the scheduler's thread lives in a
    real, long-lived worker rather than in the arbiter (threads are not
    inherited across fork). Returns None in processes that lost the lock.
    """
    if app.config.get("TESTING"):
        return

    if not _acquire_scheduler_lock(app):
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
