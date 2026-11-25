"""Fixtures shared by every test under `.ci/rediacc_ci/tests`."""

from __future__ import annotations

import os
import shutil
import tempfile
from typing import TYPE_CHECKING

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import seams
from rediacc_ci.tests import sqlite_tracking

if TYPE_CHECKING:
    from collections.abc import Iterator


def pytest_configure(config) -> None:
    """Keep every test's scratch space under the system temp base, which is the only place `quality.seams` honours a `*_ROOT` override.

    On a host whose TMPDIR points outside `/tmp` (the native host sets `~/.cache/tmp`), `tmp_path` and `tempfile.mkdtemp` landed outside it, every seam was ignored, and the gates under test scanned and wrote the real repository: on 2026-11-25 `test_gate_plan_folders.py` ran `plan_folders --sweep --write` against the tree and `git rm`-ed 34 plan files. A private 0700 directory under the system temp base replaces TMPDIR for the run (subprocesses inherit it) and becomes pytest's basetemp.
    """
    # Ubuntu's default umask 002 makes every fixture directory group-writable, which `seams` refuses as a scratch root just the same, so the run creates files with group and other write cleared.
    current = os.umask(0o022)
    os.umask(current | 0o022)
    base = seams.system_temp_base()
    if base is None or seams.inside_temp(tempfile.gettempdir()):
        return
    scratch = tempfile.mkdtemp(prefix="rediacc-pytest-", dir=base)
    os.environ["TMPDIR"] = scratch
    tempfile.tempdir = None
    if config.option.basetemp is None:
        config.option.basetemp = os.path.join(scratch, "basetemp")


@pytest.fixture(autouse=True)
def _close_sqlite_connections() -> Iterator[None]:
    """Close every sqlite connection the test opened through `sqlite3.connect` when it ends (why and limits: `sqlite_tracking`'s docstring)."""
    with sqlite_tracking.closing_every_connection():
        yield


@pytest.fixture(autouse=True)
def _isolated_lock_dir(tmp_path_factory, monkeypatch) -> None:
    """Point `XDG_RUNTIME_DIR` at a per-test directory, so no test takes or waits on the operator's real bench or fleet lock (`rediacc_ci.core.resource_lock.lock_path`). A test that needs its own directory sets the variable again."""
    run_dir = tmp_path_factory.mktemp("xdg-run")
    run_dir.chmod(0o700)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(run_dir))


@pytest.fixture
def regions_in_tmp(tmp_path) -> None:
    """The repository's regions.json beside a test's scratch root. `deploy_bench.target` reads every region's names from `<root>/regions.json`, the default region included, so a test that builds a scratch root writes it there; a test that already wrote its own keeps it."""
    dest = tmp_path / "regions.json"
    if not dest.exists():
        shutil.copy(paths.repo_root() / "regions.json", dest)
