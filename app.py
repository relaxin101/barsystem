from flask import Flask
from models import db, User
import config
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_apscheduler import APScheduler
from blueprints.auth import auth_bp
from blueprints.admin import admin_bp
from blueprints.admin.aussendungen import cronjob as aussendungen_cronjob
from utils.auto_aufbuchung import cronjob as auto_aufbuchung_cronjob
from blueprints.bar import bar_bp
from logging.config import dictConfig

dictConfig({
    'version': 1,
    'formatters': {'default': {
        'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
    }},
    'handlers': {'wsgi': {
        'class': 'logging.StreamHandler',
        'stream': 'ext://flask.logging.wsgi_errors_stream',
        'formatter': 'default',
    }},
    'root': {
        'level': 'INFO',
        'handlers': ['wsgi'],
    }
})

app = Flask(__name__)
app.config.from_object(config)

migrate = Migrate(app, db)
db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth.login"


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(bar_bp)


@app.template_filter("float_format")
def float_format_filter(value):
    return "{:.2f}".format(value).replace(".", ",")


app.jinja_env.filters["float_format"] = float_format_filter


if __name__ == "__main__":
    with app.app_context():
        if not User.query.filter_by(username=config.ADMIN_USERNAME).first():
            print(f"Erstelle initialen Admin-Benutzer: {config.ADMIN_USERNAME}")
            admin_user = User(username=config.ADMIN_USERNAME)
            admin_user.set_password(config.ADMIN_PASSWORD)
            db.session.add(admin_user)
            db.session.commit()
            print("Admin-Benutzer erfolgreich erstellt!")

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
    )
    scheduler.start()

    app.run(host="0.0.0.0", debug=True)