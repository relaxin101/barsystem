from collections import defaultdict

from flask import Blueprint, flash, render_template, request, jsonify, url_for
from flask_login import login_required
from datetime import datetime

from sqlalchemy import func, text

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
        SELECT a.id,
               a.name,
               a.zeitstempel,
               general.num_buchungen,
               general.veraendert,
               general.von_datum,
               general.bis_datum,
               COALESCE(summe_eingaenge.summe_eingaenge, 0) AS summe_eingaenge,
               COALESCE(summe_ausgaenge.summe_ausgaenge, 0) AS summe_ausgaenge
        FROM abrechnung a,
             LATERAL (
                 SELECT abrechnungs_id                                           AS id,
                        count(b.id)                                              AS num_buchungen,
                        bool_or(COALESCE(b.storniert > a.zeitstempel, FALSE))   AS veraendert,
                        MIN(b.zeitstempel)                                       AS von_datum,
                        MAX(b.zeitstempel)                                       AS bis_datum
                 FROM buchung b
                 WHERE a.id = abrechnungs_id
                 GROUP BY abrechnungs_id
             ) general
             NATURAL LEFT JOIN (
                 SELECT abrechnungs_id AS id, sum(gesamtpreis) AS summe_eingaenge
                 FROM buchung
                 WHERE gesamtpreis > 0.0
                   AND storniert IS NULL
                 GROUP BY abrechnungs_id
             ) summe_eingaenge
             NATURAL LEFT JOIN (
                 SELECT abrechnungs_id AS id, -1 * sum(gesamtpreis) AS summe_ausgaenge
                 FROM buchung
                 WHERE gesamtpreis < 0.0
                   AND storniert IS NULL
                 GROUP BY abrechnungs_id
             ) summe_ausgaenge
        ORDER BY zeitstempel DESC
        """
        abrechnungen = connection.execute(text(sql))
    return render_template("admin/abrechnung/index.html", abrechnungen=abrechnungen)


@abrechnung_bp.route("/create", methods=["POST"])
@login_required
def create():
    data = request.get_json()
    name = data.get("name")
    modus = data.get("modus")
    start = data.get("start")
    end = data.get("end")

    abrechnung = Abrechnung(name=name)
    db.session.add(abrechnung)

    query = Buchung.query.filter(Buchung.abrechnungs_id.is_(None))

    if modus == "zeitraum":
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
        query = query.filter(
            Buchung.zeitstempel >= start_dt,
            Buchung.zeitstempel <= end_dt,
        )

    buchungen = query.all()
    for b in buchungen:
        b.abrechnung_obj = abrechnung

    db.session.commit()
    return jsonify({"success": True})


@abrechnung_bp.route("/<int:abrechnung_id>")
@login_required
def detail(abrechnung_id):
    abrechnung = Abrechnung.query.get_or_404(abrechnung_id)

    buchungen = (
        Buchung.query
        .filter_by(abrechnungs_id=abrechnung.id)
        .order_by(Buchung.zeitstempel.desc())
        .all()
    )

    stornierte = (
        Buchung.query
        .filter(
            Buchung.abrechnungs_id == abrechnung.id,
            Buchung.storniert != None,
            Buchung.storniert > abrechnung.zeitstempel,
        )
        .order_by(Buchung.storniert.desc())
        .all()
    )

    # FIX: Crash wenn Abrechnung keine Buchungen hat
    von_datum = None
    bis_datum = None
    if buchungen:
        with db.engine.connect() as connection:
            sql = f"""
                SELECT MIN(b.zeitstempel) AS von_datum,
                       MAX(b.zeitstempel) AS bis_datum
                FROM buchung b
                WHERE b.abrechnungs_id = {abrechnung_id}
                GROUP BY abrechnungs_id
            """
            results = list(connection.execute(text(sql)))
            if results:
                von_datum = results[0][0]
                bis_datum = results[0][1]

    konten = defaultdict(lambda: {"mitglied": None, "einzahlungen": 0, "konsum": 0})
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
        konten=konten,
        von_datum=von_datum,
        bis_datum=bis_datum,
    )


@abrechnung_bp.route("/<int:abrechnung_id>/update", methods=["POST"])
@login_required
def update(abrechnung_id):
    abrechnung = Abrechnung.query.get_or_404(abrechnung_id)
    data = request.get_json()
    start = datetime.fromisoformat(data["start"])
    ende = datetime.fromisoformat(data["ende"])

    Buchung.query.filter_by(abrechnungs_id=abrechnung.id).update({"abrechnungs_id": None})

    buchungen = (
        Buchung.query
        .filter(
            Buchung.abrechnungs_id == None,
            Buchung.zeitstempel >= start,
            Buchung.zeitstempel <= ende,
        )
        .all()
    )
    for b in buchungen:
        b.abrechnungs_id = abrechnung.id

    abrechnung.zeitstempel = datetime.now()
    db.session.commit()
    return jsonify(success=True)


@abrechnung_bp.route("/<int:abrechnung_id>/refresh", methods=["POST"])
@login_required
def refresh(abrechnung_id):
    abrechnung = Abrechnung.query.get_or_404(abrechnung_id)
    abrechnung.zeitstempel = datetime.now()
    db.session.commit()
    return jsonify(success=True)


@abrechnung_bp.route("/<int:abrechnung_id>/delete", methods=["POST"])
@login_required
def delete(abrechnung_id):
    abrechnung = Abrechnung.query.get_or_404(abrechnung_id)
    Buchung.query.filter_by(abrechnungs_id=abrechnung.id).update({"abrechnungs_id": None})
    db.session.delete(abrechnung)
    db.session.commit()
    flash("Abrechnung gelöscht", "success")
    return jsonify(success=True, redirect=url_for("admin.abrechnung.index"))
