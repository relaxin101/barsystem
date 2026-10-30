"""Automatische Aufbuchung via IMAP-Postfach."""
import email
import imaplib
import logging
import re
from email.header import decode_header as _raw_decode
from html.parser import HTMLParser

import config
from models import Buchung, db
from utils.admin import calc_blacklist, mitglied_sperren, suche_mitglied, parse_betrag_cents
from utils.einstellungen import einstellung
from utils.zeit import utcnow

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
    with app.app_context():
        missing = [k for k, v in {
            "IMAP_HOST": config.IMAP_HOST,
            "IMAP_USER": config.IMAP_USER,
            "IMAP_PASSWORD": config.IMAP_PASSWORD,
            "AUTO_SENDER": einstellung("AUTO_SENDER"),
            "AUTO_KONTO_REGEX": einstellung("AUTO_KONTO_REGEX"),
            "AUTO_BETRAG_REGEX": einstellung("AUTO_BETRAG_REGEX"),
        }.items() if not v]
        if missing:
            logger.debug("Auto-Aufbuchung: übersprungen, fehlende Konfig: %s", ", ".join(missing))
            return

        try:
            _process_mailbox()
        except Exception:
            logger.exception("Auto-Aufbuchung: Unerwarteter Fehler")


def _process_mailbox():
    mail = imaplib.IMAP4_SSL(config.IMAP_HOST, config.IMAP_PORT)
    try:
        mail.login(config.IMAP_USER, config.IMAP_PASSWORD)
        typ, counts = mail.select("INBOX")
        logger.debug("INBOX select: typ=%s counts=%s", typ, counts)

        # IMAP-Suchkriterien aufbauen (AND-Semantik)
        parts = ["UNSEEN", f'FROM "{einstellung("AUTO_SENDER")}"']
        if einstellung("AUTO_BETREFF"):
            parts.append(f'SUBJECT "{einstellung("AUTO_BETREFF")}"')
        logger.debug("Suchkriterien: %s", parts)
        result, data = mail.search(None, *parts)
        logger.debug("UNSEEN search: result=%s data=%s", result, data)
        if result != "OK" or not data[0]:
            return

        konto_re = re.compile(einstellung("AUTO_KONTO_REGEX"), re.MULTILINE)
        betrag_re = re.compile(einstellung("AUTO_BETRAG_REGEX"), re.MULTILINE)

        for msg_id in data[0].split():
            _handle_message(mail, msg_id, konto_re, betrag_re)
    except Exception as e:
        logger.error(e)
    finally:
        try:
            mail.logout()
        except Exception as e:
            logger.error(e)


def _absender_echt(msg):
    """Prüft, ob der eigene Mailserver die Mail als echt vom AUTO_SENDER bestätigt.

    Der From-Header allein lässt sich beliebig fälschen.
    """
    # shortcut: vertraut dem obersten Authentication-Results-Header, das schützt nur,
    # wenn der eigene Mailserver ihn setzt; bei einem Providerwechsel neu prüfen.
    ergebnis = str(msg.get("Authentication-Results", "")).lower()
    domain = re.escape(einstellung("AUTO_SENDER").rpartition("@")[2].lower())
    return bool(domain) and bool(re.search(
        rf";\s*(?:dkim=pass[^;]*header\.[di]=@?|dmarc=pass[^;]*header\.from=)"
        rf"(?:[\w-]+\.)*{domain}(?![\w.-])",
        ergebnis,
    ))


def _name_passt(mitglied, konto_wert):
    """Exakter Vergleich: die Suche findet auch Teilstrings, "Max" träfe sonst "Maximilian"."""
    namen = [mitglied.name, *(mitglied.nickname or "").split(",")]
    return konto_wert.casefold() in {n.strip().casefold() for n in namen if n.strip()}


def _handle_message(mail, msg_id, konto_re, betrag_re):
    result, msg_data = mail.fetch(msg_id, "(RFC822)")
    if result != "OK":
        logger.warning("Auto-Aufbuchung: Fetch fehlgeschlagen für ID %s", msg_id)
        return

    msg = email.message_from_bytes(msg_data[0][1])
    subject = _decode_header(msg.get("Subject", ""))
    from_addr = _decode_header(msg.get("From", ""))

    if not _absender_echt(msg):
        logger.warning(
            "Auto-Aufbuchung: Absender nicht bestätigt, nicht gebucht — from=%s, subject=%s",
            from_addr, subject,
        )
        return

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
        konto_wert = konto_m.group(einstellung("AUTO_KONTO_GROUP")).strip()
    except IndexError:
        logger.error(
            "Auto-Aufbuchung: AUTO_KONTO_GROUP=%d existiert nicht im Match — from=%s, subject=%s",
            einstellung("AUTO_KONTO_GROUP"), from_addr, subject,
        )
        return

    try:
        betrag_cents = parse_betrag_cents(betrag_m.group(einstellung("AUTO_BETRAG_GROUP")))
    except IndexError:
        logger.error(
            "Auto-Aufbuchung: AUTO_BETRAG_GROUP=%d existiert nicht im Match — from=%s, subject=%s",
            einstellung("AUTO_BETRAG_GROUP"), from_addr, subject,
        )
        return
    except ValueError as exc:
        logger.error(
            "Auto-Aufbuchung: Betrag '%s' nicht parsierbar (%s) — from=%s, subject=%s",
            betrag_m.group(einstellung("AUTO_BETRAG_GROUP")), exc, from_addr, subject,
        )
        return

    if betrag_cents <= 0:
        logger.warning(
            "Auto-Aufbuchung: Betrag %d Cent ≤ 0, übersprungen — from=%s, subject=%s",
            betrag_cents, from_addr, subject,
        )
        return

    treffer = [m for m in suche_mitglied(konto_wert) if _name_passt(m, konto_wert)]

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

    mitglied = mitglied_sperren(treffer[0].id)

    try:
        mitglied.blacklist = calc_blacklist(mitglied, betrag_cents)
        mitglied.guthaben += betrag_cents
        buchung = Buchung(
            mitglied_id=mitglied.id,
            artikel_id=None,
            menge=1,
            preis_pro_einheit=betrag_cents,
            gesamtpreis=betrag_cents,
            zeitstempel=utcnow(),
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
