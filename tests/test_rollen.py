"""Tests for the admin/superadmin split (#38).

The DB role behind the Berichte can't be tested on SQLite, it needs Postgres.
"""
import io
import zipfile
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from flask import g

from models import Bericht, Einstellung, Mitglied, User
from utils.zeit import utcnow

SUPERADMIN_ROUTES = [
    ("get", "/admin/benutzer/"),
    ("post", "/admin/benutzer/anlegen"),
    ("post", "/admin/benutzer/1/passwort"),
    ("post", "/admin/benutzer/1/rolle"),
    ("post", "/admin/benutzer/1/loeschen"),
]


class TestZugriff:
    @pytest.mark.parametrize("method,url", SUPERADMIN_ROUTES)
    def test_admin_gets_403(self, auth_client, method, url):
        assert getattr(auth_client, method)(url).status_code == 403

    @pytest.mark.parametrize("method,url", SUPERADMIN_ROUTES)
    def test_anonymous_goes_to_login(self, client, method, url):
        assert getattr(client, method)(url).status_code == 302

    def test_superadmin_gets_in(self, superadmin_client):
        assert superadmin_client.get("/admin/benutzer/").status_code == 200

    def test_sidebar_hides_benutzer_for_admin(self, auth_client):
        assert "🔐 Benutzer" not in auth_client.get("/admin/buchungen/").get_data(as_text=True)

    def test_sidebar_shows_benutzer_for_superadmin(self, superadmin_client):
        assert "🔐 Benutzer" in superadmin_client.get("/admin/buchungen/").get_data(as_text=True)


class TestCreateSuperadmin:
    def _run(self, app, *args):
        return app.test_cli_runner().invoke(args=["auth", "create-superadmin", *args])

    def test_creates_superadmin(self, app):
        assert self._run(app, "--username", "chef", "--password", "geheim123").exit_code == 0
        user = User.query.filter_by(username="chef").one()
        assert user.is_superadmin
        assert user.check_password("geheim123")

    def test_existing_user_is_not_promoted(self, app, admin_user):
        result = self._run(app, "--username", "testadmin", "--password", "geheim123")
        assert result.exit_code != 0
        assert not User.query.filter_by(username="testadmin").one().is_superadmin
        assert User.query.filter_by(username="testadmin").one().check_password("testpassword")


class TestBenutzer:
    def test_create(self, superadmin_client):
        superadmin_client.post(
            "/admin/benutzer/anlegen", data={"username": "neu", "passwort": "geheim123"}
        )
        user = User.query.filter_by(username="neu").one()
        assert not user.is_superadmin
        assert user.check_password("geheim123")

    def test_create_rejects_duplicate_and_short_password(self, superadmin_client, admin_user):
        superadmin_client.post(
            "/admin/benutzer/anlegen", data={"username": "testadmin", "passwort": "geheim123"}
        )
        superadmin_client.post(
            "/admin/benutzer/anlegen", data={"username": "kurz", "passwort": "abc"}
        )
        assert User.query.count() == 2

    def test_reset_password(self, superadmin_client, admin_user):
        superadmin_client.post(
            f"/admin/benutzer/{admin_user.id}/passwort", data={"passwort": "brandneu1"}
        )
        assert admin_user.check_password("brandneu1")

    def test_toggle_role(self, superadmin_client, admin_user):
        superadmin_client.post(f"/admin/benutzer/{admin_user.id}/rolle")
        assert admin_user.is_superadmin

    def test_last_superadmin_cannot_be_demoted(self, superadmin_client, superadmin_user):
        superadmin_client.post(f"/admin/benutzer/{superadmin_user.id}/rolle")
        assert superadmin_user.is_superadmin

    def test_cannot_delete_yourself(self, superadmin_client, superadmin_user):
        superadmin_client.post(f"/admin/benutzer/{superadmin_user.id}/loeschen")
        assert User.query.filter_by(username="testsuper").count() == 1

    def test_delete_ends_access(self, app, superadmin_client, admin_user):
        client = app.test_client()
        client.post("/login", data={"username": "testadmin", "password": "testpassword"})
        g.pop("_login_user", None)  # flask-login caches in g, the test app context is shared
        superadmin_client.post(f"/admin/benutzer/{admin_user.id}/loeschen")
        assert User.query.filter_by(username="testadmin").count() == 0

        g.pop("_login_user", None)
        assert client.get("/admin/buchungen/").status_code == 302


class TestPasswort:
    def _post(self, client, aktuell, neu, wiederholung=None):
        return client.post(
            "/passwort",
            data={"aktuell": aktuell, "neu": neu, "wiederholung": wiederholung or neu},
        )

    def test_change(self, auth_client, admin_user):
        assert self._post(auth_client, "testpassword", "brandneu1").status_code == 302
        assert admin_user.check_password("brandneu1")

    @pytest.mark.parametrize("aktuell,neu,wiederholung", [
        ("falsch", "brandneu1", "brandneu1"),
        ("testpassword", "kurz", "kurz"),
        ("testpassword", "brandneu1", "brandneu2"),
    ])
    def test_rejected(self, auth_client, admin_user, aktuell, neu, wiederholung):
        self._post(auth_client, aktuell, neu, wiederholung)
        assert admin_user.check_password("testpassword")

    def test_requires_login(self, client):
        assert client.get("/passwort").status_code == 302


class TestBackup:
    def _backup(self, client):
        with patch("blueprints.admin.berichte._get_db_revision", return_value="x"):
            return client.get("/admin/export/db-backup").data

    def _restore(self, client, data):
        with patch("blueprints.admin.berichte._get_db_revision", return_value="x"), \
                patch("blueprints.admin.berichte.db.session.execute"):
            client.post(
                "/admin/export/db-restore",
                data={"file": (io.BytesIO(data), "b.zip")},
                content_type="multipart/form-data",
            )

    def _tables(self, data):
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            return {n[:-5] for n in zf.namelist() if n.endswith(".xlsx")}

    def test_admin_backup_has_no_accounts_or_settings(self, auth_client):
        tables = self._tables(self._backup(auth_client))
        assert "buchungen" in tables
        assert not {"users", "einstellungen"} & tables

    def test_superadmin_backup_has_all_tables(self, superadmin_client):
        assert {"users", "einstellungen", "buchungen"} <= self._tables(self._backup(superadmin_client))

    def _crafted_zip(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for name, rows in {
                "users": [{"id": 99, "username": "boese", "password": "x", "is_superadmin": True}],
                "einstellungen": [{"key": "AUTO_SENDER", "value": "boese@example.com"}],
                "mitglieder": [{"id": 77, "name": "Neu", "guthaben": 0}],
            }.items():
                excel = io.BytesIO()
                pd.DataFrame(rows).to_excel(excel, index=False)
                zf.writestr(f"{name}.xlsx", excel.getvalue())
        return buf.getvalue()

    def test_admin_restore_ignores_accounts_and_settings(self, auth_client):
        self._restore(auth_client, self._crafted_zip())
        assert User.query.filter_by(username="boese").count() == 0
        assert Einstellung.query.count() == 0
        assert Mitglied.query.filter_by(name="Neu").count() == 1

    def test_superadmin_roundtrip_with_settings(self, superadmin_client, db):
        db.session.add_all([
            Einstellung(key="HOTLIST_DAYS", value="21", updated_at=utcnow(), updated_by="x"),
            Einstellung(key="AUTO_SENDER", value=""),
        ])
        db.session.commit()
        data = self._backup(superadmin_client)
        Einstellung.query.delete()
        db.session.commit()

        self._restore(superadmin_client, data)

        assert db.session.get(Einstellung, "HOTLIST_DAYS").value == "21"
        assert not db.session.get(Einstellung, "AUTO_SENDER").value

    def test_superadmin_restore_skips_existing_setting(self, superadmin_client, db):
        db.session.add(Einstellung(key="HOTLIST_DAYS", value="21"))
        db.session.commit()
        data = self._backup(superadmin_client)
        db.session.get(Einstellung, "HOTLIST_DAYS").value = "30"
        db.session.commit()

        self._restore(superadmin_client, data)

        assert db.session.get(Einstellung, "HOTLIST_DAYS").value == "30"


class TestBerichte:
    def _post(self, client, **form):
        return client.post("/admin/export/", data={"query": "SELECT 1 AS x", **form})

    @pytest.fixture()
    def engines(self, db):
        """report_engine as a spy, so we see which connection a query would use."""
        with patch("blueprints.admin.berichte.report_engine", return_value=db.engine) as spy:
            yield spy

    def test_admin_query_uses_report_engine(self, auth_client, engines):
        self._post(auth_client)
        engines.assert_called_once()

    def test_admin_cannot_claim_write_access(self, auth_client, engines):
        self._post(auth_client, schreiben="on")
        engines.assert_called_once()

    def test_superadmin_is_read_only_by_default(self, superadmin_client, engines):
        self._post(superadmin_client)
        engines.assert_called_once()

    def test_superadmin_write_checkbox(self, superadmin_client, engines):
        self._post(superadmin_client, schreiben="on")
        engines.assert_not_called()

    def test_saved_report_never_runs_with_write_access(self, superadmin_client, db, engines):
        b = Bericht(name="Fremd", sql="SELECT 1")
        db.session.add(b)
        db.session.commit()
        superadmin_client.get(f"/admin/export/?id={b.id}&schreiben=on")
        engines.assert_called_once()

    def test_excel_download_uses_report_engine(self, superadmin_client, engines):
        superadmin_client.post("/admin/export/download", data={"query": "SELECT 1 AS x", "schreiben": "on"})
        engines.assert_called_once()

    def test_write_statement_without_rows(self, superadmin_client, db, mitglied):
        resp = superadmin_client.post(
            "/admin/export/",
            data={"query": f"UPDATE mitglied SET name = 'Neu' WHERE id = {mitglied.id}", "schreiben": "on"},
        )
        assert resp.status_code == 200
        db.session.refresh(mitglied)
        assert mitglied.name == "Neu"

    def test_write_checkbox_hidden_for_admin(self, auth_client):
        assert 'name="schreiben"' not in auth_client.get("/admin/export/").get_data(as_text=True)

    def test_write_checkbox_shown_for_superadmin(self, superadmin_client):
        assert 'name="schreiben"' in superadmin_client.get("/admin/export/").get_data(as_text=True)

    def test_missing_role_fails_closed(self, auth_client):
        from sqlalchemy.exc import OperationalError

        kaputt = MagicMock()
        kaputt.connect.side_effect = OperationalError("x", {}, Exception("role does not exist"))
        with patch("blueprints.admin.berichte.report_engine", return_value=kaputt):
            html = self._post(auth_client).get_data(as_text=True)
            resp = auth_client.post("/admin/export/download", data={"query": "SELECT 1"})
        assert "nicht eingerichtet" in html
        assert resp.status_code == 302


def test_sync_report_role_skips_sqlite(app):
    result = app.test_cli_runner().invoke(args=["sync-report-role"])
    assert result.exit_code == 0
    assert "Skipped" in result.output


def test_report_role_cannot_see_accounts_or_settings():
    from utils.bericht_engine import REPORT_TABLES

    assert not {"user", "einstellung"} & set(REPORT_TABLES)
