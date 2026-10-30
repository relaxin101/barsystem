"""Benutzerverwaltung im Adminpanel (nur Superadmins)"""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from blueprints.auth import MIN_PASSWORT_LAENGE
from models import db, User
from utils.admin import superadmin_required

benutzer_bp = Blueprint("benutzer", __name__, url_prefix="/benutzer")


def _zurueck():
    return redirect(url_for("admin.benutzer.index"))


def _ist_letzter_superadmin(user):
    return user.is_superadmin and User.query.filter_by(is_superadmin=True).count() == 1


@benutzer_bp.route("/")
@superadmin_required
def index():
    return render_template(
        "admin/benutzer.html",
        benutzer=User.query.order_by(User.username).all(),
        min_laenge=MIN_PASSWORT_LAENGE,
    )


@benutzer_bp.route("/anlegen", methods=["POST"])
@superadmin_required
def anlegen():
    username = request.form.get("username", "").strip()
    passwort = request.form.get("passwort", "")

    if not username:
        flash("Es muss ein Benutzername angegeben werden.", "error")
    elif User.query.filter_by(username=username).first():
        flash(f"Benutzer '{username}' gibt es bereits.", "error")
    elif len(passwort) < MIN_PASSWORT_LAENGE:
        flash(f"Das Passwort braucht mindestens {MIN_PASSWORT_LAENGE} Zeichen.", "error")
    else:
        user = User(username=username, is_superadmin="superadmin" in request.form)
        user.set_password(passwort)
        db.session.add(user)
        db.session.commit()
        flash(f"Benutzer '{username}' angelegt.", "success")
    return _zurueck()


@benutzer_bp.route("/<int:user_id>/passwort", methods=["POST"])
@superadmin_required
def passwort(user_id):
    user = User.query.get_or_404(user_id)
    neu = request.form.get("passwort", "")

    if len(neu) < MIN_PASSWORT_LAENGE:
        flash(f"Das Passwort braucht mindestens {MIN_PASSWORT_LAENGE} Zeichen.", "error")
    else:
        user.set_password(neu)
        db.session.commit()
        flash(f"Passwort von '{user.username}' geändert.", "success")
    return _zurueck()


@benutzer_bp.route("/<int:user_id>/rolle", methods=["POST"])
@superadmin_required
def rolle(user_id):
    user = User.query.get_or_404(user_id)

    if _ist_letzter_superadmin(user):
        flash("Der letzte Superadmin kann nicht herabgestuft werden.", "error")
    else:
        user.is_superadmin = not user.is_superadmin
        db.session.commit()
        flash(f"Rolle von '{user.username}' geändert.", "success")
    return _zurueck()


@benutzer_bp.route("/<int:user_id>/loeschen", methods=["POST"])
@superadmin_required
def loeschen(user_id):
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash("Das eigene Konto kann nicht gelöscht werden.", "error")
    elif _ist_letzter_superadmin(user):
        flash("Der letzte Superadmin kann nicht gelöscht werden.", "error")
    else:
        db.session.delete(user)
        db.session.commit()
        flash(f"Benutzer '{user.username}' gelöscht.", "success")
    return _zurueck()
