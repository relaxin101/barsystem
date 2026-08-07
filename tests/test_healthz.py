"""Tests for GET /healthz — the kiosk boot wait-loop's readiness signal."""

from unittest.mock import patch

from models import db


def test_healthz_ok_when_db_reachable(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert "version" in data


def test_healthz_503_when_db_unreachable(client):
    with patch.object(db.session, "execute", side_effect=Exception("db down")):
        resp = client.get("/healthz")
    assert resp.status_code == 503
    assert resp.get_json()["status"] == "error"


def test_healthz_requires_no_auth(client):
    # No login performed — must not redirect to /login like other routes do.
    resp = client.get("/healthz")
    assert resp.status_code in (200, 503)
