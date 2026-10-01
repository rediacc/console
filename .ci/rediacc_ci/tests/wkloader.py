"""The files a fixture root needs so a script that loads the well-known registry can run in it.

Bash scripts read the WK_* facts through `well_known_load` (scripts/lib/well-known.sh), which goes through `env_file_load` (scripts/lib/env-file.sh), which runs `python3 -m rediacc_ci.core.env`. `scripts/lib/common.sh` also sources `.ci/config/well-known.generated.sh` (the bash projection of the registry), so that file rides in the chain. A fixture that copies a script and `.ci/config/well-known.env` and nothing else dies at the `source` line, so each fixture calls `copy_loader` beside the registry copy. The list is the whole dependency chain and nothing more: the fixture must not become a second copy of the repository.
"""

from __future__ import annotations

import os
import pathlib
import shutil

from rediacc_ci import paths

LOADER_FILES = (
    ".ci/config/well-known.generated.sh",
    "scripts/lib/well-known.sh",
    "scripts/lib/env-file.sh",
    ".ci/rediacc_ci/__init__.py",
    ".ci/rediacc_ci/core/__init__.py",
    ".ci/rediacc_ci/core/env.py",
)


def copy_loader(root: pathlib.Path) -> None:
    """Copy the loader chain from the real tree into the fixture root `root`."""
    repo = paths.repo_root()
    for rel in LOADER_FILES:
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo / rel, dest)


def docker_less_path(farm: pathlib.Path) -> str:
    """A PATH with every tool of the host's `PATH` and no `docker`, for the case that claims docker is missing entirely.

    Prepending a fixture bin dir that merely lacks `docker` leaves the host's real one reachable behind it, so the case ran whatever this host's docker printed and read 127 only on a host that had none. Every executable the host exposes is linked into `farm` except `docker` (and its `docker-*` plugins), so the subject still finds bash, env, grep and python3, and nothing else changes."""
    farm.mkdir(parents=True, exist_ok=True)
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        base = pathlib.Path(directory or ".")
        if not base.is_dir():
            continue
        for entry in base.iterdir():
            name = entry.name
            if name == "docker" or name.startswith("docker-"):
                continue
            link = farm / name
            if not link.exists() and not link.is_symlink() and os.access(entry, os.X_OK):
                link.symlink_to(entry)
    return str(farm)
