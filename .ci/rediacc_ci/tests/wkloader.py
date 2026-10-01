"""The files a fixture root needs so a script that loads the well-known registry can run in it.

Bash scripts read the WK_* facts through `well_known_load` (scripts/lib/well-known.sh), which goes through `env_file_load` (scripts/lib/env-file.sh), which runs `python3 -m rediacc_ci.core.env`. A fixture that copies a script and `.ci/config/well-known.env` and nothing else dies at the `source` line, so each fixture calls `copy_loader` beside the registry copy. The list is the whole dependency chain and nothing more: the fixture must not become a second copy of the repository.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

from rediacc_ci import paths

if TYPE_CHECKING:
    import pathlib

LOADER_FILES = (
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
