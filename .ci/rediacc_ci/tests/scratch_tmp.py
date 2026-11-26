"""Keeps every test's scratch space under the system temp base, which is the only place `quality.seams` honours a `*_ROOT` override.

On a host whose TMPDIR points outside `/tmp` (the native host sets `~/.cache/tmp`), `tmp_path` and `tempfile.mkdtemp` landed outside it, every seam was ignored, and the gates under test scanned and wrote the real repository: on 2026-11-25 `test_gate_plan_folders.py` ran `plan_folders --sweep --write` against the tree and `git rm`-ed 34 plan files.

`install` runs from the ROOT `conftest.py`'s `pytest_configure`, because a `pytest_configure` in a conftest below the rootdir only runs when that directory is among the session's arguments. It changes the process umask and TMPDIR for the run and puts both back and removes the scratch directory through `config.add_cleanup`; a run killed before its teardown leaves one, which the next run's `install` sweeps.
"""

from __future__ import annotations

import os
import tempfile
from typing import TYPE_CHECKING

from rediacc_ci import runtmp
from rediacc_ci.quality import seams

if TYPE_CHECKING:
    import pytest

# Ubuntu's default umask 002 makes every fixture directory group-writable, which `seams` refuses as a scratch root just the same.
CLEARED_UMASK_BITS = 0o022


def install(config: pytest.Config) -> None:
    """Clear group and other write from the umask, then make a private 0700 directory under the system temp base the run's TMPDIR (subprocesses inherit it) and pytest's basetemp. A TMPDIR already inside the base is replaced too: pytest's basetemp and every node child (`node-compile-cache`, `tsx-<uid>`) would otherwise leave entries in it that nothing removes. The umask and TMPDIR are put back and the scratch directory is removed when the session's config is torn down."""
    previous_umask = os.umask(0o022)
    os.umask(previous_umask | CLEARED_UMASK_BITS)
    config.add_cleanup(lambda: os.umask(previous_umask))
    base = seams.system_temp_base()
    if base is None:
        return
    # `run_dir` first removes the scratch of every earlier run whose process is dead (a SIGKILLed one never reached its teardown), then makes this run's 0700 directory.
    scratch = runtmp.run_dir("rediacc-pytest-", str(base))
    saved = os.environ.copy()
    saved_tempdir = tempfile.tempdir
    os.environ["TMPDIR"] = scratch
    tempfile.tempdir = None
    if config.option.basetemp is None:
        config.option.basetemp = os.path.join(scratch, "basetemp")
    config.add_cleanup(lambda: _restore_tmpdir(saved, saved_tempdir))
    config.add_cleanup(lambda: runtmp.remove_tree(scratch))


def _restore_tmpdir(saved: dict[str, str], saved_tempdir: str | None) -> None:
    if "TMPDIR" in saved:
        os.environ["TMPDIR"] = saved["TMPDIR"]
    else:
        os.environ.pop("TMPDIR", None)
    # Back to the cache install found, not to "recompute": a test that had primed tempfile.tempdir keeps what it primed.
    tempfile.tempdir = saved_tempdir
