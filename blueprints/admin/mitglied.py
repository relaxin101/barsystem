from flask import (
    Blueprint,
    render_template,
    jsonify,
    request,
    url_for,
)

from flask_login import login_required

from models import db, Mitglied
from utils.admin import handle_excel_import

mitglied_bp = Blueprint(
    "mitglied",
    __name__,
    url_prefix="/mitglied",
    template_folder="../../templates/admin/mitglied",
)

DB_FIELDS = ["id", "name", "nickname", "email", "aktiv","schwaerzungs_grenze"]

# --------------------------------------------------
# Übersicht
# --------------------------------------------------

@mitglied_bp.route("/")
@login_required
def index():

    mitglieder = (
        Mitglied.query
        .order_by(Mitglied.name)
        .all()
    )

    return render_template(
        "admin/mitglied/index.html",
        mitglieder=mitglieder,
        db_fields=DB_FIELDS,
        action_url= url_for('admin.mitglied.bulk_import')
    )


# --------------------------------------------------
# Toggle aktiv
# --------------------------------------------------

@mitglied_bp.route("/toggle/<int:id>", methods=["POST"])
@login_required
def toggle(id):

    m = Mitglied.query.get_or_404(id)

    m.aktiv = not m.aktiv

    db.session.commit()

    return jsonify({
        "success": True,
        "aktiv": m.aktiv,
    })


# --------------------------------------------------
# Details
# --------------------------------------------------

@mitglied_bp.route("/<int:id>")
@login_required
def details(id):

    m = Mitglied.query.get_or_404(id)

    return jsonify({

        "success": True,

        "mitglied": {

            "id": m.id,

            "name": m.name,

            "nickname": m.nickname,

            "email": m.email,

            "guthaben": m.guthaben,

            "aktiv": m.aktiv,

            "verborgen": m.verborgen,

            "blacklist": m.blacklist,

            "schwaerzungs_grenze":
                m.schwaerzungs_grenze,

        }

    })


# --------------------------------------------------
# Update
# --------------------------------------------------

@mitglied_bp.route("/<int:id>", methods=["POST"])
@login_required
def update(id):

    m = Mitglied.query.get_or_404(id)

    data = request.get_json()

    m.name = data["name"]

    m.nickname = data["nickname"]

    m.email = data["email"]

    m.aktiv = bool(data["aktiv"])

    m.verborgen = bool(data["verborgen"])

    grenze = data.get("schwaerzungs_grenze")

    if grenze not in [None, ""]:
        m.schwaerzungs_grenze = int(
            round(float(grenze) * 100)
        )
    else:
        m.schwaerzungs_grenze = None

    db.session.commit()

    return jsonify({
        "success": True
    })


# --------------------------------------------------
# Neues Mitglied
# --------------------------------------------------

@mitglied_bp.route("/create", methods=["PUT"])
@login_required
def create():

    data = request.get_json()

    grenze = data.get("schwaerzungs_grenze")

    m = Mitglied(

        name=data["name"],

        nickname=data["nickname"],

        email=data["email"],

        aktiv=bool(data["aktiv"]),

        verborgen=bool(data["verborgen"]),

        schwaerzungs_grenze=(
            int(round(float(grenze) * 100))
            if grenze not in [None, ""]
            else None
        ),

        guthaben=0,

        blacklist=False,

    )

    db.session.add(m)

    db.session.commit()

    return jsonify({
        "success": True,
        "mitglied_id": m.id,
    })



# Mitglieder
@mitglied_bp.route("/bulk-import", methods=["POST"])
@login_required
def bulk_import():

    return handle_excel_import(
        db_fields=DB_FIELDS,
        model=Mitglied,
        redirect_url=url_for("admin.mitglied.index"),
        unique_field="id",
    )
