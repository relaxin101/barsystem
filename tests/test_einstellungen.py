"""Tests for the settings page and the DB → env → default lookup (#38)."""
import os
import re
from pathlib import Path

import pytest
from flask import g

from models import Einstellung, Mitglied
from utils.einstellungen import (
    DEFINITIONEN,
    ENV_ONLY,
    einstellung,
    pruefen,
    quelle,
    rohwert,
    speichern,
    zuruecksetzen,
)


@pytest.fixture(autouse=True)
def sauberes_env(monkeypatch):
    """.env values of whoever runs the tests must not leak in."""
    for key in DEFINITIONEN:
        monkeypatch.delenv(key, raising=False)


def _fresh():
    g.pop("einstellungen", None)


class TestLookup:
    def test_default(self, app):
        assert einstellung("HOTLIST_DAYS") == 14
        assert quelle("HOTLIST_DAYS") == "Standard"

    def test_env_beats_default(self, app, monkeypatch):
        monkeypatch.setenv("HOTLIST_DAYS", "30")
        assert einstellung("HOTLIST_DAYS") == 30
        assert quelle("HOTLIST_DAYS") == ".env"

    def test_db_beats_env(self, app, monkeypatch):
        monkeypatch.setenv("HOTLIST_DAYS", "30")
        speichern({"HOTLIST_DAYS": "7"}, "tester")
        assert einstellung("HOTLIST_DAYS") == 7
        assert quelle("HOTLIST_DAYS") == "geändert"

    def test_reset_falls_back_to_env(self, app, monkeypatch):
        monkeypatch.setenv("HOTLIST_DAYS", "30")
        speichern({"HOTLIST_DAYS": "7"}, "tester")
        zuruecksetzen("HOTLIST_DAYS")
        assert einstellung("HOTLIST_DAYS") == 30

    def test_empty_value_in_db_overrides_env(self, app, monkeypatch):
        monkeypatch.setenv("AUTO_SENDER", "bank@example.com")
        speichern({"AUTO_SENDER": ""}, "tester")
        assert einstellung("AUTO_SENDER") == ""

    def test_empty_env_number_uses_default(self, app, monkeypatch):
        """.env.example ships BREVO_TEMPLATE= with no value."""
        monkeypatch.setenv("BREVO_TEMPLATE", "")
        assert einstellung("BREVO_TEMPLATE") == 0

    @pytest.mark.parametrize("wert,cent", [("-50.0", -5000), ("-50.1", -5010), ("0", 0), ("", None)])
    def test_euro_returns_cents(self, app, monkeypatch, wert, cent):
        monkeypatch.setenv("MINDEST_GUTHABEN", wert)
        assert einstellung("MINDEST_GUTHABEN") == cent

    def test_change_reaches_other_workers(self, app, db):
        """Each worker has its own context: a write must show up on its next read."""
        assert einstellung("HOTLIST_DAYS") == 14
        db.session.add(Einstellung(key="HOTLIST_DAYS", value="9"))
        db.session.commit()

        with app.app_context():
            assert einstellung("HOTLIST_DAYS") == 9

    def test_one_query_per_request(self, app, db):
        from sqlalchemy import event

        statements = []
        event.listen(db.engine, "before_cursor_execute", lambda *a: statements.append(a[2]))
        einstellung("HOTLIST_DAYS")
        einstellung("SITE_NAME")
        rohwert("AUTO_SENDER")
        assert len(statements) == 1

    def test_saves_who_and_when(self, app, db):
        speichern({"HOTLIST_DAYS": "7"}, "tester")
        zeile = db.session.get(Einstellung, "HOTLIST_DAYS")
        assert zeile.updated_by == "tester"
        assert zeile.updated_at is not None


class TestDefaultSchwaerzungsgrenze:
    def test_new_member_gets_current_limit(self, app, db):
        speichern({"MINDEST_GUTHABEN": "-20"}, "tester")
        m = Mitglied(name="Neu")
        db.session.add(m)
        db.session.commit()
        assert m.schwaerzungs_grenze == -2000

    def test_no_limit(self, app, db):
        m = Mitglied(name="Neu")
        db.session.add(m)
        db.session.commit()
        assert m.schwaerzungs_grenze is None


class TestValidierung:
    def test_bad_regex(self, app):
        assert "AUTO_KONTO_REGEX" in pruefen({"AUTO_KONTO_REGEX": "(unclosed"})

    def test_group_above_regex_groups(self, app):
        fehler = pruefen({"AUTO_KONTO_REGEX": "(a)(b)", "AUTO_KONTO_GROUP": "3"})
        assert "2 Gruppe" in fehler["AUTO_KONTO_GROUP"]

    def test_new_regex_checked_against_saved_group(self, app):
        speichern({"AUTO_KONTO_REGEX": "(a)(b)(c)", "AUTO_KONTO_GROUP": "3"}, "tester")
        _fresh()
        assert "AUTO_KONTO_GROUP" in pruefen({"AUTO_KONTO_REGEX": "(a)"})

    def test_matching_group_is_fine(self, app):
        assert pruefen({"AUTO_BETRAG_REGEX": "(a)(b)", "AUTO_BETRAG_GROUP": "2"}) == {}

    def test_group_zero_is_the_whole_match(self, app):
        assert pruefen({"AUTO_BETRAG_REGEX": "a", "AUTO_BETRAG_GROUP": "0"}) == {}

    def test_empty_regex_disables_the_job(self, app):
        assert pruefen({"AUTO_KONTO_REGEX": ""}) == {}

    def test_broken_regex_in_env_does_not_crash(self, app, monkeypatch):
        monkeypatch.setenv("AUTO_KONTO_REGEX", "(unclosed")
        assert pruefen({"AUTO_KONTO_GROUP": "2"}) == {}

    @pytest.mark.parametrize("wert", ["abc", "", "0", "-1"])
    def test_hotlist_days_rejected(self, app, wert):
        assert "HOTLIST_DAYS" in pruefen({"HOTLIST_DAYS": wert})

    @pytest.mark.parametrize("wert,gueltig", [("-50", True), ("-50,5", True), ("", True), ("viel", False)])
    def test_euro(self, app, wert, gueltig):
        assert ("MINDEST_GUTHABEN" not in pruefen({"MINDEST_GUTHABEN": wert})) is gueltig

    def test_german_comma_is_saved_usable(self, app):
        speichern({"MINDEST_GUTHABEN": "-50,5"}, "tester")
        _fresh()
        assert einstellung("MINDEST_GUTHABEN") == -5050


class TestSeite:
    URL = "/admin/einstellungen/"

    def test_requires_login(self, client):
        assert client.get(self.URL).status_code == 302

    def test_admin_sees_only_general_settings(self, auth_client):
        html = auth_client.get(self.URL).get_data(as_text=True)
        assert 'name="HOTLIST_DAYS"' in html
        assert 'name="AUTO_KONTO_REGEX"' not in html
        assert "System" not in html

    def test_superadmin_sees_everything(self, superadmin_client):
        html = superadmin_client.get(self.URL).get_data(as_text=True)
        assert all(f'name="{key}"' in html for key in DEFINITIONEN)
        assert all(key in html for key in ENV_ONLY)

    def test_admin_saves_general_setting(self, auth_client):
        auth_client.post(self.URL, data={"HOTLIST_DAYS": "21"})
        assert einstellung("HOTLIST_DAYS") == 21
        assert Einstellung.query.get("HOTLIST_DAYS").updated_by == "testadmin"

    def test_admin_cannot_post_superadmin_key(self, auth_client):
        resp = auth_client.post(self.URL, data={"HOTLIST_DAYS": "21", "AUTO_SENDER": "boese@example.com"})
        assert resp.status_code == 403
        assert Einstellung.query.count() == 0

    def test_admin_cannot_reset_superadmin_key(self, auth_client, db):
        db.session.add(Einstellung(key="AUTO_SENDER", value="bank@example.com"))
        db.session.commit()
        assert auth_client.post(f"{self.URL}AUTO_SENDER/zuruecksetzen").status_code == 403
        assert Einstellung.query.count() == 1

    def test_unchanged_values_stay_at_their_source(self, superadmin_client):
        """Saving the form as shown must not freeze .env values into the DB."""
        html = superadmin_client.get(self.URL).get_data(as_text=True)
        form = dict(re.findall(r'name="([A-Z_]+)"\s+value="([^"]*)"', html))
        assert len(form) == len(DEFINITIONEN)
        superadmin_client.post(self.URL, data=form)
        assert Einstellung.query.count() == 0

    def test_invalid_input_saves_nothing_and_keeps_input(self, superadmin_client):
        resp = superadmin_client.post(
            self.URL, data={"HOTLIST_DAYS": "21", "AUTO_KONTO_REGEX": "(unclosed"}
        )
        html = resp.get_data(as_text=True)
        assert resp.status_code == 400
        assert Einstellung.query.count() == 0
        assert 'value="(unclosed"' in html
        assert 'value="21"' in html
        assert "Ungültiger regulärer Ausdruck" in html

    def test_reset(self, auth_client):
        auth_client.post(self.URL, data={"HOTLIST_DAYS": "21"})
        auth_client.post(f"{self.URL}HOTLIST_DAYS/zuruecksetzen")
        assert Einstellung.query.count() == 0

    def test_unknown_key_returns_404(self, superadmin_client):
        assert superadmin_client.post(f"{self.URL}GIBTSNICHT/zuruecksetzen").status_code == 404

    def test_reset_button_is_not_part_of_the_main_form(self, auth_client):
        """Inside it, it would be the default button and Enter would reset instead of save."""
        auth_client.post(self.URL, data={"HOTLIST_DAYS": "21"})
        html = auth_client.get(self.URL).get_data(as_text=True)
        assert 'form="reset-HOTLIST_DAYS"' in html
        assert 'formaction' not in html

    def test_secrets_never_rendered(self, superadmin_client, monkeypatch):
        monkeypatch.setenv("BREVO_SECRET", "streng-geheim-1")
        monkeypatch.setenv("IMAP_PASSWORD", "streng-geheim-2")
        monkeypatch.setenv("DATABASE_PASSWORD", "streng-geheim-3")
        html = superadmin_client.get(self.URL).get_data(as_text=True)
        assert "streng-geheim" not in html
        assert "gesetzt" in html

    def test_no_secret_is_a_setting(self):
        assert not {k for k, geheim in ENV_ONLY.items() if geheim} & DEFINITIONEN.keys()


class TestWirkung:
    def test_schwaerzungstext(self, client, db, mitglied, artikel):
        speichern({"SCHWAERZUNGS_TEXT": "Erst zahlen!"}, "tester")
        mitglied.blacklist = True
        db.session.commit()
        assert "Erst zahlen!" in client.get(f"/bar/buchen?mitglied_id={mitglied.id}").get_data(as_text=True)

    def test_site_names(self, client, auth_client):
        speichern({"SITE_NAME": "Zur Linde", "SITE_NAME_ADMIN": "Linde Intern"}, "tester")
        assert "Zur Linde" in client.get("/login").get_data(as_text=True)
        assert "Linde Intern" in auth_client.get("/admin/buchungen/").get_data(as_text=True)

    def test_brevo_sender(self, app):
        from unittest.mock import patch

        from utils.brevo import single_mail

        speichern({"BREVO_SENDER_NAME": "Kassa"}, "tester")
        with patch("utils.brevo.requests.post") as post:
            single_mail("s", "a@example.com", "A", "m", "0")
        assert post.call_args.kwargs["json"]["sender"]["name"] == "Kassa"

    def test_auto_aufbuchung_job_reads_settings_inside_app_context(self, app):
        """The scheduler thread has no app context until cronjob opens one."""
        from unittest.mock import patch

        from utils import auto_aufbuchung

        speichern({"AUTO_KONTO_REGEX": "(a)", "AUTO_BETRAG_REGEX": "(b)"}, "tester")
        with patch.object(auto_aufbuchung.config, "IMAP_HOST", "h"), \
                patch.object(auto_aufbuchung.config, "IMAP_USER", "u"), \
                patch.object(auto_aufbuchung.config, "IMAP_PASSWORD", "p"), \
                patch("utils.auto_aufbuchung._process_mailbox") as process:
            auto_aufbuchung.cronjob(app)
        process.assert_called_once()


def test_env_example_is_complete():
    """Every setting in the registry and every .env-only value is documented."""
    example = (Path(__file__).parent.parent / ".env.example").read_text("utf-8")
    documented = set(re.findall(r"^([A-Z_]+)=", example, re.MULTILINE))
    missing = (ENV_ONLY.keys() | DEFINITIONEN.keys()) - documented
    assert missing == {"SITE_NAME", "SITE_NAME_ADMIN"}  # neu, nur im Adminpanel
