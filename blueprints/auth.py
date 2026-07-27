from urllib.parse import urlparse

import click
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from models import db, User
from flask_login import login_user, logout_user, login_required, current_user

auth_bp = Blueprint("auth", __name__)


def _safe_redirect_target(target):
    """Return target if it is a safe local URL, otherwise None.

    Prevents open-redirects by only allowing relative paths that point
    back into this application (no host or scheme).
    """
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return None
    if not target.startswith("/"):
        return None
    return target


@auth_bp.cli.command("change-admin-password")
@click.option("--username", default=None,
              help="Username to update. Defaults to ADMIN_USERNAME from config.")
@click.password_option()
def change_admin_password(username, password):
    """Change the password of an admin user."""
    if username is None:
        username = current_app.config["ADMIN_USERNAME"]

    user = User.query.filter_by(username=username).first()
    if user is None:
        raise click.ClickException(f"User '{username}' does not exist.")

    user.set_password(password)
    db.session.commit()
    click.echo(f"Password for user '{username}' updated.")


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
            return redirect(url_for("admin.buchungen.history"))
        else:
            flash("Ungültige Anmeldedaten!", "error")

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    """Abmeldung.

    Optionally accepts a ``next`` parameter (query string or form) with a
    local URL to redirect to after logging out. Defaults to the bar list.
    """
    logout_user()
    flash("Erfolgreich abgemeldet!", "info")
    target = _safe_redirect_target(request.values.get("next"))
    return redirect(target or url_for("bar.bar_interface"))
