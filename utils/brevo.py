"""
Utils for sending requests to Brevo
"""
import logging
from datetime import datetime, timedelta

import requests
from sqlalchemy import func, case

from config import BREVO_SECRET, BREVO_SENDER_MAIL, BREVO_SENDER_NAME, BREVO_TEMPLATE
from models import db, Mitglied, Buchung, Artikel, Aussendung

logger = logging.getLogger(__name__)


def _eur(cents):
    return f"€ {cents / 100:.2f}".replace(".", ",")


def _resolve_template(template_override=None):
    """Gibt die Template-ID zurueck - Ueberschreibung hat Vorrang."""
    if template_override is not None:
        return int(template_override)
    return BREVO_TEMPLATE


def _get_verbrauch(mitglied_id, since):
    """
    Gibt den Verbrauch eines Mitglieds seit 'since' als HTML-String zurueck.
    Nur nicht-stornierte Buchungen mit einem Artikel (keine manuellen Aufbuchungen).
    """
    if since is None:
        return ""

    rows = (
        db.session.query(
            Artikel.name,
            func.sum(Buchung.menge).label("menge"),
            Buchung.preis_pro_einheit,
        )
        .join(Artikel, Artikel.id == Buchung.artikel_id)
        .filter(
            Buchung.mitglied_id == mitglied_id,
            Buchung.artikel_id.isnot(None),
            Buchung.zeitstempel >= since,
            Buchung.storniert.is_(None),
        )
        .group_by(Artikel.name, Buchung.preis_pro_einheit)
        .order_by(Artikel.name)
        .all()
    )

    if not rows:
        return ""

    td = "padding:3px 12px 3px 0;vertical-align:top;"
    td_r = "padding:3px 0 3px 12px;text-align:right;vertical-align:top;"
    sep = "border-top:1px solid #000;padding:0;"

    html = (
        '<table style="border-collapse:collapse;font-family:inherit;">'
        "<thead><tr>"
        f'<th style="text-align:left;{td}border-bottom:1px solid #000;">Artikel</th>'
        f'<th style="text-align:right;padding:3px 12px;border-bottom:1px solid #000;">Menge</th>'
        f'<th style="text-align:right;padding:3px 12px;border-bottom:1px solid #000;">Preis/St.</th>'
        f'<th style="text-align:right;{td_r}border-bottom:1px solid #000;">Gesamt</th>'
        "</tr></thead><tbody>"
    )
    for row in rows:
        gesamt_cents = row.menge * row.preis_pro_einheit
        html += (
            "<tr>"
            f'<td style="{td}">{row.name}</td>'
            f'<td style="text-align:right;padding:3px 12px;">{int(row.menge)}</td>'
            f'<td style="text-align:right;padding:3px 12px;">{_eur(row.preis_pro_einheit)}</td>'
            f'<td style="{td_r}">{_eur(gesamt_cents)}</td>'
            "</tr>"
        )
    html += (
        "<tr>"
        f'<td style="{sep}"></td>'
        f'<td style="{sep}"></td>'
        f'<td style="{sep}"></td>'
        f'<td style="{sep}"></td>'
        "</tr>"
        "</tbody></table>"
    )
    return html


def _get_summen(mitglied_id, since):
    """Gibt (gutschrift_str, abbuchung_str) der Periode im Format '€ 0,00' zurueck."""
    if since is None:
        return "€ 0,00", "€ 0,00"

    row = (
        db.session.query(
            func.coalesce(
                func.sum(case((Buchung.gesamtpreis > 0, Buchung.gesamtpreis), else_=0)), 0
            ).label("gutschrift"),
            func.coalesce(
                func.sum(case((Buchung.gesamtpreis < 0, -Buchung.gesamtpreis), else_=0)), 0
            ).label("abbuchung"),
        )
        .filter(
            Buchung.mitglied_id == mitglied_id,
            Buchung.zeitstempel >= since,
            Buchung.storniert.is_(None),
        )
        .one()
    )

    return _eur(row.gutschrift), _eur(row.abbuchung)


def single_mail(subject, recipient_mail, recipient_name, message, amount,
                verbrauch=None, gutschrift=None, abbuchung=None, template=None):
    """Sendet eine einzelne E-Mail via Brevo."""
    template_id = _resolve_template(template)
    response = requests.post(
        url="https://api.brevo.com/v3/smtp/email",
        headers={"api-key": BREVO_SECRET},
        json={
            "sender": {
                "email": BREVO_SENDER_MAIL,
                "name": BREVO_SENDER_NAME,
            },
            "subject": subject,
            "templateId": template_id,
            "params": {
                "title": subject,
                "name": recipient_name,
                "amount": amount,
                "message": message.replace("\n", "<br>"),
                "verbrauch": verbrauch or "",
                "gutschrift": gutschrift or "€ 0,00",
                "abbuchung": abbuchung or "€ 0,00",
            },
            "to": [{"email": recipient_mail, "name": recipient_name}],
        },
    )
    if not response.ok:
        logger.error(
            "Brevo request to %s failed with %s: %s",
            recipient_mail, response.status_code, response.content,
        )
    else:
        logger.info("Mail successfully sent to %s", recipient_mail)
    return response


def bulk_mail(mitglieder, subject, message, since=None, template=None):
    """
    Sendet E-Mails an eine Liste von Mitgliedern.

    since: datetime ab der der Verbrauch berechnet wird (None = kein Verbrauch).
    """
    sent = 0
    failed = 0

    for m in mitglieder:
        if not m.email:
            continue
        try:
            verbrauch = _get_verbrauch(m.id, since)
            gutschrift, abbuchung = _get_summen(m.id, since)
            response = single_mail(
                subject=subject,
                recipient_mail=m.email,
                recipient_name=m.name,
                message=message,
                amount=_eur(m.guthaben),
                verbrauch=verbrauch,
                gutschrift=gutschrift,
                abbuchung=abbuchung,
                template=template,
            )
            if response.ok:
                sent += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1
            logger.error("Mail error for %s: %s", m.email, e)

    return sent, failed


def _get_since(aussendung):
    """Berechnet den 'since'-Zeitpunkt fuer eine Aussendung."""
    if aussendung.alle_mitglieder or not aussendung.member_days:
        return None
    return datetime.now() - timedelta(days=aussendung.member_days)


def _get_recipients(aussendung):
    """Ermittelt die Empfaenger-Liste fuer eine Aussendung."""
    if aussendung.alle_mitglieder:
        return Mitglied.query.filter_by(aktiv=True).all()

    if aussendung.member_days and aussendung.member_days > 0:
        since = datetime.now() - timedelta(days=aussendung.member_days)
        return (
            db.session.query(Mitglied)
            .join(Buchung, Buchung.mitglied_id == Mitglied.id)
            .filter(
                Buchung.zeitstempel >= since,
                Buchung.storniert.is_(None),
                Mitglied.aktiv == True,
            )
            .distinct()
            .all()
        )

    return Mitglied.query.filter_by(blacklist=True).all()


def get_member_count(aussendung):
    """Gibt die Anzahl der Empfaenger fuer eine Aussendung zurueck."""
    if aussendung.alle_mitglieder:
        return Mitglied.query.filter_by(aktiv=True).count()

    if aussendung.member_days and aussendung.member_days > 0:
        since = datetime.now() - timedelta(days=aussendung.member_days)
        return (
            db.session.query(Mitglied.id)
            .join(Buchung, Buchung.mitglied_id == Mitglied.id)
            .filter(
                Buchung.zeitstempel >= since,
                Buchung.storniert.is_(None),
                Mitglied.aktiv == True,
            )
            .distinct()
            .count()
        )

    return Mitglied.query.filter_by(blacklist=True).count()


def aussendungen(aussendung):
    """Fuehrt eine Aussendung aus. Gibt (error_code, message) zurueck."""
    if not aussendung.aktiv:
        return 1, "Aussendung ist inaktiv."

    mitglieder = _get_recipients(aussendung)
    since = _get_since(aussendung)

    sent, failed = bulk_mail(
        mitglieder,
        aussendung.subject,
        aussendung.message,
        since=since,
        template=aussendung.brevo_template,
    )

    aussendung.last_run = datetime.now()
    db.session.commit()

    return 0, f"Aussendung ausgefuehrt: {sent} gesendet, {failed} fehlgeschlagen."