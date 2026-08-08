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
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "password!")

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

    MINDEST_GUTHABEN = _parse_mindest_guthaben()
    SCHWAERZUNGS_TEXT = os.environ.get("SCHWAERZUNGS_TEXT", "Du bist geschwärzt!")
    RANKING_DEFAULT_STUNDEN = int(os.environ.get("RANKING_DEFAULT_STUNDEN", 24))
    RANKING_CONFIG_TTL_STUNDEN = int(os.environ.get("RANKING_CONFIG_TTL_STUNDEN", 12))
    HOTLIST_DAYS = int(os.environ.get("HOTLIST_DAYS", 14))

    BREVO_SECRET = os.environ.get("BREVO_SECRET")
    BREVO_SENDER_MAIL = os.environ.get("BREVO_SENDER_MAIL")
    BREVO_SENDER_NAME = os.environ.get("BREVO_SENDER_NAME")
    BREVO_TEMPLATE = int(os.environ.get("BREVO_TEMPLATE", 0))

    IMAP_HOST = os.environ.get("IMAP_HOST")
    IMAP_PORT = int(os.environ.get("IMAP_PORT", 993))
    IMAP_USER = os.environ.get("IMAP_USER")
    IMAP_PASSWORD = os.environ.get("IMAP_PASSWORD")
    AUTO_SENDER = os.environ.get("AUTO_SENDER")
    AUTO_BETREFF = os.environ.get("AUTO_BETREFF")
    AUTO_KONTO_REGEX = os.environ.get("AUTO_KONTO_REGEX")
    AUTO_KONTO_GROUP = int(os.environ.get("AUTO_KONTO_GROUP", 1))
    AUTO_BETRAG_REGEX = os.environ.get("AUTO_BETRAG_REGEX")
    AUTO_BETRAG_GROUP = int(os.environ.get("AUTO_BETRAG_GROUP", 1))


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

# Module-level variables kept for backward compatibility.
# brevo.py imports these directly; auto_aufbuchung.py accesses them via `import config`.
MINDEST_GUTHABEN = _parse_mindest_guthaben()

SCHWAERZUNGS_TEXT = os.environ.get("SCHWAERZUNGS_TEXT", "Du bist geschwärzt!")
RANKING_DEFAULT_STUNDEN = int(os.environ.get("RANKING_DEFAULT_STUNDEN", 24))
RANKING_CONFIG_TTL_STUNDEN = int(os.environ.get("RANKING_CONFIG_TTL_STUNDEN", 12))
HOTLIST_DAYS = int(os.environ.get("HOTLIST_DAYS", 14))

BREVO_SECRET = os.environ.get("BREVO_SECRET")
BREVO_SENDER_MAIL = os.environ.get("BREVO_SENDER_MAIL")
BREVO_SENDER_NAME = os.environ.get("BREVO_SENDER_NAME")
BREVO_TEMPLATE = int(os.environ.get("BREVO_TEMPLATE", 0))

IMAP_HOST = os.environ.get("IMAP_HOST")
IMAP_PORT = int(os.environ.get("IMAP_PORT", 993))
IMAP_USER = os.environ.get("IMAP_USER")
IMAP_PASSWORD = os.environ.get("IMAP_PASSWORD")
AUTO_SENDER = os.environ.get("AUTO_SENDER")
AUTO_BETREFF = os.environ.get("AUTO_BETREFF")
AUTO_KONTO_REGEX = os.environ.get("AUTO_KONTO_REGEX")
AUTO_KONTO_GROUP = int(os.environ.get("AUTO_KONTO_GROUP", 1))
AUTO_BETRAG_REGEX = os.environ.get("AUTO_BETRAG_REGEX")
AUTO_BETRAG_GROUP = int(os.environ.get("AUTO_BETRAG_GROUP", 1))

DEBUG = os.environ.get("FLASK_DEBUG", "0").lower() in ("1", "true")
