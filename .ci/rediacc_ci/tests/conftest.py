"""Fixtures shared by every test under `.ci/rediacc_ci/tests`."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from rediacc_ci.tests import sqlite_tracking

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _close_sqlite_connections() -> Iterator[None]:
    """Close every sqlite connection the test opened when it ends (why: `sqlite_tracking`'s docstring)."""
    with sqlite_tracking.closing_every_connection():
        yield
