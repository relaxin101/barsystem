"""export/report blueprint in admin panel"""

import io
import zipfile
from datetime import timezone

import numpy as np
import pandas as pd
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from flask_login import current_user, login_required
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from models import (
    db, Bericht, Einstellung, Mitglied, Artikel, User, Buchung, Abrechnung, Aussendung, UTCDateTime,
)
from utils.admin import export_df_to_excel, normalize_line_endings, unescape_excel_cr
from utils.bericht_engine import report_engine
from utils.zeit import local_now, naive_local, naive_utc

# Reihenfolge beachtet FK-Abhängigkeiten: Buchung zuletzt (referenziert Mitglied, Artikel, Abrechnung)
_BACKUP_TABLES = [
    ("users", User),
    ("einstellungen", Einstellung),
    ("berichte", Bericht),
    ("aussendungen", Aussendung),
    ("abrechnungen", Abrechnung),
    ("mitglieder", Mitglied),
    ("artikel", Artikel),
    ("buchungen", Buchung),
]
# Nur für Superadmins, in beide Richtungen: users enthält Passwort-Hashes und ein
# präpariertes ZIP könnte sonst Konten oder Superadmin-Einstellungen anlegen.
_SUPERADMIN_TABLES = {"users", "einstellungen"}

export_bp = Blueprint("export", __name__, url_prefix="/export")


def _backup_tables():
    if current_user.is_superadmin:
        return _BACKUP_TABLES
    return [t for t in _BACKUP_TABLES if t[0] not in _SUPERADMIN_TABLES]


def _execute_query(query, schreiben=False):
    """Führt Bericht-SQL aus und gibt (Spalten, Zeilen) zurück.

    Immer lesend, auch für Superadmins: ein Bericht kann von jemand anderem
    gespeichert worden sein. Schreibzugriff gibt es nur pro Ausführung.
    """
    engine = db.engine if schreiben and current_user.is_superadmin else report_engine()
    try:
        conn = engine.connect()
    except OperationalError as e:
        raise RuntimeError(
            "Berichte-Zugang ist nicht eingerichtet (flask sync-report-role)."
        ) from e
    with conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        result_proxy = conn.execute(text(query))
        if not result_proxy.returns_rows:  # UPDATE etc. mit Schreibzugriff
            return [], []
        return list(result_proxy.keys()), result_proxy.fetchall()


@export_bp.route("/", methods=["GET", "POST"])
@login_required
def admin_export():
    results = None
    query = ""
    error = None

    bericht_id = request.args.get("id", "").strip()
    if bericht_id:
        query = Bericht.query.get_or_404(bericht_id).sql

    if request.method == "POST":
        query = request.form.get("query", "").strip()

    if query:
        try:
            schreiben = request.method == "POST" and "schreiben" in request.form
            columns, rows = _execute_query(query, schreiben)
            results = [dict(zip(columns, map(naive_local, row))) for row in rows]
            if schreiben and current_user.is_superadmin:
                flash("Abfrage mit Schreibzugriff ausgeführt.", "success")
        except Exception as e:
            error = str(e.args)

    berichte = [
        {"id": b.id, "name": b.name, "sql": b.sql}
        for b in Bericht.query.all()
    ]
    return render_template(
        "admin/admin_export.html",
        id=bericht_id,
        query=query,
        results=results,
        error=error,
        berichte=berichte,
    )


@export_bp.route("/export/berichte", methods=["POST"])  # FIX: @login_required nach @route
@login_required
def create_berichte():
    query = request.form.get("query", "").strip()
    if not query:
        flash("Es muss eine Query angegeben werden", "error")
        return redirect(url_for("admin.export.admin_export"))

    name = request.form.get("name", "").strip()
    if not name:
        flash("Es muss ein Name angegeben werden", "error")
        return redirect(url_for("admin.export.admin_export"))

    bericht = Bericht(sql=normalize_line_endings(query), name=name)
    db.session.add(bericht)
    db.session.commit()
    return redirect(url_for("admin.export.admin_export"))


@export_bp.route("/berichte/<int:bericht_id>", methods=["POST"])
@login_required
def delete_berichte(bericht_id):
    if request.form.get("_method") == "DELETE":
        bericht = Bericht.query.get_or_404(bericht_id)
        db.session.delete(bericht)
        db.session.commit()
        flash(f"Bericht '{bericht.name}' wurde gelöscht.", "success")
    return redirect(url_for("admin.export.admin_export"))


@export_bp.route("/download", methods=["POST"])
@login_required
def download():
    query = request.form.get("query", "").strip()
    try:
        columns, rows = _execute_query(query)
    except RuntimeError as e:
        flash(str(e), "error")
        return redirect(url_for("admin.export.admin_export"))
    return export_df_to_excel(pd.DataFrame(rows, columns=columns), "export.xlsx")


def _get_db_revision():
    with db.engine.connect() as conn:
        row = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
        return row[0] if row else "unknown"


def _restore_value(model, col, value):
    """Backups speichern Zeitstempel als naives UTC (verlustfrei auch in der Umstellungsstunde)."""
    if isinstance(model.__table__.columns[col].type, UTCDateTime):
        return None if pd.isna(value) else value.replace(tzinfo=timezone.utc)
    return unescape_excel_cr(value)


@export_bp.route("/db-backup")
@login_required
def db_backup():
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("ebs_version.txt", _get_db_revision())

        for name, model in _backup_tables():
            columns = [c.key for c in model.__table__.columns]
            rows = model.query.all()
            df = pd.DataFrame(
                [{col: naive_utc(getattr(r, col)) for col in columns} for r in rows],
                columns=columns,
            )
            excel_buf = io.BytesIO()
            with pd.ExcelWriter(excel_buf, engine="xlsxwriter") as writer:
                df.to_excel(writer, index=False, sheet_name=name)
            zf.writestr(f"{name}.xlsx", excel_buf.getvalue())

    zip_buffer.seek(0)
    timestamp = local_now().strftime("%Y%m%d_%H%M%S")
    return send_file(
        zip_buffer,
        as_attachment=True,
        download_name=f"db_backup_{timestamp}.zip",
        mimetype="application/zip",
    )


@export_bp.route("/db-restore", methods=["POST"])
@login_required
def db_restore():
    file = request.files.get("file")
    if not file or file.filename == "":
        flash("Bitte eine ZIP-Datei auswählen.", "error")
        return redirect(url_for("admin.export.admin_export"))

    summary = []

    try:
        with zipfile.ZipFile(io.BytesIO(file.read())) as zf:
            if "ebs_version.txt" in zf.namelist():
                backup_rev = zf.read("ebs_version.txt").decode().strip()
                current_rev = _get_db_revision()
                if backup_rev != current_rev:
                    flash(
                        f"Import abgebrochen: Datenbankversion stimmt nicht überein "
                        f"(Backup: {backup_rev}, aktuell: {current_rev}).",
                        "error",
                    )
                    return redirect(url_for("admin.export.admin_export"))

            # In definierter Reihenfolge importieren
            names_in_zip = {n[:-5] for n in zf.namelist() if n.endswith(".xlsx")}
            ordered = [
                (name, model)
                for name, model in _backup_tables()
                if name in names_in_zip
            ]

            for name, model in ordered:
                # read_excel rät Typen auch bei Textzellen: aus "21" würde sonst 21.0
                dtype = {"value": str} if model is Einstellung else None
                df = pd.read_excel(io.BytesIO(zf.read(f"{name}.xlsx")), dtype=dtype)
                df = df.replace({np.nan: None})
                columns = [c.key for c in model.__table__.columns]
                pk_column = model.__mapper__.primary_key[0].key
                inserted = skipped = 0

                for _, row in df.iterrows():
                    row_data = {
                        col: _restore_value(model, col, row.get(col))
                        for col in columns
                        if col in df.columns
                    }
                    if model is Bericht and row_data.get("sql"):
                        row_data["sql"] = normalize_line_endings(row_data["sql"])
                    pk = row_data.get(pk_column)
                    if pk is not None and db.session.get(model, pk) is not None:
                        skipped += 1
                        continue
                    db.session.add(model(**row_data))
                    inserted += 1

                # Sequenz nach Import zurücksetzen (nötig wenn IDs explizit gesetzt wurden)
                if pk_column == "id":
                    db.session.flush()  # sonst fehlt die letzte Zeile in MAX(id)
                    table = model.__tablename__
                    db.session.execute(text(
                        f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                        f"COALESCE((SELECT MAX(id)+1 FROM \"{table}\"), 1))"
                    ))
                db.session.commit()
                summary.append(f"{name}: {inserted} eingefügt, {skipped} übersprungen")

    except zipfile.BadZipFile:
        flash("Ungültige ZIP-Datei.", "error")
        return redirect(url_for("admin.export.admin_export"))
    except Exception as e:
        db.session.rollback()
        flash(f"Fehler beim Import: {e}", "error")
        return redirect(url_for("admin.export.admin_export"))

    flash("Restore abgeschlossen: " + " | ".join(summary), "success")
    return redirect(url_for("admin.export.admin_export"))
