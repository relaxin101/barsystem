from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, session
from sqlalchemy import func, case

import config as app_config
from models import db, Artikel, Buchung, Mitglied, RankingArtikel, RankingKonfiguration

ranking_bp = Blueprint("ranking", __name__, url_prefix="/ranking")

_SESSION_STUNDEN = 'ranking_stunden'
_SESSION_ARTIKEL = 'ranking_artikel_ids'
_SESSION_MODUS   = 'ranking_modus'
_SESSION_SET_AT  = 'ranking_config_set_at'


def _check_and_expire_config():
    set_at_str = session.get(_SESSION_SET_AT)
    if not set_at_str:
        return
    if datetime.now() - datetime.fromisoformat(set_at_str) > timedelta(hours=app_config.RANKING_CONFIG_TTL_STUNDEN):
        session.pop(_SESSION_STUNDEN, None)
        session.pop(_SESSION_ARTIKEL, None)
        session.pop(_SESSION_MODUS,   None)
        session.pop(_SESSION_SET_AT,  None)


def _get_db_konfiguration():
    config = RankingKonfiguration.query.get(1)
    if config is None:
        config = RankingKonfiguration(id=1, stunden=24)
        db.session.add(config)
        db.session.commit()
    return config


def _get_session_stunden():
    if _SESSION_STUNDEN not in session:
        session[_SESSION_STUNDEN] = app_config.RANKING_DEFAULT_STUNDEN
    return session[_SESSION_STUNDEN]


def _get_session_artikel_ids():
    if _SESSION_ARTIKEL not in session:
        session[_SESSION_ARTIKEL] = [
            a.id for a in Artikel.query.filter(Artikel.reinalkohol_liter > 0).all()
        ]
    return set(session[_SESSION_ARTIKEL])


def _get_session_modus():
    if _SESSION_MODUS not in session:
        session[_SESSION_MODUS] = 'menge'
    return session[_SESSION_MODUS]


_VALID_MODI = ('menge', 'reinalkohol', 'umsatz')


@ranking_bp.route("/")
def index():
    _check_and_expire_config()
    stunden     = _get_session_stunden()
    selected_ids = _get_session_artikel_ids()
    modus       = _get_session_modus()
    seit        = datetime.now() - timedelta(hours=stunden)

    artikel_liste = (
        Artikel.query
        .filter(Artikel.id.in_(selected_ids))
        .order_by(Artikel.reihenfolge)
        .all()
    ) if selected_ids else []

    if not artikel_liste:
        return render_template(
            "ranking/index.html",
            eintraege=[], artikel_liste=[],
            stunden=stunden, seit=seit, modus=modus,
        )

    n = len(artikel_liste)
    artikel_cols = [
        func.sum(
            case((Buchung.artikel_id == a.id, Buchung.menge), else_=0)
        ).label(f"art_{a.id}")
        for a in artikel_liste
    ]
    gesamt_menge_col  = func.sum(Buchung.menge).label("gesamt_menge")
    gesamt_umsatz_col = (func.sum(
        case((Buchung.gesamtpreis < 0, Buchung.gesamtpreis), else_=0)
    ) * -1).label("gesamt_umsatz")

    rows = (
        db.session.query(Mitglied, *artikel_cols, gesamt_menge_col, gesamt_umsatz_col)
        .join(Buchung, Buchung.mitglied_id == Mitglied.id)
        .filter(
            Buchung.artikel_id.in_(list(selected_ids)),
            Buchung.storno == False,
            Mitglied.aktiv == True,
            Buchung.zeitstempel >= seit,
        )
        .group_by(Mitglied.id)
        .all()
    )

    eintraege = []
    for row in rows:
        mitglied   = row[0]
        art_stueck    = {a.id: row[i + 1] for i, a in enumerate(artikel_liste)}

        # Menge-Anzeige: Stück-Artikel → Stückzahl, Volumen-Artikel → Stückzahl × volumen_liter
        art_menge = {}
        for a in artikel_liste:
            cnt = art_stueck.get(a.id, 0)
            if a.typ == 'volumen':
                art_menge[a.id] = round(cnt * (a.volumen_liter or 0.5), 3)
            else:
                art_menge[a.id] = cnt
        gesamt_menge = round(sum(art_menge.values()), 3)

        # Reinalkohol: Stückzahl × reinalkohol_liter × 1000 (mL)
        art_reinalkohol = {
            a.id: round(art_stueck.get(a.id, 0) * (a.reinalkohol_liter or 0) * 1000, 1)
            for a in artikel_liste
        }
        gesamt_reinalkohol = round(sum(art_reinalkohol.values()), 1)

        # Umsatz aus tatsächlich gebuchten Preisen (Cent)
        gesamt_umsatz = row[n + 2] or 0

        eintraege.append({
            "mitglied":           mitglied,
            "art_stueck":         art_stueck,
            "art_menge":          art_menge,
            "art_reinalkohol":    art_reinalkohol,
            "gesamt_menge":       gesamt_menge,
            "gesamt_reinalkohol": gesamt_reinalkohol,
            "gesamt_umsatz":      gesamt_umsatz,
        })

    if modus == 'reinalkohol':
        eintraege.sort(key=lambda e: e['gesamt_reinalkohol'], reverse=True)
    elif modus == 'umsatz':
        eintraege.sort(key=lambda e: e['gesamt_umsatz'], reverse=True)
    else:
        eintraege.sort(key=lambda e: e['gesamt_menge'], reverse=True)

    return render_template(
        "ranking/index.html",
        eintraege=eintraege,
        artikel_liste=artikel_liste,
        stunden=stunden,
        seit=seit,
        modus=modus,
    )


@ranking_bp.route("/config", methods=["GET"])
def config():
    _check_and_expire_config()
    stunden      = _get_session_stunden()
    selected_ids = _get_session_artikel_ids()
    modus        = _get_session_modus()
    alle_artikel = Artikel.query.filter_by(aktiv=True).order_by(Artikel.reihenfolge).all()
    return render_template(
        "ranking/config.html",
        alle_artikel=alle_artikel,
        selected_ids=selected_ids,
        stunden=stunden,
        modus=modus,
    )


@ranking_bp.route("/config/toggle/<int:artikel_id>", methods=["POST"])
def toggle_artikel(artikel_id):
    Artikel.query.get_or_404(artikel_id)
    ids = _get_session_artikel_ids()
    if artikel_id in ids:
        ids.discard(artikel_id)
        aktiv = False
    else:
        ids.add(artikel_id)
        aktiv = True
    session[_SESSION_ARTIKEL] = list(ids)
    session[_SESSION_SET_AT] = datetime.now().isoformat()
    return jsonify({"success": True, "aktiv": aktiv})


@ranking_bp.route("/config/stunden", methods=["POST"])
def set_stunden():
    data = request.get_json()
    try:
        stunden = int(data.get("stunden", 24))
        if stunden < 1:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "Ungültiger Wert"}), 400
    session[_SESSION_STUNDEN] = stunden
    session[_SESSION_SET_AT] = datetime.now().isoformat()
    return jsonify({"success": True, "stunden": stunden})


@ranking_bp.route("/config/modus", methods=["POST"])
def set_modus():
    modus = request.get_json().get("modus", "menge")
    if modus not in _VALID_MODI:
        modus = "menge"
    session[_SESSION_MODUS] = modus
    session[_SESSION_SET_AT] = datetime.now().isoformat()
    return jsonify({"success": True, "modus": modus})


@ranking_bp.route("/config/alle-auswaehlen", methods=["POST"])
def alle_auswaehlen():
    session[_SESSION_ARTIKEL] = [
        a.id for a in Artikel.query.filter_by(aktiv=True).all()
    ]
    session[_SESSION_SET_AT] = datetime.now().isoformat()
    return redirect(url_for("ranking.config"))


@ranking_bp.route("/config/alle-abwaehlen", methods=["POST"])
def alle_abwaehlen():
    session[_SESSION_ARTIKEL] = []
    session[_SESSION_SET_AT] = datetime.now().isoformat()
    return redirect(url_for("ranking.config"))


@ranking_bp.route("/api/version")
def api_version():
    """Lightweight fingerprint of current booking state for polling."""
    max_id      = db.session.query(func.max(Buchung.id)).scalar() or 0
    max_storno  = db.session.query(func.max(Buchung.storno_updated_at)).scalar()
    fingerprint = f"{max_id}_{max_storno.isoformat() if max_storno else 'none'}"
    return jsonify({"v": fingerprint})


@ranking_bp.route("/config/reset", methods=["POST"])
def reset_config():
    session.pop(_SESSION_STUNDEN, None)
    session.pop(_SESSION_ARTIKEL, None)
    session.pop(_SESSION_MODUS,   None)
    session.pop(_SESSION_SET_AT,  None)
    return redirect(url_for("ranking.config"))
