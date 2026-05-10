from collections import defaultdict

from flask import Blueprint, flash, render_template, request, jsonify, url_for
from flask_login import login_required
from datetime import datetime

from sqlalchemy import text

from models import db, Abrechnung, Buchung


abrechnung_bp = Blueprint(
    "abrechnung",
    __name__,
    url_prefix="/abrechnung",
    template_folder="../../templates/admin/abrechnung/"
)

@abrechnung_bp.route("/")
@login_required
def index():

    with db.engine.connect() as connection:
        sql = """
        SELECT * FROM abrechnung a,
            LATERAL (
                    SELECT abrechnungs_id as id, 
                    count(b.id) as num_buchungen, 
                    bool_or(COALESCE(b.storniert > a.zeitstempel, FALSE)) as veraendert,
                    MIN(b.zeitstempel) as von_datum, 
                    MAX(b.zeitstempel) as bis_datum
                    FROM buchung b
                    WHERE a.id = abrechnungs_id
                    GROUP BY abrechnungs_id)
            general
            NATURAL JOIN (
                    SELECT abrechnungs_id as id, sum(gesamtpreis) as summe_eingaenge 
                    FROM buchung
                    WHERE gesamtpreis > 0.0
                    AND storniert is NULL
                    GROUP BY abrechnungs_id)
            summe_eingaenge
            NATURAL JOIN (
                    SELECT abrechnungs_id as id, -1*sum(gesamtpreis) as summe_ausgaenge 
                    FROM buchung
                    WHERE gesamtpreis < 0.0
                    AND storniert is NULL
                    GROUP BY abrechnungs_id)
            summe_ausgaenge
            WHERE a.id = general.id
        """
        abrechnungen = connection.execute(text(sql))
    return render_template(
        "admin/abrechnung/index.html",
        abrechnungen=abrechnungen
    )


@abrechnung_bp.route("/create", methods=["POST"])
@login_required
def create():

    data = request.get_json()

    name = data.get("name")

    modus = data.get("modus")

    start = data.get("start")

    end = data.get("end")

    abrechnung = Abrechnung(
        name=name
    )

    db.session.add(abrechnung)

    query = Buchung.query.filter(
        Buchung.abrechnungs_id.is_(None)
    )

    if modus == "zeitraum":

        start_dt = datetime.fromisoformat(start)

        end_dt = datetime.fromisoformat(end)

        query = query.filter(
            Buchung.zeitstempel >= start_dt,
            Buchung.zeitstempel <= end_dt
        )

    buchungen = query.all()

    for b in buchungen:

        b.abrechnung_obj = abrechnung

    db.session.commit()

    return jsonify({
        "success": True
    })

# ---------------------------------------------------------
# Detailseite
# ---------------------------------------------------------
@abrechnung_bp.route("/<int:abrechnung_id>")
def detail(abrechnung_id):

    abrechnung = Abrechnung.query.get_or_404(abrechnung_id)

    buchungen = (
        Buchung.query
        .filter_by(abrechnungs_id=abrechnung.id)
        .order_by(Buchung.zeitstempel.desc())
        .all()
    )

    # -----------------------------------------
    # Nachträglich stornierte Buchungen
    # -----------------------------------------
    stornierte = (
        Buchung.query
        .filter(
            Buchung.abrechnungs_id == abrechnung.id,
            Buchung.storniert != None,
            Buchung.storniert > abrechnung.zeitstempel
        )
        .order_by(Buchung.storniert.desc())
        .all()
    )

    # -----------------------------------------
    # Kontoübersicht
    # -----------------------------------------
    konten = defaultdict(lambda: {
        "mitglied": None,
        "einzahlungen": 0,
        "konsum": 0
    })

    for b in buchungen:

        konto = konten[b.mitglied_id]
        konto["mitglied"] = b.mitglied_obj

        if b.gesamtpreis < 0:
            konto["einzahlungen"] += abs(b.gesamtpreis)
        else:
            konto["konsum"] += b.gesamtpreis

    return render_template(
        "admin/abrechnung/detail.html",
        abrechnung=abrechnung,
        buchungen=buchungen,
        stornierte=stornierte,
        konten=konten
    )


# ---------------------------------------------------------
# Zeitraum ändern
# ---------------------------------------------------------
@abrechnung_bp.route("/<int:abrechnung_id>/update", methods=["POST"])
def update(abrechnung_id):

    abrechnung = Abrechnung.query.get_or_404(abrechnung_id)

    data = request.get_json()

    start = datetime.fromisoformat(data["start"])
    ende = datetime.fromisoformat(data["ende"])

    # alte Buchungen lösen
    Buchung.query.filter_by(
        abrechnungs_id=abrechnung.id
    ).update({
        "abrechnungs_id": None
    })

    # neue Buchungen zuweisen
    buchungen = (
        Buchung.query
        .filter(
            Buchung.abrechnungs_id == None,
            Buchung.zeitstempel >= start,
            Buchung.zeitstempel <= ende
        )
        .all()
    )

    for b in buchungen:
        b.abrechnungs_id = abrechnung.id

    abrechnung.zeitstempel = datetime.utcnow()

    db.session.commit()

    return jsonify(success=True)


# ---------------------------------------------------------
# Refresh
# ---------------------------------------------------------
@abrechnung_bp.route("/<int:abrechnung_id>/refresh", methods=["POST"])
def refresh(abrechnung_id):

    #flash("reached")
    abrechnung = Abrechnung.query.get_or_404(abrechnung_id)

    abrechnung.zeitstempel = datetime.now()

    db.session.commit()

    return jsonify(success=True)


# ---------------------------------------------------------
# Löschen
# ---------------------------------------------------------
@abrechnung_bp.route("/<int:abrechnung_id>/delete", methods=["POST"])
def delete(abrechnung_id):

    abrechnung = Abrechnung.query.get_or_404(abrechnung_id)

    Buchung.query.filter_by(
        abrechnungs_id=abrechnung.id
    ).update({
        "abrechnungs_id": None
    })

    db.session.delete(abrechnung)

    db.session.commit()

    flash("Abrechnung gelöscht", "success")

    return jsonify(
        success=True,
        redirect=url_for("admin.abrechnung.index")
    )
