"""Tests for utils/version.py — the value reported by /healthz."""

import os
from unittest.mock import patch

from utils.version import get_version


def test_app_version_env_wins():
    with patch.dict(os.environ, {"APP_VERSION": "abc1234"}):
        assert get_version() == "abc1234"


def test_falls_back_to_git_head_without_env():
    os.environ.pop("APP_VERSION", None)
    version = get_version()
    assert isinstance(version, str)
    assert version != ""
