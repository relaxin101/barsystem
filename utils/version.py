"""Resolve the running build's version for /healthz."""

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def get_version():
    """Return the git commit of the running build, or "unknown".

    APP_VERSION wins (baked into the Docker image via the GIT_SHA build arg,
    since .git is dockerignored). Outside the container, .git/HEAD is parsed
    directly so no git binary is required.
    """
    env_version = os.environ.get("APP_VERSION")
    if env_version:
        return env_version

    try:
        head = (_REPO_ROOT / ".git" / "HEAD").read_text().strip()
        if not head.startswith("ref:"):
            return head[:12]
        ref = head.split(None, 1)[1]
        ref_file = _REPO_ROOT / ".git" / ref
        if ref_file.exists():
            return ref_file.read_text().strip()[:12]
        packed = _REPO_ROOT / ".git" / "packed-refs"
        for line in packed.read_text().splitlines():
            if line.endswith(ref):
                return line.split(" ", 1)[0][:12]
    except OSError:
        pass
    return "unknown"
