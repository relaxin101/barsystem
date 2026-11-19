"""Benutzerverwaltung im Adminpanel (nur Superuser)"""

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user

from blueprints.auth import MIN_PASSWORT_LAENGE
from models import db, User
from utils.admin import superuser_required

benutzer_bp = Blueprint("benutzer", __name__, url_prefix="/benutzer")


def _zurueck():
    return redirect(url_for("admin.benutzer.index"))


def _ist_standarduser(user):
    return user.username == current_app.config["ADMIN_USERNAME"]


def _ist_letzter_superuser(user):
    return user.is_superuser and User.query.filter_by(is_superuser=True).count() == 1


@benutzer_bp.route("/")
@superuser_required
def index():
    return render_template(
        "admin/benutzer.html",
        benutzer=User.query.order_by(User.username).all(),
        min_laenge=MIN_PASSWORT_LAENGE,
    )


@benutzer_bp.route("/anlegen", methods=["POST"])
@superuser_required
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
        user = User(username=username, is_superuser="superuser" in request.form)
        user.set_password(passwort)
        db.session.add(user)
        db.session.commit()
        flash(f"Benutzer '{username}' angelegt.", "success")
    return _zurueck()


@benutzer_bp.route("/<int:user_id>/passwort", methods=["POST"])
@superuser_required
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
@superuser_required
def rolle(user_id):
    user = User.query.get_or_404(user_id)

    if _ist_standarduser(user):
        flash("Der Standarduser aus der .env ist immer Superuser.", "error")
    elif _ist_letzter_superuser(user):
        flash("Der letzte Superuser kann nicht herabgestuft werden.", "error")
    else:
        user.is_superuser = not user.is_superuser
        db.session.commit()
        flash(f"Rolle von '{user.username}' geändert.", "success")
    return _zurueck()


@benutzer_bp.route("/<int:user_id>/loeschen", methods=["POST"])
@superuser_required
def loeschen(user_id):
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash("Das eigene Konto kann nicht gelöscht werden.", "error")
    elif _ist_standarduser(user):
        flash("Der Standarduser aus der .env kann nicht gelöscht werden.", "error")
    elif _ist_letzter_superuser(user):
        flash("Der letzte Superuser kann nicht gelöscht werden.", "error")
    else:
        db.session.delete(user)
        db.session.commit()
        flash(f"Benutzer '{user.username}' gelöscht.", "success")
    return _zurueck()
