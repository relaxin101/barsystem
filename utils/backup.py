"""Consistent database backup via pg_dump, exposed as `flask backup`.

The app owns "give me a consistent dump" so host-side cron shrinks to one
line calling the container command; only the append-only NAS mirror stays
host-side (the app should not hold NAS credentials).
"""

import gzip
import os
import subprocess
from datetime import datetime
from pathlib import Path

from sqlalchemy.engine import make_url

COMPLETENESS_MARKER = b"PostgreSQL database dump complete"


def dump_is_complete(path):
    """Check that the gzip'd dump ends with pg_dump's completion marker."""
    tail = b""
    with gzip.open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            tail = (tail + chunk)[-4096:]
    return COMPLETENESS_MARKER in tail


def create_backup(database_uri, output_dir):
    """Write a gzip'd pg_dump to output_dir and verify it; return the file path.

    Raises RuntimeError on any failure; incomplete dumps are deleted, never
    left lying around as a plausible-looking backup.
    """
    url = make_url(database_uri)
    if not url.drivername.startswith("postgresql"):
        raise RuntimeError(
            f"backup requires PostgreSQL, got '{url.drivername}'"
        )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    outfile = output_dir / f"barsystem_{timestamp}.sql.gz"

    cmd = [
        "pg_dump",
        "--no-password",
        "-h", url.host or "localhost",
        "-p", str(url.port or 5432),
        "-U", url.username or "postgres",
        "-d", url.database or "postgres",
    ]
    env = dict(os.environ, PGPASSWORD=url.password or "")

    try:
        with gzip.open(outfile, "wb") as gz:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env
            )
            assert proc.stdout is not None and proc.stderr is not None
            stdout, stderr_pipe = proc.stdout, proc.stderr
            for chunk in iter(lambda: stdout.read(1 << 16), b""):
                gz.write(chunk)
            stderr = stderr_pipe.read()
            proc.wait()
    except FileNotFoundError:
        outfile.unlink(missing_ok=True)
        raise RuntimeError(
            "pg_dump not found — is postgresql-client installed in the image?"
        )

    if proc.returncode != 0:
        outfile.unlink(missing_ok=True)
        raise RuntimeError(
            f"pg_dump failed (exit {proc.returncode}): "
            f"{stderr.decode(errors='replace').strip()}"
        )
    if not dump_is_complete(outfile):
        outfile.unlink(missing_ok=True)
        raise RuntimeError("dump is missing the completeness marker — discarded")
    return outfile
