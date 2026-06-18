"""Tests for blueprints/admin/abrechnung.py — create, update, refresh, delete."""
from datetime import datetime, timedelta

from models import Abrechnung, Buchung, Mitglied, Artikel


def _buchung(db, mitglied, artikel, ts=None):
    b = Buchung(
        mitglied_id=mitglied.id,
        artikel_id=artikel.id,
        menge=1,
        preis_pro_einheit=200,
        gesamtpreis=-200,
        storno=False,
        zeitstempel=ts or datetime.now(),
    )
    db.session.add(b)
    db.session.commit()
    return b


class TestAbrechnungCreate:
    def test_create_all_pending_buchungen(self, auth_client, db, mitglied, artikel):
        b1 = _buchung(db, mitglied, artikel)
        b2 = _buchung(db, mitglied, artikel)

        resp = auth_client.post(
            "/admin/abrechnung/create",
            json={"name": "Abrechnung Q1", "modus": "alle"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

        db.session.refresh(b1)
        db.session.refresh(b2)
        a = Abrechnung.query.filter_by(name="Abrechnung Q1").first()
        assert a is not None
        assert b1.abrechnungs_id == a.id
        assert b2.abrechnungs_id == a.id

    def test_create_zeitraum_filters_buchungen(self, auth_client, db, mitglied, artikel):
        old = _buchung(db, mitglied, artikel, ts=datetime.now() - timedelta(days=10))
        recent = _buchung(db, mitglied, artikel, ts=datetime.now())

        start = (datetime.now() - timedelta(days=1)).isoformat()
        end = (datetime.now() + timedelta(hours=1)).isoformat()

        resp = auth_client.post(
            "/admin/abrechnung/create",
            json={"name": "Zeitraum Q1", "modus": "zeitraum", "start": start, "end": end},
        )
        assert resp.status_code == 200

        db.session.refresh(old)
        db.session.refresh(recent)
        a = Abrechnung.query.filter_by(name="Zeitraum Q1").first()
        assert recent.abrechnungs_id == a.id
        assert old.abrechnungs_id is None  # outside time range

    def test_create_does_not_include_already_assigned(self, auth_client, db, mitglied, artikel):
        """Buchungen already assigned to an Abrechnung stay put."""
        existing = Abrechnung(name="Old")
        db.session.add(existing)
        db.session.commit()

        b = _buchung(db, mitglied, artikel)
        b.abrechnungs_id = existing.id
        db.session.commit()

        auth_client.post(
            "/admin/abrechnung/create",
            json={"name": "New One", "modus": "alle"},
        )

        db.session.refresh(b)
        assert b.abrechnungs_id == existing.id  # unchanged

    def test_create_requires_login(self, client):
        resp = client.post("/admin/abrechnung/create", json={"name": "X", "modus": "alle"})
        assert resp.status_code in (302, 401)


class TestAbrechnungUpdate:
    def test_update_reassigns_buchungen(self, auth_client, db, mitglied, artikel):
        a = Abrechnung(name="Test Abrechnung")
        db.session.add(a)

        b_old = _buchung(db, mitglied, artikel, ts=datetime.now() - timedelta(days=5))
        b_old.abrechnungs_id = a.id

        b_new = _buchung(db, mitglied, artikel, ts=datetime.now())
        db.session.commit()

        start = (datetime.now() - timedelta(hours=1)).isoformat()
        end = (datetime.now() + timedelta(hours=1)).isoformat()

        resp = auth_client.post(
            f"/admin/abrechnung/{a.id}/update",
            json={"start": start, "ende": end},
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

        db.session.refresh(b_old)
        db.session.refresh(b_new)
        assert b_old.abrechnungs_id is None  # outside new range → unassigned
        assert b_new.abrechnungs_id == a.id


class TestAbrechnungRefresh:
    def test_refresh_updates_zeitstempel(self, auth_client, db):
        old_ts = datetime.now() - timedelta(hours=2)
        a = Abrechnung(name="Refresh Test", zeitstempel=old_ts)
        db.session.add(a)
        db.session.commit()

        resp = auth_client.post(f"/admin/abrechnung/{a.id}/refresh")
        assert resp.status_code == 200

        db.session.refresh(a)
        assert a.zeitstempel > old_ts


class TestAbrechnungDelete:
    def test_delete_removes_abrechnung_and_unassigns_buchungen(
        self, auth_client, db, mitglied, artikel
    ):
        a = Abrechnung(name="To Delete")
        db.session.add(a)
        db.session.commit()

        b = _buchung(db, mitglied, artikel)
        b.abrechnungs_id = a.id
        db.session.commit()
        abrechnung_id = a.id

        resp = auth_client.post(f"/admin/abrechnung/{abrechnung_id}/delete")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

        assert Abrechnung.query.get(abrechnung_id) is None
        db.session.refresh(b)
        assert b.abrechnungs_id is None

    def test_delete_nonexistent_returns_404(self, auth_client):
        resp = auth_client.post("/admin/abrechnung/99999/delete")
        assert resp.status_code == 404
