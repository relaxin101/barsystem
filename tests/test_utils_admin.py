"""Tests for utils/admin.py"""
import io
from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from models import Mitglied, Artikel
from utils.admin import (
    calc_blacklist,
    export_df_to_excel,
    import_excel_to_db,
    parse_betrag_cents,
    parse_daterange,
)


# ---------------------------------------------------------------------------
# parse_betrag_cents — pure function, no fixtures needed
# ---------------------------------------------------------------------------

class TestParseBetragCents:
    def test_german_with_thousands(self):
        assert parse_betrag_cents("1.234,56") == 123456

    def test_german_simple(self):
        assert parse_betrag_cents("5,00") == 500

    def test_english_decimal(self):
        assert parse_betrag_cents("1234.56") == 123456

    def test_english_with_thousands(self):
        assert parse_betrag_cents("1,234.56") == 123456

    def test_integer_string(self):
        assert parse_betrag_cents("10") == 1000

    def test_whitespace_stripped(self):
        assert parse_betrag_cents("  3,50  ") == 350

    def test_zero(self):
        assert parse_betrag_cents("0,00") == 0


# ---------------------------------------------------------------------------
# calc_blacklist — pure logic
# ---------------------------------------------------------------------------

class TestCalcBlacklist:
    def test_no_grenze_never_blacklisted(self):
        m = Mitglied(name="T", guthaben=100, schwaerzungs_grenze=None, blacklist=False)
        assert calc_blacklist(m, -200) is False

    def test_crosses_threshold_gets_blacklisted(self):
        # 1000 - 600 = 400 < 500 → blacklisted
        m = Mitglied(name="T", guthaben=1000, schwaerzungs_grenze=500, blacklist=False)
        assert calc_blacklist(m, -600) is True

    def test_stays_above_threshold_not_blacklisted(self):
        # 1000 - 300 = 700 >= 500 → not blacklisted
        m = Mitglied(name="T", guthaben=1000, schwaerzungs_grenze=500, blacklist=False)
        assert calc_blacklist(m, -300) is False

    def test_below_threshold_but_never_crossed(self):
        # guthaben=300 < threshold=500 → condition (guthaben >= threshold) false → not blacklisted
        m = Mitglied(name="T", guthaben=300, schwaerzungs_grenze=500, blacklist=False)
        assert calc_blacklist(m, -100) is False

    def test_already_blacklisted_balance_still_negative(self):
        m = Mitglied(name="T", guthaben=-100, schwaerzungs_grenze=500, blacklist=True)
        assert calc_blacklist(m, 50) is True  # -100 + 50 = -50 < 0

    def test_already_blacklisted_aufbuchung_clears(self):
        m = Mitglied(name="T", guthaben=-100, schwaerzungs_grenze=500, blacklist=True)
        assert calc_blacklist(m, 200) is False  # -100 + 200 = 100 >= 0

    def test_exact_threshold_not_blacklisted(self):
        # 1000 - 500 = 500 == threshold → not blacklisted (strictly less than)
        m = Mitglied(name="T", guthaben=1000, schwaerzungs_grenze=500, blacklist=False)
        assert calc_blacklist(m, -500) is False

    def test_one_cent_below_threshold(self):
        # 1000 - 501 = 499 < 500 → blacklisted
        m = Mitglied(name="T", guthaben=1000, schwaerzungs_grenze=500, blacklist=False)
        assert calc_blacklist(m, -501) is True

    def test_positive_aufbuchung_not_blacklisted(self):
        m = Mitglied(name="T", guthaben=0, schwaerzungs_grenze=500, blacklist=False)
        assert calc_blacklist(m, 1000) is False


# ---------------------------------------------------------------------------
# parse_daterange — needs request context
# ---------------------------------------------------------------------------

class TestParseDaterange:
    def test_no_params_returns_defaults(self, app):
        with app.test_request_context("/"):
            start, end = parse_daterange()
            assert start < end

    def test_date_only_format(self, app):
        with app.test_request_context("/?start=2024-01-01&end=2024-06-30"):
            start, end = parse_daterange()
            assert start.date() == date(2024, 1, 1)
            assert end.date() == date(2024, 6, 30)

    def test_datetime_format(self, app):
        with app.test_request_context("/?start=2024-03-15T08:00&end=2024-03-15T20:00"):
            start, end = parse_daterange()
            assert start.hour == 8
            assert end.hour == 20

    def test_invalid_param_falls_back_to_default(self, app):
        with app.test_request_context("/?start=not-a-date"):
            start, end = parse_daterange()
            assert start < end  # fallback: no crash


# ---------------------------------------------------------------------------
# import_excel_to_db — needs DB; mock the PostgreSQL setval call
# ---------------------------------------------------------------------------

class TestImportExcelToDb:
    def _make_excel(self, rows):
        buf = io.BytesIO()
        pd.DataFrame(rows).to_excel(buf, index=False)
        buf.seek(0)
        return buf

    def test_creates_new_records(self, db):
        excel = self._make_excel([
            {"name": "Alice", "email": "alice@example.com"},
            {"name": "Bob", "email": "bob@example.com"},
        ])
        mapping = {"name": "name", "email": "email"}
        with patch("utils.admin.db.session.execute"):
            import_excel_to_db(excel, Mitglied, mapping)

        assert Mitglied.query.filter_by(name="Alice").count() == 1
        assert Mitglied.query.filter_by(name="Bob").count() == 1

    def test_updates_existing_record_by_unique_field(self, db):
        m = Mitglied(name="Original Name", email="old@example.com")
        db.session.add(m)
        db.session.commit()

        excel = self._make_excel([{"id": m.id, "name": "Updated Name", "email": "new@example.com"}])
        mapping = {"id": "id", "name": "name", "email": "email"}
        with patch("utils.admin.db.session.execute"):
            import_excel_to_db(excel, Mitglied, mapping, unique_field="id")

        db.session.refresh(m)
        assert m.name == "Updated Name"
        assert m.email == "new@example.com"

    def test_skips_empty_rows(self, db):
        excel = self._make_excel([{"name": None, "email": None}])
        mapping = {"name": "name", "email": "email"}
        with patch("utils.admin.db.session.execute"):
            import_excel_to_db(excel, Mitglied, mapping)
        assert Mitglied.query.count() == 0

    def test_price_columns_converted_to_cents(self, db):
        excel = self._make_excel([{"name": "Bier", "preis": "2,50"}])
        mapping = {"name": "name", "preis": "preis"}
        with patch("utils.admin.db.session.execute"):
            import_excel_to_db(excel, Artikel, mapping)

        a = Artikel.query.filter_by(name="Bier").first()
        assert a is not None
        assert a.preis == 250

    def test_aktiv_column_coerced_to_bool(self, db):
        excel = self._make_excel([{"name": "Member", "aktiv": 1}])
        mapping = {"name": "name", "aktiv": "aktiv"}
        with patch("utils.admin.db.session.execute"):
            import_excel_to_db(excel, Mitglied, mapping)

        m = Mitglied.query.filter_by(name="Member").first()
        assert m.aktiv is True


# ---------------------------------------------------------------------------
# export_df_to_excel — needs app context (send_file)
# ---------------------------------------------------------------------------

class TestExportDfToExcel:
    def test_returns_excel_response(self, client, admin_user):
        """Hit a real export endpoint to verify Excel generation end-to-end."""
        client.post("/login", data={"username": "testadmin", "password": "testpassword"})
        resp = client.get("/admin/export/mitglieder")
        assert resp.status_code == 200
        assert "spreadsheetml" in resp.content_type
