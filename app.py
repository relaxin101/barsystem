from flask import Flask
from models import db, User
import config  # Importiere deine Konfigurationsdatei
from flask_migrate import Migrate
from flask_login import LoginManager
from blueprints.auth import auth_bp
from blueprints.admin import admin_bp
from blueprints.bar import bar_bp

app = Flask(__name__)

# Lade die Konfiguration aus config.py
app.config.from_object(config)

migrate = Migrate(app, db)

# Initialisiere die Datenbank mit der Flask-App
db.init_app(app)

# Initialisiere Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = (
    "auth.login"  # Wo der Benutzer hingeleitet wird, wenn er nicht angemeldet ist
)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(bar_bp)


# Template filter for formatting floats
@app.template_filter("float_format")
def float_format_filter(value):
    return "{:.2f}".format(value).replace(".", ",")


app.jinja_env.filters["float_format"] = float_format_filter


# --- App starten ---
if __name__ == "__main__":
    with app.app_context():
        # --- Admin-Benutzer überprüfen und erstellen ---
        if not User.query.filter_by(username=config.ADMIN_USERNAME).first():
            print(f"Erstelle initialen Admin-Benutzer: {config.ADMIN_USERNAME}")
            admin_user = User(username=config.ADMIN_USERNAME)
            admin_user.set_password(config.ADMIN_PASSWORD)  # Passwort wird gehasht
            db.session.add(admin_user)
            db.session.commit()
            print("Admin-Benutzer erfolgreich erstellt!")

        app.run(host="0.0.0.0", debug=True)
