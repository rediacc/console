"""Keeps every test's scratch space under the system temp base, which is the only place `quality.seams` honours a `*_ROOT` override.

On a host whose TMPDIR points outside `/tmp` (the native host sets `~/.cache/tmp`), `tmp_path` and `tempfile.mkdtemp` landed outside it, every seam was ignored, and the gates under test scanned and wrote the real repository: on 2026-11-25 `test_gate_plan_folders.py` ran `plan_folders --sweep --write` against the tree and `git rm`-ed 34 plan files.

`install` runs from the ROOT `conftest.py`'s `pytest_configure`, because a `pytest_configure` in a conftest below the rootdir only runs when that directory is among the session's arguments. It changes the process umask and TMPDIR for the run and puts both back through `config.add_cleanup`.
"""

from __future__ import annotations

import os
import tempfile
from typing import TYPE_CHECKING

from rediacc_ci.quality import seams

if TYPE_CHECKING:
    import pytest

# Ubuntu's default umask 002 makes every fixture directory group-writable, which `seams` refuses as a scratch root just the same.
CLEARED_UMASK_BITS = 0o022


def install(config: pytest.Config) -> None:
    """Clear group and other write from the umask and, when the temp directory is outside the system temp base, make a private 0700 directory under that base the run's TMPDIR (subprocesses inherit it) and pytest's basetemp. Both changes are undone when the session's config is torn down; a TMPDIR already inside the base is left as it is."""
    previous_umask = os.umask(0o022)
    os.umask(previous_umask | CLEARED_UMASK_BITS)
    config.add_cleanup(lambda: os.umask(previous_umask))
    base = seams.system_temp_base()
    if base is None or seams.inside_temp(tempfile.gettempdir()):
        return
    scratch = tempfile.mkdtemp(prefix="rediacc-pytest-", dir=base)
    saved = os.environ.copy()
    os.environ["TMPDIR"] = scratch
    tempfile.tempdir = None
    if config.option.basetemp is None:
        config.option.basetemp = os.path.join(scratch, "basetemp")
    config.add_cleanup(lambda: _restore_tmpdir(saved))


def _restore_tmpdir(saved: dict[str, str]) -> None:
    if "TMPDIR" in saved:
        os.environ["TMPDIR"] = saved["TMPDIR"]
    else:
        os.environ.pop("TMPDIR", None)
    tempfile.tempdir = None
