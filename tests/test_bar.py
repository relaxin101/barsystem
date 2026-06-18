"""Tests for blueprints/bar.py — booking flow and members API."""
from datetime import datetime
from unittest.mock import patch

from models import Buchung, Mitglied, Artikel


class TestBuchen:
    def test_single_booking_deducts_guthaben(self, client, db, mitglied, artikel):
        initial = mitglied.guthaben
        resp = client.post(
            "/bar/buchen",
            json={"mitglied_id": mitglied.id, "artikel_id": artikel.id, "menge": 1},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

        db.session.refresh(mitglied)
        assert mitglied.guthaben == initial - artikel.preis

    def test_booking_creates_buchung_record(self, client, db, mitglied, artikel):
        client.post(
            "/bar/buchen",
            json={"mitglied_id": mitglied.id, "artikel_id": artikel.id, "menge": 2},
        )
        b = Buchung.query.filter_by(mitglied_id=mitglied.id).first()
        assert b is not None
        assert b.menge == 2
        assert b.gesamtpreis == -(artikel.preis * 2)

    def test_batch_booking(self, client, db, mitglied, artikel):
        artikel2 = Artikel(name="Wasser", preis=100, reihenfolge=2, aktiv=True)
        db.session.add(artikel2)
        db.session.commit()

        initial = mitglied.guthaben
        resp = client.post(
            "/bar/buchen",
            json={
                "mitglied_id": mitglied.id,
                "artikel": [
                    {"artikel_id": artikel.id, "menge": 1},
                    {"artikel_id": artikel2.id, "menge": 2},
                ],
            },
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

        db.session.refresh(mitglied)
        assert mitglied.guthaben == initial - artikel.preis - (artikel2.preis * 2)
        assert Buchung.query.filter_by(mitglied_id=mitglied.id).count() == 2

    def test_booking_blacklisted_member_rejected(self, client, db, mitglied, artikel):
        mitglied.blacklist = True
        db.session.commit()

        resp = client.post(
            "/bar/buchen",
            json={"mitglied_id": mitglied.id, "artikel_id": artikel.id, "menge": 1},
        )
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_booking_nonexistent_member_returns_404(self, client, artikel):
        resp = client.post(
            "/bar/buchen",
            json={"mitglied_id": 99999, "artikel_id": artikel.id, "menge": 1},
        )
        assert resp.status_code == 404

    def test_booking_nonexistent_artikel_returns_404(self, client, mitglied):
        resp = client.post(
            "/bar/buchen",
            json={"mitglied_id": mitglied.id, "artikel_id": 99999, "menge": 1},
        )
        assert resp.status_code == 404

    def test_booking_missing_data_returns_400(self, client):
        resp = client.post("/bar/buchen", json={})
        assert resp.status_code == 400

    def test_booking_negative_menge_returns_400(self, client, mitglied, artikel):
        resp = client.post(
            "/bar/buchen",
            json={"mitglied_id": mitglied.id, "artikel_id": artikel.id, "menge": -1},
        )
        assert resp.status_code == 400

    def test_booking_triggers_blacklist_on_threshold_cross(self, client, db, mitglied, artikel):
        """Purchase crossing schwaerzungs_grenze sets blacklist."""
        mitglied.guthaben = 300  # 3 €
        mitglied.schwaerzungs_grenze = 200  # 2 € threshold
        db.session.commit()

        # artikel.preis = 200 → new guthaben = 100 < 200 → blacklisted
        resp = client.post(
            "/bar/buchen",
            json={"mitglied_id": mitglied.id, "artikel_id": artikel.id, "menge": 1},
        )
        assert resp.status_code == 200

        db.session.refresh(mitglied)
        assert mitglied.guthaben == 100
        assert mitglied.blacklist is True

    def test_zero_menge_items_skipped(self, client, db, mitglied, artikel):
        """Booking with menge=0 for all items returns 400."""
        resp = client.post(
            "/bar/buchen",
            json={
                "mitglied_id": mitglied.id,
                "artikel": [{"artikel_id": artikel.id, "menge": 0}],
            },
        )
        assert resp.status_code == 400


class TestMembersApi:
    def test_api_returns_all_members_without_search(self, client, db):
        m1 = Mitglied(name="Alice", guthaben=0, aktiv=True)
        m2 = Mitglied(name="Bob", guthaben=0, aktiv=True)
        db.session.add_all([m1, m2])
        db.session.commit()

        resp = client.get("/api/members")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        names = [m["name"] for m in data["members"]]
        assert "Alice" in names
        assert "Bob" in names

    def test_api_search_calls_suche_mitglied(self, client, db):
        m = Mitglied(name="Max Mustermann", guthaben=0, aktiv=True)
        db.session.add(m)
        db.session.commit()

        with patch("blueprints.bar.suche_mitglied", return_value=[m]) as mock_search:
            resp = client.get("/api/members?search=Max")

        mock_search.assert_called_once_with("Max", limit=None)
        assert resp.status_code == 200
        data = resp.get_json()
        assert any(x["name"] == "Max Mustermann" for x in data["members"])

    def test_api_respects_limit_param(self, client, db):
        for i in range(5):
            db.session.add(Mitglied(name=f"Member {i}", guthaben=0, aktiv=True))
        db.session.commit()

        resp = client.get("/api/members?limit=2")
        data = resp.get_json()
        assert len(data["members"]) <= 2

    def test_api_member_has_expected_fields(self, client, db, mitglied):
        resp = client.get("/api/members")
        data = resp.get_json()
        member = next(m for m in data["members"] if m["id"] == mitglied.id)
        assert "id" in member
        assert "name" in member
        assert "guthaben" in member
        assert "blacklist" in member
        assert "gepinnt" in member


class TestBarInterface:
    def test_bar_interface_loads(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_buchen_get_requires_mitglied_id(self, client):
        resp = client.get("/bar/buchen")
        assert resp.status_code in (302, 400)

    def test_buchen_get_with_mitglied(self, client, mitglied):
        resp = client.get(f"/bar/buchen?mitglied_id={mitglied.id}")
        assert resp.status_code == 200


class TestHotlist:
    def test_hotlist_returns_members(self, client, db):
        m = Mitglied(name="Hotlist Member", guthaben=500, aktiv=True, gepinnt=False)
        db.session.add(m)
        db.session.commit()

        resp = client.get("/api/members")
        data = resp.get_json()
        names = [x["name"] for x in data["members"]]
        assert "Hotlist Member" in names

    def test_pinned_members_included(self, client, db):
        pinned = Mitglied(name="Pinned One", guthaben=0, aktiv=True, gepinnt=True)
        db.session.add(pinned)
        db.session.commit()

        resp = client.get("/api/members")
        data = resp.get_json()
        names = [x["name"] for x in data["members"]]
        assert "Pinned One" in names

    def test_inactive_members_excluded_from_hotlist(self, client, db):
        inactive = Mitglied(name="Inactive Person", guthaben=0, aktiv=False)
        db.session.add(inactive)
        db.session.commit()

        resp = client.get("/api/members")
        data = resp.get_json()
        names = [x["name"] for x in data["members"]]
        assert "Inactive Person" not in names
