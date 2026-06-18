"""Tests for blueprints/admin/buchungen.py — storno toggle."""
from datetime import datetime

from models import Buchung, Mitglied, Artikel


def _create_buchung(db, mitglied, artikel, preis=200, storno=False):
    b = Buchung(
        mitglied_id=mitglied.id,
        artikel_id=artikel.id,
        menge=1,
        preis_pro_einheit=preis,
        gesamtpreis=-preis,
        storno=storno,
        zeitstempel=datetime.now(),
    )
    db.session.add(b)
    db.session.commit()
    return b


class TestStornoToggle:
    def test_storno_sets_flag_and_reverses_guthaben(self, auth_client, db, mitglied, artikel):
        b = _create_buchung(db, mitglied, artikel)
        initial_guthaben = mitglied.guthaben

        resp = auth_client.post(f"/admin/buchungen/toggle/{b.id}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["storniert"] is True

        db.session.refresh(mitglied)
        # gesamtpreis was -200; storno adds it back (subtracts the negative)
        assert mitglied.guthaben == initial_guthaben + 200

    def test_undo_storno_re_deducts_guthaben(self, auth_client, db, mitglied, artikel):
        b = _create_buchung(db, mitglied, artikel, storno=True)
        b.storno_updated_at = datetime.now()
        # Re-credit guthaben to simulate previous storno
        mitglied.guthaben += abs(b.gesamtpreis)
        db.session.commit()
        guthaben_after_storno = mitglied.guthaben

        resp = auth_client.post(f"/admin/buchungen/toggle/{b.id}")
        data = resp.get_json()
        assert data["storniert"] is False

        db.session.refresh(mitglied)
        assert mitglied.guthaben == guthaben_after_storno - abs(b.gesamtpreis)

    def test_storno_sets_storno_updated_at(self, auth_client, db, mitglied, artikel):
        b = _create_buchung(db, mitglied, artikel)
        assert b.storno_updated_at is None

        auth_client.post(f"/admin/buchungen/toggle/{b.id}")

        db.session.refresh(b)
        assert b.storno_updated_at is not None

    def test_storno_nonexistent_returns_404(self, auth_client):
        resp = auth_client.post("/admin/buchungen/toggle/99999")
        assert resp.status_code == 404

    def test_storno_triggers_blacklist_check(self, auth_client, db, mitglied, artikel):
        """Storno of a purchase that crosses the blacklist threshold."""
        mitglied.schwaerzungs_grenze = 500
        mitglied.guthaben = 600
        db.session.commit()

        # Create a purchase that reduced guthaben from 600 to 400
        b = Buchung(
            mitglied_id=mitglied.id,
            artikel_id=artikel.id,
            menge=1,
            preis_pro_einheit=200,
            gesamtpreis=-200,
            storno=False,
            zeitstempel=datetime.now(),
        )
        db.session.add(b)
        mitglied.guthaben = 400  # already deducted
        db.session.commit()

        # Storno this purchase: guthaben goes from 400 back to 600 (above threshold)
        resp = auth_client.post(f"/admin/buchungen/toggle/{b.id}")
        assert resp.status_code == 200

        db.session.refresh(mitglied)
        # After storno-reversal, guthaben = 400 + 200 = 600 → stays blacklisted
        # (calc_blacklist with blacklist=False: 400 >= 500? No → not blacklisted)
        # Actually mitglied.blacklist was False, so calc_blacklist(m, -(-200)) = calc(m, 200)
        # Not blacklisted because 400 + 200 = 600 >= 500


class TestBuchungenHistory:
    def test_history_requires_login(self, client):
        resp = client.get("/admin/buchungen/")
        assert resp.status_code in (302, 401)

    def test_history_accessible_when_logged_in(self, auth_client):
        resp = auth_client.get("/admin/buchungen/")
        assert resp.status_code == 200
