import os

# Pfad zur SQLite-Datenbankdatei
# Die Datenbankdatei wird im Hauptverzeichnis des Projekts gespeichert.
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(BASE_DIR, 'barsystem.db')

# Deaktiviert eine Warnung von SQLAlchemy, die nicht unbedingt notwendig ist.
SQLALCHEMY_TRACK_MODIFICATIONS = False

# Ein geheimer Schlüssel für Flask-Sitzungen und Sicherheitsfunktionen.
# Ändere diesen Wert in der echten Anwendung zu einem langen, zufälligen String!
SECRET_KEY = 'dein_sehr_geheimer_schluessel_hier_aendern'

# --- Admin Zugang für Flask-Login (für den Admin-Bereich) ---
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'Herulia1908!' # AENDERE DIESES PASSWORT SOFORT!