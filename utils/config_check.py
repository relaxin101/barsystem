"""Fail-fast validation of production config against shipped defaults.

Two silent failure classes motivated this: env naming drift (readme said
SECRET_KEY, code reads FLASK_SECRET_KEY — following the readme left the
insecure default active silently) and shipped defaults surviving into
production. With 5432 published to the LAN, a default DB password is a
real exposure, not a cosmetic one.
"""

from sqlalchemy.engine import make_url

INSECURE_SECRET_KEYS = {"dev-secret-key-change-in-prod", "supersecret"}
INSECURE_DB_PASSWORDS = {"postgres", "bibamus"}
INSECURE_ADMIN_PASSWORDS = {"password", "password!"}


def find_insecure_defaults(config):
    """Return (errors, warnings) — lists of messages naming the offending variable.

    Errors must block boot in production; warnings are logged only.
    """
    errors = []
    warnings = []

    if config.get("SECRET_KEY") in INSECURE_SECRET_KEYS:
        errors.append(
            "FLASK_SECRET_KEY is the shipped default — set a random string in .env"
        )

    try:
        db_password = make_url(config.get("SQLALCHEMY_DATABASE_URI", "")).password
    except Exception:
        db_password = None
    if db_password in INSECURE_DB_PASSWORDS:
        errors.append(
            "DATABASE_PASSWORD is the shipped default — port 5432 is published, "
            "this is exposed to the LAN"
        )

    if config.get("ADMIN_PASSWORD") in INSECURE_ADMIN_PASSWORDS:
        errors.append("ADMIN_PASSWORD is the shipped default — choose a real password")

    if config.get("ADMIN_USERNAME") == "admin":
        warnings.append("ADMIN_USERNAME is the default 'admin'")

    return errors, warnings


def validate_production_config(config):
    """Raise RuntimeError (refusing to boot) if shipped secrets are still active."""
    errors, warnings = find_insecure_defaults(config)
    if errors:
        raise RuntimeError(
            "Refusing to start with insecure default config:\n  - "
            + "\n  - ".join(errors)
        )
    return warnings
