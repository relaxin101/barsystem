from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from sqlalchemy import or_, func, text, desc
from models import db, Mitglied, Artikel, Buchung
from datetime import datetime
from config import MINDEST_GUTHABEN

bar_bp = Blueprint("bar", __name__)


def hotlist():
    """
    Hole die letzten häufigsten Käufer
    """
    # Hole die letzten 20 Buchungen
    letzte_buchungen = (
        Buchung.query.order_by(Buchung.id.desc())
        .limit(50)  # etwas größer, falls einige doppelt sind
        .all()
    )

    # Sammle die Mitglieds-IDs aus diesen Buchungen
    mitglied_ids = {b.mitglied_id for b in letzte_buchungen}

    # Berechne für diese Mitglieder die Gesamtmenge aller Käufe
    mitglieder_mit_mengen = (
        db.session.query(Mitglied, func.sum(Buchung.menge).label("gesamtmenge"))
        .join(Mitglied.buchungen_von_mitglied)
        .filter(Buchung.mitglied_id.in_(mitglied_ids))
        .group_by(Mitglied.id)
        .order_by(desc("gesamtmenge"), Mitglied.name)
        .limit(20)
        .all()
    )
    return [m for m, _ in mitglieder_mit_mengen]


@bar_bp.route("/", methods=["GET", "POST"])
def bar_interface():
    """
    Hauptinterface für die Bar.
    Zeigt eine Mitglieder-Suchleiste und nach der Auswahl die Artikel an.
    """
    # Mitglieder abrufen
    mitglieder = hotlist()

    return render_template(
        "bar/bar_interface.html",
        mitglieder=[
            {
                "id": mitglied.id,
                "name": mitglied.name,
                "nickname": mitglied.nickname,
                "guthaben": mitglied.guthaben,
                "blacklist": mitglied.blacklist,
            }
            for mitglied in mitglieder
        ],
    )


@bar_bp.route("/api/members", methods=["GET"])
def get_members_api():
    search_term = request.args.get("search", "")  # Suchbegriff aus den URL-Parametern

    if search_term:
        # PostgreSQL text search across name and nickname columns
        # Using to_tsvector for full-text search
        members_query = Mitglied.query.filter(
            text(
                """
                to_tsvector( name || ' ' || nickname)  @@  to_tsquery(:search_term) 
                or name iLike '%' || :search_term || '%' 
                or nickname iLike '%' || :search_term || '%'"""
            )
        ).params(search_term=search_term)
        members = members_query.order_by(Mitglied.name).all()
    else:
        members = hotlist()

    return jsonify(
        {
            "success": True,
            "members": list(
                map(
                    lambda member: {
                        "id": member.id,
                        "name": member.name,
                        "nickname": member.nickname,
                        "guthaben": member.guthaben,
                        "blacklist": member.blacklist,
                        # Füge hier alle weiteren Daten hinzu, die du im Frontend benötigst
                    },
                    members,
                )
            ),
        }
    )


@bar_bp.route("/bar/buchen", methods=["GET", "POST"])
def buchen():
    if request.method == "GET":
        mitglied_id = request.args.get("mitglied_id")
        if not mitglied_id:
            flash("Mitglied-ID fehlt!", "error")
            return redirect(url_for("bar.bar_interface"))

        mitglied = Mitglied.query.get(mitglied_id)
        if not mitglied:
            flash("Mitglied nicht gefunden!", "error")
            return redirect(url_for("bar.bar_interface"))

        artikel_liste = Artikel.query.order_by(Artikel.order).all()
        buchungen = (
            Buchung.query.filter_by(mitglied_id=mitglied.id)
            .order_by(Buchung.zeitstempel.desc())
            .limit(5)
            .all()
        )

        return render_template(
            "bar/buchen.html",
            mitglied=mitglied,
            artikel_liste=artikel_liste,
            buchungen=buchungen,
        )

    # POST → Buchung
    data = request.get_json()
    mitglied_id = data.get("mitglied_id")
    artikel_id = data.get("artikel_id")
    menge = data.get("menge")

    if not all([mitglied_id, artikel_id, menge]):
        return jsonify({"success": False, "message": "Fehlende Daten."}), 400

    mitglied = Mitglied.query.get(mitglied_id)
    artikel = Artikel.query.get(artikel_id)
    if not mitglied or not artikel:
        return (
            jsonify(
                {"success": False, "message": "Mitglied oder Artikel nicht gefunden."}
            ),
            404,
        )

    try:
        menge = int(menge)

        gesamtpreis = artikel.preis * menge
        if not mitglied.blacklist and mitglied.guthaben < MINDEST_GUTHABEN:
            pass  # User ist manuell entschwärzt worden
        elif mitglied.blacklist:
            message = "Kein Geld 🗿"
            flash(message, "error")
            return (
                jsonify({"success": False, "message": message}),
                400,
            )
        elif mitglied.guthaben - gesamtpreis < MINDEST_GUTHABEN:
            mitglied.blacklist = True
        else:
            mitglied.blacklist = False

        mitglied.guthaben -= gesamtpreis
        artikel.bestand -= menge

        neue_buchung = Buchung(
            mitglied_id=mitglied.id,
            artikel_id=artikel.id,
            menge=menge,
            preis_pro_einheit=artikel.preis,
            gesamtpreis=gesamtpreis,
            zeitstempel=datetime.utcnow(),
        )
        db.session.add(neue_buchung)
        db.session.commit()

        # Flask flash und redirect
        flash(
            f"Buchung für {mitglied.name} erfolgreich: {menge}× {artikel.name} ({gesamtpreis:.2f}€)",
            "success",
        )
        return jsonify({"success": True, "redirect_url": url_for("bar.bar_interface")})

    except Exception as e:
        db.session.rollback()
        print(f"Fehler bei der Buchung: {e}")
        return (
            jsonify(
                {"success": False, "message": "Interner Serverfehler bei der Buchung."}
            ),
            500,
        )
