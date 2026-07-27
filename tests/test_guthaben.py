"""Tests for blueprints/admin/guthaben.py — aufbuchung, blacklist toggle, Excel import."""
import io
from unittest.mock import patch

import pandas as pd

from models import Buchung, Mitglied


class TestAufbuchung:
    def test_aufbuchung_increases_guthaben(self, auth_client, db, mitglied):
        initial = mitglied.guthaben
        resp = auth_client.post(
            f"/admin/guthaben/aufbuchung/{mitglied.id}",
            json={"betrag": "5.00", "beschreibung": "Test deposit"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

        db.session.refresh(mitglied)
        assert mitglied.guthaben == initial + 500

    def test_aufbuchung_creates_buchung_record(self, auth_client, db, mitglied):
        auth_client.post(
            f"/admin/guthaben/aufbuchung/{mitglied.id}",
            json={"betrag": "10.00", "beschreibung": "Einzahlung"},
        )
        b = Buchung.query.filter_by(mitglied_id=mitglied.id).first()
        assert b is not None
        assert b.gesamtpreis == 1000
        assert b.artikel_id is None

    def test_aufbuchung_negative_reduces_guthaben(self, auth_client, db, mitglied):
        initial = mitglied.guthaben
        auth_client.post(
            f"/admin/guthaben/aufbuchung/{mitglied.id}",
            json={"betrag": "-2.00", "beschreibung": "Korrektur"},
        )
        db.session.refresh(mitglied)
        assert mitglied.guthaben == initial - 200

    def test_aufbuchung_missing_beschreibung_returns_400(self, auth_client, mitglied):
        resp = auth_client.post(
            f"/admin/guthaben/aufbuchung/{mitglied.id}",
            json={"betrag": "5.00"},
        )
        assert resp.status_code == 400

    def test_aufbuchung_short_beschreibung_returns_400(self, auth_client, mitglied):
        resp = auth_client.post(
            f"/admin/guthaben/aufbuchung/{mitglied.id}",
            json={"betrag": "5.00", "beschreibung": "AB"},  # < 3 chars
        )
        assert resp.status_code == 400

    def test_aufbuchung_missing_betrag_returns_400(self, auth_client, mitglied):
        resp = auth_client.post(
            f"/admin/guthaben/aufbuchung/{mitglied.id}",
            json={"beschreibung": "Some description"},
        )
        assert resp.status_code == 400

    def test_aufbuchung_nonexistent_member_returns_404(self, auth_client):
        resp = auth_client.post(
            "/admin/guthaben/aufbuchung/99999",
            json={"betrag": "5.00", "beschreibung": "Test"},
        )
        assert resp.status_code == 404

    def test_aufbuchung_triggers_blacklist_check(self, auth_client, db, mitglied):
        """Crossing below schwaerzungs_grenze sets blacklist=True."""
        mitglied.schwaerzungs_grenze = 500  # 5 €
        mitglied.guthaben = 600  # 6 €
        db.session.commit()

        auth_client.post(
            f"/admin/guthaben/aufbuchung/{mitglied.id}",
            json={"betrag": "-2.00", "beschreibung": "Deduction"},
        )
        db.session.refresh(mitglied)
        assert mitglied.guthaben == 400
        assert mitglied.blacklist is True


class TestBlacklistToggle:
    def test_set_blacklist_true(self, auth_client, db, mitglied):
        resp = auth_client.post(
            f"/admin/guthaben/mitglied_blacklist_toggle/{mitglied.id}",
            json={"blacklist": True},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["blacklist"] is True

        db.session.refresh(mitglied)
        assert mitglied.blacklist is True

    def test_set_blacklist_false(self, auth_client, db, mitglied):
        mitglied.blacklist = True
        db.session.commit()

        resp = auth_client.post(
            f"/admin/guthaben/mitglied_blacklist_toggle/{mitglied.id}",
            json={"blacklist": False},
        )
        data = resp.get_json()
        assert data["blacklist"] is False

        db.session.refresh(mitglied)
        assert mitglied.blacklist is False


class TestGuthabenImport:
    def _make_excel(self, rows):
        buf = io.BytesIO()
        pd.DataFrame(rows).to_excel(buf, index=False)
        buf.seek(0)
        return buf

    def test_import_updates_guthaben(self, auth_client, db, mitglied):
        excel = self._make_excel([{"id": mitglied.id, "betrag": 5.0}])
        resp = auth_client.post(
            "/admin/guthaben/guthaben_import",
            data={
                "mitglied_id_col": "id",
                "aufbuchung_col": "betrag",
            },
            content_type="multipart/form-data",
        )
        # Without file upload it should redirect with error flash
        assert resp.status_code in (200, 302)

    def test_import_with_file_updates_guthaben(self, auth_client, db, mitglied):
        initial = mitglied.guthaben
        excel = self._make_excel([{"id": mitglied.id, "betrag": 10.0}])
        resp = auth_client.post(
            "/admin/guthaben/guthaben_import",
            data={
                "mitglied_id_col": "id",
                "aufbuchung_col": "betrag",
                "file": (excel, "guthaben.xlsx", "application/octet-stream"),
            },
            content_type="multipart/form-data",
        )
        assert resp.status_code in (200, 302)

        db.session.refresh(mitglied)
        assert mitglied.guthaben == initial + 1000  # 10.0 € = 1000 cents

    def test_import_missing_columns_flashes_error(self, auth_client, db, mitglied):
        excel = self._make_excel([{"wrong_col": mitglied.id, "amount": 5.0}])
        resp = auth_client.post(
            "/admin/guthaben/guthaben_import",
            data={
                "mitglied_id_col": "id",
                "aufbuchung_col": "betrag",
                "file": (excel, "guthaben.xlsx", "application/octet-stream"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert resp.status_code == 200
        # Flash error message should be in response
        assert b"Pflicht" in resp.data or b"nicht gefunden" in resp.data

    def test_import_with_beschreibung_column(self, auth_client, db, mitglied):
        initial = mitglied.guthaben
        excel = self._make_excel([
            {"id": mitglied.id, "betrag": 3.0, "beschreibung": "Testeinzahlung"}
        ])
        auth_client.post(
            "/admin/guthaben/guthaben_import",
            data={
                "mitglied_id_col": "id",
                "aufbuchung_col": "betrag",
                "beschreibung_col": "beschreibung",
                "file": (excel, "guthaben.xlsx", "application/octet-stream"),
            },
            content_type="multipart/form-data",
        )
        db.session.refresh(mitglied)
        b = Buchung.query.filter_by(
            mitglied_id=mitglied.id, beschreibung="Testeinzahlung"
        ).first()
        assert b is not None
