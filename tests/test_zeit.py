"""Tests for time zone handling (#32): UTC in the DB, local time at the edges.

SQLite has no timestamptz and no session time zone, so the Postgres side
(migration, saved reports) can't be covered here.
"""
import io
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from sqlalchemy.exc import StatementError

from models import Abrechnung, Aussendung, Buchung
from utils.admin import export_df_to_excel, parse_daterange
from utils.zeit import naive_local, naive_utc, parse_local, utcnow

UTC = timezone.utc
SOMMER = datetime(2026, 7, 15, 18, 30, tzinfo=UTC)  # 20:30 in Wien
WINTER = datetime(2026, 1, 15, 18, 30, tzinfo=UTC)  # 19:30 in Wien


def _buchung(db, mitglied, artikel, ts=SOMMER, **kwargs):
    b = Buchung(
        mitglied_id=mitglied.id,
        artikel_id=artikel.id,
        menge=1,
        preis_pro_einheit=200,
        gesamtpreis=-200,
        storno=False,
        zeitstempel=ts,
        **kwargs,
    )
    db.session.add(b)
    db.session.commit()
    return b


class TestParseLocal:
    def test_summer_offset(self):
        assert parse_local("2026-07-15T20:30") == SOMMER

    def test_winter_offset(self):
        assert parse_local("2026-01-15T19:30") == WINTER

    def test_aware_input_keeps_its_offset(self):
        assert parse_local("2026-07-15T18:30:00+00:00") == SOMMER

    def test_nonexistent_hour_when_clocks_go_forward(self):
        assert parse_local("2026-03-29T02:30").astimezone(UTC).hour == 1

    def test_ambiguous_hour_when_clocks_go_back_is_the_first_one(self):
        assert parse_local("2026-10-25T02:30").astimezone(UTC).hour == 0


class TestNaive:
    def test_naive_local(self):
        assert naive_local(SOMMER) == datetime(2026, 7, 15, 20, 30)

    def test_naive_utc(self):
        assert naive_utc(SOMMER.astimezone(timezone(timedelta(hours=2)))) == datetime(
            2026, 7, 15, 18, 30
        )

    @pytest.mark.parametrize("value", [None, "text", 1.5, datetime(2026, 1, 1)])
    def test_everything_else_stays(self, value):
        assert naive_local(value) == value
        assert naive_utc(value) == value


class TestLocalTimeFilter:
    def test_formats_in_local_time(self, app):
        local_time = app.jinja_env.filters["local_time"]
        assert local_time(SOMMER) == "15.07.2026 20:30"
        assert local_time(WINTER) == "15.01.2026 19:30"

    def test_custom_format(self, app):
        assert app.jinja_env.filters["local_time"](SOMMER, "%H:%M") == "20:30"

    def test_none_is_empty(self, app):
        assert app.jinja_env.filters["local_time"](None) == ""

    def test_fixed_offset_from_raw_query(self, app):
        value = SOMMER.astimezone(timezone(timedelta(hours=2)))
        assert app.jinja_env.filters["local_time"](value) == "15.07.2026 20:30"


class TestUTCDateTime:
    def test_rejects_naive(self, db):
        db.session.add(Abrechnung(name="Naiv", zeitstempel=datetime(2026, 7, 15, 20, 30)))
        with pytest.raises(StatementError, match="Naive datetime"):
            db.session.commit()
        db.session.rollback()

    def test_returns_aware_utc(self, db):
        a = Abrechnung(name="Wien", zeitstempel=parse_local("2026-07-15T20:30"))
        db.session.add(a)
        db.session.commit()
        db.session.refresh(a)
        assert a.zeitstempel == SOMMER
        assert a.zeitstempel.utcoffset() == timedelta(0)

    def test_default_is_aware(self, db):
        a = Abrechnung(name="Default")
        db.session.add(a)
        db.session.commit()
        db.session.refresh(a)
        assert utcnow() - a.zeitstempel < timedelta(minutes=1)


class TestDaterange:
    def test_input_is_local_time(self, app):
        with app.test_request_context("/?start=2026-07-15T20:00&end=2026-07-15T21:00"):
            start, end = parse_daterange()
        assert start == datetime(2026, 7, 15, 18, 0, tzinfo=UTC)
        assert end == datetime(2026, 7, 15, 19, 0, tzinfo=UTC)

    def test_default_starts_at_local_midnight(self, app):
        with app.test_request_context("/"):
            start, _ = parse_daterange()
        assert (start.hour, start.minute) == (0, 0)
        assert start.utcoffset() is not None

    def test_filter_matches_the_displayed_time(self, auth_client, db, mitglied, artikel):
        _buchung(db, mitglied, artikel)

        html = auth_client.get(
            "/admin/buchungen/?start=2026-07-15T20:00&end=2026-07-15T21:00"
        ).get_data(as_text=True)
        assert "15.07.2026 20:30" in html
        assert 'value="2026-07-15T20:00"' in html

        # 18:00–19:00 ist die UTC-Zeit der Buchung, nicht die Ortszeit
        html = auth_client.get(
            "/admin/buchungen/?start=2026-07-15T18:00&end=2026-07-15T19:00"
        ).get_data(as_text=True)
        assert "15.07.2026 20:30" not in html


class TestAbrechnung:
    def test_zeitraum_is_local_time(self, auth_client, db, mitglied, artikel):
        b = _buchung(db, mitglied, artikel)

        auth_client.post(
            "/admin/abrechnung/create",
            json={
                "name": "UTC-Fenster",
                "modus": "zeitraum",
                "start": "2026-07-15T18:00",
                "end": "2026-07-15T19:00",
            },
        )
        db.session.refresh(b)
        assert b.abrechnungs_id is None

        auth_client.post(
            "/admin/abrechnung/create",
            json={
                "name": "Orts-Fenster",
                "modus": "zeitraum",
                "start": "2026-07-15T20:00",
                "end": "2026-07-15T21:00",
            },
        )
        db.session.refresh(b)
        assert b.abrechnung_obj.name == "Orts-Fenster"

    def test_detail_shows_local_time(self, auth_client, db, mitglied, artikel):
        a = Abrechnung(name="Detail", zeitstempel=WINTER)
        db.session.add(a)
        db.session.commit()
        _buchung(db, mitglied, artikel, abrechnungs_id=a.id)

        html = auth_client.get(f"/admin/abrechnung/{a.id}").get_data(as_text=True)
        assert "15.01.2026, um 19:30" in html
        assert "value=2026-07-15T20:30:00" in html

    def test_detail_without_buchungen(self, auth_client, db):
        a = Abrechnung(name="Leer")
        db.session.add(a)
        db.session.commit()
        assert auth_client.get(f"/admin/abrechnung/{a.id}").status_code == 200

    def test_storno_after_abrechnung_is_detected(self, auth_client, db, mitglied, artikel):
        a = Abrechnung(name="Alt", zeitstempel=SOMMER)
        db.session.add(a)
        db.session.commit()
        b = _buchung(db, mitglied, artikel, abrechnungs_id=a.id)

        data = auth_client.post(f"/admin/buchungen/toggle/{b.id}").get_json()
        assert 'Abrechnung' in data["message"]


class TestExcel:
    def test_buchungen_download_in_local_time(self, auth_client, db, mitglied, artikel):
        _buchung(db, mitglied, artikel)
        resp = auth_client.get(
            "/admin/buchungen/download?start=2026-07-15T20:00&end=2026-07-15T21:00"
        )
        assert resp.status_code == 200
        assert "buchungen_2026-07-15_20-00_2026-07-15_21-00.xlsx" in resp.headers["Content-Disposition"]
        assert pd.read_excel(io.BytesIO(resp.data))["Datum"][0] == "2026-07-15 20:30"

    def test_export_accepts_aware_values(self, app):
        """Report rows from Postgres carry a fixed offset, Excel rejects those."""
        wien = timezone(timedelta(hours=2))
        df = pd.DataFrame({
            "zeit": [SOMMER.astimezone(wien), None, WINTER],
            "name": ["a", "b", None],
            "betrag": [1.5, None, 2],
        })
        with app.test_request_context("/"):
            resp = export_df_to_excel(df, "export.xlsx")
            resp.direct_passthrough = False
            result = pd.read_excel(io.BytesIO(resp.get_data()))
        assert result["zeit"][0] == pd.Timestamp("2026-07-15 20:30")
        assert pd.isna(result["zeit"][1])
        assert result["zeit"][2] == pd.Timestamp("2026-01-15 19:30")
        assert result["betrag"][0] == 1.5


class TestBackupRestore:
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

    def test_backup_stores_naive_utc(self, auth_client, db, mitglied, artikel):
        _buchung(db, mitglied, artikel)
        with zipfile.ZipFile(io.BytesIO(self._backup(auth_client))) as zf:
            df = pd.read_excel(io.BytesIO(zf.read("buchungen.xlsx")))
        assert df["zeitstempel"][0] == pd.Timestamp("2026-07-15 18:30")

    def test_roundtrip_keeps_instants(self, auth_client, db, mitglied, artikel):
        mit = _buchung(db, mitglied, artikel, storno_updated_at=WINTER)
        ohne = _buchung(db, mitglied, artikel)
        mit_id, ohne_id = mit.id, ohne.id
        data = self._backup(auth_client)

        Buchung.query.delete()
        db.session.commit()
        self._restore(auth_client, data)

        assert db.session.get(Buchung, mit_id).zeitstempel == SOMMER
        assert db.session.get(Buchung, mit_id).storno_updated_at == WINTER
        assert db.session.get(Buchung, ohne_id).storno_updated_at is None

    def test_roundtrip_with_column_all_empty(self, auth_client, db, mitglied, artikel):
        b_id = _buchung(db, mitglied, artikel).id
        data = self._backup(auth_client)

        Buchung.query.delete()
        db.session.commit()
        self._restore(auth_client, data)

        assert db.session.get(Buchung, b_id).storno_updated_at is None


class TestScheduler:
    def test_cronjob_compares_last_run(self, app, db):
        from blueprints.admin.aussendungen import cronjob

        faellig = Aussendung(
            subject="Fällig", message="m", frequenz="7", aktiv=True,
            last_run=utcnow() - timedelta(days=8),
        )
        offen = Aussendung(
            subject="Offen", message="m", frequenz="7", aktiv=True,
            last_run=utcnow() - timedelta(days=1),
        )
        db.session.add_all([faellig, offen])
        db.session.commit()

        with patch("blueprints.admin.aussendungen.brevo_send") as send:
            cronjob(app)

        assert [call.args[0].subject for call in send.call_args_list] == ["Fällig"]


def test_ranking_renders(client):
    assert client.get("/ranking/").status_code == 200


def test_templates_do_not_format_utc_directly():
    """strftime in a template would silently print UTC, use |local_time."""
    templates = Path(__file__).parent.parent / "templates"
    offenders = [p.name for p in templates.rglob("*.html") if ".strftime(" in p.read_text("utf-8")]
    assert offenders == []
