"""Zeitzonen-Helfer.

Die Datenbank speichert Zeitpunkte (timestamptz), in Python sind sie immer
aware UTC. In Ortszeit (APP_TIMEZONE) wird nur an den Rändern umgerechnet:
Anzeige, Formular-Eingaben und Excel.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import config

LOCAL_TZ = ZoneInfo(config.APP_TIMEZONE)


def utcnow():
    """Jetzt als aware UTC – für alles, was gespeichert oder mit DB-Werten verglichen wird."""
    return datetime.now(timezone.utc)


def local_now():
    """Jetzt in Ortszeit – für Vorgabewerte und Dateinamen."""
    return datetime.now(LOCAL_TZ)


def parse_local(value):
    """ISO-String aus einem Formular (datetime-local) als Ortszeit lesen."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=LOCAL_TZ)
    return parsed


def naive_local(value):
    """Aware datetime zu naiver Ortszeit (für Excel), alles andere bleibt unverändert."""
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.astimezone(LOCAL_TZ).replace(tzinfo=None)
    return value


def naive_utc(value):
    """Aware datetime zu naivem UTC (Format der Excel-Backups), alles andere bleibt unverändert."""
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value
