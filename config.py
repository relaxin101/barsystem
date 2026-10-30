import logging
import os


def _parse_mindest_guthaben():
    val = os.environ.get("MINDEST_GUTHABEN")
    return int(100 * float(val)) if val else None


def _resolve_secret_key():
    # The readme used to say `SECRET_KEY`, but the code has always read
    # `FLASK_SECRET_KEY` — following the old readme left the insecure
    # default active silently. Accept the old name for one transition
    # release so already-deployed .env files with SECRET_KEY still work.
    value = os.environ.get("FLASK_SECRET_KEY")
    if value:
        return value
    legacy = os.environ.get("SECRET_KEY")
    if legacy:
        logging.getLogger(__name__).warning(
            "SECRET_KEY is deprecated, rename it to FLASK_SECRET_KEY in .env"
        )
        return legacy
    return "dev-secret-key-change-in-prod"


class BaseConfig:
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = _resolve_secret_key()
    SESSION_COOKIE_SAMESITE = "Lax"
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "password!")
    APP_TIMEZONE = os.environ.get("APP_TIMEZONE", "Europe/Vienna")

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "SQLALCHEMY_DATABASE_URI",
        "postgresql://{username}:{password}@{host}:{port}/{name}".format(
            username=os.environ.get("DATABASE_USERNAME", "postgres"),
            password=os.environ.get("DATABASE_PASSWORD", "postgres"),
            host=os.environ.get("DATABASE_HOST", "localhost"),
            port=os.environ.get("DATABASE_PORT", "5432"),
            name=os.environ.get("DATABASE_NAME", "postgres"),
        ),
    )

    BREVO_SECRET = os.environ.get("BREVO_SECRET")

    IMAP_HOST = os.environ.get("IMAP_HOST")
    IMAP_PORT = int(os.environ.get("IMAP_PORT", 993))
    IMAP_USER = os.environ.get("IMAP_USER")
    IMAP_PASSWORD = os.environ.get("IMAP_PASSWORD")


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class ProductionConfig(BaseConfig):
    DEBUG = False


class TestingConfig(BaseConfig):
    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test-secret-key"
    ADMIN_USERNAME = "testadmin"
    ADMIN_PASSWORD = "testpassword"


config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}

# Module-level variables for values that stay in .env (see utils/einstellungen.py).
# brevo.py and auto_aufbuchung.py read them here; migration 7906e1e0673b needs MINDEST_GUTHABEN.
MINDEST_GUTHABEN = _parse_mindest_guthaben()
APP_TIMEZONE = os.environ.get("APP_TIMEZONE", "Europe/Vienna")


BREVO_SECRET = os.environ.get("BREVO_SECRET")

IMAP_HOST = os.environ.get("IMAP_HOST")
IMAP_PORT = int(os.environ.get("IMAP_PORT", 993))
IMAP_USER = os.environ.get("IMAP_USER")
IMAP_PASSWORD = os.environ.get("IMAP_PASSWORD")

DEBUG =os.environ.get("FLASK_DEBUG", "0").lower() in ("1", "true")
