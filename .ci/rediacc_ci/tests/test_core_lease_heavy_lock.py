"""`core_lease.py heavy-lock`: the machine-wide lock that serializes the heavy gates (check:deps, check:ci-account-server, build:www) across trees (PLAN-ciquick-cpu L3).

WHAT IS AT RISK. A lock that only looks like one: two trees' heavy gates started together would both run at once and the machine would load past its cores again, a single heavy gate would wait on nothing, or the heavy gates of ONE run would wait on each other (build:www behind a 467 s account-server suite timed out on 2026-11-23).

Driven through the real CLI over a temp pool directory, so neither the real pool nor an enclosing grant leaks in. A tree is the working directory the gate starts in.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import time

from rediacc_ci import core_lease

MODULE = pathlib.Path(core_lease.__file__).resolve()
ANSWER_S = 20.0
HOLD_S = 1.0


def _env(pool: pathlib.Path) -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {core_lease.HELD_ENV, core_lease.ENV, "PYTEST_ADDOPTS"}
    }
    env[core_lease.DIR_ENV] = str(pool)
    env[core_lease.TOKENS_ENV] = "4"
    return env


def _tree(base: pathlib.Path, name: str) -> pathlib.Path:
    path = base / name
    path.mkdir(exist_ok=True)
    return path


def _heavy(
    base: pathlib.Path, tree: str, tag: str, *flags: str, hold: float = HOLD_S
) -> subprocess.Popen[str]:
    """A heavy gate started in checkout `tree` that records its start and end times in base/log and holds for `hold`."""
    script = (
        "import sys,time\n"
        "f=open(sys.argv[1],'a')\n"
        "f.write('start %s %%f\\n' %% time.time()); f.flush()\n"
        "time.sleep(%f)\n"
        "f.write('end %s %%f\\n' %% time.time()); f.flush()\n" % (tag, hold, tag)
    )
    return subprocess.Popen(
        [
            sys.executable,
            str(MODULE),
            "heavy-lock",
            *flags,
            "--",
            sys.executable,
            "-c",
            script,
            str(base / "log"),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_env(base / "pool"),
        cwd=_tree(base, tree),
    )


def _wait_started(base: pathlib.Path, tag: str) -> None:
    """Block until gate `tag` has logged its start, so a later gate really starts behind it (a fixed sleep lost that race on a slow interpreter start)."""
    deadline = time.monotonic() + ANSWER_S
    log = base / "log"
    while time.monotonic() < deadline:
        if log.is_file() and "start %s " % tag in log.read_text():
            return
        time.sleep(0.02)
    raise AssertionError("gate %r never started within %.0f s" % (tag, ANSWER_S))


def _events(base: pathlib.Path) -> list[tuple[str, str, float]]:
    rows = []
    for line in (base / "log").read_text().splitlines():
        kind, tag, stamp = line.split()
        rows.append((kind, tag, float(stamp)))
    return sorted(rows, key=lambda r: r[2])


def test_two_trees_heavy_gates_started_together_run_one_after_the_other(
    tmp_path: pathlib.Path,
) -> None:
    first = _heavy(tmp_path, "tree-a", "a")
    second = _heavy(tmp_path, "tree-b", "b")
    out = [p.communicate(timeout=ANSWER_S) for p in (first, second)]
    assert (first.returncode, second.returncode) == (0, 0), out
    order = [(kind, tag) for kind, tag, _ in _events(tmp_path)]
    assert (order[0][0], order[1][0]) == ("start", "end"), order
    assert order[0][1] == order[1][1], "the second gate started before the first ended: %s" % order
    waited = [stderr for _, stderr in out if "heavy lock" in stderr]
    assert len(waited) == 1, "exactly the later gate says it waits: %s" % out


def test_heavy_gates_of_one_tree_do_not_wait_on_each_other(tmp_path: pathlib.Path) -> None:
    first = _heavy(tmp_path, "tree-a", "a", hold=2.0)
    _wait_started(tmp_path, "a")
    second = _heavy(tmp_path, "tree-a", "b", hold=0.2)
    out = [p.communicate(timeout=ANSWER_S) for p in (first, second)]
    assert (first.returncode, second.returncode) == (0, 0), out
    order = [(kind, tag) for kind, tag, _ in _events(tmp_path)]
    assert order == [("start", "a"), ("start", "b"), ("end", "b"), ("end", "a")], order
    assert all("heavy lock" not in stderr for _, stderr in out), out


def test_a_single_heavy_gate_does_not_wait(tmp_path: pathlib.Path) -> None:
    proc = _heavy(tmp_path, "tree-a", "solo")
    _, stderr = proc.communicate(timeout=ANSWER_S)
    assert proc.returncode == 0, stderr
    assert "heavy lock" not in stderr, stderr
    assert [kind for kind, _, _ in _events(tmp_path)] == ["start", "end"]


def test_the_timeout_ends_a_wait_with_the_short_exit(tmp_path: pathlib.Path) -> None:
    holder = _heavy(tmp_path, "tree-a", "holder")
    _wait_started(tmp_path, "holder")
    blocked = _heavy(tmp_path, "tree-b", "late", "--timeout", "0.3")
    _, stderr = blocked.communicate(timeout=ANSWER_S)
    holder.communicate(timeout=ANSWER_S)
    assert blocked.returncode == core_lease.EXIT_SHORT, stderr
    assert {tag for _, tag, _ in _events(tmp_path)} == {"holder"}


def test_a_killed_holder_frees_the_lock(tmp_path: pathlib.Path) -> None:
    holder = subprocess.Popen(
        [sys.executable, str(MODULE), "heavy-lock", "--", "sleep", "60"],
        env=_env(tmp_path / "pool"),
        cwd=_tree(tmp_path, "tree-a"),
        stderr=subprocess.PIPE,
        text=True,
    )
    # CONTROL: the holder really holds the lock before the kill. A gate arriving behind it times out with the short exit; one that is admitted means the holder has not taken the lock yet, so ask again.
    deadline = time.monotonic() + ANSWER_S
    while True:
        probe = _heavy(tmp_path, "tree-b", "probe", "--timeout", "0.3", hold=0.0)
        probe.communicate(timeout=ANSWER_S)
        if probe.returncode == core_lease.EXIT_SHORT:
            break
        assert probe.returncode == 0, probe.returncode
        assert time.monotonic() < deadline, "the holder never held the lock"
    holder.kill()
    holder.communicate(timeout=ANSWER_S)
    after = _heavy(tmp_path, "tree-b", "after", "--timeout", "5")
    _, stderr = after.communicate(timeout=ANSWER_S)
    assert after.returncode == 0, stderr


def test_an_unwritable_owner_file_does_not_stop_a_gate_the_free_lock_admits(
    tmp_path: pathlib.Path,
) -> None:
    """Review aed5f186.1: the owner file is advisory; a failed write must not escape as a traceback."""
    # A directory where the owner file goes makes the atomic replace raise OSError.
    (tmp_path / core_lease.HEAVY_OWNER_NAME).mkdir()
    fd = core_lease.acquire_heavy_lock(tmp_path, root="/tree-a", timeout=1.0)
    assert fd is not None
    assert fd != core_lease.HEAVY_BYPASS
    os.close(fd)
