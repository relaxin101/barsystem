"""Tests for the base-template footer — Feedback link should only show admins."""


def test_footer_hidden_on_bar_page(client):
    resp = client.get("/", follow_redirects=True)
    assert resp.status_code == 200
    assert "Feedback?" not in resp.get_data(as_text=True)


def test_footer_shown_in_admin_panel(auth_client):
    resp = auth_client.get("/admin/buchungen/", follow_redirects=True)
    assert resp.status_code == 200
    assert "Feedback?" in resp.get_data(as_text=True)
