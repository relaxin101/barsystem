"""Integration test: create_app("production") must refuse to boot with
shipped-default secrets still active, and boot fine once they're changed.

config.py reads os.environ at class-definition time, so the env vars have
to be set before the module (re)loads — importlib.reload forces that.
"""

import importlib

import pytest


@pytest.fixture()
def production_env(monkeypatch):
    monkeypatch.setenv("DATABASE_USERNAME", "ergo")
    monkeypatch.setenv("DATABASE_HOST", "localhost")
    monkeypatch.setenv("DATABASE_NAME", "barliste")
    monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
    yield monkeypatch


def test_production_boot_refused_with_default_admin_password(production_env):
    production_env.setenv("FLASK_SECRET_KEY", "a-real-random-secret")
    production_env.setenv("ADMIN_PASSWORD", "password!")
    import config

    importlib.reload(config)
    try:
        from app import create_app

        with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
            create_app("production")
    finally:
        importlib.reload(config)


def test_production_boots_with_secure_secrets(production_env):
    production_env.setenv("FLASK_SECRET_KEY", "a-real-random-secret")
    production_env.setenv("ADMIN_PASSWORD", "a-real-password")
    import config

    importlib.reload(config)
    try:
        from app import create_app

        app = create_app("production")
        assert app is not None
    finally:
        importlib.reload(config)
