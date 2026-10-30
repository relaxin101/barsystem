"""Tests for sending Aussendungen: gunicorn kills requests after 30 s."""
from unittest.mock import MagicMock, patch

from models import Aussendung, Mitglied
from utils.brevo import aussendungen, single_mail
from utils.zeit import utcnow


def _aussendung(db, **kwargs):
    a = Aussendung(subject="S", message="M", frequenz="7", alle_mitglieder=True, aktiv=True, **kwargs)
    db.session.add(a)
    db.session.commit()
    return a


class SyncThread:
    """Runs the target on start(), so the test can see the result."""

    def __init__(self, target, args, daemon):
        self.target, self.args = target, args
        assert daemon

    def start(self):
        self.target(*self.args)


def test_brevo_call_has_a_timeout(app):
    with patch("utils.brevo.requests.post") as post:
        single_mail("s", "a@example.com", "A", "m", "0")
    assert post.call_args.kwargs["timeout"] == 10


def test_run_leaves_sending_to_the_scheduler(auth_client, db):
    a = _aussendung(db, last_run=utcnow())

    with patch("blueprints.admin.aussendungen.brevo_send") as send:
        data = auth_client.post(f"/admin/aussendungen/run/{a.id}").get_json()

    assert data["success"] is True
    send.assert_not_called()
    db.session.refresh(a)
    assert a.last_run is None


def test_scheduler_sends_after_run(app, auth_client, db):
    from blueprints.admin.aussendungen import cronjob

    a = _aussendung(db, last_run=utcnow())
    auth_client.post(f"/admin/aussendungen/run/{a.id}")

    with patch("blueprints.admin.aussendungen.brevo_send") as send:
        cronjob(app)

    send.assert_called_once()


def test_run_refuses_inactive(auth_client, db):
    a = _aussendung(db)
    a.aktiv = False
    db.session.commit()

    assert auth_client.post(f"/admin/aussendungen/run/{a.id}").get_json()["success"] is False


def test_last_run_is_saved_before_sending(app, db):
    """If the process dies mid-send, nobody gets the same mail twice."""
    a = _aussendung(db)
    gesehen = []

    def bulk(*args, **kwargs):
        db.session.expire_all()
        gesehen.append(db.session.get(Aussendung, a.id).last_run)
        return 0, 0

    with patch("utils.brevo.bulk_mail", side_effect=bulk):
        aussendungen(a)

    assert gesehen[0] is not None


def test_form_send_returns_before_mails_go_out(auth_client, db):
    db.session.add(Mitglied(name="A", email="a@example.com", aktiv=True, guthaben=0))
    db.session.commit()
    thread = MagicMock()

    with patch("blueprints.admin.aussendungen.Thread", return_value=thread), \
            patch("blueprints.admin.aussendungen.bulk_mail") as bulk:
        data = auth_client.post(
            "/admin/aussendungen/send",
            json={"subject": "S", "message": "M", "alle_mitglieder": True},
        ).get_json()

    assert data["success"] is True
    thread.start.assert_called_once()
    bulk.assert_not_called()


def test_background_send_reaches_members(auth_client, db):
    db.session.add(Mitglied(name="A", email="a@example.com", aktiv=True, guthaben=0))
    db.session.commit()

    with patch("blueprints.admin.aussendungen.Thread", SyncThread), \
            patch("blueprints.admin.aussendungen.bulk_mail", return_value=(1, 0)) as bulk:
        auth_client.post(
            "/admin/aussendungen/send",
            json={"subject": "S", "message": "M", "alle_mitglieder": True},
        )

    assert [m.name for m in bulk.call_args.args[0]] == ["A"]
