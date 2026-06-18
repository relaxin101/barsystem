"""Tests for blueprints/admin/mitglied.py — create, update, toggle, details."""
import json
import pytest
from models import Mitglied


class TestMitgliedCreate:
    def test_create_returns_mitglied_id(self, auth_client):
        resp = auth_client.put(
            "/admin/mitglied/create",
            json={
                "name": "New Member",
                "nickname": "NM",
                "email": "nm@example.com",
                "aktiv": True,
                "gepinnt": False,
                "schwaerzungs_grenze": None,
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "mitglied_id" in data

    def test_create_persists_to_db(self, auth_client, db):
        auth_client.put(
            "/admin/mitglied/create",
            json={
                "name": "Persisted Member",
                "nickname": None,
                "email": None,
                "aktiv": True,
                "gepinnt": False,
                "schwaerzungs_grenze": None,
            },
        )
        m = Mitglied.query.filter_by(name="Persisted Member").first()
        assert m is not None
        assert m.guthaben == 0
        assert m.blacklist is False

    def test_create_with_schwaerzungs_grenze(self, auth_client, db):
        auth_client.put(
            "/admin/mitglied/create",
            json={
                "name": "Thresh Member",
                "nickname": None,
                "email": None,
                "aktiv": True,
                "gepinnt": False,
                "schwaerzungs_grenze": 5.0,  # €5.00
            },
        )
        m = Mitglied.query.filter_by(name="Thresh Member").first()
        assert m.schwaerzungs_grenze == 500  # cents

    def test_create_requires_login(self, client):
        resp = client.put("/admin/mitglied/create", json={"name": "X"})
        assert resp.status_code in (302, 401)


class TestMitgliedUpdate:
    def test_update_changes_fields(self, auth_client, db, mitglied):
        resp = auth_client.post(
            f"/admin/mitglied/{mitglied.id}",
            json={
                "name": "Updated Name",
                "nickname": "UN",
                "email": "updated@example.com",
                "aktiv": False,
                "gepinnt": True,
                "schwaerzungs_grenze": None,
            },
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

        db.session.refresh(mitglied)
        assert mitglied.name == "Updated Name"
        assert mitglied.nickname == "UN"
        assert mitglied.aktiv is False
        assert mitglied.gepinnt is True

    def test_update_schwaerzungs_grenze(self, auth_client, db, mitglied):
        auth_client.post(
            f"/admin/mitglied/{mitglied.id}",
            json={
                "name": mitglied.name,
                "nickname": None,
                "email": None,
                "aktiv": True,
                "gepinnt": False,
                "schwaerzungs_grenze": 10.0,
            },
        )
        db.session.refresh(mitglied)
        assert mitglied.schwaerzungs_grenze == 1000

    def test_update_clears_grenze_with_empty_string(self, auth_client, db, mitglied):
        mitglied.schwaerzungs_grenze = 500
        db.session.commit()

        auth_client.post(
            f"/admin/mitglied/{mitglied.id}",
            json={
                "name": mitglied.name,
                "nickname": None,
                "email": None,
                "aktiv": True,
                "gepinnt": False,
                "schwaerzungs_grenze": "",
            },
        )
        db.session.refresh(mitglied)
        assert mitglied.schwaerzungs_grenze is None

    def test_update_nonexistent_returns_404(self, auth_client):
        resp = auth_client.post(
            "/admin/mitglied/99999",
            json={"name": "X", "nickname": None, "email": None,
                  "aktiv": True, "gepinnt": False, "schwaerzungs_grenze": None},
        )
        assert resp.status_code == 404


class TestMitgliedToggle:
    def test_toggle_deactivates_active(self, auth_client, db, mitglied):
        assert mitglied.aktiv is True
        resp = auth_client.post(f"/admin/mitglied/toggle/{mitglied.id}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["aktiv"] is False

    def test_toggle_activates_inactive(self, auth_client, db, mitglied):
        mitglied.aktiv = False
        db.session.commit()

        resp = auth_client.post(f"/admin/mitglied/toggle/{mitglied.id}")
        data = resp.get_json()
        assert data["aktiv"] is True


class TestMitgliedDetails:
    def test_details_returns_member_json(self, auth_client, mitglied):
        resp = auth_client.get(f"/admin/mitglied/{mitglied.id}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["mitglied"]["name"] == mitglied.name
        assert data["mitglied"]["guthaben"] == mitglied.guthaben

    def test_details_nonexistent_returns_404(self, auth_client):
        resp = auth_client.get("/admin/mitglied/99999")
        assert resp.status_code == 404
