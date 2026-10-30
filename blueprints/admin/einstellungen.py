"""Einstellungen im Adminpanel"""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from utils.einstellungen import (
    DEFINITIONEN,
    env_status,
    pruefen,
    quelle,
    rohwert,
    speichern,
    zuruecksetzen,
)
from utils.version import get_version

einstellungen_bp = Blueprint("einstellungen", __name__, url_prefix="/einstellungen")


def _darf_aendern(definition):
    return current_user.is_superadmin or not definition.superadmin


def _seite(eingaben=None, fehler=None, status=200):
    eingaben = eingaben or {}
    gruppen = {}
    for definition in DEFINITIONEN.values():
        if _darf_aendern(definition):
            gruppen.setdefault(definition.gruppe, []).append({
                "definition": definition,
                "wert": eingaben.get(definition.key, rohwert(definition.key)),
                "quelle": quelle(definition.key),
            })
    return render_template(
        "admin/einstellungen.html",
        gruppen=gruppen,
        fehler=fehler or {},
        env_status=env_status() if current_user.is_superadmin else None,
        version=get_version(),
    ), status


@einstellungen_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "GET":
        return _seite()

    eingaben = {k: v for k, v in request.form.items() if k in DEFINITIONEN}
    # Der Server prüft selbst, das Formular zeigt die Felder nur nicht an
    if not all(_darf_aendern(DEFINITIONEN[k]) for k in eingaben):
        abort(403)

    aenderungen = {k: v for k, v in eingaben.items() if v != rohwert(k)}
    fehler = pruefen(aenderungen)
    if fehler:
        flash("Nichts gespeichert, bitte die markierten Felder prüfen.", "error")
        return _seite(eingaben, fehler, status=400)

    if aenderungen:
        speichern(aenderungen, current_user.username)
    flash("Einstellungen gespeichert.", "success")
    return redirect(url_for("admin.einstellungen.index"))


@einstellungen_bp.route("/<key>/zuruecksetzen", methods=["POST"])
@login_required
def zuruecksetzen_route(key):
    definition = DEFINITIONEN.get(key) or abort(404)
    if not _darf_aendern(definition):
        abort(403)
    zuruecksetzen(key)
    flash(f"{definition.label} zurückgesetzt.", "success")
    return redirect(url_for("admin.einstellungen.index"))
