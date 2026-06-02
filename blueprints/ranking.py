from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from sqlalchemy import func, case

from models import db, Artikel, Buchung, Mitglied, RankingArtikel, RankingKonfiguration

ranking_bp = Blueprint("ranking", __name__, url_prefix="/ranking")


def _get_konfiguration():
    """Gibt die Singleton-Konfiguration zurück, legt sie bei Bedarf an."""
    config = RankingKonfiguration.query.get(1)
    if config is None:
        config = RankingKonfiguration(id=1, stunden=24)
        db.session.add(config)
        db.session.commit()
    return config


@ranking_bp.route("/")
def index():
    config = _get_konfiguration()
    selected = RankingArtikel.query.join(Artikel, RankingArtikel.artikel_id == Artikel.id).order_by(Artikel.reihenfolge).all()

    seit = datetime.now() - timedelta(hours=config.stunden)

    if not selected:
        return render_template(
            "ranking/index.html",
            eintraege=[],
            artikel_liste=[],
            stunden=config.stunden,
            seit=seit,
        )

    selected_ids = [ra.artikel_id for ra in selected]
    artikel_liste = [ra.artikel_obj for ra in selected]

    # Pro Artikel eine aggregierte Spalte
    artikel_cols = [
        func.sum(
            case((Buchung.artikel_id == a.id, Buchung.menge), else_=0)
        ).label(f"art_{a.id}")
        for a in artikel_liste
    ]

    gesamt_col = func.sum(Buchung.menge).label("gesamt")

    rows = (
        db.session.query(Mitglied, *artikel_cols, gesamt_col)
        .join(Buchung, Buchung.mitglied_id == Mitglied.id)
        .filter(
            Buchung.artikel_id.in_(selected_ids),
            Buchung.storno == False,
            Mitglied.aktiv == True,
            Buchung.zeitstempel >= seit,
        )
        .group_by(Mitglied.id)
        .order_by(gesamt_col.desc())
        .all()
    )

    eintraege = []
    for row in rows:
        mitglied = row[0]
        art_mengen = {a.id: row[i + 1] for i, a in enumerate(artikel_liste)}
        gesamt = row[-1]
        eintraege.append({
            "mitglied": mitglied,
            "art_mengen": art_mengen,
            "gesamt": gesamt,
        })

    return render_template(
        "ranking/index.html",
        eintraege=eintraege,
        artikel_liste=artikel_liste,
        stunden=config.stunden,
        seit=seit,
    )


@ranking_bp.route("/config", methods=["GET"])
def config():
    konfiguration = _get_konfiguration()
    alle_artikel = Artikel.query.filter_by(aktiv=True).order_by(Artikel.reihenfolge).all()
    selected_ids = {ra.artikel_id for ra in RankingArtikel.query.all()}
    return render_template(
        "ranking/config.html",
        alle_artikel=alle_artikel,
        selected_ids=selected_ids,
        stunden=konfiguration.stunden,
    )


@ranking_bp.route("/config/toggle/<int:artikel_id>", methods=["POST"])
def toggle_artikel(artikel_id):
    artikel = Artikel.query.get_or_404(artikel_id)
    eintrag = RankingArtikel.query.filter_by(artikel_id=artikel_id).first()
    if eintrag:
        db.session.delete(eintrag)
        aktiv = False
    else:
        db.session.add(RankingArtikel(artikel_id=artikel_id))
        aktiv = True
    db.session.commit()
    return jsonify({"success": True, "aktiv": aktiv, "name": artikel.name})


@ranking_bp.route("/config/stunden", methods=["POST"])
def set_stunden():
    data = request.get_json()
    try:
        stunden = int(data.get("stunden", 24))
        if stunden < 1:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "Ungültiger Wert"}), 400

    config = _get_konfiguration()
    config.stunden = stunden
    db.session.commit()
    return jsonify({"success": True, "stunden": stunden})
