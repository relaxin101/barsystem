"""Eigene Datenbank-Rolle für Berichte.

Die SQL-Abfragen der Bericht-Verwaltung sind freier Text von Admins, darum
laufen sie nicht über den App-Benutzer: der ist in Docker ein Postgres-Superuser.
SET ROLE reicht nicht, denn die Abfrage könnte einfach RESET ROLE enthalten.
Die Grenze ist deshalb ein eigener Login, der nur REPORT_TABLES lesen darf.

Die Rolle wird per CLI statt per Migration angelegt, weil Rollen nicht in
pg_dump enthalten sind und sie ein Restore auf ein frisches Volume überleben muss.
"""

import hashlib
import hmac

from flask import current_app
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from models import db

REPORT_ROLE = "bericht_leser"
# Neue Tabellen müssen hier eingetragen werden, sonst sehen Berichte sie nicht.
# user und einstellung fehlen absichtlich.
REPORT_TABLES = ("buchung", "mitglied", "artikel", "abrechnung", "aussendung", "bericht")


def _report_password(secret_key):
    """Aus SECRET_KEY abgeleitet, damit in der .env nichts dazukommt."""
    return hmac.new(secret_key.encode(), REPORT_ROLE.encode(), hashlib.sha256).hexdigest()


def sync_report_role(engine, secret_key):
    """Legt die Rolle an oder bringt sie auf den Sollzustand. Mehrfach aufrufbar."""
    password = _report_password(secret_key)  # nur Hex-Zeichen, Quoting unkritisch
    tables = ", ".join(REPORT_TABLES)
    with engine.begin() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname = :role"), {"role": REPORT_ROLE}
        ).scalar()
        verb = "ALTER" if exists else "CREATE"
        conn.execute(text(
            f"{verb} ROLE {REPORT_ROLE} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
            f"PASSWORD '{password}'"
        ))
        conn.execute(text(f"ALTER ROLE {REPORT_ROLE} SET default_transaction_read_only = on"))
        # Unter dem 30-s-Timeout von Gunicorn, sonst stirbt der Worker vor der Fehlermeldung
        conn.execute(text(f"ALTER ROLE {REPORT_ROLE} SET statement_timeout = '25s'"))
        conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {REPORT_ROLE}"))
        conn.execute(text(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {REPORT_ROLE}"))
        conn.execute(text(f"GRANT SELECT ON {tables} TO {REPORT_ROLE}"))


def report_engine():
    """Engine für Bericht-Abfragen.

    Gibt es die Rolle nicht, schlägt der Login fehl: es gibt absichtlich keinen
    Rückfall auf db.engine. Die engine options behalten die Session-Zeitzone,
    ohne sie würden Berichte wieder in UTC auswerten.
    """
    if db.engine.dialect.name != "postgresql":
        return db.engine

    engine = current_app.extensions.get("report_engine")
    if engine is None:
        url = db.engine.url.set(
            username=REPORT_ROLE,
            password=_report_password(current_app.config["SECRET_KEY"]),
        )
        engine = create_engine(
            url,
            poolclass=NullPool,
            **current_app.config.get("SQLALCHEMY_ENGINE_OPTIONS", {}),
        )
        current_app.extensions["report_engine"] = engine
    return engine
