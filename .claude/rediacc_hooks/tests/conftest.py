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


@pytest.fixture(autouse=True)
def _no_ambient_git_config(tmp_path_factory, monkeypatch):
    """Git reads no global or system config in the hook suite.

    A CI job whose App token writes a global `url.*.insteadOf` turns the guards' rewrite doubt on for every case: PR 605 run 43317534585 failed `test_push_elsewhere`'s control row on it, and the guard control suites run by `test_hooks_delegates` fail the same way under that config. A test that needs a git setting writes it into its own repository."""
    empty = tmp_path_factory.getbasetemp() / "empty-gitconfig"
    if not empty.exists():
        empty.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.delenv("GIT_CONFIG_COUNT", raising=False)
