from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from datetime import datetime, timedelta

from models import db, Mitglied, Buchung, Aussendung
from utils.brevo import (
    aussendungen as brevo_send,
    bulk_mail,
    single_mail,
    get_member_count,
)
from config import BREVO_TEMPLATE

aussendungen_bp = Blueprint("aussendungen", __name__, url_prefix="/aussendungen")


def _freq_to_days(frequenz):
    """Konvertiert Frequenz-String zu Anzahl Tage."""
    mapping = {"daily": 1, "weekly": 7, "monthly": 30, "yearly": 365}
    if frequenz in mapping:
        return mapping[frequenz]
    try:
        return int(frequenz)
    except (ValueError, TypeError):
        return 7


# Uebersicht
@aussendungen_bp.route("/", methods=["GET"])
@login_required
def index():
    alle = Aussendung.query.order_by(Aussendung.id.desc()).all()
    return render_template(
        "admin/aussendungen.html",
        aussendungen=alle,
        brevo_template_default=BREVO_TEMPLATE,
    )


# Sofortversand (Formular)
@aussendungen_bp.route("/send", methods=["POST"])
@login_required
def send_aussendung():
    data = request.get_json()
    subject = (data.get("subject") or "").strip()
    message = (data.get("message") or "").strip()
    days = int(data.get("days") or 7)
    alle_mitglieder = bool(data.get("alle_mitglieder", False))
    test_receiver = (data.get("test_receiver") or "").strip()
    brevo_tpl = data.get("brevo_template") or None
    if brevo_tpl:
        brevo_tpl = int(brevo_tpl)

    if not subject or not message:
        return jsonify({"success": False, "message": "Betreff und Nachricht sind erforderlich."})

    if test_receiver:
        response = single_mail(
            subject=subject,
            recipient_mail=test_receiver,
            recipient_name="Test User",
            message=message,
            amount="0.00 EUR",
            template=brevo_tpl,
        )
        if response.ok:
            return jsonify({"success": True, "message": f"Test-Email erfolgreich an {test_receiver} gesendet."})
        return jsonify({"success": False, "message": f"Fehler beim Senden: {response.status_code}"})

    if alle_mitglieder:
        mitglieder = Mitglied.query.filter_by(aktiv=True).all()
    else:
        since = datetime.now() - timedelta(days=days)
        mitglieder = (
            db.session.query(Mitglied)
            .join(Buchung, Buchung.mitglied_id == Mitglied.id)
            .filter(
                Buchung.zeitstempel >= since,
                Buchung.storno == False,
                Mitglied.aktiv == True,
            )
            .distinct()
            .all()
        )

    if not mitglieder:
        return jsonify({"success": False, "message": "Keine Mitglieder gefunden."})

    # since nur setzen wenn nach Konsumenten gefiltert wird
    since = (datetime.now() - timedelta(days=days)) if not alle_mitglieder else None
    sent, failed = bulk_mail(mitglieder, subject, message, since=since, template=brevo_tpl)
    return jsonify({"success": True, "message": f"{sent} Mails gesendet, {failed} fehlgeschlagen."})


# Neue Aussendung speichern
@aussendungen_bp.route("/create", methods=["POST"])
@login_required
def create_aussendung():
    data = request.get_json()
    subject = (data.get("subject") or "").strip()
    message = (data.get("message") or "").strip()
    frequenz = (data.get("frequenz") or "7").strip()
    alle_mitglieder = bool(data.get("alle_mitglieder", False))
    brevo_tpl = data.get("brevo_template") or None

    interval = _freq_to_days(frequenz)
    days = int(data.get("days") or interval)
    if not alle_mitglieder and days < interval:
        days = interval

    if not subject or not message:
        return jsonify({"success": False, "message": "Betreff und Nachricht sind erforderlich."})

    a = Aussendung(
        subject=subject,
        message=message,
        frequenz=frequenz,
        member_days=days,
        alle_mitglieder=alle_mitglieder,
        brevo_template=int(brevo_tpl) if brevo_tpl else None,
        aktiv=True,
    )
    db.session.add(a)
    db.session.commit()
    return jsonify({"success": True})


# Aussendung aktualisieren
@aussendungen_bp.route("/update/<int:id>", methods=["POST"])
@login_required
def update_aussendung(id):
    a = Aussendung.query.get_or_404(id)
    data = request.get_json()

    a.subject = (data.get("subject") or "").strip()
    a.message = (data.get("message") or "").strip()
    a.frequenz = (data.get("frequenz") or "7").strip()
    a.alle_mitglieder = bool(data.get("alle_mitglieder", False))

    interval = _freq_to_days(a.frequenz)
    days = int(data.get("days") or interval)
    if not a.alle_mitglieder and days < interval:
        days = interval
    a.member_days = days

    brevo_tpl = data.get("brevo_template") or None
    a.brevo_template = int(brevo_tpl) if brevo_tpl else None

    db.session.commit()
    return jsonify({"success": True})


# Aussendung loeschen
@aussendungen_bp.route("/delete/<int:id>", methods=["POST"])
@login_required
def delete_aussendung(id):
    a = Aussendung.query.get_or_404(id)
    db.session.delete(a)
    db.session.commit()
    return jsonify({"success": True})


# Aktiv-Toggle
@aussendungen_bp.route("/toggle/<int:id>", methods=["POST"])
@login_required
def toggle_aussendung(id):
    a = Aussendung.query.get_or_404(id)
    a.aktiv = not a.aktiv
    db.session.commit()
    return jsonify({"success": True, "aktiv": a.aktiv})


# Empfaenger-Vorschau fuer gespeicherte Aussendung
@aussendungen_bp.route("/preview/<int:id>", methods=["GET"])
@login_required
def preview_aussendung(id):
    a = Aussendung.query.get_or_404(id)
    count = get_member_count(a)
    return jsonify({"success": True, "count": count})


# Sofortversand einer gespeicherten Aussendung
@aussendungen_bp.route("/run/<int:id>", methods=["POST"])
@login_required
def run_aussendung(id):
    a = Aussendung.query.get_or_404(id)
    error, message = brevo_send(a)
    return jsonify({"success": not bool(error), "message": message})


# Aussendung laden (fuer Bearbeitungs-Formular)
@aussendungen_bp.route("/get/<int:id>", methods=["GET"])
@login_required
def get_aussendung(id):
    a = Aussendung.query.get_or_404(id)
    return jsonify({
        "success": True,
        "aussendung": {
            "id": a.id,
            "subject": a.subject,
            "message": a.message,
            "frequenz": a.frequenz,
            "member_days": a.member_days,
            "alle_mitglieder": a.alle_mitglieder,
            "brevo_template": a.brevo_template,
            "aktiv": a.aktiv,
        },
    })


# Empfaenger-Anzahl fuer Ad-hoc-Versand (Formular-Vorschau)
@aussendungen_bp.route("/send_preview", methods=["POST"])
@login_required
def send_preview():
    data = request.get_json()
    alle = bool(data.get("alle_mitglieder", False))
    days = int(data.get("days") or 7)

    if alle:
        count = Mitglied.query.filter_by(aktiv=True).count()
    else:
        since = datetime.now() - timedelta(days=days)
        count = (
            db.session.query(Mitglied.id)
            .join(Buchung, Buchung.mitglied_id == Mitglied.id)
            .filter(
                Buchung.zeitstempel >= since,
                Buchung.storno == False,
                Mitglied.aktiv == True,
            )
            .distinct()
            .count()
        )
    return jsonify({"success": True, "count": count})


# Cronjob (wird von app.py gestartet)
def cronjob(app):
    with app.app_context():
        alle = Aussendung.query.filter_by(aktiv=True).all()
        for a in alle:
            days = _freq_to_days(a.frequenz)
            if a.last_run is None or a.last_run + timedelta(days=days) <= datetime.now():
                brevo_send(a)