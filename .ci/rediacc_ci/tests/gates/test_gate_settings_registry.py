"""Drives `.ci/scripts/quality/check_settings_registry.py` (check:ci-settings-registry) as a program against fixture trees and the real one.

WHY BOTH THIS AND THE GATE'S `--selftest`. The selftest proves the readers and the rules on fixtures built inside the gate's own process. What it cannot prove is the program: the exit code each verdict maps to, that findings land on stderr and the shape line on stdout, that `--root` re-points every path, and that the real tree reads green with a non-trivial count. A gate whose only controls are internal is thinner than this repo's standard.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys

from rediacc_ci import paths

GATE = paths.from_root(".ci", "scripts", "quality", "check_settings_registry.py")


def load_gate():
    paths.on_sys_path(paths.quality_dir())
    spec = importlib.util.spec_from_file_location("check_settings_registry", GATE)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GATE), *args], capture_output=True, text=True, timeout=120, check=False
    )


def tree(tmp_path, entries, conf=None, py=None):
    gate = load_gate()
    gate.build_fixture(tmp_path, entries, conf, gate.FIXTURE_PY if py is None else py)
    return tmp_path


def test_the_real_tree_is_green_with_a_non_trivial_count():
    result = run()
    assert result.returncode == 0, result.stderr
    line = result.stdout.strip().splitlines()[-1]
    assert "every copy agrees and sits in range" in line
    counts = [int(w) for w in line.replace(",", " ").split() if w.isdigit()]
    # settings, copies, files: a registry that collapsed to nothing must not read green.
    assert counts[0] >= 10, line
    assert counts[1] >= counts[0], line
    assert counts[2] >= 1, line


def test_selftest_passes():
    result = run("--selftest")
    assert result.returncode == 0, result.stderr
    assert "selftest ok" in result.stdout


def test_a_clean_fixture_passes(tmp_path):
    gate = load_gate()
    result = run("--root", str(tree(tmp_path, [gate.fixture_entry()])))
    assert result.returncode == 0, result.stderr
    assert "1 settings, 3 copies across 2 files" in result.stdout


def test_a_planted_disagreement_is_exit_1_and_names_the_copies_and_the_fix(tmp_path):
    gate = load_gate()
    conf = json.loads(json.dumps(gate.FIXTURE_JSON))
    conf["limits"]["b"] = 2500
    result = run("--root", str(tree(tmp_path, [gate.fixture_entry()], conf)))
    assert result.returncode == 1
    assert "copies disagree" in result.stderr
    assert "conf.json#/limits/b=2500" in result.stderr
    assert "npm run settings -- set" in result.stderr
    assert result.stdout == ""


def test_a_python_copy_out_of_agreement_is_exit_1(tmp_path):
    gate = load_gate()
    result = run(
        "--root",
        str(tree(tmp_path, [gate.fixture_entry()], py=gate.FIXTURE_PY.replace("2_000", "2_001"))),
    )
    assert result.returncode == 1
    assert "mod.py#CEILINGS['a']=2001" in result.stderr


def test_a_python_copy_that_is_not_utf8_is_no_verdict(tmp_path):
    """Review 06823e7c.1: an undecodable copy raised UnicodeDecodeError out of the gate (a traceback, exit 1)."""
    gate = load_gate()
    root = tree(tmp_path, [gate.fixture_entry()])
    (root / "mod.py").write_bytes(b"CEILINGS = {'a': 2_000}  # \xff\xfe\n")
    result = run("--root", str(root))
    assert result.returncode == 2, result.stderr
    assert "not valid UTF-8" in result.stderr
    assert "Traceback" not in result.stderr


def test_a_dangling_path_is_exit_1(tmp_path):
    gate = load_gate()
    entry = gate.fixture_entry(copies=[{"file": "conf.json", "json_path": "/limits/missing"}])
    result = run("--root", str(tree(tmp_path, [entry])))
    assert result.returncode == 1
    assert "does not resolve" in result.stderr


def test_an_out_of_range_value_is_exit_1(tmp_path):
    gate = load_gate()
    result = run("--root", str(tree(tmp_path, [gate.fixture_entry(max=1500)])))
    assert result.returncode == 1
    assert "outside the registered range [1000, 1500]" in result.stderr


def test_a_missing_registered_file_is_exit_1(tmp_path):
    gate = load_gate()
    entry = gate.fixture_entry(copies=[{"file": "nowhere.json", "json_path": "/a"}])
    result = run("--root", str(tree(tmp_path, [entry])))
    assert result.returncode == 1
    assert "nowhere.json#/a: file missing" in result.stderr


def test_an_empty_registry_is_no_verdict_never_a_pass(tmp_path):
    result = run("--root", str(tree(tmp_path, [])))
    assert result.returncode == 2
    assert "NO VERDICT" in result.stderr
    assert "zero settings" in result.stderr


def test_a_missing_registry_is_no_verdict(tmp_path):
    result = run("--root", str(tmp_path))
    assert result.returncode == 2
    assert "cannot be read" in result.stderr
