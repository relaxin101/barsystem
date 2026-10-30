"""Tests for utils/auto_aufbuchung.py — pure helpers + mocked IMAP."""
import email
import email.message
import email.mime.multipart
import email.mime.text
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from models import Mitglied
from utils.auto_aufbuchung import (
    _absender_echt,
    _decode_header,
    _get_body,
    _handle_message,
    _name_passt,
    _strip_html,
)
from utils.einstellungen import speichern


# ---------------------------------------------------------------------------
# _strip_html
# ---------------------------------------------------------------------------

def test_strip_html_plain():
    # The HTMLParser fires handle_data once per text node and joins with spaces;
    # "Hello " and "World" are separate nodes → single trailing/leading space each.
    result = _strip_html("<p>Hello <b>World</b></p>")
    assert "Hello" in result and "World" in result


def test_strip_html_empty():
    assert _strip_html("") == ""


def test_strip_html_no_tags():
    result = _strip_html("Just text")
    assert "Just text" in result


def test_strip_html_nested():
    result = _strip_html("<html><body><p>Amount: <strong>10,00</strong></p></body></html>")
    assert "10,00" in result


# ---------------------------------------------------------------------------
# _decode_header
# ---------------------------------------------------------------------------

def test_decode_header_plain_string():
    assert _decode_header("Hello") == "Hello"


def test_decode_header_empty():
    assert _decode_header("") == ""


def test_decode_header_none():
    assert _decode_header(None) == ""


def test_decode_header_encoded():
    # RFC 2047 encoded word
    encoded = "=?utf-8?b?SGVsbG8gV29ybGQ=?="  # "Hello World" in base64
    result = _decode_header(encoded)
    assert "Hello World" in result


# ---------------------------------------------------------------------------
# _get_body
# ---------------------------------------------------------------------------

def _make_simple_message(content, content_type="text/plain"):
    msg = email.message.Message()
    msg["Content-Type"] = content_type
    msg.set_payload(content.encode("utf-8"), charset="utf-8")
    return msg


def test_get_body_plain_text():
    msg = _make_simple_message("Transfer: 25,00 EUR")
    body = _get_body(msg)
    assert "25,00" in body


def test_get_body_html_fallback():
    msg = _make_simple_message("<p>Amount: 50,00 EUR</p>", content_type="text/html")
    body = _get_body(msg)
    assert "50,00" in body


def test_get_body_multipart_prefers_plain():
    # Use the already-imported top-level names to avoid shadowing 'email' locally.
    outer = email.mime.multipart.MIMEMultipart("alternative")
    outer.attach(email.mime.text.MIMEText("Plain: 30,00 EUR", "plain", "utf-8"))
    outer.attach(email.mime.text.MIMEText("<p>HTML: 30,00 EUR</p>", "html", "utf-8"))

    body = _get_body(outer)
    assert "Plain:" in body


# ---------------------------------------------------------------------------
# _handle_message — mocked IMAP + DB
# ---------------------------------------------------------------------------

ECHT = "mx.provider.at; spf=pass smtp.mailfrom=example.com; dkim=pass header.d=example.com"


def _make_raw_email(subject: str, from_addr: str, body: str, auth: str = ECHT) -> bytes:
    import email.mime.text
    msg = email.mime.text.MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_addr
    if auth:
        msg["Authentication-Results"] = auth
    return msg.as_bytes()


@pytest.fixture()
def bank_sender(app):
    speichern({"AUTO_SENDER": "bank@example.com"}, "test")


@pytest.mark.parametrize("auth,echt", [
    (ECHT, True),
    ("mx; dkim=pass header.i=@example.com header.s=sel", True),  # so schreibt es Gmail
    ("mx; dkim=pass header.d=mail.example.com", True),
    ("mx; dkim=fail header.d=example.com; dmarc=pass header.from=example.com", True),
    ("mx; dmarc=pass action=none header.from=example.com", True),
    ("", False),
    ("mx; dkim=fail header.d=example.com", False),
    ("mx; dkim=none; dmarc=fail header.from=example.com", False),
    ("mx; dkim=pass header.d=evil.com", False),
    ("mx; dkim=pass header.d=example.com.evil.com", False),
    ("mx; dkim=pass header.d=notexample.com", False),
    ("mx; dkim=fail header.d=evil.com header.from=example.com", False),
])
def test_absender_echt(app, bank_sender, auth, echt):
    msg = email.message_from_bytes(_make_raw_email("s", "bank@example.com", "b", auth))
    assert _absender_echt(msg) is echt


def test_absender_echt_trusts_only_the_top_header(app, bank_sender):
    """A forged header sits below the one our own mail server puts on top."""
    msg = email.message.Message()
    msg["Authentication-Results"] = "mx; dkim=none; dmarc=fail header.from=example.com"
    msg["Authentication-Results"] = "evil; dkim=pass header.d=example.com"
    assert _absender_echt(msg) is False


def test_absender_echt_without_sender_setting(app):
    msg = email.message_from_bytes(_make_raw_email("s", "bank@example.com", "b"))
    assert _absender_echt(msg) is False


@pytest.mark.parametrize("konto,passt", [
    ("Max Mustermann", True),
    ("max mustermann", True),
    ("Stonks", True),
    ("Maxi", True),
    ("Max", False),
    ("", False),
    ("%", False),
])
def test_name_passt(konto, passt):
    m = Mitglied(name="Max Mustermann", nickname="Stonks, Maxi ,")
    assert _name_passt(m, konto) is passt


def test_name_passt_empty_never_matches_without_nickname():
    assert _name_passt(Mitglied(name="Max", nickname=None), "") is False


class TestHandleMessage:
    @pytest.fixture(autouse=True)
    def _sender(self, bank_sender):
        pass

    def _make_mail_mock(self, subject="Überweisung", from_addr="bank@example.com",
                        body="Absender: Max Mustermann Betrag: 10,00", auth=ECHT):
        raw = _make_raw_email(subject, from_addr, body, auth)
        mail = MagicMock()
        mail.fetch.return_value = ("OK", [(None, raw)])
        return mail

    @pytest.mark.parametrize("auth", ["", "mx; dkim=fail header.d=example.com"])
    def test_forged_sender_is_not_booked(self, app, db, auth):
        import re
        from models import Buchung

        with app.app_context():
            m = Mitglied(name="Max Mustermann", aktiv=True, guthaben=0)
            db.session.add(m)
            db.session.commit()
            mail = self._make_mail_mock(auth=auth)

            with patch("utils.auto_aufbuchung.suche_mitglied", return_value=[m]):
                _handle_message(mail, b"1", re.compile(r"Absender: (.+?) Betrag"), re.compile(r"Betrag: (\d+,\d+)"))

            db.session.refresh(m)
            assert m.guthaben == 0
            assert Buchung.query.count() == 0

    def test_partial_name_is_not_booked(self, app, db):
        """"Max" must not land on Maximilian just because he is the only substring hit."""
        import re

        with app.app_context():
            m = Mitglied(name="Maximilian", aktiv=True, guthaben=0)
            db.session.add(m)
            db.session.commit()
            mail = self._make_mail_mock(body="Absender: Max Betrag: 10,00")

            with patch("utils.auto_aufbuchung.suche_mitglied", return_value=[m]):
                _handle_message(mail, b"1", re.compile(r"Absender: (.+?) Betrag"), re.compile(r"Betrag: (\d+,\d+)"))

            db.session.refresh(m)
            assert m.guthaben == 0

    def test_exact_match_beats_longer_names(self, app, db):
        import re

        with app.app_context():
            max_ = Mitglied(name="Max", aktiv=True, guthaben=0)
            lang = Mitglied(name="Maximilian", aktiv=True, guthaben=0)
            db.session.add_all([max_, lang])
            db.session.commit()
            mail = self._make_mail_mock(body="Absender: Max Betrag: 10,00")

            with patch("utils.auto_aufbuchung.suche_mitglied", return_value=[max_, lang]):
                _handle_message(mail, b"1", re.compile(r"Absender: (.+?) Betrag"), re.compile(r"Betrag: (\d+,\d+)"))

            db.session.refresh(max_)
            db.session.refresh(lang)
            assert (max_.guthaben, lang.guthaben) == (1000, 0)
            mail.store.assert_called_once_with(b"1", "+FLAGS", "\\Seen")

    def test_no_regex_match_marks_seen_and_returns(self, app, db):
        """When regex doesn't match, the mail is NOT marked seen (no member found)."""
        import re
        mail = self._make_mail_mock(body="nothing relevant")
        konto_re = re.compile(r"Absender: (\S+)")
        betrag_re = re.compile(r"Betrag: (\d+,\d+)")

        with app.app_context():
            _handle_message(mail, b"1", konto_re, betrag_re)

        # fetch called, but store (mark seen) NOT called since regex didn't match
        mail.fetch.assert_called_once()
        mail.store.assert_not_called()

    def test_zero_or_negative_amount_skipped(self, app, db):
        import re
        mail = self._make_mail_mock(body="Absender: Max Mustermann Betrag: 0,00")
        konto_re = re.compile(r"Absender: (.+?) Betrag")
        betrag_re = re.compile(r"Betrag: (\d+,\d+)")

        with app.app_context():
            _handle_message(mail, b"1", konto_re, betrag_re)

        mail.store.assert_not_called()

    def test_no_matching_member_still_marks_seen(self, app, db):
        """Mail is marked seen before member lookup, even if no member found."""
        import re
        mail = self._make_mail_mock(body="Absender: UnknownPerson Betrag: 25,00")
        konto_re = re.compile(r"Absender: (.+?) Betrag")
        betrag_re = re.compile(r"Betrag: (\d+,\d+)")

        with app.app_context():
            # suche_mitglied uses PostgreSQL SQL — mock it to return no results
            with patch("utils.auto_aufbuchung.suche_mitglied", return_value=[]):
                _handle_message(mail, b"1", konto_re, betrag_re)

        mail.store.assert_called_once_with(b"1", "+FLAGS", "\\Seen")

    def test_matching_member_creates_buchung(self, app, db):
        import re
        from models import Mitglied, Buchung

        with app.app_context():
            m = Mitglied(name="Max Mustermann", aktiv=True, guthaben=0)
            db.session.add(m)
            db.session.commit()

            mail = self._make_mail_mock(body="Absender: Max Mustermann Betrag: 10,00")
            konto_re = re.compile(r"Absender: (.+?) Betrag")
            betrag_re = re.compile(r"Betrag: (\d+,\d+)")

            # suche_mitglied uses PostgreSQL-specific SQL — mock it
            with patch("utils.auto_aufbuchung.suche_mitglied", return_value=[m]):
                _handle_message(mail, b"1", konto_re, betrag_re)

            db.session.refresh(m)
            assert m.guthaben == 1000  # 10,00 € = 1000 cents
            assert Buchung.query.filter_by(mitglied_id=m.id).count() == 1

    def test_ambiguous_member_match_skips_booking(self, app, db):
        import re
        from models import Mitglied, Buchung

        with app.app_context():
            m1 = Mitglied(name="Max", aktiv=True, guthaben=0)
            m2 = Mitglied(name="Max", aktiv=True, guthaben=0)
            db.session.add_all([m1, m2])
            db.session.commit()

            mail = self._make_mail_mock(body="Absender: Max Betrag: 10,00")
            konto_re = re.compile(r"Absender: (.+?) Betrag")
            betrag_re = re.compile(r"Betrag: (\d+,\d+)")

            with patch("utils.auto_aufbuchung.suche_mitglied", return_value=[m1, m2]):
                _handle_message(mail, b"1", konto_re, betrag_re)

            assert Buchung.query.count() == 0
            mail.store.assert_called_once()  # still marks as seen
