from flask import Blueprint, flash, render_template, request, jsonify, url_for
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
    artikel = Artikel.query.order_by(Artikel.reihenfolge).all()
    return render_template(
        "admin/artikel/index.html",
        artikel=artikel,
        db_fields=DB_FIELDS,
        action_url=url_for('admin.artikel.bulk_import')
    )


@artikel_bp.route("/toggle/<int:artikel_id>", methods=["POST"])
@login_required
def toggle_artikel(artikel_id):
    artikel = Artikel.query.get_or_404(artikel_id)
    artikel.aktiv = not artikel.aktiv
    db.session.commit()
    return jsonify({"success": True, "aktiv": artikel.aktiv})


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
            "typ": artikel.typ or 'volumen',
            "volumen_liter": artikel.volumen_liter if artikel.volumen_liter is not None else 0.5,
            "reinalkohol_liter": artikel.reinalkohol_liter if artikel.reinalkohol_liter is not None else 0.0,
        }
    })


@artikel_bp.route("/<int:artikel_id>", methods=["POST"])
@login_required
def update_artikel(artikel_id):
    artikel = Artikel.query.get_or_404(artikel_id)
    data = request.get_json()

    artikel.name = data.get("name", artikel.name)
    artikel.preis = int(round(float(data.get("preis", artikel.preis / 100.0)) * 100, 0))
    artikel.reihenfolge = int(data.get("reihenfolge", artikel.reihenfolge))
    artikel.aktiv = bool(data.get("aktiv"))
    artikel.typ = data.get("typ", artikel.typ or 'volumen')

    if artikel.typ == 'volumen':
        artikel.volumen_liter = float(data.get("volumen_liter", artikel.volumen_liter or 0.5))
        artikel.reinalkohol_liter = float(data.get("reinalkohol_liter", artikel.reinalkohol_liter or 0.0))
    else:
        artikel.volumen_liter = None
        artikel.reinalkohol_liter = None

    db.session.commit()
    return jsonify({"success": True})


@artikel_bp.route("/create", methods=["PUT"])
@login_required
def create():
    data = request.get_json()
    typ = data.get("typ", "volumen")

    artikel = Artikel(
        name=data["name"],
        preis=int(round(float(data["preis"]) * 100)),
        reihenfolge=int(data["order"]),
        aktiv=bool(data["aktiv"]),
        typ=typ,
        volumen_liter=float(data.get("volumen_liter", 0.5)) if typ == 'volumen' else None,
        reinalkohol_liter=float(data.get("reinalkohol_liter", 0.0)) if typ == 'volumen' else None,
    )

    db.session.add(artikel)
    db.session.flush()  # get artikel.id before commit
    db.session.commit()

    return jsonify({"success": True, "artikel_id": artikel.id})


@artikel_bp.route("/bulk-import", methods=["POST"])
@login_required
def bulk_import():
    return handle_excel_import(
        db_fields=DB_FIELDS,
        model=Artikel,
        redirect_url=url_for("admin.artikel.index"),
        unique_field="id",
    )
