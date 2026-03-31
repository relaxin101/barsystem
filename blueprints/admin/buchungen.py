
"""Buchungen blueprint for admin panel"""

from datetime import timedelta

from flask import (
Blueprint,
render_template,
request,
flash,
jsonify,
)
from flask_login import login_required
from sqlalchemy import desc
import pandas as pd

from models import db, Buchung
from utils.admin import *

buchungen_bp = Blueprint("buchungen", __name__, url_prefix="/buchungen")

@login_required
@buchungen_bp.route("/")
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


@login_required
@buchungen_bp.route("/toggle/<int:buchung_id>", methods=["POST"])
def toggle(buchung_id):
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
@buchungen_bp.route("/download")
@login_required
def download():
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


