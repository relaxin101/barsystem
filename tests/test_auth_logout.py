"""Tests for the logout route and its optional redirect target."""


class TestLogoutRedirect:
    def test_logout_defaults_to_bar_interface(self, auth_client):
        resp = auth_client.get("/logout")
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/")

    def test_logout_honours_safe_next_target(self, auth_client):
        resp = auth_client.get("/logout", query_string={"next": "/ranking"})
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/ranking")

    def test_logout_rejects_external_next_target(self, auth_client):
        resp = auth_client.get("/logout", query_string={"next": "https://evil.example/phish"})
        assert resp.status_code == 302
        assert "evil.example" not in resp.headers["Location"]
        assert resp.headers["Location"].endswith("/")

    def test_logout_rejects_protocol_relative_next_target(self, auth_client):
        resp = auth_client.get("/logout", query_string={"next": "//evil.example/phish"})
        assert resp.status_code == 302
        assert "evil.example" not in resp.headers["Location"]

    def test_logout_actually_logs_out(self, auth_client):
        auth_client.get("/logout")
        # A login-required page should now redirect to the login form.
        resp = auth_client.get("/logout")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]
