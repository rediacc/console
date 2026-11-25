"""Fixtures shared by every test under `.ci/rediacc_ci/tests`."""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest

from rediacc_ci import paths
from rediacc_ci.tests import sqlite_tracking

if TYPE_CHECKING:
    from collections.abc import Iterator


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
