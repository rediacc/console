"""`rediacc_ci.ops.probe_receipt_stability`, the port of `probe-receipt-stability.sh`.

Every case runs against a throwaway git repo with a stand-in for the gate run, so nothing here touches the checkout or its receipt. The stand-in prints what the real run prints, waits for the plant, and writes the receipt the way the runner does; each Rule T case changes one of those facts.
"""

from __future__ import annotations

import io
import json
import pathlib
import subprocess
import sys

import pytest

from rediacc_ci.ops import probe_receipt_stability as probe


def _repo(tmp_path: pathlib.Path) -> pathlib.Path:
    root = tmp_path / "repo"
    (root / ".ci" / "cache").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


# A stand-in run: reports one selected gate, waits until the plant exists, then warns and records the receipt. `STABLE` is the value written, `WARN` whether the warning prints, `SELECT` whether a gate is reported.
STAND_IN = """
import glob, json, sys, time
select, warn, stable = sys.argv[1] == "1", sys.argv[2] == "1", sys.argv[3]
if select:
    print("1 gate selected", flush=True)
deadline = time.time() + 20
while not glob.glob("STABILITY-PROBE-*") and time.time() < deadline:
    time.sleep(0.05)
if warn:
    print("working tree CHANGED during the run", flush=True)
if stable != "missing":
    with open(".ci/cache/prepush-receipt.json", "w", encoding="utf-8") as fh:
        json.dump({"stable": json.loads(stable)}, fh)
"""


def _run(root, *, select="1", warn="1", stable="false"):
    out = io.StringIO()
    command = (sys.executable, "-c", STAND_IN, select, warn, stable)
    rc = probe.run_probe(root, command=command, settle=0.2, out=out)
    return rc, out.getvalue()


def _leftovers(root: pathlib.Path) -> list[str]:
    return [p.name for p in root.iterdir() if p.name.startswith(probe.PLANT_PREFIX)]


def test_a_moving_tree_that_records_stable_false_passes(tmp_path):
    root = _repo(tmp_path)
    rc, out = _run(root)
    assert rc == 0, out
    assert "stable : False" in out
    assert _leftovers(root) == []


def test_delta_exit_code_is_the_verdict_for_a_stable_true_receipt(tmp_path):
    """The bash exited 0 whatever the receipt said; a field that can only say true must fail the control."""
    rc, out = _run(_repo(tmp_path), stable="true")
    assert rc == 1
    assert "stable=True" in out


def test_delta_a_vacuous_run_with_no_gate_or_warning_fails(tmp_path):
    rc, out = _run(_repo(tmp_path), select="0", warn="0")
    assert rc == 1
    assert "selected no gate" in out
    assert "no 'working tree CHANGED' warning" in out


def test_delta_an_unreadable_receipt_is_reported_not_a_traceback(tmp_path):
    root = _repo(tmp_path)
    rc, out = _run(root, stable="missing")
    assert rc == 1
    assert "FIELD UNREADABLE" in out
    assert "Traceback" not in out


def test_delta_the_plant_is_removed_when_the_probe_dies_midway(tmp_path, monkeypatch):
    """An interrupted probe must still leave the checkout clean; the bash removed the plant only after a successful `wait`."""
    root = _repo(tmp_path)

    def boom(_root):
        raise RuntimeError("git went away")

    monkeypatch.setattr(probe, "git_status", boom)
    command = (sys.executable, "-c", STAND_IN, "1", "1", "false")
    with pytest.raises(RuntimeError):
        probe.run_probe(root, command=command, settle=0.2, out=io.StringIO())
    assert _leftovers(root) == []


def test_delta_an_unwritable_plant_is_a_reported_failure_not_a_traceback(tmp_path, monkeypatch):
    """Review 09ee66c6.2: when the plant cannot be written the run is killed and the probe says so, rather than raising OSError out of `run_probe`."""
    root = _repo(tmp_path)
    monkeypatch.setattr(probe, "plant_name", lambda _pid: "no-such-dir/STABILITY-PROBE-x")
    out = io.StringIO()
    command = (sys.executable, "-c", STAND_IN, "1", "1", "false")
    rc = probe.run_probe(root, command=command, settle=0.2, out=out)
    assert rc == 1
    assert "FAIL: the probe could not run" in out.getvalue()
    assert _leftovers(root) == []


def test_delta_the_capture_file_is_removed(tmp_path, monkeypatch):
    seen = []
    real = probe.tempfile.mkstemp

    def spy(*args, **kwargs):
        fd, name = real(*args, **kwargs)
        seen.append(name)
        return fd, name

    monkeypatch.setattr(probe.tempfile, "mkstemp", spy)
    _run(_repo(tmp_path))
    assert seen
    assert not any(pathlib.Path(name).exists() for name in seen)


def test_read_stable_distinguishes_absent_from_unreadable(tmp_path):
    receipt = tmp_path / "r.json"
    assert probe.read_stable(receipt) is None
    receipt.write_text("[]", encoding="utf-8")
    assert probe.read_stable(receipt) is None
    receipt.write_text(json.dumps({"other": 1}), encoding="utf-8")
    assert probe.read_stable(receipt) == probe.ABSENT
    receipt.write_text(json.dumps({"stable": False}), encoding="utf-8")
    assert probe.read_stable(receipt) is False


def test_the_plant_name_has_no_ignored_suffix():
    """`.gitignore` ignores `*.tmp`; a plant with that suffix never reaches `git status` and the control would measure nothing."""
    assert not probe.plant_name(1234).endswith(".tmp")
    assert probe.plant_name(1234).startswith(probe.PLANT_PREFIX)
