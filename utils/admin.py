"""Hilfsfunktionen für die admin pages"""

import io
from datetime import datetime, timedelta
from flask import request, send_file, flash, redirect
import pandas as pd
import numpy as np
from sqlalchemy import text
import re

from models import db, Mitglied


# -------------------------
# 📄 Hilfsfunktion: Zeitraum ermitteln
# -------------------------
def parse_daterange():
    """Liest start/end-Parameter aus und gibt datetime-Objekte zurück."""
    start_str = request.args.get("start")
    end_str = request.args.get("end")

    now = datetime.now()
    end_date = now.replace(second=0, microsecond=0)
    start_date = (end_date - timedelta(days=30)).replace(hour=0, minute=0)

    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        if start_str:
            try:
                start_date = datetime.strptime(start_str, fmt)
                break
            except ValueError:
                continue

    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        if end_str:
            try:
                end_date = datetime.strptime(end_str, fmt)
                break
            except ValueError:
                continue

    return start_date, end_date


# --------------------------------
# 🧠 Hilfsfunktion für den Export
# --------------------------------
def export_model_to_excel(model, columns, filename):
    data = model.query.all()
    rows = [{col: getattr(d, col) for col in columns} for d in data]
    df = pd.DataFrame(rows)
    return export_df_to_excel(df, filename)


def export_df_to_excel(df, filename):
    output = io.BytesIO()
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


def suche_mitglied(search_term: str) -> list:
    """Durchsucht aktive Mitglieder nach Name und Nickname (PostgreSQL Full-Text + iLike)."""
    return (
        Mitglied.query.filter(
            text(
                """
                aktiv = true and (
                    to_tsvector(name || ' ' || coalesce(nickname, '')) @@ to_tsquery(:search_term)
                    or name iLike '%' || :search_term || '%'
                    or nickname iLike '%' || :search_term || '%'
                )
                """
            )
        )
        .params(search_term=search_term)
        .order_by(Mitglied.name)
        .all()
    )

def parse_betrag_cents(raw: str) -> int:
    """Betrag-String zu Cent konvertieren.

    Unterstützt deutsches Format (1.234,56) und englisches (1,234.56 / 1234.56).
    """
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
