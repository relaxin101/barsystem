"""Tests for the FLASK_SECRET_KEY / legacy SECRET_KEY resolution in config.py."""

import importlib

import config


def _reload():
    importlib.reload(config)


def test_flask_secret_key_used_when_set(monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "new-style-value")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    _reload()
    assert config.BaseConfig.SECRET_KEY == "new-style-value"


def test_legacy_secret_key_used_as_fallback(monkeypatch):
    monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)
    monkeypatch.setenv("SECRET_KEY", "legacy-style-value")
    _reload()
    assert config.BaseConfig.SECRET_KEY == "legacy-style-value"


def test_flask_secret_key_wins_over_legacy(monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "new-style-value")
    monkeypatch.setenv("SECRET_KEY", "legacy-style-value")
    _reload()
    assert config.BaseConfig.SECRET_KEY == "new-style-value"


def test_falls_back_to_dev_default_when_neither_set(monkeypatch):
    monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    _reload()
    assert config.BaseConfig.SECRET_KEY == "dev-secret-key-change-in-prod"
