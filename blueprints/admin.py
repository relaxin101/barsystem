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
)
from flask_login import login_required
from sqlalchemy import desc
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
@admin_bp.route("/admin/export", methods=["GET"])
@login_required
def admin_export():
    """Zeigt eine Seite mit Buttons für verschiedene Exporte."""
    return render_template("admin/admin_export.html")


# --------------------------------
# 📋 Mitglieder-Export
# --------------------------------
@admin_bp.route("/admin/export/mitglieder")
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
@admin_bp.route("/admin/export/produkte")
@login_required
def export_produkte():
    return export_model_to_excel(
        model=Artikel,
        columns=["id", "name", "preis"],  # Passe an dein Modell an
        filename="produkte_export.xlsx",
    )


# Mitglieder
@admin_bp.route("/mitglieder", methods=["GET", "POST"])
@login_required
def admin_mitglieder():
    db_fields = ["id", "name", "nickname", "email"]

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
    db_fields = ["id", "name", "preis"]

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


###############################################################################
################### ALT
##############################################################################


@admin_bp.route("/bestand_anpassen/<int:artikel_id>", methods=["POST"])
@login_required  # Oder @admin_required, falls du eine separate Admin-Rolle hast
def bestand_anpassen(artikel_id):
    if request.method == "POST":
        try:
            menge = int(request.form.get("menge"))  # Menge aus dem Formular abrufen

            artikel = Artikel.query.get_or_404(artikel_id)  # Artikel finden

            # Bestand anpassen (addieren)
            artikel.bestand += menge

            db.session.commit()  # Änderungen speichern
            flash(
                f'Bestand für "{artikel.name}" um {menge} aktualisiert. Neuer Bestand: {artikel.bestand}',
                "success",
            )
        except ValueError:
            flash("Ungültige Menge eingegeben.", "danger")
        except Exception as e:
            flash(f"Fehler beim Anpassen des Bestands: {e}", "danger")
            db.session.rollback()  # Bei Fehler Rollback

    return redirect(url_for("admin.admin_bereich"))  # Zurück zur Admin-Seite


@admin_bp.route("/bestand_auf_setzen/<int:artikel_id>", methods=["POST"])
@login_required  # Oder @admin_required
def bestand_auf_setzen(artikel_id):
    if request.method == "POST":
        try:
            # Die neue Bestandsmenge aus dem Formular abrufen
            neuer_bestand = int(request.form.get("neuer_bestand"))

            if neuer_bestand < 0:
                flash("Der Bestand kann nicht negativ sein.", "danger")
                return redirect(url_for("admin.admin_bereich"))

            artikel = Artikel.query.get_or_404(artikel_id)  # Artikel finden

            alter_bestand = (
                artikel.bestand
            )  # Speichere den alten Wert für die Nachricht
            artikel.bestand = neuer_bestand  # Bestand auf den exakten Wert setzen

            db.session.commit()  # Änderungen speichern
            flash(
                f'Bestand für "{artikel.name}" von {alter_bestand} auf {neuer_bestand} gesetzt.',
                "success",
            )
        except ValueError:
            flash("Ungültiger Wert eingegeben.", "danger")
        except Exception as e:
            flash(f"Fehler beim Setzen des Bestands: {e}", "danger")
            db.session.rollback()  # Bei Fehler Rollback

    return redirect(url_for("admin.admin_bereich"))  # Zurück zur Admin-Seite
