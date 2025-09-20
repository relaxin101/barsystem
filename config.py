import os

# PostgreSQL Database Configuration
# Uses environment variables for database connection
DATABASE_NAME = os.environ.get('DATABASE_NAME', 'postgres')
DATABASE_USERNAME = os.environ.get('DATABASE_USERNAME', 'postgres')
DATABASE_PASSWORD = os.environ.get('DATABASE_PASSWORD', 'postgres')
DATABASE_HOST = os.environ.get('DATABASE_HOST', 'localhost')
DATABASE_PORT = os.environ.get('DATABASE_PORT', '5432')

# PostgreSQL Database URI
SQLALCHEMY_DATABASE_URI = (
    f"postgresql://{DATABASE_USERNAME}:{DATABASE_PASSWORD}@"
    f"{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}"
)

# Deaktiviert eine Warnung von SQLAlchemy, die nicht unbedingt notwendig ist.
SQLALCHEMY_TRACK_MODIFICATIONS = False

# Ein geheimer Schlüssel für Flask-Sitzungen und Sicherheitsfunktionen.
# Ändere diesen Wert in der echten Anwendung zu einem langen, zufälligen String!
SECRET_KEY = os.environ.get('SECRET_KEY', 'asdfasdfasdfasdf')

# --- Admin Zugang für Flask-Login (für den Admin-Bereich) ---
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'password!')