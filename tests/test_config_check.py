"""Tests for utils/config_check.py — fail-fast validation of prod secrets."""

import pytest

from utils.config_check import find_insecure_defaults, validate_production_config

SECURE_CONFIG = {
    "SECRET_KEY": "a-random-generated-value",
    "SQLALCHEMY_DATABASE_URI": "postgresql://ergo:s3cr3t-pw@db:5432/barliste",
    "ADMIN_PASSWORD": "a-real-password",
    "ADMIN_USERNAME": "chefin",
}


def test_secure_config_has_no_errors_or_warnings():
    errors, warnings = find_insecure_defaults(SECURE_CONFIG)
    assert errors == []
    assert warnings == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"SECRET_KEY": "dev-secret-key-change-in-prod"},
        {"SECRET_KEY": "supersecret"},
        {"SQLALCHEMY_DATABASE_URI": "postgresql://ergo:bibamus@db:5432/barliste"},
        {"SQLALCHEMY_DATABASE_URI": "postgresql://postgres:postgres@db:5432/barliste"},
        {"ADMIN_PASSWORD": "password"},
        {"ADMIN_PASSWORD": "password!"},
    ],
)
def test_shipped_defaults_are_flagged_as_errors(overrides):
    config = {**SECURE_CONFIG, **overrides}
    errors, _ = find_insecure_defaults(config)
    assert len(errors) == 1


def test_default_admin_username_is_only_a_warning():
    config = {**SECURE_CONFIG, "ADMIN_USERNAME": "admin"}
    errors, warnings = find_insecure_defaults(config)
    assert errors == []
    assert len(warnings) == 1


def test_validate_raises_on_insecure_config():
    config = {**SECURE_CONFIG, "ADMIN_PASSWORD": "password"}
    with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
        validate_production_config(config)


def test_validate_returns_warnings_on_secure_config():
    assert validate_production_config(SECURE_CONFIG) == []
