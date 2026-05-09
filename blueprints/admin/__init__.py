"""Admin routes"""

from datetime import timedelta

from flask import (
Blueprint,
render_template,
request,
url_for,
)
from flask_login import login_required

from models import Artikel, Mitglied
from utils.admin import *
from blueprints.admin.berichte import export_bp
from blueprints.admin.guthaben import guthaben_bp
from blueprints.admin.buchungen import buchungen_bp
from blueprints.admin.aussendungen import aussendungen_bp
from blueprints.admin.artikel import artikel_bp
from blueprints.admin.mitglied import mitglied_bp

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
admin_bp.register_blueprint(export_bp)
admin_bp.register_blueprint(guthaben_bp)
admin_bp.register_blueprint(buchungen_bp)
admin_bp.register_blueprint(aussendungen_bp)
admin_bp.register_blueprint(artikel_bp)
admin_bp.register_blueprint(mitglied_bp)


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


