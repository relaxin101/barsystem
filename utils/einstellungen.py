"""Einstellungen, die im Adminpanel geändert werden können.

Reihenfolge: Zeile in der Datenbank, dann Umgebungsvariable (.env), dann
Standardwert. Bestehende Standorte laufen also ohne Zutun aus ihrer .env weiter.

Gelesen wird pro Request bzw. Scheduler-Lauf frisch aus der Datenbank. app.config
ginge nicht: jeder der Gunicorn-Worker hat seine eigene Kopie.

Zugangsdaten (BREVO_SECRET, IMAP_*) sind bewusst nicht hier, sie landen sonst in
jedem Datenbank-Backup. Siehe ENV_ONLY.
"""

import os
import re
from dataclasses import dataclass

from flask import g
from sqlalchemy import select

from models import db, Einstellung
from utils.zeit import utcnow


@dataclass(frozen=True)
class Definition:
    key: str
    label: str
    gruppe: str
    typ: str = "text"  # text, zahl, euro, regex
    standard: object = None
    superadmin: bool = False
    minimum: int = None
    hilfe: str = ""


GRUPPE_ALLGEMEIN = "Allgemein"
GRUPPE_AUSSENDUNGEN = "Aussendungen"
GRUPPE_AUTO = "Auto-Aufbuchung"

DEFINITIONEN = {d.key: d for d in (
    Definition("SITE_NAME", "Name der Barliste", GRUPPE_ALLGEMEIN, standard="Ergo Bibamus!"),
    Definition("SITE_NAME_ADMIN", "Name im Adminpanel", GRUPPE_ALLGEMEIN, standard="Creotorium"),
    Definition("SCHWAERZUNGS_TEXT", "Schwärzungstext", GRUPPE_ALLGEMEIN, standard="Du bist geschwärzt!"),
    Definition(
        "MINDEST_GUTHABEN", "Standard-Schwärzungslimit (€)", GRUPPE_ALLGEMEIN, typ="euro",
        hilfe="Gilt für neue Mitglieder, z. B. -50. Leer heißt: kein Limit.",
    ),
    Definition(
        "HOTLIST_DAYS", "Hotlist (Tage)", GRUPPE_ALLGEMEIN, typ="zahl", standard=14, minimum=1,
        hilfe="Wer in dieser Zeit gebucht hat, steht in der Barliste weiter oben.",
    ),
    Definition("RANKING_DEFAULT_STUNDEN", "Ranking-Zeitraum (Stunden)", GRUPPE_ALLGEMEIN, typ="zahl", standard=24, minimum=1),
    Definition(
        "RANKING_CONFIG_TTL_STUNDEN", "Ranking-Auswahl gilt (Stunden)", GRUPPE_ALLGEMEIN, typ="zahl",
        standard=12, minimum=1,
    ),

    Definition("BREVO_SENDER_MAIL", "Absender-Adresse", GRUPPE_AUSSENDUNGEN, superadmin=True, hilfe="Muss bei Brevo freigeschaltet sein."),
    Definition("BREVO_SENDER_NAME", "Absender-Name", GRUPPE_AUSSENDUNGEN, superadmin=True),
    Definition("BREVO_TEMPLATE", "Standard-Template (ID)", GRUPPE_AUSSENDUNGEN, typ="zahl", standard=0, superadmin=True, minimum=0),

    Definition("AUTO_SENDER", "Filter: Absender", GRUPPE_AUTO, superadmin=True, hilfe="Leer heißt: kein Filter."),
    Definition("AUTO_BETREFF", "Filter: Betreff", GRUPPE_AUTO, superadmin=True, hilfe="Leer heißt: kein Filter."),
    Definition("AUTO_KONTO_REGEX", "Regex für das Konto", GRUPPE_AUTO, typ="regex", superadmin=True, hilfe="Leer deaktiviert die Auto-Aufbuchung."),
    Definition("AUTO_KONTO_GROUP", "Gruppe im Konto-Regex", GRUPPE_AUTO, typ="zahl", standard=1, superadmin=True, minimum=0),
    Definition("AUTO_BETRAG_REGEX", "Regex für den Betrag", GRUPPE_AUTO, typ="regex", superadmin=True, hilfe="Leer deaktiviert die Auto-Aufbuchung."),
    Definition("AUTO_BETRAG_GROUP", "Gruppe im Betrag-Regex", GRUPPE_AUTO, typ="zahl", standard=1, superadmin=True, minimum=0),
)}

_REGEX_GRUPPEN = (
    ("AUTO_KONTO_REGEX", "AUTO_KONTO_GROUP"),
    ("AUTO_BETRAG_REGEX", "AUTO_BETRAG_GROUP"),
)

# Nur in der .env änderbar, im Adminpanel nur sichtbar. Geheime Werte
# werden nie angezeigt, nur ob sie gesetzt sind.
ENV_ONLY = {
    "APP_TIMEZONE": False,
    "APP_PORT": False,
    "ADMIN_USERNAME": False,
    "ADMIN_PASSWORD": True,
    "FLASK_DEBUG": False,
    "FLASK_SECRET_KEY": True,
    "DATABASE_HOST": False,
    "DATABASE_PORT": False,
    "DATABASE_NAME": False,
    "DATABASE_USERNAME": False,
    "DATABASE_PASSWORD": True,
    "BREVO_SECRET": True,
    "IMAP_HOST": False,
    "IMAP_PORT": False,
    "IMAP_USER": False,
    "IMAP_PASSWORD": True,
}


def _db_werte():
    if "einstellungen" not in g:
        g.einstellungen = dict(
            db.session.execute(select(Einstellung.key, Einstellung.value)).all()
        )
    return g.einstellungen


def rohwert(key):
    """Aktueller Wert als Text, so wie er im Formular steht."""
    werte = _db_werte()
    if key in werte:
        return werte[key] or ""  # das Excel-Backup macht aus "" None
    wert = os.environ.get(key)
    if wert is not None:
        return wert
    standard = DEFINITIONEN[key].standard
    return "" if standard is None else str(standard)


def einstellung(key):
    """Aktueller Wert im passenden Typ. Euro-Beträge kommen in Cent zurück."""
    definition = DEFINITIONEN[key]
    wert = rohwert(key)
    if definition.typ == "zahl":
        return int(wert) if wert else definition.standard
    if definition.typ == "euro":
        return round(float(wert) * 100) if wert else None
    return wert


def quelle(key):
    if key in _db_werte():
        return "geändert"
    return ".env" if key in os.environ else "Standard"


def _fehler_im_wert(definition, wert):
    if definition.typ == "zahl":
        try:
            zahl = int(wert)
        except ValueError:
            return "Bitte eine ganze Zahl eingeben."
        if definition.minimum is not None and zahl < definition.minimum:
            return f"Der Wert muss mindestens {definition.minimum} sein."
    elif definition.typ == "euro" and wert:
        try:
            float(wert.replace(",", "."))
        except ValueError:
            return "Bitte einen Betrag eingeben, z. B. -50."
    elif definition.typ == "regex":
        try:
            re.compile(wert)
        except re.error as e:
            return f"Ungültiger regulärer Ausdruck: {e}"
    return None


def pruefen(aenderungen):
    """Gibt {key: Fehlertext} zurück. Ein kaputter Regex würde sonst erst den Job treffen."""
    fehler = {}
    for key, wert in aenderungen.items():
        meldung = _fehler_im_wert(DEFINITIONEN[key], wert)
        if meldung:
            fehler[key] = meldung

    for regex_key, gruppe_key in _REGEX_GRUPPEN:
        if not {regex_key, gruppe_key} & aenderungen.keys() or {regex_key, gruppe_key} & fehler.keys():
            continue
        regex = aenderungen.get(regex_key, rohwert(regex_key))
        gruppe = aenderungen.get(gruppe_key, rohwert(gruppe_key))
        if not regex or not gruppe:
            continue
        try:
            anzahl = re.compile(regex).groups
        except re.error:  # unveränderter Wert aus der .env
            continue
        if int(gruppe) > anzahl:
            fehler[gruppe_key] = f"Der Regex hat nur {anzahl} Gruppe(n)."
    return fehler


def speichern(aenderungen, benutzer):
    for key, wert in aenderungen.items():
        if DEFINITIONEN[key].typ == "euro":
            wert = wert.replace(",", ".")
        zeile = db.session.get(Einstellung, key) or Einstellung(key=key)
        zeile.value = wert
        zeile.updated_at = utcnow()
        zeile.updated_by = benutzer
        db.session.add(zeile)
    db.session.commit()
    g.pop("einstellungen", None)


def zuruecksetzen(key):
    zeile = db.session.get(Einstellung, key)
    if zeile:
        db.session.delete(zeile)
        db.session.commit()
    g.pop("einstellungen", None)


def env_status():
    """(Name, angezeigter Wert) für alles, was nur in der .env geändert werden kann."""
    status = []
    for key, geheim in ENV_ONLY.items():
        wert = os.environ.get(key)
        if geheim:
            status.append((key, "gesetzt" if wert else "fehlt"))
        else:
            status.append((key, wert or "—"))
    return status
