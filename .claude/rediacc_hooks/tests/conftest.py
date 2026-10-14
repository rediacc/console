"""Fixtures shared by the hook suite, defined here so a test module receives them by parameter name without importing them.

A fixture imported into a module and then taken as a parameter of the same name is a redefinition as far as the linter can tell; pytest's own lookup (module, then this file) makes the import unnecessary."""

from __future__ import annotations

import pytest

from rediacc_hooks.tests.test_wl_report_inbox import Scratch
from rediacc_hooks.tests.wlfix import Fixture


@pytest.fixture
def wl(tmp_path):
    """One sandbox per test, torn down with `tmp_path`."""
    fixture = Fixture(tmp_path / "hookfix")
    fixture.setup()
    return fixture


@pytest.fixture
def sc(tmp_path):
    """The base for every scratch universe, captured ONCE.

    Deriving it from TMPDIR at call time instead would nest each case inside the previous case's TMPDIR, and the slugified worklist name (which embeds the whole absolute path) then grows until it trips ENAMETOOLONG a dozen cases in, which is exactly what the first run of the bash suite did.
    """
    scratch = Scratch(tmp_path / "case")
    yield scratch
    scratch.close_handles()
