"""Tests for blueprints/admin/artikel.py — create, update, toggle."""
from models import Artikel


class TestArtikelCreate:
    def test_create_returns_id(self, auth_client):
        resp = auth_client.put(
            "/admin/artikel/create",
            json={
                "name": "Neues Bier",
                "preis": "2.50",
                "order": 1,
                "aktiv": True,
                "typ": "volumen",
                "volumen_liter": 0.5,
                "reinalkohol_liter": 0.02,
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "artikel_id" in data

    def test_create_persists_to_db(self, auth_client, db):
        auth_client.put(
            "/admin/artikel/create",
            json={
                "name": "Stored Wasser",
                "preis": "1.00",
                "order": 2,
                "aktiv": True,
                "typ": "volumen",
                "volumen_liter": 0.33,
                "reinalkohol_liter": 0.0,
            },
        )
        a = Artikel.query.filter_by(name="Stored Wasser").first()
        assert a is not None
        assert a.preis == 100
        assert a.aktiv is True

    def test_create_non_volumen_type(self, auth_client, db):
        auth_client.put(
            "/admin/artikel/create",
            json={
                "name": "Snack",
                "preis": "0.50",
                "order": 3,
                "aktiv": True,
                "typ": "sonstiges",
            },
        )
        a = Artikel.query.filter_by(name="Snack").first()
        assert a is not None
        assert a.typ == "sonstiges"
        # SQLAlchemy applies column defaults when None is passed in the ORM constructor,
        # so volumen_liter/reinalkohol_liter keep their defaults for non-volumen articles.

    def test_create_requires_login(self, client):
        resp = client.put("/admin/artikel/create", json={"name": "X"})
        assert resp.status_code in (302, 401)


class TestArtikelUpdate:
    def test_update_changes_name_and_price(self, auth_client, db, artikel):
        resp = auth_client.post(
            f"/admin/artikel/{artikel.id}",
            json={
                "name": "Updated Bier",
                "preis": "3.00",
                "reihenfolge": 5,
                "aktiv": False,
                "typ": "volumen",
                "volumen_liter": 0.5,
                "reinalkohol_liter": 0.02,
            },
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

        db.session.refresh(artikel)
        assert artikel.name == "Updated Bier"
        assert artikel.preis == 300
        assert artikel.aktiv is False
        assert artikel.reihenfolge == 5

    def test_update_nonexistent_returns_404(self, auth_client):
        resp = auth_client.post(
            "/admin/artikel/99999",
            json={"name": "X", "preis": "1.00", "reihenfolge": 1,
                  "aktiv": True, "typ": "volumen"},
        )
        assert resp.status_code == 404

    def test_get_artikel_returns_details(self, auth_client, artikel):
        resp = auth_client.get(f"/admin/artikel/{artikel.id}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["artikel"]["name"] == artikel.name
        assert data["artikel"]["preis"] == artikel.preis


class TestArtikelToggle:
    def test_toggle_deactivates(self, auth_client, db, artikel):
        assert artikel.aktiv is True
        resp = auth_client.post(f"/admin/artikel/toggle/{artikel.id}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["aktiv"] is False

    def test_toggle_activates(self, auth_client, db, artikel):
        artikel.aktiv = False
        db.session.commit()

        resp = auth_client.post(f"/admin/artikel/toggle/{artikel.id}")
        data = resp.get_json()
        assert data["aktiv"] is True
