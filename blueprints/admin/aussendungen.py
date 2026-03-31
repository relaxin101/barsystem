from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from datetime import datetime, timedelta

from models import db, Mitglied, Buchung, Aussendung
from utils.brevo import aussendungen, bulk_mail, single_mail, bulk_mail
#from app import scheduler

aussendungen_bp = Blueprint(
    "aussendungen",
    __name__,
    url_prefix="/aussendungen"
)


# --------------------------------
# 📬 Übersicht / Formular
# --------------------------------
@aussendungen_bp.route("/", methods=["GET"])
@login_required
def index():
    aussendungen = Aussendung.query.order_by(Aussendung.id.desc()).all()
    return render_template(
        "admin/aussendungen.html",
        aussendungen=aussendungen
    )

# --------------------------------
# 📤 Versand starten
# --------------------------------
@aussendungen_bp.route("/send", methods=["POST"])
@login_required
def send_aussendung():
    subject = request.form.get("subject")
    message = request.form.get("message")
    days = request.form.get("days", type=int)
    days = 7 if days is None or days < 0 else days
    test_receiver = request.form.get("test-receiver")

    if not subject or not message:
        flash("Betreff und Nachricht sind erforderlich.", "danger")
        return redirect(url_for("admin.aussendungen.index"))

    # Zeitraum: letzte 7 Tage
    seven_days_ago = datetime.now() - timedelta(days=days)

    # Mitglieder mit Buchungen in diesem Zeitraum
    mitglieder = (
        db.session.query(Mitglied)
        .join(Buchung, Buchung.mitglied_id == Mitglied.id)
        .filter(Buchung.zeitstempel >= seven_days_ago, Buchung.storniert.is_(None))
        .distinct()
        .all()
    )
    if test_receiver:
        response = single_mail(
            subject=subject,
            recipient_mail=test_receiver,
            recipient_name="Test User",
            message=message,
            amount="48.00 €"
        )
        if response.ok:
            flash(f"Email erfolgreich abgesendet", "success")
        else:
            flash(f"Error {response.status_code}: {response.content}", "error")
        return redirect(url_for("admin.aussendungen.index"))

    if not mitglieder:
        flash("Keine Mitglieder mit Buchungen in den letzten 7 Tagen gefunden.", "warning")
        return redirect(url_for("admin.aussendungen.index"))

    sent, failed = bulk_mail(mitglieder, subject, message)

    flash(f"{sent} Mails gesendet, {failed} fehlgeschlagen.", "success" if sent else "warning")
    return redirect(url_for("admin.aussendungen.index"))

@aussendungen_bp.route("/create", methods=["POST"])
@login_required
def create_aussendung():
    subject = request.form.get("subject")
    message = request.form.get("message")
    frequenz = request.form.get("frequenz")
    days = request.form.get("days", type=int)
    days = 7 if days is None or days < 0 else days

    if not subject or not message:
        flash("Subject und Message sind erforderlich", "danger")
        return redirect(url_for("admin.aussendungen.index"))

    a = Aussendung(
        subject=subject,
        message=message,
        frequenz=frequenz,
        member_days=days,
        aktiv=True
    )
    db.session.add(a)
    db.session.commit()

    flash("Aussendung erstellt", "success")
    return redirect(url_for("admin.aussendungen.index"))

@aussendungen_bp.route("/update/<int:id>", methods=["POST"])
@login_required
def update_aussendung(id):
    a = Aussendung.query.get_or_404(id)

    a.subject = request.form.get("subject")
    a.frequenz = request.form.get("frequenz")
    a.member_days = request.form.get("member_days")

    db.session.commit()

    flash("Aussendung aktualisiert", "success")
    return redirect(url_for("admin.aussendungen.index"))

@aussendungen_bp.route("/delete/<int:id>", methods=["POST"])
@login_required
def delete_aussendung(id):
    a = Aussendung.query.get_or_404(id)

    db.session.delete(a)
    db.session.commit()

    flash("Aussendung gelöscht", "success")
    return redirect(url_for("admin.aussendungen.index"))

@aussendungen_bp.route("/toggle/<int:id>", methods=["POST"])
@login_required
def toggle_aussendung(id):
    a = Aussendung.query.get_or_404(id)

    a.aktiv = not a.aktiv
    db.session.commit()

    return {"success": True, "aktiv": a.aktiv}

@aussendungen_bp.route("/run/<int:id>", methods=["POST"])
@login_required
def run_aussendung(id):
    a = Aussendung.query.get_or_404(id)
    error, message = aussendungen(a)
    flash(message, "error" if error else "success")
    return redirect(url_for("admin.aussendungen.index"))



#@scheduler.task('interval', id='aussendungen', seconds=3600)
def cronjob():
    aussendungen = Aussendung.query.filter_by(aktiv=True).all()

    for a in aussendungen:
        # Zeitraum basierend auf Frequenz
        days_map = {
            "daily": 1,
            "weekly": 7,
            "monthly": 30,
            "yearly": 365
        }
        if not a.frequenz.isdigit and not a.frequenz in days_map.keys():
            continue

        days = days_map.get(a.frequenz, 7) if not a.frequenz.isdigit() else int(a.frequenz)
        if a.last_run + timedelta(days=days) <= datetime.now():
            run_aussendung(a.id)

    db.session.commit()



