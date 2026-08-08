"""Tests for utils/backup.py — the `flask backup` implementation.

pg_dump isn't installed in the test environment, so these tests put a
fake pg_dump shell script on PATH instead of shelling out to a real one.
"""

import gzip
import os
import stat

import pytest

from utils.backup import COMPLETENESS_MARKER, create_backup, dump_is_complete

DB_URI = "postgresql://ergo:bibamus@db:5432/barliste"


def _install_fake_pg_dump(tmp_path, monkeypatch, script_body):
    fake_bin = tmp_path / "fakebin"
    fake_bin.mkdir()
    script = fake_bin / "pg_dump"
    script.write_text(f"#!/bin/sh\n{script_body}\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ.get('PATH', '')}")


def test_dump_is_complete_true_when_marker_present(tmp_path):
    path = tmp_path / "ok.sql.gz"
    with gzip.open(path, "wb") as f:
        f.write(b"-- some rows\n" + COMPLETENESS_MARKER + b"\n")
    assert dump_is_complete(path) is True


def test_dump_is_complete_false_when_truncated(tmp_path):
    path = tmp_path / "truncated.sql.gz"
    with gzip.open(path, "wb") as f:
        f.write(b"-- some rows, cut off mid-write")
    assert dump_is_complete(path) is False


def test_create_backup_rejects_non_postgres_uri(tmp_path):
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        create_backup("sqlite:///:memory:", tmp_path)


def test_create_backup_success(tmp_path, monkeypatch):
    _install_fake_pg_dump(
        tmp_path,
        monkeypatch,
        f'echo "-- dump\\n{COMPLETENESS_MARKER.decode()}"',
    )
    outfile = create_backup(DB_URI, tmp_path / "out")
    assert outfile.exists()
    assert dump_is_complete(outfile)


def test_create_backup_missing_pg_dump(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    (tmp_path / "empty").mkdir()
    with pytest.raises(RuntimeError, match="pg_dump not found"):
        create_backup(DB_URI, tmp_path / "out")


def test_create_backup_nonzero_exit_discards_file(tmp_path, monkeypatch):
    _install_fake_pg_dump(
        tmp_path, monkeypatch, 'echo "connection refused" >&2\nexit 1'
    )
    out_dir = tmp_path / "out"
    with pytest.raises(RuntimeError, match="connection refused"):
        create_backup(DB_URI, out_dir)
    assert list(out_dir.glob("*.sql.gz")) == []


def test_create_backup_incomplete_dump_discards_file(tmp_path, monkeypatch):
    _install_fake_pg_dump(tmp_path, monkeypatch, 'echo "-- partial dump, no marker"')
    out_dir = tmp_path / "out"
    with pytest.raises(RuntimeError, match="completeness marker"):
        create_backup(DB_URI, out_dir)
    assert list(out_dir.glob("*.sql.gz")) == []
