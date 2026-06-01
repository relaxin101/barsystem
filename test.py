from datetime import datetime
from email.header import decode_header as _raw_decode
from html.parser import HTMLParser

from dataclasses import dataclass
import imaplib
import re
import email



IMAP_HOST="imap.gmx.net"
IMAP_PORT="993"
IMAP_USER="ndw-ergo@gmx.at"
IMAP_PASSWORD="U33n!MSt62wKCnNt#*Vm"
AUTO_BETRAG_GROUP=1
AUTO_BETRAG_REGEX="^.*Sie haben soeben (.*) EUR auf Ihr Konto 0115 erhalten\\.\\s*$"
AUTO_BETREFF=None
AUTO_SENDER=None
AUTO_KONTO_GROUP=4
AUTO_KONTO_REGEX="^.*Buchungstext:\\s*((Barschulden)|(BS))(.*)\\.\\s*$"

# %% 

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


def _parse_betrag_cents(raw: str) -> int:
    """Betrag-String zu Cent konvertieren.

    Unterstützt deutsches Format (1.234,56) und englisches (1,234.56 / 1234.56).
    """
    raw = raw.strip()
    # Deutsches Format: endet auf ,XX
    if re.search(r",\d{2}$", raw):
        raw = raw.replace(".", "").replace(",", ".")
    else:
        raw = raw.replace(",", "")
    return round(float(raw) * 100)


# ---------------------------------------------------------------------------
# Cronjob
# ---------------------------------------------------------------------------
def _process_mailbox():
    mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    try:
        mail.login(IMAP_USER, IMAP_PASSWORD)
        mail.select("INBOX")

        # IMAP-Suchkriterien aufbauen (AND-Semantik)
        parts = ["UNSEEN"]
        if AUTO_SENDER:
            parts.append(f'FROM "{AUTO_SENDER}"')
        if AUTO_BETREFF:
            parts.append(f'SUBJECT "{AUTO_BETREFF}"')
        criteria = "(" + " ".join(parts) + ")"

        result, data = mail.search(None, criteria)
        if result != "OK" or not data[0]:
            return

        konto_re = re.compile(AUTO_KONTO_REGEX, re.IGNORECASE | re.MULTILINE)
        betrag_re = re.compile(AUTO_BETRAG_REGEX, re.IGNORECASE | re.MULTILINE)

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
        print("Auto-Aufbuchung: Fetch fehlgeschlagen für ID %s", msg_id)
        return

    msg = email.message_from_bytes(msg_data[0][1])
    subject = _decode_header(msg.get("Subject", ""))
    from_addr = _decode_header(msg.get("From", ""))
    body = _get_body(msg)
    search_text = f"{subject}\n{from_addr}\n{body}"

    konto_m = konto_re.search(search_text)
    betrag_m = betrag_re.search(search_text)

    if not konto_m or not betrag_m:
        print(konto_m.group(AUTO_KONTO_GROUP), betrag_m)
        print(
            "Auto-Aufbuchung: Regex kein Treffer — from=%s, subject=%s",
            from_addr, subject,
        )
        return

    try:
        konto_wert = konto_m.group(AUTO_KONTO_GROUP).strip()
    except IndexError:
        print(
            "Auto-Aufbuchung: AUTO_KONTO_GROUP=%d existiert nicht im Match — from=%s, subject=%s",
            AUTO_KONTO_GROUP, from_addr, subject,
        )
        return

    try:
        betrag_cents = _parse_betrag_cents(betrag_m.group(AUTO_BETRAG_GROUP))
    except IndexError:
        print(
            "Auto-Aufbuchung: AUTO_BETRAG_GROUP=%d existiert nicht im Match — from=%s, subject=%s",
            AUTO_BETRAG_GROUP, from_addr, subject,
        )
        return
    except ValueError as exc:
        print(
            "Auto-Aufbuchung: Betrag '%s' nicht parsierbar (%s) — from=%s, subject=%s",
            betrag_m.group(AUTO_BETRAG_GROUP), exc, from_addr, subject,
        )
        return

    if betrag_cents <= 0:
        print(
            "Auto-Aufbuchung: Betrag %d Cent ≤ 0, übersprungen — from=%s, subject=%s",
            betrag_cents, from_addr, subject,
        )
        return


    # Zuerst als gelesen markieren, damit die Mail nicht nochmals verarbeitet wird
    mail.store(msg_id, "+FLAGS", "\\Seen")

    try:
        print("SUCCESS")
        print(konto_wert, betrag_cents)
    except Exception as e:
        print(e)
        

if __name__ == "__main__":
    _process_mailbox()
