"""Tests for the `flask backup` CLI command (see app.py's backup_cmd)."""

from pathlib import Path
from unittest.mock import patch


def _run(app, env=None):
    runner = app.test_cli_runner()
    return runner.invoke(args=["backup"], env=env)


def test_backup_reports_written_path(app):
    fake_path = Path("/tmp/barsystem_20260101_000000.sql.gz")
    with patch("utils.backup.create_backup", return_value=fake_path) as mock_create:
        result = _run(app)

    assert result.exit_code == 0
    assert str(fake_path) in result.output
    mock_create.assert_called_once()


def test_backup_uses_backup_dir_env_var(app, monkeypatch):
    monkeypatch.setenv("BACKUP_DIR", "/custom/backups")
    with patch("utils.backup.create_backup", return_value=Path("x.sql.gz")) as mock_create:
        _run(app)

    args, _ = mock_create.call_args
    assert args[1] == "/custom/backups"


def test_backup_failure_exits_nonzero(app):
    with patch("utils.backup.create_backup", side_effect=RuntimeError("pg_dump failed")):
        result = _run(app)

    assert result.exit_code != 0
    assert "pg_dump failed" in result.output
