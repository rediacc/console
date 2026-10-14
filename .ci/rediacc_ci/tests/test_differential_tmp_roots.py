"""`differential.pytest_tmp_roots` folds per-test temp directories under an explicit `--basetemp` as well as pytest's default `pytest-<N>` layout (worklist #ad157280)."""

from __future__ import annotations

import pytest

from rediacc_ci.tests import differential as diff

# A basetemp outside every real temp root, so the default `pytest-<N>` pattern can never match it by accident.
BT = "/srv/check-bt"


@pytest.fixture(autouse=True)
def _own_basetemp(monkeypatch):
    """Each case sets its own basetemp on a private list, so the session's real setting (from the root conftest) is back in place for the next test."""
    monkeypatch.setattr(diff, "_BASETEMP_RES", [])


def test_the_default_layout_is_folded_without_a_basetemp():
    value = "--out=/tmp/pytest-of-u/pytest-7/test_x0/out.json"
    assert diff.pytest_tmp_roots(value) == ("/tmp/pytest-of-u/pytest-7/test_x0",)


def test_a_tmp_path_under_an_explicit_basetemp_is_folded():
    diff.set_basetemp(BT)
    value = f"--out={BT}/test_x0/out.json env={BT}/popen-gw3/test_y0"
    assert diff.pytest_tmp_roots(value) == (f"{BT}/test_x0", f"{BT}/popen-gw3/test_y0")


def test_control_without_set_basetemp_the_same_path_is_not_folded():
    assert diff.pytest_tmp_roots(f"{BT}/test_x0/out.json") == ()
