"""Tests for utils/brevo.py — external HTTP calls are mocked."""
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from models import Aussendung, Buchung, Mitglied, Artikel
from utils.brevo import (
    _eur,
    _get_recipients,
    _get_since,
    _get_summen,
    _get_verbrauch,
    _resolve_template,
    aussendungen,
    bulk_mail,
    get_member_count,
    single_mail,
)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def test_eur_formats_correctly():
    assert _eur(0) == "€ 0,00"
    assert _eur(100) == "€ 1,00"
    assert _eur(1234) == "€ 12,34"
    assert _eur(-50) == "€ -0,50"


def test_resolve_template_uses_override():
    assert _resolve_template(99) == 99


def test_resolve_template_falls_back_to_global():
    import config
    assert _resolve_template(None) == config.BREVO_TEMPLATE


def test_get_since_returns_none_for_alle_mitglieder():
    a = Aussendung(
        subject="X", message="Y", frequenz="7",
        member_days=7, alle_mitglieder=True,
        aktiv=True,
    )
    assert _get_since(a) is None


def test_get_since_returns_none_if_no_member_days():
    a = Aussendung(
        subject="X", message="Y", frequenz="7",
        member_days=0, alle_mitglieder=False,
        aktiv=True,
    )
    assert _get_since(a) is None


def test_get_since_computes_timedelta(app):
    a = Aussendung(
        subject="X", message="Y", frequenz="7",
        member_days=7, alle_mitglieder=False,
        aktiv=True,
    )
    since = _get_since(a)
    assert since is not None
    assert abs((datetime.now() - since).days - 7) <= 1


# ---------------------------------------------------------------------------
# DB-dependent helpers
# ---------------------------------------------------------------------------

def test_get_recipients_alle_mitglieder(db):
    m1 = Mitglied(name="Anna", aktiv=True, guthaben=0)
    m2 = Mitglied(name="Bob", aktiv=False, guthaben=0)
    db.session.add_all([m1, m2])
    db.session.commit()

    a = Aussendung(
        subject="X", message="Y", frequenz="7",
        member_days=0, alle_mitglieder=True, aktiv=True,
    )
    result = _get_recipients(a)
    names = [m.name for m in result]
    assert "Anna" in names
    assert "Bob" not in names  # inactive


def test_get_recipients_blacklist_only(db):
    m_black = Mitglied(name="Blacklisted", aktiv=True, guthaben=-100, blacklist=True)
    m_good = Mitglied(name="Good", aktiv=True, guthaben=500, blacklist=False)
    db.session.add_all([m_black, m_good])
    db.session.commit()

    # member_days=0, alle_mitglieder=False → blacklist recipients
    a = Aussendung(
        subject="X", message="Y", frequenz="7",
        member_days=0, alle_mitglieder=False, aktiv=True,
    )
    result = _get_recipients(a)
    names = [m.name for m in result]
    assert "Blacklisted" in names
    assert "Good" not in names


def test_get_member_count_alle(db):
    db.session.add_all([
        Mitglied(name="A", aktiv=True, guthaben=0),
        Mitglied(name="B", aktiv=True, guthaben=0),
        Mitglied(name="C", aktiv=False, guthaben=0),
    ])
    db.session.commit()

    a = Aussendung(
        subject="X", message="Y", frequenz="7",
        member_days=0, alle_mitglieder=True, aktiv=True,
    )
    assert get_member_count(a) == 2  # only active


def test_get_verbrauch_empty(db, mitglied):
    result = _get_verbrauch(mitglied.id, datetime.now() - timedelta(days=30))
    assert result == ""


def test_get_verbrauch_with_buchung(db, mitglied, artikel):
    b = Buchung(
        mitglied_id=mitglied.id,
        artikel_id=artikel.id,
        menge=2,
        preis_pro_einheit=artikel.preis,
        gesamtpreis=-(artikel.preis * 2),
        storno=False,
        zeitstempel=datetime.now(),
    )
    db.session.add(b)
    db.session.commit()

    result = _get_verbrauch(mitglied.id, datetime.now() - timedelta(hours=1))
    assert artikel.name in result
    assert "<table" in result


def test_get_summen_no_buchungen(db, mitglied):
    gutschrift, abbuchung = _get_summen(mitglied.id, datetime.now() - timedelta(days=1))
    assert gutschrift == "€ 0,00"
    assert abbuchung == "€ 0,00"


def test_get_summen_with_buchungen(db, mitglied, artikel):
    b1 = Buchung(
        mitglied_id=mitglied.id, artikel_id=None,
        menge=1, preis_pro_einheit=500, gesamtpreis=500,
        storno=False, zeitstempel=datetime.now(),
        beschreibung="Aufladung",
    )
    b2 = Buchung(
        mitglied_id=mitglied.id, artikel_id=artikel.id,
        menge=1, preis_pro_einheit=200, gesamtpreis=-200,
        storno=False, zeitstempel=datetime.now(),
    )
    db.session.add_all([b1, b2])
    db.session.commit()

    gutschrift, abbuchung = _get_summen(mitglied.id, datetime.now() - timedelta(hours=1))
    assert gutschrift == "€ 5,00"
    assert abbuchung == "€ 2,00"


# ---------------------------------------------------------------------------
# single_mail — mock HTTP
# ---------------------------------------------------------------------------

def test_single_mail_calls_brevo_api():
    mock_response = MagicMock()
    mock_response.ok = True

    with patch("utils.brevo.requests.post", return_value=mock_response) as mock_post:
        result = single_mail(
            subject="Test",
            recipient_mail="user@example.com",
            recipient_name="User",
            message="Hello",
            amount="€ 10,00",
        )

    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["json"]["to"][0]["email"] == "user@example.com"
    assert result.ok is True


def test_single_mail_logs_on_failure():
    mock_response = MagicMock()
    mock_response.ok = False
    mock_response.status_code = 401
    mock_response.content = b"Unauthorized"

    with patch("utils.brevo.requests.post", return_value=mock_response):
        result = single_mail("Sub", "x@y.com", "X", "msg", "€ 0,00")

    assert result.ok is False


# ---------------------------------------------------------------------------
# bulk_mail — mock HTTP + DB
# ---------------------------------------------------------------------------

def test_bulk_mail_skips_members_without_email(db):
    m = Mitglied(name="No Email", guthaben=0, aktiv=True, email=None)
    db.session.add(m)
    db.session.commit()

    with patch("utils.brevo.requests.post") as mock_post:
        sent, failed = bulk_mail([m], "Sub", "msg")

    mock_post.assert_not_called()
    assert sent == 0
    assert failed == 0


def test_bulk_mail_sends_to_members_with_email(db):
    m = Mitglied(name="With Email", guthaben=500, aktiv=True, email="a@b.com")
    db.session.add(m)
    db.session.commit()

    mock_resp = MagicMock()
    mock_resp.ok = True

    with patch("utils.brevo.requests.post", return_value=mock_resp):
        sent, failed = bulk_mail([m], "Sub", "msg")

    assert sent == 1
    assert failed == 0


# ---------------------------------------------------------------------------
# aussendungen — integration (mock HTTP)
# ---------------------------------------------------------------------------

def test_aussendungen_inactive_returns_error(db):
    a = Aussendung(
        subject="X", message="Y", frequenz="7",
        member_days=0, alle_mitglieder=True, aktiv=False,
    )
    db.session.add(a)
    db.session.commit()

    code, msg = aussendungen(a)
    assert code == 1
    assert "inaktiv" in msg


def test_aussendungen_active_updates_last_run(db):
    m = Mitglied(name="Member", guthaben=0, aktiv=True, email="m@example.com")
    a = Aussendung(
        subject="Newsletter", message="Hi", frequenz="7",
        member_days=0, alle_mitglieder=True, aktiv=True,
    )
    db.session.add_all([m, a])
    db.session.commit()

    mock_resp = MagicMock()
    mock_resp.ok = True
    with patch("utils.brevo.requests.post", return_value=mock_resp):
        code, msg = aussendungen(a)

    assert code == 0
    assert a.last_run is not None
