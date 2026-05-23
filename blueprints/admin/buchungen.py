"""Buchungen blueprint for admin panel"""

from datetime import timedelta

from flask import Blueprint, render_template, request, flash, jsonify
from flask_login import login_required
from sqlalchemy import desc
import pandas as pd

from models import db, Buchung
from utils.admin import export_df_to_excel, parse_daterange, calc_blacklist
from datetime import datetime

buchungen_bp = Blueprint("buchungen", __name__, url_prefix="/buchungen")


@buchungen_bp.route("/")  # FIX: @login_required nach @route
@login_required
def history():
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


@buchungen_bp.route("/toggle/<int:buchung_id>", methods=["POST"])  # FIX: @login_required nach @route
@login_required
def toggle(buchung_id):
    buchung = Buchung.query.get_or_404(buchung_id)
    if buchung.storno:
        buchung.storno = False
        buchung.mitglied_obj.blacklist = calc_blacklist(buchung.mitglied_obj, buchung.gesamtpreis)
        buchung.mitglied_obj.guthaben += buchung.gesamtpreis
    else:
        buchung.storno = True
        buchung.mitglied_obj.blacklist = calc_blacklist(buchung.mitglied_obj, -buchung.gesamtpreis)
        buchung.mitglied_obj.guthaben -= buchung.gesamtpreis
    buchung.storno_updated_at = datetime.now()
    db.session.commit()

    is_veraendert = buchung.abrechnungs_id is not None and (
        buchung.storno_updated_at > buchung.abrechnung_obj.zeitstempel
    )
    return jsonify({
        "success": True,
        "storniert": buchung.storno,
        "message": (
            f'Abrechnung {buchung.abrechnung_obj.id} "{buchung.abrechnung_obj.name}" '
            f'hat sich aufgrund des Stornos geändert'
        ) if is_veraendert else None,
    })


@buchungen_bp.route("/download")
@login_required
def download():
    """Exportiert alle Buchungen im gewählten Zeitraum als Excel."""
    start_date, end_date = parse_daterange()

    # FIX: outerjoin statt join – Buchungen ohne Artikel (Aufbuchungen) werden mitexportiert
    buchungen = (
        Buchung.query.join(Buchung.mitglied_obj)
        .outerjoin(Buchung.artikel_obj)
        .filter(Buchung.zeitstempel.between(start_date, end_date + timedelta(days=1)))
        .order_by(desc(Buchung.zeitstempel))
        .all()
    )

    data = [
        {
            "Datum": b.zeitstempel.strftime("%Y-%m-%d %H:%M"),
            "Mitglied": b.mitglied_obj.name,
            "Artikel": b.artikel_obj.name if b.artikel_obj else "",
            "Beschreibung": b.beschreibung or "",
            "Menge": b.menge,
            "Preis/Einheit (€)": round(b.preis_pro_einheit / 100, 2),
            "Gesamtpreis (€)": round(b.gesamtpreis / 100, 2),
            "Storniert": "Ja" if b.storno else "Nein",
        }
        for b in buchungen
    ]

    df = pd.DataFrame(data)
    filename = f"buchungen_{start_date}_{end_date}.xlsx"
    return export_df_to_excel(df, filename)
