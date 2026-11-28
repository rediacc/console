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
from rediacc_ci.tests.gates import harness

SUITE = """import time

import pytest


@pytest.fixture(scope="module")
def world():
    time.sleep(0.6)
    yield 1
    time.sleep(0.5)


def test_first_takes_the_module_fixture(world):
    time.sleep(0.05)


def test_second_shares_it(world):
    pass


@pytest.fixture
def slow_exit():
    yield
    time.sleep(0.3)


def test_own_teardown(slow_exit):
    pass


class TestSlow:
    def test_slow_call(self):
        # Burns 0.5 s of CPU, measured on the CPU clock so a loaded machine cannot shrink it (the ratchet judges CPU time, K4).
        end = time.process_time() + 0.5
        while time.process_time() < end:
            pass


def test_sleepy_call():
    # Slow on the wall clock only: under K4 this is no longer a slow test.
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
    assert slow["call_cpu"] >= 0.45, slow
    sleepy = tests["t.test_heavy::test_sleepy_call"]
    assert sleepy["call"] >= 0.45, sleepy
    assert sleepy["call_cpu"] < 0.2, sleepy
    assert first["shared_setup_cpu"] < first["shared_setup"], first
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
    # K4: a test slow only on the wall clock (it sleeps) is judged on its CPU and passes.
    assert "test_sleepy_call" not in out.err, out.err
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
        harness.nested_pytest_argv(
            tmp_path.parent / (tmp_path.name + "-basetemp"),
            "-q",
            "-p",
            "no:cacheprovider",
            "-p",
            plugin.__name__,
        ),
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not list(tmp_path.rglob("*.json"))


@pytest.mark.parametrize("workers", ["0", "2"])
def test_teardown_is_split_into_the_tests_own_and_the_shared_fixtures(tmp_path, workers):
    """Finding 7d7ecd77.1: a function fixture's 0.3 s teardown stays the test's; the module fixture's 0.5 s lands on the module's last test and is shared."""
    junit = _run_suite(tmp_path, workers)
    tests = json.loads(ratchet.phases_path(junit).read_text(encoding="utf-8"))["tests"]
    own = tests["t.test_heavy::test_own_teardown"]
    assert own["teardown"] >= 0.3, own
    shared_total = sum(t["shared_teardown"] for t in tests.values())
    assert shared_total >= 0.45, tests
    assert own["teardown"] - own["shared_teardown"] >= 0.25, own
    # The split is checked on the wall fields; the fixtures sleep, so their CPU is near zero and K4 judges CPU when present.
    split = ratchet.own_seconds({k: v for k, v in own.items() if not k.endswith("_cpu")})
    assert split is not None, own
    _own, _shared = split
    assert _own >= 0.3
