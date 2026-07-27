import click
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from models import db, User
from flask_login import login_user, logout_user, login_required, current_user

auth_bp = Blueprint("auth", __name__)


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
    """Abmeldung."""
    logout_user()
    flash("Erfolgreich abgemeldet!", "info")
    return redirect(url_for("bar.bar_interface"))
