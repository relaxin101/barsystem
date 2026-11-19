"""Hilfsfunktionen für die admin pages"""

import io
from datetime import timedelta
from functools import wraps
from typing import Optional
from flask import abort, request, send_file, flash, redirect
from flask_login import current_user, login_required
import pandas as pd
import numpy as np
from sqlalchemy import text
import re
from numbers import Real

from models import db, Mitglied
from utils.zeit import local_now, naive_local, parse_local, parse_local_ende


def superuser_required(view):
    """Wie login_required, angemeldete User ohne Superuser-Rolle bekommen 403."""

    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_superuser:
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def mitglied_sperren(mitglied_id):
    """Liest ein Mitglied frisch und sperrt die Zeile bis zum Commit.

    Sonst überschreiben sich gleichzeitige Buchungen gegenseitig das Guthaben.
    populate_existing, weil with_for_update ein schon geladenes Objekt nicht aktualisiert.
    """
    return db.session.get(Mitglied, mitglied_id, with_for_update=True, populate_existing=True)


# -------------------------
# 📄 Hilfsfunktion: Zeitraum ermitteln
# -------------------------
def parse_daterange():
    """Liest start/end-Parameter aus und gibt datetime-Objekte in Ortszeit zurück."""
    start_str = request.args.get("start")
    end_str = request.args.get("end")

    end_date = local_now()
    start_date = (end_date - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)

    try:
        if start_str:
            start_date = parse_local(start_str)
    except ValueError:
        pass
    try:
        if end_str:
            end_date = parse_local_ende(end_str)
    except ValueError:
        pass

    return start_date, end_date


# --------------------------------
# 🧠 Hilfsfunktion für den Export
# --------------------------------
def export_df_to_excel(df, filename):
    output = io.BytesIO()
    # Excel kennt keine Zeitzonen, Zeitstempel daher als Ortszeit ausgeben
    df = df.astype(object).map(naive_local)
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Daten")
    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def import_excel_to_db(file_stream, model, field_mapping, unique_field=None):
    """
    Liest eine Excel-Datei aus einem Stream ein und erstellt oder aktualisiert DB-Einträge.

    Args:
        file_stream: FileStorage oder BytesIO
        model: SQLAlchemy-Modell
        field_mapping: dict {db_field: excel_column_name}
        unique_field: optional, DB-Feldname für Updates (z.B. "id")
    """
    df = pd.read_excel(file_stream)
    df = df.replace({np.nan: None})

    def price_mapper(key, value):
        if "preis" in key and value is not None:
            return parse_betrag_cents(value)
        if key == "schwaerzungs_grenze" and value is not None:
            # Excel enthält Euro, die DB speichert Cent
            return parse_betrag_cents(value)
        return value

    def aktiv_mapper(key, value):
        if key in ("aktiv", "gepinnt") and value is not None:
            return value == 1 or value == "1" or value is True
        return value

    for _, row in df.iterrows():
        entry_data = {
            db_field: row.get(excel_col)
            for db_field, excel_col in field_mapping.items()
            if excel_col in df.columns
        }

        if not any(v is not None for v in entry_data.values()):
            continue  # leere Zeile überspringen

        # Werte transformieren
        entry_data = {
            k: aktiv_mapper(k, price_mapper(k, v))
            for k, v in entry_data.items()
        }

        # Prüfen auf bestehende Einträge anhand unique_field
        existing = None
        if unique_field and unique_field in entry_data and entry_data[unique_field] is not None:
            existing = model.query.filter_by(
                **{unique_field: entry_data[unique_field]}
            ).first()

        if existing:
            for key, value in entry_data.items():
                setattr(existing, key, value)
        else:
            # Bei neuen Einträgen die ID weglassen, damit die DB sie auto-generiert
            new_data = {k: v for k, v in entry_data.items()
                        if k != unique_field or entry_data.get(unique_field) is not None}
            db.session.add(model(**new_data))

    db.session.commit()

    # Sequenz nach Import zurücksetzen (nötig wenn IDs explizit gesetzt wurden)
    table = model.__tablename__
    db.session.execute(text(
        f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
        f"COALESCE((SELECT MAX(id)+1 FROM \"{table}\"), 1))"
    ))
    db.session.commit()


def handle_excel_import(db_fields, model, redirect_url, unique_field=None):
    """Zentrale Logik für den Excel-Import."""
    file = request.files.get("file")
    mapping = {f: request.form.get(f) for f in db_fields}

    if not file or file.filename == "":
        flash("Bitte wähle eine Datei aus.", "error")
        return redirect(redirect_url)

    try:
        import_excel_to_db(file.stream, model, mapping, unique_field=unique_field)
        flash(f"{model.__tablename__.capitalize()} erfolgreich importiert!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Fehler beim Import: {e}", "error")

    return redirect(redirect_url)


def suche_mitglied(search_term: str, limit: Optional[int] = None) -> list[Mitglied]:
    """Durchsucht aktive Mitglieder nach Name und Nickname iLike."""
    q = (
        Mitglied.query.filter(
            text(
                """
                aktiv = true and (
                    name iLike '%' || :search_term || '%'
                    or nickname iLike '%' || :search_term || '%'
                )
                """
            )
        )
        .params(search_term=search_term)
        .order_by(Mitglied.name)
    )
    if limit is not None:
        q = q.limit(limit)
    return q.all()

def normalize_line_endings(text_value: str) -> str:
    """CRLF/CR -> LF, inkl. von xlsxwriter escapetem CR (``_x000D_``)."""
    return (
        text_value.replace("_x000D_", "\r")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )


def unescape_excel_cr(value):
    """Macht das Escaping von ``\\r`` durch xlsxwriter beim Einlesen rückgängig."""
    if isinstance(value, str):
        return value.replace("_x000D_", "\r")
    return value


def parse_betrag_cents(raw) -> int:
    """Betrag (String oder Zahl) zu Cent konvertieren.

    Unterstützt deutsches Format (1.234,56) und englisches (1,234.56 / 1234.56).
    Numerische Excel-Zellen (int/float) werden direkt als Euro-Betrag gewertet.
    """
    if isinstance(raw, Real):
        return round(raw * 100)
    raw = raw.strip()
    # Deutsches Format: endet auf ,XX
    if re.search(r",\d{2}$", raw):
        raw = raw.replace(".", "").replace(",", ".")
    else:
        raw = raw.replace(",", "")
    return round(float(raw) * 100)




def calc_blacklist(mitglied: Mitglied, betrag: int) -> bool:
    """
    Berechnet ob das Mitglied geschwärzt werden soll.

    Args:
        mitglied: Das zu ändernde Mitglied
        betrag: Änderung des Guthabens (negativ = Abbuchung, positiv = Aufbuchung)
    """
    if mitglied.schwaerzungs_grenze is None:
        return False

    if mitglied.blacklist:
        return mitglied.guthaben + betrag < 0
    else:
        return (
            mitglied.guthaben >= mitglied.schwaerzungs_grenze
            and mitglied.guthaben + betrag < mitglied.schwaerzungs_grenze
        )
