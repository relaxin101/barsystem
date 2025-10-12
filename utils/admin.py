"""Hilfsfunktionen für die admin pages"""

import io

from datetime import datetime, timedelta
from flask import request, send_file, flash, redirect
import pandas as pd
import numpy as np

from models import db


# -------------------------
# 📄 Hilfsfunktion: Zeitraum ermitteln
# -------------------------
def parse_daterange():
    """Liest start/end-Parameter aus und gibt Datumsobjekte zurück."""
    start_str = request.args.get("start")
    end_str = request.args.get("end")

    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=30)

    if start_str:
        try:
            start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    if end_str:
        try:
            end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    return start_date, end_date


# --------------------------------
# 🧠 Hilfsfunktion für den Export
# --------------------------------
def export_model_to_excel(model, columns, filename):
    """
    Exportiert Daten eines Modells als Excel-Datei (In-Memory).
    columns: Liste der Spalten, die exportiert werden sollen.
    filename: Dateiname für den Download.
    """
    # Hole alle Einträge aus der DB
    data = model.query.all()

    # Wandle in Pandas DataFrame um
    rows = [{col: getattr(d, col) for col in columns} for d in data]
    df = pd.DataFrame(rows)

    return export_df_to_excel(df, filename)


def export_df_to_excel(df, filename):
    # Schreibe in Bytes-Buffer als Excel
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
    Liest eine Excel-Datei aus einem Stream (BytesIO oder FileStorage) ein
    und erstellt oder aktualisiert DB-Einträge.

    Args:
        file_stream: FileStorage (request.files['file']) oder BytesIO
        model: SQLAlchemy-Modell (z.B. Mitglied oder Artikel)
        field_mapping: dict {db_field: excel_column_name}
        unique_field: optional, eindeutiges Feld für Updates
    """
    # Direkt aus Stream einlesen
    df = pd.read_excel(file_stream)
    df = df.replace({np.nan: None})
    print(field_mapping)

    for _, row in df.iterrows():
        entry_data = {
            db_field: row.get(excel_col)
            for db_field, excel_col in field_mapping.items()
            if excel_col in df.columns
        }
        print(entry_data)

        if not any(entry_data.values()):
            continue  # leere Zeile überspringen

        # Prüfen auf bestehende Einträge
        existing = None
        if unique_field and unique_field in entry_data:
            existing = (
                model.query.filter_by(id=entry_data[field_mapping["id"]]).first()
                if field_mapping["id"] and field_mapping["id"] in entry_data
                else False
            )

        if existing:
            # Update
            for key, value in entry_data.items():
                setattr(existing, key, value)
        else:
            # Neu
            db.session.add(model(**entry_data))

    db.session.commit()


def handle_excel_import(db_fields, model, redirect_url, unique_field=None):
    """Zentrale Logik für den Excel-Import ohne Datei auf der Festplatte."""
    file = request.files.get("file")
    mapping = {f: request.form.get(f) for f in db_fields}

    if not file or file.filename == "":
        flash("Bitte wähle eine Datei aus.", "error")
        return redirect(redirect_url)

    try:
        # Datei direkt aus FileStorage übergeben
        import_excel_to_db(file.stream, model, mapping, unique_field=unique_field)
        flash(f"{model.__tablename__.capitalize()} erfolgreich importiert!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Fehler beim Import: {e}", "error")

    return redirect(redirect_url)
