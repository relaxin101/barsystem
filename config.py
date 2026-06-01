import os

# PostgreSQL Database Configuration
# Uses environment variables for database connection
DATABASE_NAME = os.environ.get("DATABASE_NAME", "postgres")
DATABASE_USERNAME = os.environ.get("DATABASE_USERNAME", "postgres")
DATABASE_PASSWORD = os.environ.get("DATABASE_PASSWORD", "postgres")
DATABASE_HOST = os.environ.get("DATABASE_HOST", "localhost")
DATABASE_PORT = os.environ.get("DATABASE_PORT", "5432")

# PostgreSQL Database URI
SQLALCHEMY_DATABASE_URI = os.environ.get("SQLALCHEMY_DATABASE_URI", 
    f"postgresql://{DATABASE_USERNAME}:{DATABASE_PASSWORD}@"
    f"{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}"
)

# Deaktiviert eine Warnung von SQLAlchemy, die nicht unbedingt notwendig ist.
SQLALCHEMY_TRACK_MODIFICATIONS = False

# Ein geheimer Schlüssel für Flask-Sitzungen und Sicherheitsfunktionen.
# Ändere diesen Wert in der echten Anwendung zu einem langen, zufälligen String!
SECRET_KEY = os.environ.get("SECRET_KEY", "asdfasdfasdfasdf")

# --- Admin Zugang für Flask-Login (für den Admin-Bereich) ---
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "password!")


_guthaben = os.environ.get("MINDEST_GUTHABEN", None)
MINDEST_GUTHABEN = int(100*float(_guthaben)) if _guthaben else None


# Aussendungen specials
BREVO_SECRET = os.environ.get("BREVO_SECRET")
BREVO_SENDER_MAIL = os.environ.get("BREVO_SENDER_MAIL")
BREVO_SENDER_NAME = os.environ.get("BREVO_SENDER_NAME")
BREVO_TEMPLATE = int(os.environ.get("BREVO_TEMPLATE",0))

# Auto-Aufbuchung via IMAP (alle optional — fehlt IMAP_HOST/USER/PASSWORD, wird der Job übersprungen)
IMAP_HOST = os.environ.get("IMAP_HOST")
IMAP_PORT = int(os.environ.get("IMAP_PORT", "993"))
IMAP_USER = os.environ.get("IMAP_USER")
IMAP_PASSWORD = os.environ.get("IMAP_PASSWORD")
AUTO_SENDER = os.environ.get("AUTO_SENDER")           # Absender-Filter (optional)
AUTO_BETREFF = os.environ.get("AUTO_BETREFF")         # Betreff-Filter (optional, Teilstring)
AUTO_KONTO_REGEX = os.environ.get("AUTO_KONTO_REGEX")         # Regex → Mitglied-Name oder -E-Mail
AUTO_KONTO_GROUP = int(os.environ.get("AUTO_KONTO_GROUP", "1")) # Welche Capture-Group verwenden (default: 1)
AUTO_BETRAG_REGEX = os.environ.get("AUTO_BETRAG_REGEX")         # Regex → Betrag in €
AUTO_BETRAG_GROUP = int(os.environ.get("AUTO_BETRAG_GROUP", "1")) # Welche Capture-Group verwenden (default: 1)
