"""The control for `rediacc_ci.pytest_tmp`: a SIGKILLed pytest's basetemp is reclaimed by the next run.

pytest writes its pid into `<basetemp>/.lock` and deletes a numbered basetemp only once that lock is three days old, so a killed run's tree used to stay for three days; on 2026-09-24 ten of them held most of /tmp's inodes. Every case here drives a REAL child pytest, isolated from this run by giving it its own temp base, and loads the plugin with `-p` exactly as the repo-root conftest does.

The planted defect is the same scenario with the plugin left out of the second run: the killed tree must then survive, and the control must say so.
"""

from __future__ import annotations

import os
import pathlib
import signal
import subprocess
import sys
import time

import pytest

from rediacc_ci import runtmp

CI_DIR = pathlib.Path(__file__).resolve().parents[2]
PYTEST = [sys.executable, "-m", "pytest"]

# The child's test body. It uses `tmp_path` (which makes pytest create and LOCK its basetemp), records where that is, and then either dies without unwinding, waits for a release file, or just passes.
_CHILD_TEST = """
import os, pathlib, signal, time

MODE = {mode!r}
REPORT = {report!r}
RELEASE = {release!r}


def test_child(tmp_path):
    for i in range(20):
        (tmp_path / ("f%d" % i)).write_text("x")
    (tmp_path / MODE).write_text(MODE)
    pathlib.Path(REPORT).write_text(str(tmp_path))
    if MODE == "die":
        os.kill(os.getpid(), signal.SIGKILL)
    if MODE == "hold":
        deadline = time.monotonic() + 120
        while not os.path.exists(RELEASE) and time.monotonic() < deadline:
            time.sleep(0.05)
"""


def _child(
    work: pathlib.Path, name: str, mode: str, *, plugin: bool = True
) -> tuple[subprocess.Popen, pathlib.Path, pathlib.Path]:
    """Start one child pytest in its own scratch directory. Returns (process, report file, release file)."""
    case = work / name
    case.mkdir()
    report = case / "report"
    release = case / "release"
    (case / "test_child.py").write_text(
        _CHILD_TEST.format(mode=mode, report=str(report), release=str(release)), encoding="utf-8"
    )
    argv = [*PYTEST, "-q", "-p", "no:cacheprovider", "-p", "no:randomly"]
    if plugin:
        argv += ["-p", "rediacc_ci.pytest_tmp"]
    argv.append(str(case / "test_child.py"))
    env = {
        "PATH": os.defpath,
        "PYTHONPATH": str(CI_DIR),
        "PYTHONDONTWRITEBYTECODE": "1",
        "TMPDIR": str(work / "base"),
        "USER": "ctl",
        "LOGNAME": "ctl",
    }
    proc = subprocess.Popen(
        argv,
        cwd=str(case),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return proc, report, release


def _basetemp_of(report: pathlib.Path) -> pathlib.Path:
    """`tmp_path` is `<basetemp>/<test>0`; the basetemp is its parent."""
    return pathlib.Path(report.read_text(encoding="utf-8")).parent


def _wait_for(path: pathlib.Path, proc: subprocess.Popen) -> None:
    deadline = time.monotonic() + 120
    while not path.exists():
        assert proc.poll() is None or path.exists(), "the child exited before reporting: %r" % (
            proc.stdout.read() if proc.stdout else b""
        )
        assert time.monotonic() < deadline, "the child never reported its tmp_path"
        time.sleep(0.05)


def _finish(proc: subprocess.Popen) -> bytes:
    out, _ = proc.communicate(timeout=120)
    return out or b""


def _scenario(work: pathlib.Path, *, sweeping_run_has_plugin: bool) -> None:
    (work / "base").mkdir()
    # THE LIVE RUN STARTS FIRST. Every run that loads the plugin sweeps at start, so a live run started AFTER the kill would itself reclaim the killed tree, and pytest would then hand the freed number to the live run: the first cut of this control measured exactly that, one path for both.
    live, live_report, live_release = _child(work, "live", "hold")
    try:
        _wait_for(live_report, live)
        live_base = _basetemp_of(live_report)

        killed, killed_report, _ = _child(work, "killed", "die")
        _finish(killed)
        assert killed.returncode == -signal.SIGKILL, (
            "the killed child was supposed to die by SIGKILL"
        )
        killed_base = _basetemp_of(killed_report)
        assert killed_base != live_base
        assert (killed_base / ".lock").is_file(), (
            "a killed pytest left no lock, so this is not the case the sweep exists for"
        )

        sweeper, _, _ = _child(work, "sweeper", "pass", plugin=sweeping_run_has_plugin)
        out = _finish(sweeper)
        assert sweeper.returncode == 0, out.decode(errors="replace")[-2000:]

        assert (live_base / "test_child0" / "hold").is_file(), (
            "the sweep removed the basetemp of a run that is still ALIVE"
        )
        # BY CONTENT, NOT BY PATH. The sweeping run uses `tmp_path` too, and pytest numbers basetemps from the highest one left, so once the killed `pytest-N` is gone the sweeper is handed `pytest-N` again. The first cut asserted on the path and read the sweeper's own fresh tree as the killed one surviving.
        assert not (killed_base / "test_child0" / "die").exists(), (
            "the killed run's basetemp survived the next run: %s" % killed_base
        )
    finally:
        live_release.write_text("go")
        _finish(live)


def test_a_killed_runs_basetemp_is_reclaimed_by_the_next_run(tmp_path: pathlib.Path) -> None:
    _scenario(tmp_path, sweeping_run_has_plugin=True)


def test_planted_defect_without_the_plugin_the_killed_tree_survives(tmp_path: pathlib.Path) -> None:
    with pytest.raises(AssertionError, match="survived the next run"):
        _scenario(tmp_path, sweeping_run_has_plugin=False)


# --------------------------------------------------------------------------- the sweep itself, both directions


def _basetemp(root: pathlib.Path, n: int, lock: str | None) -> pathlib.Path:
    path = root / ("pytest-%d" % n)
    (path / "t0").mkdir(parents=True)
    (path / "t0" / "f").write_text("x")
    if lock is not None:
        (path / ".lock").write_text(lock)
    return path


def _dead_pid() -> int:
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def test_the_sweep_removes_only_a_dead_lock(tmp_path: pathlib.Path) -> None:
    dead = _basetemp(tmp_path, 1, str(_dead_pid()))
    keep = [
        _basetemp(tmp_path, 2, str(os.getpid())),  # a live run
        _basetemp(tmp_path, 3, None),  # exited cleanly: pytest's own retention owns it
        _basetemp(tmp_path, 4, "not-a-pid"),
    ]
    other = tmp_path / "not-a-basetemp"
    other.mkdir()
    (other / ".lock").write_text(str(_dead_pid()))
    assert runtmp.sweep_dead_basetemps(str(tmp_path)) == [str(dead)]
    for path in [*keep, other]:
        assert path.is_dir(), path


def test_a_read_only_tree_is_still_removed(tmp_path: pathlib.Path) -> None:
    dead = _basetemp(tmp_path, 7, str(_dead_pid()))
    (dead / "t0" / "f").chmod(0o000)
    (dead / "t0").chmod(0o500)
    assert runtmp.sweep_dead_basetemps(str(tmp_path)) == [str(dead)]
    assert not dead.exists()


def test_a_missing_root_is_an_empty_answer_not_an_error(tmp_path: pathlib.Path) -> None:
    assert runtmp.sweep_dead_basetemps(str(tmp_path / "absent")) == []
