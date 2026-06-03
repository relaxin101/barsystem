"""Automatische Aufbuchung via IMAP-Postfach."""
import email
import imaplib
import logging
import re
from datetime import datetime
from email.header import decode_header as _raw_decode
from html.parser import HTMLParser

import config
from models import Buchung, db
from utils.admin import calc_blacklist, suche_mitglied, parse_betrag_cents

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts = []

    def handle_data(self, data):
        self._parts.append(data)

    def get_text(self):
        return " ".join(self._parts)


def _strip_html(html: str) -> str:
    s = _HTMLStripper()
    s.feed(html)
    return s.get_text()


def _decode_header(value: str) -> str:
    if not value:
        return ""
    parts = _raw_decode(value)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded)


def _get_body(msg: email.message.Message) -> str:
    """Plain-text body extrahieren, HTML als Fallback."""
    plain = html = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if "attachment" in cd:
                continue
            charset = part.get_content_charset() or "utf-8"
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            text = payload.decode(charset, errors="replace")
            if ct == "text/plain" and not plain:
                plain = text
            elif ct == "text/html" and not html:
                html = text
    else:
        charset = msg.get_content_charset() or "utf-8"
        payload = msg.get_payload(decode=True)
        if payload:
            text = payload.decode(charset, errors="replace")
            if msg.get_content_type() == "text/html":
                html = text
            else:
                plain = text
    return plain or _strip_html(html)


# ---------------------------------------------------------------------------
# Cronjob
# ---------------------------------------------------------------------------

def cronjob(app):
    missing = [k for k, v in {
        "IMAP_HOST": config.IMAP_HOST,
        "IMAP_USER": config.IMAP_USER,
        "IMAP_PASSWORD": config.IMAP_PASSWORD,
        "AUTO_KONTO_REGEX": config.AUTO_KONTO_REGEX,
        "AUTO_BETRAG_REGEX": config.AUTO_BETRAG_REGEX,
    }.items() if not v]
    if missing:
        logger.debug("Auto-Aufbuchung: übersprungen, fehlende Konfig: %s", ", ".join(missing))
        return

    with app.app_context():
        try:
            _process_mailbox()
        except Exception:
            logger.exception("Auto-Aufbuchung: Unerwarteter Fehler")


def _process_mailbox():
    mail = imaplib.IMAP4_SSL(config.IMAP_HOST, config.IMAP_PORT)
    try:
        mail.login(config.IMAP_USER, config.IMAP_PASSWORD)
        mail.select("INBOX")

        # IMAP-Suchkriterien aufbauen (AND-Semantik)
        parts = ["UNSEEN"]
        if config.AUTO_SENDER:
            parts.append(f'FROM "{config.AUTO_SENDER}"')
        if config.AUTO_BETREFF:
            parts.append(f'SUBJECT "{config.AUTO_BETREFF}"')
        criteria = "(" + " ".join(parts) + ")"

        result, data = mail.search(None, criteria)
        if result != "OK" or not data[0]:
            return

        konto_re = re.compile(config.AUTO_KONTO_REGEX, re.MULTILINE)
        betrag_re = re.compile(config.AUTO_BETRAG_REGEX, re.MULTILINE)

        for msg_id in data[0].split():
            _handle_message(mail, msg_id, konto_re, betrag_re)
    finally:
        try:
            mail.logout()
        except Exception:
            pass


def _handle_message(mail, msg_id, konto_re, betrag_re):
    result, msg_data = mail.fetch(msg_id, "(RFC822)")
    if result != "OK":
        logger.warning("Auto-Aufbuchung: Fetch fehlgeschlagen für ID %s", msg_id)
        return

    msg = email.message_from_bytes(msg_data[0][1])
    subject = _decode_header(msg.get("Subject", ""))
    from_addr = _decode_header(msg.get("From", ""))
    body = _get_body(msg)
    search_text = f"{subject}\n{from_addr}\n{body}"

    konto_m = konto_re.search(search_text)
    betrag_m = betrag_re.search(search_text)

    if not konto_m or not betrag_m:
        logger.warning(
            "Auto-Aufbuchung: Regex kein Treffer — from=%s, subject=%s",
            from_addr, subject,
        )
        return

    try:
        konto_wert = konto_m.group(config.AUTO_KONTO_GROUP).strip()
    except IndexError:
        logger.error(
            "Auto-Aufbuchung: AUTO_KONTO_GROUP=%d existiert nicht im Match — from=%s, subject=%s",
            config.AUTO_KONTO_GROUP, from_addr, subject,
        )
        return

    try:
        betrag_cents = parse_betrag_cents(betrag_m.group(config.AUTO_BETRAG_GROUP))
    except IndexError:
        logger.error(
            "Auto-Aufbuchung: AUTO_BETRAG_GROUP=%d existiert nicht im Match — from=%s, subject=%s",
            config.AUTO_BETRAG_GROUP, from_addr, subject,
        )
        return
    except ValueError as exc:
        logger.error(
            "Auto-Aufbuchung: Betrag '%s' nicht parsierbar (%s) — from=%s, subject=%s",
            betrag_m.group(config.AUTO_BETRAG_GROUP), exc, from_addr, subject,
        )
        return

    if betrag_cents <= 0:
        logger.warning(
            "Auto-Aufbuchung: Betrag %d Cent ≤ 0, übersprungen — from=%s, subject=%s",
            betrag_cents, from_addr, subject,
        )
        return

    treffer = suche_mitglied(konto_wert)

    # Zuerst als gelesen markieren, damit die Mail nicht nochmals verarbeitet wird
    mail.store(msg_id, "+FLAGS", "\\Seen")

    if not treffer:
        logger.warning(
            "Auto-Aufbuchung: Kein Mitglied für Konto '%s' — from=%s, subject=%s",
            konto_wert, from_addr, subject,
        )
        return

    if len(treffer) > 1:
        namen = ", ".join(m.name for m in treffer)
        logger.warning(
            "Auto-Aufbuchung: Mehrdeutiger Treffer für '%s' (%s) — from=%s, subject=%s",
            konto_wert, namen, from_addr, subject,
        )
        return

    mitglied = treffer[0]

    try:
        mitglied.blacklist = calc_blacklist(mitglied, betrag_cents)
        mitglied.guthaben += betrag_cents
        buchung = Buchung(
            mitglied_id=mitglied.id,
            artikel_id=None,
            menge=1,
            preis_pro_einheit=betrag_cents,
            gesamtpreis=betrag_cents,
            zeitstempel=datetime.now(),
            beschreibung=f"Auto-Aufbuchung: {subject[:200]}",
            storno=False,
        )
        db.session.add(buchung)
        db.session.commit()
        logger.info(
            "Auto-Aufbuchung: %.2f € für %s gebucht (from=%s, subject=%s)",
            betrag_cents / 100, mitglied.name, from_addr, subject,
        )
    except Exception:
        db.session.rollback()
        logger.exception(
            "Auto-Aufbuchung: DB-Fehler für Mitglied '%s', %.2f € — bitte manuell nachbuchen!",
            mitglied.name, betrag_cents / 100,
        )
