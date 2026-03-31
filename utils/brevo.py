"""
Utils for sending requests to brevo
"""
import requests
import logging
from datetime import datetime, timedelta
from config import BREVO_SECRET, BREVO_SENDER_MAIL, BREVO_SENDER_NAME, BREVO_TEMPLATE
from models import db, Mitglied, Buchung, Aussendung

logger = logging.getLogger(__name__)

def single_mail(subject, recipient_mail, recipient_name, message, amount):
    """
    Send a single
    """
    response = requests.post( 
        url="https://api.brevo.com/v3/smtp/email",
        headers={"api-key": BREVO_SECRET},
        json={
            "sender": {
                "email": BREVO_SENDER_MAIL,
                "name": BREVO_SENDER_NAME
            },
            "subject": subject,
            "templateId": BREVO_TEMPLATE,
            "params":  {
                  "title": subject,
                  "name": recipient_name,
                  "amount": amount,
                  "message": message
            },
            "to": [
                {
                    "email": recipient_mail,
                    "name": recipient_name
                }
            ]
        }
    )
    if not response.ok:
        logger.error(f"Brevo request to {recipient_mail} failed with {response.status_code}: {response.content}")
    else:
        logger.info(f"Mail successfully sent to {recipient_mail}")
    return response


def bulk_mail(mitglieder, subject, message):
    sent = 0
    failed = 0

    for m in mitglieder:
        if not m.email:
            continue

        try:
            response = single_mail(
                subject=subject,
                recipient_mail=m.email,
                recipient_name=m.name,
                message=message,
                amount=f"{m.guthaben:.2f} €"
            )

            if response.ok:
                sent += 1
            else:
                failed += 1

        except Exception as e:
            failed += 1
            print(f"Mail error for {m.email}: {e}")
    return (sent, failed)

def aussendungen(aussendung: Aussendung):
    if not aussendung.aktiv:
        return 1, "Aussendung ist inaktiv."


    if aussendung.member_days > 0:
        since = datetime.now() - timedelta(days=aussendung.member_days)

        mitglieder = (
            db.session.query(Mitglied)
            .join(Buchung, Buchung.mitglied_id == Mitglied.id)
            .filter(
                Buchung.zeitstempel >= since,
                Buchung.storniert.is_(None)
            )
            .distinct()
            .all()
        )
    else:
        mitglieder =  Mitglied.query .filter_by( blacklist=True) .all()
        
    


    sent, failed = bulk_mail(mitglieder, aussendung.subject, aussendung.message)

    # 🕒 last_run setzen
    aussendung.last_run = datetime.now()
    db.session.commit()

    return 0, f"Aussendung ausgeführt: {sent} gesendet, {failed} fehlgeschlagen."

