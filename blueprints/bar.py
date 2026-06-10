import os

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app, session
from sqlalchemy import or_, func, text, desc
from models import db, Mitglied, Artikel, Buchung
from datetime import datetime, timedelta
from utils.admin import calc_blacklist, suche_mitglied

bar_bp = Blueprint("bar", __name__)


def hotlist(limit: int = None):
    from flask import current_app
    hotlist_days = current_app.config.get("HOTLIST_DAYS", 14)
    since = datetime.now() - timedelta(days=hotlist_days)

    # Bucket 1: pinned, sorted A→Z — always included
    pinned = (
        Mitglied.query
        .filter(Mitglied.aktiv == True, Mitglied.gepinnt == True)
        .order_by(Mitglied.name)
        .all()
    )
    pinned_ids = {m.id for m in pinned}

    remaining = (limit - len(pinned)) if limit is not None else None
    if remaining is not None and remaining <= 0:
        return pinned

    # Bucket 2: most consumed last HOTLIST_DAYS days, sorted by sum desc then alph
    recent_filters = [
        Mitglied.aktiv == True,
        Mitglied.gepinnt == False,
        Buchung.zeitstempel >= since,
        Buchung.storno == False,
        Buchung.gesamtpreis < 0,
    ]
    if pinned_ids:
        recent_filters.append(~Mitglied.id.in_(pinned_ids))

    recent_q = (
        db.session.query(Mitglied)
        .join(Buchung, Buchung.mitglied_id == Mitglied.id)
        .filter(*recent_filters)
        .group_by(Mitglied.id)
        .order_by(func.sum(Buchung.gesamtpreis).asc(), Mitglied.name)
    )
    if remaining is not None:
        recent_q = recent_q.limit(remaining)
    recent = recent_q.all()
    recent_ids = {m.id for m in recent}

    if remaining is not None:
        remaining -= len(recent)
        if remaining <= 0:
            return pinned + recent

    # Bucket 3: most consumed all-time, sorted by sum desc then alph
    exclude_b3 = pinned_ids | recent_ids
    alltime_filters = [
        Mitglied.aktiv == True,
        Mitglied.gepinnt == False,
        Buchung.storno == False,
        Buchung.gesamtpreis < 0,
    ]
    if exclude_b3:
        alltime_filters.append(~Mitglied.id.in_(exclude_b3))

    alltime_q = (
        db.session.query(Mitglied)
        .join(Buchung, Buchung.mitglied_id == Mitglied.id)
        .filter(*alltime_filters)
        .group_by(Mitglied.id)
        .order_by(func.sum(Buchung.gesamtpreis).asc(), Mitglied.name)
    )
    if remaining is not None:
        alltime_q = alltime_q.limit(remaining)
    alltime = alltime_q.all()
    alltime_ids = {m.id for m in alltime}

    if remaining is not None:
        remaining -= len(alltime)
        if remaining <= 0:
            return pinned + recent + alltime

    # Bucket 4: all remaining active non-pinned, sorted A→Z
    exclude_b4 = pinned_ids | recent_ids | alltime_ids
    alpha_filters = [
        Mitglied.aktiv == True,
        Mitglied.gepinnt == False,
    ]
    if exclude_b4:
        alpha_filters.append(~Mitglied.id.in_(exclude_b4))

    alpha_q = (
        Mitglied.query
        .filter(*alpha_filters)
        .order_by(Mitglied.name)
    )
    if remaining is not None:
        alpha_q = alpha_q.limit(remaining)
    alpha = alpha_q.all()

    return pinned + recent + alltime + alpha


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
    search_term = request.args.get("search", "")
    limit = request.args.get("limit", type=int)

    if search_term:
        members = suche_mitglied(search_term, limit=limit)
    else:
        members = hotlist(limit=limit)

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
                        "gepinnt": member.gepinnt,
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

        artikel_liste = Artikel.query.where(Artikel.aktiv).order_by(Artikel.reihenfolge, Artikel.name).all()
        buchungen = (
            Buchung.query.filter_by(mitglied_id=mitglied.id)
            .order_by(Buchung.zeitstempel.desc())
            .limit(5)
            .all()
        )

        schwaerzung_dir = os.path.join(current_app.static_folder, "schwaerzung")
        allowed_ext = {".webp", ".png", ".jpg", ".jpeg", ".gif"}
        images = sorted([
            f for f in os.listdir(schwaerzung_dir)
            if os.path.splitext(f)[1].lower() in allowed_ext
        ])
        if images:
            idx = session.get("schwaerzung_idx", 0) % len(images)
            session["schwaerzung_idx"] = (idx + 1) % len(images)
            schwaerzungs_bild = url_for("static", filename=f"schwaerzung/{images[idx]}")
        else:
            schwaerzungs_bild = None

        return render_template(
            "bar/buchen.html",
            mitglied=mitglied,
            artikel_liste=artikel_liste,
            buchungen=buchungen,
            schwaerzungs_text=current_app.config.get("SCHWAERZUNGS_TEXT"),
            schwaerzungs_bild=schwaerzungs_bild,
        )

    # POST → Buchung(en)
    data = request.get_json()

    mitglied_id = data.get("mitglied_id")

    # Unterstützt:
    # { artikel_id, menge }
    # ODER
    # { artikel: [ {artikel_id, menge}, ... ] }

    artikel_liste = data.get("artikel")

    if artikel_liste is None:
        # Fallback für alte Einzelbuchung
        artikel_id = data.get("artikel_id")
        menge = data.get("menge")

        artikel_liste = [
            {
                "artikel_id": artikel_id,
                "menge": menge,
            }
        ]

    if not mitglied_id or not artikel_liste:
        return jsonify({
            "success": False,
            "message": "Fehlende Daten."
        }), 400

    mitglied = Mitglied.query.get(mitglied_id)

    if not mitglied:
        return jsonify({
            "success": False,
            "message": "Mitglied nicht gefunden."
        }), 404

    try:

        gesamte_buchungen = []
        gesamtpreis = 0

        # -------------------------
        # Validierung
        # -------------------------
        for item in artikel_liste:

            artikel_id = item.get("artikel_id")
            menge = int(item.get("menge", 0))
            if menge < 0:
                return jsonify({
                    "success": False,
                    "message": "Menge darf nicht negativ sein"
                }), 400

            if not artikel_id or menge <= 0:
                continue

            artikel = Artikel.query.get(artikel_id)

            if not artikel:
                return jsonify({
                    "success": False,
                    "message": f"Artikel {artikel_id} nicht gefunden."
                }), 404

            preis = artikel.preis * menge
            gesamtpreis -= preis

            gesamte_buchungen.append({
                "artikel": artikel,
                "menge": menge,
                "gesamtpreis": -1*preis,
            })

        if len(gesamte_buchungen) == 0:
            return jsonify({
                "success": False,
                "message": "Keine gültigen Artikel."
            }), 400

        # -------------------------
        # Blacklist / Guthaben
        # -------------------------
        if mitglied.blacklist:
            message = "Kein Geld 🗿"
            flash(message, "error")

            return jsonify({
                "success": False,
                "message": message
            }), 400
        else:
            setattr(mitglied, "blacklist", calc_blacklist(mitglied, gesamtpreis))

        # -------------------------
        # Guthaben aktualisieren
        # -------------------------
        mitglied.guthaben += gesamtpreis

        # -------------------------
        # Buchungen anlegen
        # -------------------------
        for eintrag in gesamte_buchungen:

            artikel = eintrag["artikel"]
            menge = eintrag["menge"]

            neue_buchung = Buchung(
                mitglied_id=mitglied.id,
                artikel_id=artikel.id,
                menge=menge,
                preis_pro_einheit=artikel.preis,
                gesamtpreis=eintrag["gesamtpreis"],
                zeitstempel=datetime.now(),
            )

            db.session.add(neue_buchung)
            db.session.add(mitglied)

        db.session.commit()

        betrag = f"{abs(gesamtpreis / 100):.2f}".replace(".", ",")
        flash(
            f"Buchung erfolgreich: € {betrag}",
            "success",
        )

        return jsonify({
            "success": True,
            "redirect_url": url_for("bar.bar_interface")
        })

    except Exception as e:
        flash(str(e))

        db.session.rollback()

        return jsonify({
            "success": False,
            "message": "Interner Serverfehler bei der Buchung."
        }), 500
