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

from models import db, Artikel, Buchung, Mitglied, Bericht
from utils.admin import *
from config import BESTAND_WARN_SCHWELLENWERT, MINDEST_GUTHABEN

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
        .outerjoin(Buchung.artikel_obj)
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
        buchung.mitglied_obj.guthaben -= buchung.gesamtpreis
        flash(f"Buchung i.d.H.v. {buchung.gesamtpreis} storniert", "info")
    else:
        buchung.storniert = datetime.utcnow()
        buchung.mitglied_obj.guthaben += buchung.gesamtpreis
        flash(f"Storno i.d.H.v. {buchung.gesamtpreis} rückgängig gemacht", "info")
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

    bericht_id = request.args.get("id", "").strip()
    if bericht_id:
        query = Bericht.query.get_or_404(bericht_id).sql

    if request.method == "POST":
        query = request.form.get("query", "").strip()

    if query:
        try:
            # Reine Lese-Verbindung
            readonly_engine = db.get_engine()
            with readonly_engine.connect() as conn:
                conn = conn.execution_options(
                    isolation_level="AUTOCOMMIT",  # SQL-injection as a Service (SaaS)
                )
                result_proxy = conn.execute(text(query))
                # Spalten + Daten für Template
                columns = result_proxy.keys()
                results = [dict(zip(columns, row)) for row in result_proxy.fetchall()]

        except Exception as e:
            error = str(e.args)

    berichte = [
        {
            "id": bericht.id,
            "name": bericht.name,
            "sql": bericht.sql,
        }
        for bericht in Bericht.query.all()
    ]
    return render_template(
        "admin/admin_export.html",
        id=bericht_id,
        query=query,
        results=results,
        error=error,
        berichte=berichte,
    )


@login_required
@admin_bp.route("berichte", methods=["POST"])
def create_berichte():
    query = request.form.get("query", "").strip()
    if not query:
        flash("Es muss eine Query angegeben werden", "error")
        return redirect(url_for("admin.admin_export"))

    name = request.form.get("name", "").strip()

    if not name:
        flash("Es muss ein Name angegeben werden", "error")
        return redirect(url_for("admin.admin_export"))
    bericht = Bericht(sql=query, name=name)
    db.session.add(bericht)
    db.session.commit()
    return redirect(url_for("admin.admin_export"))


@admin_bp.route("/berichte/<int:bericht_id>", methods=["POST"])
@login_required
def delete_berichte(bericht_id):
    if request.form.get("_method") == "DELETE":
        bericht = Bericht.query.get_or_404(bericht_id)
        db.session.delete(bericht)
        db.session.commit()
        flash(f"Bericht '{bericht.name}' wurde gelöscht.", "success")
    return redirect(url_for("admin.admin_export"))


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
            unique_field="id",
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
    """Endpoint um Artikel zu importieren oder aktualisieren"""
    db_fields = ["id", "name", "preis", "bestand", "mindestbestand", "bestand", "order"]

    if request.method == "POST":
        return handle_excel_import(
            db_fields=db_fields,
            model=Artikel,
            redirect_url=url_for("admin.admin_produkte"),
            unique_field="id",
        )

    return render_template(
        "admin/admin_produkte.html",
        title="Produkt-Import",
        action_url=url_for("admin.admin_produkte"),
        db_fields=db_fields,
    )


# --------------------------------
# 💶 Guthaben Management
# --------------------------------
@admin_bp.route("/guthaben", methods=["GET"])
@login_required
def guthaben_management():
    mitglieder = Mitglied.query.order_by(Mitglied.name).all()
    return render_template("admin/guthaben.html", mitglieder=mitglieder)


# 🧮 Toggle Blacklist
@admin_bp.route("/mitglied_blacklist_toggle/<int:mitglied_id>", methods=["POST"])
@login_required
def mitglied_blacklist_toggle(mitglied_id):
    data = request.get_json()
    mitglied = Mitglied.query.get_or_404(mitglied_id)
    mitglied.blacklist = bool(data.get("blacklist"))
    db.session.commit()
    return jsonify({"success": True, "blacklist": mitglied.blacklist})


# 📤 Excel Import für Guthabenänderungen
@admin_bp.route("/guthaben_import", methods=["POST"])
@login_required
def guthaben_import():
    file = request.files.get("file")
    mitglied_col = request.form.get("mitglied_id_col")
    aufbuchung_col = request.form.get("aufbuchung_col")

    if not file:
        flash("Keine Datei hochgeladen!", "error")
        return redirect(url_for("admin.guthaben_management"))

    # Excel einlesen
    df = pd.read_excel(file)

    # Prüfen, ob die Spalten existieren
    if mitglied_col not in df.columns or aufbuchung_col not in df.columns:
        flash("Spaltennamen nicht gefunden. Bitte überprüfe die Zuordnung.", "error")
        return redirect(url_for("admin.guthaben_management"))

    # Nur Zeilen behalten, wo BEIDE Werte numerisch und nicht leer sind
    df = df[[mitglied_col, aufbuchung_col]].copy()
    df = df.dropna(subset=[mitglied_col, aufbuchung_col])

    # Versuch, die Werte in Zahlen umzuwandeln (nicht konvertierbare werden NaN)
    df[mitglied_col] = pd.to_numeric(df[mitglied_col], errors="coerce")
    df[aufbuchung_col] = pd.to_numeric(df[aufbuchung_col], errors="coerce")

    # Nur Zeilen mit gültigen Zahlen behalten
    df = df.dropna(subset=[mitglied_col, aufbuchung_col])

    if df.empty:
        flash(
            "Keine gültigen Zeilen gefunden (beide Spalten müssen Zahlen enthalten).",
            "error",
        )
        return redirect(url_for("admin.guthaben_management"))

    count = 0
    for _, row in df.iterrows():
        try:
            mitglied_id = int(row[mitglied_col])
            betrag = float(row[aufbuchung_col])
            mitglied = Mitglied.query.get(mitglied_id)
            print(row)
            if mitglied:
                mitglied.guthaben += betrag

                if mitglied.guthaben < MINDEST_GUTHABEN:
                    mitglied.blacklist = True
                elif mitglied.guthaben > MINDEST_GUTHABEN:
                    mitglied.blacklist = False

                buchung = Buchung(
                    mitglied_id=mitglied.id,
                    artikel_id=None,  # oder Dummy
                    menge=1,
                    preis_pro_einheit=betrag,
                    gesamtpreis=betrag,
                    zeitstempel=datetime.now(),
                    storniert=None,
                )
                db.session.add(buchung)
                count += 1
        except Exception as e:
            print("Fehler bei Zeile:", e)

    db.session.commit()
    flash(f"{count} Guthabenänderungen durchgeführt.", "success")
    return redirect(url_for("admin.guthaben_management"))
