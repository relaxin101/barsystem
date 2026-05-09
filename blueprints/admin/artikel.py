from flask import Blueprint, render_template, request, jsonify, url_for
from flask_login import login_required

from models import db, Artikel
from utils.admin import handle_excel_import

artikel_bp = Blueprint(
    "artikel",
    __name__,
    url_prefix="/artikel",
    template_folder="../../templates/admin/artikel",
)
DB_FIELDS = ["id", "reihenfolge", "name", "preis", "aktiv"]


@artikel_bp.route("/", methods=["GET"])
@login_required
def index():
    """Main page für artikel verwaltung"""

    artikel = Artikel.query.order_by(Artikel.reihenfolge).all()

    return render_template(
        "admin/artikel/index.html",
        artikel=artikel,
        db_fields=DB_FIELDS,
    )


# ---------------------------------------------------
# Aktiv Toggle
# ---------------------------------------------------
@artikel_bp.route("/toggle/<int:artikel_id>", methods=["POST"])
@login_required
def toggle_artikel(artikel_id):

    artikel = Artikel.query.get_or_404(artikel_id)

    artikel.aktiv = not artikel.aktiv

    db.session.commit()

    return jsonify({
        "success": True,
        "aktiv": artikel.aktiv,
    })


# ---------------------------------------------------
# Einzelnen Artikel laden
# ---------------------------------------------------
@artikel_bp.route("/<int:artikel_id>", methods=["GET"])
@login_required
def get_artikel(artikel_id):

    artikel = Artikel.query.get_or_404(artikel_id)

    return jsonify({
        "success": True,
        "artikel": {
            "id": artikel.id,
            "name": artikel.name,
            "preis": artikel.preis,
            "reihenfolge": artikel.reihenfolge,
            "aktiv": artikel.aktiv,
        }
    })


@artikel_bp.route("/<int:artikel_id>", methods=["POST"])
@login_required
def update_artikel(artikel_id):
    """Artikel bearbeiten"""

    artikel = Artikel.query.get_or_404(artikel_id)

    data = request.get_json()

    artikel.name = data.get("name", artikel.name)
    artikel.preis = int(float(data.get("preis", artikel.preis / 100)) * 100)
    artikel.reihenfolge = int(data.get("reihenfolge", artikel.reihenfolge))
    artikel.aktiv = bool(data.get("aktiv"))

    db.session.commit()

    return jsonify({
        "success": True
    })

@artikel_bp.route("/create", methods=["PUT"])
@login_required
def create():
    """Artikel anlegen"""

    data = request.get_json()

    artikel = Artikel(
        name=data["name"],
        preis=int(round(float(data["preis"]) * 100)),
        reihenfolge=int(data["order"]),
        aktiv=bool(data["aktiv"]),
    )

    db.session.add(artikel)
    db.session.commit()

    return jsonify({
        "success": True,
        "artikel_id": artikel.id
    })

# ---------------------------------------------------
# Excel mit Artikeln importieren
# ---------------------------------------------------
@artikel_bp.route("/bulk-import", methods=["POST"])
@login_required
def bulk_import():
    """Endpoint um Artikel zu importieren oder aktualisieren"""
    return handle_excel_import(
        db_fields=DB_FIELDS,
        model=Artikel,
        redirect_url=url_for("admin.artikel.index"),
        unique_field="id",
    )

