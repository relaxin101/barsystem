"""Admin routes"""

from flask import Blueprint, render_template, request, url_for, redirect
from flask_login import login_required

from models import Artikel, Mitglied
from utils.admin import export_model_to_excel
from blueprints.admin.berichte import export_bp
from blueprints.admin.guthaben import guthaben_bp
from blueprints.admin.buchungen import buchungen_bp
from blueprints.admin.aussendungen import aussendungen_bp
from blueprints.admin.artikel import artikel_bp
from blueprints.admin.mitglied import mitglied_bp
from blueprints.admin.abrechnung import abrechnung_bp

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
admin_bp.register_blueprint(export_bp)
admin_bp.register_blueprint(guthaben_bp)
admin_bp.register_blueprint(buchungen_bp)
admin_bp.register_blueprint(aussendungen_bp)
admin_bp.register_blueprint(artikel_bp)
admin_bp.register_blueprint(mitglied_bp)
admin_bp.register_blueprint(abrechnung_bp)


@admin_bp.route("/")
@login_required
def main_page():
    return redirect(url_for("admin.buchungen.history"))  # FIX: fehlte return


@admin_bp.route("/export/mitglieder")
@login_required
def export_mitglieder():
    return export_model_to_excel(
        model=Mitglied,
        columns=["id", "name", "email"],
        filename="mitglieder_export.xlsx",
    )


@admin_bp.route("/export/produkte")
@login_required
def export_produkte():
    return export_model_to_excel(
        model=Artikel,
        columns=["id", "name", "preis", "bestand", "mindestbestand", "bestand"],
        filename="produkte_export.xlsx",
    )
