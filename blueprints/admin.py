"""Admin routes"""

from datetime import timedelta
import io

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    send_file,
    jsonify,
    current_app,
)
from flask_login import login_required
from sqlalchemy import desc, text
import pandas as pd

from models import db, Artikel, Buchung, Mitglied
from utils.admin import *
from config import BESTAND_WARN_SCHWELLENWERT

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@login_required
@admin_bp.route("/")
def buchungshistorie():
    """Zeigt die Buchungshistorie mit Pagination und Datumsfilter."""
    page = request.args.get("page", 1, type=int)
    per_page = 20

    start_date, end_date = parse_daterange()

    query = (
        Buchung.query.join(Buchung.mitglied_obj)
        .join(Buchung.artikel_obj)
        .filter(Buchung.zeitstempel.between(start_date, end_date + timedelta(days=1)))
        .order_by(desc(Buchung.zeitstempel))
    )

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    buchungen = pagination.items

    return render_template(
        "admin/buchungshistorie.html",
        buchungen=buchungen,
        pagination=pagination,
        start_date=start_date,
        end_date=end_date,
    )


@login_required
@admin_bp.route("/buchung_toggle/<int:buchung_id>", methods=["POST"])
def buchung_toggle(buchung_id):
    buchung = Buchung.query.get_or_404(buchung_id)
    if buchung.storniert:
        buchung.storniert = None
        # flash(f"Buchung i.d.H.v. {buchung.gesamtpreis} storniert")
    else:
        buchung.storniert = datetime.utcnow()
        # flash(f"Storno i.d.H.v. {buchung.gesamtpreis} rückgängig gemacht")
    db.session.commit()
    return jsonify({"success": True, "storniert": bool(buchung.storniert)})


# -------------------------
# 📤 Export: Buchungen als Excel
# -------------------------
@admin_bp.route("/admin/buchungshistorie/export")
@login_required
def export_buchungen():
    """Exportiert alle Buchungen im gewählten Zeitraum als Excel."""
    start_date, end_date = parse_daterange()

    # Daten abrufen
    buchungen = (
        Buchung.query.join(Buchung.mitglied_obj)
        .join(Buchung.artikel_obj)
        .filter(Buchung.zeitstempel.between(start_date, end_date + timedelta(days=1)))
        .order_by(desc(Buchung.zeitstempel))
        .all()
    )

    # In DataFrame umwandeln
    data = [
        {
            "Datum": b.zeitstempel.strftime("%Y-%m-%d %H:%M"),
            "Mitglied": b.mitglied_obj.name,
            "Artikel": b.artikel_obj.name,
            "Menge": b.menge,
            "Preis/Einheit (€)": round(b.preis_pro_einheit, 2),
            "Gesamtpreis (€)": round(b.gesamtpreis, 2),
            "Storniert": "Ja" if b.storniert else "Nein",
        }
        for b in buchungen
    ]

    df = pd.DataFrame(data)

    filename = f"buchungen_{start_date}_{end_date}.xlsx"

    return export_df_to_excel(df, filename)


# --------------------------------
# 📦 Admin-Seite: Export Auswahl
# --------------------------------
@admin_bp.route("/export", methods=["GET", "POST"])
@login_required
def admin_export():
    """
    Admin-Interface für eigene SQL Queries.
    Query wird readonly ausgeführt, Ergebnis als Tabelle angezeigt und kann als Excel exportiert werden.
    """
    results = None
    query = ""
    error = None

    if request.method == "POST":
        query = request.form.get("query", "").strip()
        if query:
            try:
                # Reine Lese-Verbindung
                readonly_engine = db.get_engine()
                with readonly_engine.connect() as conn:
                    conn = conn.execution_options(
                        isolation_level="AUTOCOMMIT", readonly=True
                    )
                    result_proxy = conn.execute(text(query))
                    # Spalten + Daten für Template
                    columns = result_proxy.keys()
                    results = [
                        dict(zip(columns, row)) for row in result_proxy.fetchall()
                    ]

            except Exception as e:
                error = str(e.args)

    return render_template(
        "admin/admin_export.html", query=query, results=results, error=error
    )


# --------------------------------
# 📋 Mitglieder-Export
# --------------------------------
@admin_bp.route("/export/mitglieder")
@login_required
def export_mitglieder():
    return export_model_to_excel(
        model=Mitglied,
        columns=["id", "name", "email"],  # Passe an dein Modell an
        filename="mitglieder_export.xlsx",
    )


# --------------------------------
# 🛒 Produkte-Export
# --------------------------------
@admin_bp.route("/export/produkte")
@login_required
def export_produkte():
    return export_model_to_excel(
        model=Artikel,
        columns=[
            "id",
            "name",
            "preis",
            "bestand",
            "mindestbestand",
            "bestand",
        ],  # Passe an dein Modell an
        filename="produkte_export.xlsx",
    )


@admin_bp.route("/sql_export/download", methods=["POST"])
@login_required
def sql_export_download():
    query = request.form.get("query", "").strip()

    readonly_engine = db.get_engine()
    with readonly_engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT", readonly=True)
        result_proxy = conn.execute(text(query))
        df = pd.DataFrame(result_proxy.fetchall(), columns=result_proxy.keys())

    return export_df_to_excel(df, "export.xlsx")


# Mitglieder
@admin_bp.route("/mitglieder", methods=["GET", "POST"])
@login_required
def admin_mitglieder():
    db_fields = ["id", "name", "nickname", "email", "guthaben"]

    if request.method == "POST":
        return handle_excel_import(
            db_fields=db_fields,
            model=Mitglied,
            redirect_url=url_for("admin.admin_mitglieder"),
            unique_field="email",
        )

    return render_template(
        "admin/admin_mitglieder.html",
        title="Mitglieder-Import",
        action_url=url_for("admin.admin_mitglieder"),
        db_fields=db_fields,
    )


# Produkte
@admin_bp.route("/produkte", methods=["GET", "POST"])
@login_required
def admin_produkte():
    db_fields = ["id", "name", "preis", "bestand", "mindestbestand", "bestand"]

    if request.method == "POST":
        return handle_excel_import(
            db_fields=db_fields,
            model=Artikel,
            redirect_url=url_for("admin.admin_produkte"),
            unique_field="name",
        )

    return render_template(
        "admin/admin_produkte.html",
        title="Produkt-Import",
        action_url=url_for("admin.admin_produkte"),
        db_fields=db_fields,
    )
