from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import db, User
from flask_login import login_user, logout_user, login_required, current_user

auth_bp = Blueprint('auth', __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Anmeldung für Administratoren."""
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            flash("Erfolgreich angemeldet!", "success")
            return redirect(url_for("admin.admin_bereich"))
        else:
            flash("Ungültige Anmeldedaten!", "error")

    return render_template("admin/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    """Abmeldung."""
    logout_user()
    flash("Erfolgreich abgemeldet!", "info")
    return redirect(url_for("bar.bar_interface"))
