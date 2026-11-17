"""`pytest_phase_timing`: a real pytest run, serial and under xdist, writes each test's phases with its shared-fixture setup apart, and the ratchet judges the test on its own time.

The scratch suite sleeps fractions of a second, and the ratchet runs with a threshold scaled to them, so the module-fixture case is the 16.9 s `test_githook_generated_artifacts` shape in miniature without any test here being slow.
"""

import json
import os
import pathlib
import subprocess
import sys

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import pytest_phase_timing as plugin
from rediacc_ci.quality import pytest_slow_ratchet as ratchet

SUITE = """import time

import pytest


@pytest.fixture(scope="module")
def world():
    time.sleep(0.6)
    return 1


def test_first_takes_the_module_fixture(world):
    time.sleep(0.05)


def test_second_shares_it(world):
    pass


class TestSlow:
    def test_slow_call(self):
        time.sleep(0.45)
"""
THRESHOLD = "0.4"


def _run_suite(tmp_path: pathlib.Path, workers: str) -> pathlib.Path:
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (tmp_path / "t").mkdir(exist_ok=True)
    (tmp_path / "t" / "test_heavy.py").write_text(SUITE, encoding="utf-8")
    junit = tmp_path / "junit.xml"
    env = dict(os.environ, PYTHONPATH=str(paths.repo_root() / ".ci"))
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "-n",
            workers,
            "--junitxml",
            str(junit),
            "-p",
            plugin.__name__,
            plugin.OPTION,
            str(ratchet.phases_path(junit)),
            "t",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return junit


@pytest.mark.parametrize("workers", ["0", "2"])
def test_a_real_run_writes_phases_keyed_like_its_junit(tmp_path, workers):
    junit = _run_suite(tmp_path, workers)
    tests = json.loads(ratchet.phases_path(junit).read_text(encoding="utf-8"))["tests"]
    first = tests["t.test_heavy::test_first_takes_the_module_fixture"]
    assert first["nodeid"] == "t/test_heavy.py::test_first_takes_the_module_fixture"
    assert first["shared_setup"] >= 0.5, first
    assert first["setup"] >= first["shared_setup"]
    assert first["call"] < 0.4, first
    slow = tests["t.test_heavy.TestSlow::test_slow_call"]
    assert slow["shared_setup"] == pytest.approx(0.0, abs=0.05)
    assert slow["call"] >= 0.45
    junit_nodes = set(ratchet.read_durations([junit]))
    assert junit_nodes == set(tests), "every junit case joins its phase entry on one key"


@pytest.mark.parametrize("workers", ["0", "2"])
def test_the_ratchet_passes_the_fixture_heavy_test_and_fails_the_slow_call(
    tmp_path, capsys, workers
):
    junit = _run_suite(tmp_path, workers)
    allow = tmp_path / "allow.json"
    allow.write_text('{"entries": []}', encoding="utf-8")
    rc = ratchet.main(["--junit", str(junit), "--allow", str(allow), "--threshold", THRESHOLD])
    out = capsys.readouterr()
    assert rc == 1
    assert "TestSlow::test_slow_call took" in out.err
    assert "test_first_takes_the_module_fixture" not in out.err, out.err
    assert "note:" not in out.out


def test_control_without_the_phase_file_the_fixture_heavy_test_fails(tmp_path, capsys):
    """The same run judged on junit time alone: the module fixture's 0.6 s puts the first test over the threshold."""
    junit = _run_suite(tmp_path, "0")
    ratchet.phases_path(junit).unlink()
    allow = tmp_path / "allow.json"
    allow.write_text('{"entries": []}', encoding="utf-8")
    rc = ratchet.main(["--junit", str(junit), "--allow", str(allow), "--threshold", THRESHOLD])
    out = capsys.readouterr()
    assert rc == 1
    assert "test_first_takes_the_module_fixture took" in out.err
    assert "no phase file at" in out.out


@pytest.mark.parametrize(
    ("nodeid", "node"),
    [
        ("a/b/test_x.py::test_y", "a.b.test_x::test_y"),
        ("a/test_x.py::TestC::test_y[p/q r]", "a.test_x.TestC::test_y[p/q r]"),
        (".ci/t/test_x.py::test_y@grp", ".ci.t.test_x::test_y"),
    ],
)
def test_the_junit_node_matches_pytests_own_mangling(nodeid, node):
    assert plugin.junit_node(nodeid) == node


def test_without_the_option_the_plugin_writes_nothing(tmp_path):
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (tmp_path / "test_one.py").write_text("def test_one():\n    pass\n", encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=str(paths.repo_root() / ".ci"))
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", plugin.__name__],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not list(tmp_path.rglob("*.json"))
