"""Tests for the user/superuser split (#38).

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

SUPERUSER_ROUTES = [
    ("get", "/admin/benutzer/"),
    ("post", "/admin/benutzer/anlegen"),
    ("post", "/admin/benutzer/1/passwort"),
    ("post", "/admin/benutzer/1/rolle"),
    ("post", "/admin/benutzer/1/loeschen"),
]


class TestZugriff:
    @pytest.mark.parametrize("method,url", SUPERUSER_ROUTES)
    def test_admin_gets_403(self, auth_client, method, url):
        assert getattr(auth_client, method)(url).status_code == 403

    @pytest.mark.parametrize("method,url", SUPERUSER_ROUTES)
    def test_anonymous_goes_to_login(self, client, method, url):
        assert getattr(client, method)(url).status_code == 302

    def test_superuser_gets_in(self, superuser_client):
        assert superuser_client.get("/admin/benutzer/").status_code == 200

    def test_sidebar_hides_benutzer_for_admin(self, auth_client):
        assert "🔐 Benutzer" not in auth_client.get("/admin/buchungen/").get_data(as_text=True)

    def test_sidebar_shows_benutzer_for_superuser(self, superuser_client):
        assert "🔐 Benutzer" in superuser_client.get("/admin/buchungen/").get_data(as_text=True)


class TestCreateSuperuser:
    def _run(self, app, *args):
        return app.test_cli_runner().invoke(args=["auth", "create-user", "--superuser", *args])

    def test_creates_superuser(self, app):
        assert self._run(app, "--username", "chef", "--password", "geheim123").exit_code == 0
        user = User.query.filter_by(username="chef").one()
        assert user.is_superuser
        assert user.check_password("geheim123")

    def test_existing_user_is_not_promoted(self, app, admin_user):
        result = self._run(app, "--username", "testadmin", "--password", "geheim123")
        assert result.exit_code != 0
        assert not User.query.filter_by(username="testadmin").one().is_superuser
        assert User.query.filter_by(username="testadmin").one().check_password("testpassword")


class TestCreateDefaultUser:
    def _run(self, app):
        return app.test_cli_runner().invoke(args=["auth", "create-default-user"])

    def test_creates_superuser(self, app):
        assert self._run(app).exit_code == 0
        user = User.query.filter_by(username="testadmin").one()
        assert user.is_superuser
        assert user.check_password("testpassword")

    def test_promotes_existing_user_and_keeps_password(self, app, admin_user):
        assert self._run(app).exit_code == 0
        user = User.query.filter_by(username="testadmin").one()
        assert user.is_superuser
        assert user.check_password("testpassword")


class TestBenutzer:
    def test_create(self, superuser_client):
        superuser_client.post(
            "/admin/benutzer/anlegen", data={"username": "neu", "passwort": "geheim123"}
        )
        user = User.query.filter_by(username="neu").one()
        assert not user.is_superuser
        assert user.check_password("geheim123")

    def test_create_rejects_duplicate_and_short_password(self, superuser_client, admin_user):
        superuser_client.post(
            "/admin/benutzer/anlegen", data={"username": "testadmin", "passwort": "geheim123"}
        )
        superuser_client.post(
            "/admin/benutzer/anlegen", data={"username": "kurz", "passwort": "abc"}
        )
        assert User.query.count() == 2

    def test_reset_password(self, superuser_client, admin_user):
        superuser_client.post(
            f"/admin/benutzer/{admin_user.id}/passwort", data={"passwort": "brandneu1"}
        )
        assert admin_user.check_password("brandneu1")

    def test_toggle_role(self, superuser_client, normal_user):
        superuser_client.post(f"/admin/benutzer/{normal_user.id}/rolle")
        assert normal_user.is_superuser

    def test_default_user_cannot_be_demoted_or_deleted(self, superuser_client, db):
        default = User(username="testadmin", is_superuser=True)
        default.set_password("testpassword")
        db.session.add(default)
        db.session.commit()
        superuser_client.post(f"/admin/benutzer/{default.id}/rolle")
        superuser_client.post(f"/admin/benutzer/{default.id}/loeschen")
        assert User.query.filter_by(username="testadmin").one().is_superuser

    def test_last_superuser_cannot_be_demoted(self, superuser_client, superuser_user):
        superuser_client.post(f"/admin/benutzer/{superuser_user.id}/rolle")
        assert superuser_user.is_superuser

    def test_cannot_delete_yourself(self, superuser_client, superuser_user):
        superuser_client.post(f"/admin/benutzer/{superuser_user.id}/loeschen")
        assert User.query.filter_by(username="testsuper").count() == 1

    def test_delete_ends_access(self, app, superuser_client, normal_user):
        client = app.test_client()
        client.post("/login", data={"username": "testuser", "password": "testpassword"})
        g.pop("_login_user", None)  # flask-login caches in g, the test app context is shared
        superuser_client.post(f"/admin/benutzer/{normal_user.id}/loeschen")
        assert User.query.filter_by(username="testuser").count() == 0

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

    def test_superuser_backup_has_all_tables(self, superuser_client):
        assert {"users", "einstellungen", "buchungen"} <= self._tables(self._backup(superuser_client))

    def _crafted_zip(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for name, rows in {
                "users": [{"id": 99, "username": "boese", "password": "x", "is_superuser": True}],
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

    def test_superuser_roundtrip_with_settings(self, superuser_client, db):
        db.session.add_all([
            Einstellung(key="HOTLIST_DAYS", value="21", updated_at=utcnow(), updated_by="x"),
            Einstellung(key="AUTO_SENDER", value=""),
        ])
        db.session.commit()
        data = self._backup(superuser_client)
        Einstellung.query.delete()
        db.session.commit()

        self._restore(superuser_client, data)

        assert db.session.get(Einstellung, "HOTLIST_DAYS").value == "21"
        assert not db.session.get(Einstellung, "AUTO_SENDER").value

    def test_superuser_restore_skips_existing_setting(self, superuser_client, db):
        db.session.add(Einstellung(key="HOTLIST_DAYS", value="21"))
        db.session.commit()
        data = self._backup(superuser_client)
        db.session.get(Einstellung, "HOTLIST_DAYS").value = "30"
        db.session.commit()

        self._restore(superuser_client, data)

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

    def test_superuser_is_read_only_by_default(self, superuser_client, engines):
        self._post(superuser_client)
        engines.assert_called_once()

    def test_superuser_write_checkbox(self, superuser_client, engines):
        self._post(superuser_client, schreiben="on")
        engines.assert_not_called()

    def test_saved_report_never_runs_with_write_access(self, superuser_client, db, engines):
        b = Bericht(name="Fremd", sql="SELECT 1")
        db.session.add(b)
        db.session.commit()
        superuser_client.get(f"/admin/export/?id={b.id}&schreiben=on")
        engines.assert_called_once()

    def test_excel_download_uses_report_engine(self, superuser_client, engines):
        superuser_client.post("/admin/export/download", data={"query": "SELECT 1 AS x", "schreiben": "on"})
        engines.assert_called_once()

    def test_write_statement_without_rows(self, superuser_client, db, mitglied):
        resp = superuser_client.post(
            "/admin/export/",
            data={"query": f"UPDATE mitglied SET name = 'Neu' WHERE id = {mitglied.id}", "schreiben": "on"},
        )
        assert resp.status_code == 200
        db.session.refresh(mitglied)
        assert mitglied.name == "Neu"

    def test_write_checkbox_hidden_for_admin(self, auth_client):
        assert 'name="schreiben"' not in auth_client.get("/admin/export/").get_data(as_text=True)

    def test_write_checkbox_shown_for_superuser(self, superuser_client):
        assert 'name="schreiben"' in superuser_client.get("/admin/export/").get_data(as_text=True)

    def test_missing_role_fails_closed(self, auth_client):
        from sqlalchemy.exc import OperationalError

        kaputt = MagicMock()
        kaputt.connect.side_effect = OperationalError("x", {}, Exception("role does not exist"))
        with patch("blueprints.admin.berichte.report_engine", return_value=kaputt):
            html = self._post(auth_client).get_data(as_text=True)
            resp = auth_client.post("/admin/export/download", data={"query": "SELECT 1"})
        assert "nicht eingerichtet" in html
        assert resp.status_code == 302

    def test_saved_report_shows_its_name(self, auth_client, db):
        b = Bericht(name="Umsatz", sql="SELECT 1")
        db.session.add(b)
        db.session.commit()
        html = auth_client.get(f"/admin/export/?id={b.id}").get_data(as_text=True)
        assert 'value="Umsatz" data-original="Umsatz"' in html

    def test_rename_keeps_sql(self, auth_client, db):
        b = Bericht(name="Alt", sql="SELECT 1")
        db.session.add(b)
        db.session.commit()
        resp = auth_client.post(
            f"/admin/export/berichte/{b.id}/umbenennen", data={"name": " Neu ", "query": "SELECT 2"}
        )
        assert resp.headers["Location"].endswith(f"?id={b.id}")
        db.session.refresh(b)
        assert (b.name, b.sql) == ("Neu", "SELECT 1")

    @pytest.fixture()
    def bericht(self, db):
        b = Bericht(name="Alt", sql="SELECT 1 AS x")
        db.session.add(b)
        db.session.commit()
        return b

    def test_testing_keeps_report_active_and_ignores_write_access(self, superuser_client, bericht, engines):
        html = superuser_client.post(
            f"/admin/export/?id={bericht.id}", data={"query": "SELECT 2 AS x", "testen": "1", "schreiben": "on"}
        ).get_data(as_text=True)
        engines.assert_called_once()  # lesend wie ein gespeicherter Bericht
        assert 'data-original="Alt"' in html
        assert 'data-getestet="SELECT 2 AS x"' in html

    def test_failed_test_offers_no_save(self, auth_client, bericht, engines):
        html = auth_client.post(
            f"/admin/export/?id={bericht.id}", data={"query": "SELECT FROM nirgends", "testen": "1"}
        ).get_data(as_text=True)
        assert 'data-getestet=""' in html

    def test_update_sql_saves_only_the_query(self, auth_client, bericht, engines, db):
        resp = auth_client.post(
            f"/admin/export/berichte/{bericht.id}/abfrage", data={"query": "SELECT 2 AS x\r\n", "name": "Anders"}
        )
        assert resp.headers["Location"].endswith(f"?id={bericht.id}")
        db.session.refresh(bericht)
        assert (bericht.name, bericht.sql) == ("Alt", "SELECT 2 AS x")
        engines.assert_called_once()

    def test_update_sql_rejects_broken_query_without_test(self, auth_client, bericht, engines, db):
        auth_client.post(f"/admin/export/berichte/{bericht.id}/abfrage", data={"query": "SELECT FROM nirgends"})
        db.session.refresh(bericht)
        assert bericht.sql == "SELECT 1 AS x"

    def test_rename_rejects_empty_name(self, auth_client, db):
        b = Bericht(name="Alt", sql="SELECT 1")
        db.session.add(b)
        db.session.commit()
        auth_client.post(f"/admin/export/berichte/{b.id}/umbenennen", data={"name": "  "})
        db.session.refresh(b)
        assert b.name == "Alt"


def test_sync_report_role_skips_sqlite(app):
    result = app.test_cli_runner().invoke(args=["sync-report-role"])
    assert result.exit_code == 0
    assert "Skipped" in result.output


def test_report_role_cannot_see_accounts_or_settings():
    from utils.bericht_engine import REPORT_TABLES

    assert not {"user", "einstellung"} & set(REPORT_TABLES)
