"""`differential.pytest_tmp_roots` folds per-test temp directories under an explicit `--basetemp` as well as pytest's default `pytest-<N>` layout (worklist #ad157280)."""

from __future__ import annotations

import os
import pathlib
import tempfile

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


def test_a_directory_that_pytest_did_not_number_is_not_folded():
    """Under a basetemp that holds real files (`--basetemp=.`), a path below a plain directory stays itself."""
    diff.set_basetemp(BT)
    assert diff.pytest_tmp_roots(f"{BT}/src/x.py {BT}/docs/readme.md") == ()


def test_a_symlinked_basetemp_is_folded_in_its_resolved_form_too():
    # Outside pytest's own `pytest-<N>` tree: under tmp_path the default pattern would fold tmp_path itself, and the case would no longer isolate the basetemp forms.
    with tempfile.TemporaryDirectory(prefix="bt-") as top:
        real = pathlib.Path(top) / "real-bt"
        real.mkdir()
        link = pathlib.Path(top) / "link-bt"
        os.symlink(real, link)
        _assert_both_forms(link)


def _assert_both_forms(link):
    diff.set_basetemp(link)
    spelled = f"{os.path.abspath(link)}/test_x0/out.json"
    resolved = f"{os.path.realpath(link)}/test_y0/out.json"
    assert diff.pytest_tmp_roots(spelled, resolved) == (
        f"{os.path.abspath(link)}/test_x0",
        f"{os.path.realpath(link)}/test_y0",
    )
