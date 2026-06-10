"""export/report blueprint in admin panel"""

import io
import zipfile
from datetime import datetime

import numpy as np
import pandas as pd
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required
from sqlalchemy import text

from models import db, Bericht, Mitglied, Artikel, User, Buchung, Abrechnung, Aussendung
from utils.admin import export_df_to_excel

# Reihenfolge beachtet FK-Abhängigkeiten: Buchung zuletzt (referenziert Mitglied, Artikel, Abrechnung)
_BACKUP_TABLES = [
    ("users", User),
    ("berichte", Bericht),
    ("aussendungen", Aussendung),
    ("abrechnungen", Abrechnung),
    ("mitglieder", Mitglied),
    ("artikel", Artikel),
    ("buchungen", Buchung),
]

export_bp = Blueprint("export", __name__, url_prefix="/export")


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
            readonly_engine = db.get_engine()
            with readonly_engine.connect() as conn:
                conn = conn.execution_options(isolation_level="AUTOCOMMIT")
                result_proxy = conn.execute(text(query))
                columns = result_proxy.keys()
                results = [dict(zip(columns, row)) for row in result_proxy.fetchall()]
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

    bericht = Bericht(sql=query, name=name)
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
    readonly_engine = db.get_engine()
    with readonly_engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT", readonly=True)
        result_proxy = conn.execute(text(query))
        df = pd.DataFrame(result_proxy.fetchall(), columns=result_proxy.keys())
    return export_df_to_excel(df, "export.xlsx")


def _get_db_revision():
    with db.engine.connect() as conn:
        row = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
        return row[0] if row else "unknown"


@export_bp.route("/db-backup")
@login_required
def db_backup():
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("ebs_version.txt", _get_db_revision())

        for name, model in _BACKUP_TABLES:
            columns = [c.key for c in model.__table__.columns]
            rows = model.query.all()
            df = pd.DataFrame(
                [{col: getattr(r, col) for col in columns} for r in rows],
                columns=columns,
            )
            excel_buf = io.BytesIO()
            with pd.ExcelWriter(excel_buf, engine="xlsxwriter") as writer:
                df.to_excel(writer, index=False, sheet_name=name)
            zf.writestr(f"{name}.xlsx", excel_buf.getvalue())

    zip_buffer.seek(0)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
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
                for name, model in _BACKUP_TABLES
                if name in names_in_zip
            ]

            for name, model in ordered:
                df = pd.read_excel(io.BytesIO(zf.read(f"{name}.xlsx")))
                df = df.replace({np.nan: None})
                columns = [c.key for c in model.__table__.columns]
                inserted = skipped = 0

                for _, row in df.iterrows():
                    row_data = {
                        col: row.get(col)
                        for col in columns
                        if col in df.columns
                    }
                    pk = row_data.get("id")
                    if pk is not None and db.session.get(model, pk) is not None:
                        skipped += 1
                        continue
                    db.session.add(model(**row_data))
                    inserted += 1

                # Sequenz nach Import zurücksetzen (nötig wenn IDs explizit gesetzt wurden)
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
