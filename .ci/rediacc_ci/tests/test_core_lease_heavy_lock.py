"""`core_lease.py heavy-lock`: the machine-wide lock that serializes the heavy gates (check:deps, check:ci-account-server, build:www) across trees (PLAN-ciquick-cpu L3).

WHAT IS AT RISK. A lock that only looks like one: two heavy gates started together would both run at once and the machine would load past its cores again, or a single heavy gate would wait on nothing.

Driven through the real CLI over a temp pool directory, so neither the real pool nor an enclosing grant leaks in.
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


def _heavy(pool: pathlib.Path, log: pathlib.Path, tag: str, *flags: str) -> subprocess.Popen[str]:
    """A heavy gate that records its start and end times in `log` and holds for HOLD_S."""
    script = (
        "import sys,time\n"
        "f=open(sys.argv[1],'a')\n"
        "f.write('start %s %%f\\n' %% time.time()); f.flush()\n"
        "time.sleep(%f)\n"
        "f.write('end %s %%f\\n' %% time.time()); f.flush()\n" % (tag, HOLD_S, tag)
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
            str(log),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_env(pool),
    )


def _events(log: pathlib.Path) -> list[tuple[str, str, float]]:
    rows = []
    for line in log.read_text().splitlines():
        kind, tag, stamp = line.split()
        rows.append((kind, tag, float(stamp)))
    return sorted(rows, key=lambda r: r[2])


def test_two_heavy_gates_started_together_run_one_after_the_other(tmp_path: pathlib.Path) -> None:
    log = tmp_path / "log"
    first = _heavy(tmp_path / "pool", log, "a")
    second = _heavy(tmp_path / "pool", log, "b")
    out = [p.communicate(timeout=ANSWER_S) for p in (first, second)]
    assert (first.returncode, second.returncode) == (0, 0), out
    order = [(kind, tag) for kind, tag, _ in _events(log)]
    assert (order[0][0], order[1][0]) == ("start", "end"), order
    assert order[0][1] == order[1][1], "the second gate started before the first ended: %s" % order
    waited = [stderr for _, stderr in out if "heavy lock" in stderr]
    assert len(waited) == 1, "exactly the later gate says it waits: %s" % out


def test_a_single_heavy_gate_does_not_wait(tmp_path: pathlib.Path) -> None:
    log = tmp_path / "log"
    proc = _heavy(tmp_path / "pool", log, "solo")
    _, stderr = proc.communicate(timeout=ANSWER_S)
    assert proc.returncode == 0, stderr
    assert "heavy lock" not in stderr, stderr
    rows = _events(log)
    assert [kind for kind, _, _ in rows] == ["start", "end"]


def test_the_timeout_ends_a_wait_with_the_short_exit(tmp_path: pathlib.Path) -> None:
    log = tmp_path / "log"
    holder = _heavy(tmp_path / "pool", log, "holder")
    time.sleep(0.5)
    blocked = _heavy(tmp_path / "pool", log, "late", "--timeout", "0.3")
    _, stderr = blocked.communicate(timeout=ANSWER_S)
    holder.communicate(timeout=ANSWER_S)
    assert blocked.returncode == core_lease.EXIT_SHORT, stderr
    assert {tag for _, tag, _ in _events(log)} == {"holder"}


def test_a_killed_holder_frees_the_lock(tmp_path: pathlib.Path) -> None:
    pool = tmp_path / "pool"
    log = tmp_path / "log"
    holder = subprocess.Popen(
        [sys.executable, str(MODULE), "heavy-lock", "--", "sleep", "60"],
        env=_env(pool),
        stderr=subprocess.PIPE,
        text=True,
    )
    time.sleep(0.5)
    holder.kill()
    holder.communicate(timeout=ANSWER_S)
    after = _heavy(pool, log, "after", "--timeout", "5")
    _, stderr = after.communicate(timeout=ANSWER_S)
    assert after.returncode == 0, stderr
