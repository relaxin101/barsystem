"""Admin routes"""

from datetime import timedelta

from flask import (
Blueprint,
render_template,
request,
url_for,
flash,
jsonify,
)
from flask_login import login_required
from sqlalchemy import desc, text
import pandas as pd

from models import db, Artikel, Buchung, Mitglied
from utils.admin import *
from blueprints.admin.berichte import export_bp
from blueprints.admin.guthaben import guthaben_bp
from blueprints.admin.buchungen import buchungen_bp

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
admin_bp.register_blueprint(export_bp)
admin_bp.register_blueprint(guthaben_bp)
admin_bp.register_blueprint(buchungen_bp)


@admin_bp.route("/")
@login_required
def main_page():
    redirect(url_for("admin.buchungen.history"))

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


