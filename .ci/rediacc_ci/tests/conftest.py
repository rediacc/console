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


@pytest.fixture
def regions_in_tmp(tmp_path) -> None:
    """The repository's regions.json beside a test's scratch root. `deploy_bench.target` reads every region's names from `<root>/regions.json`, the default region included, so a test that builds a scratch root writes it there; a test that already wrote its own keeps it."""
    dest = tmp_path / "regions.json"
    if not dest.exists():
        shutil.copy(paths.repo_root() / "regions.json", dest)
