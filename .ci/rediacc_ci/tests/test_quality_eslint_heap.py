"""`rediacc_ci.quality.eslint_heap`, the port of `scripts/eslint-heap.sh`.

THE BASH TWIN WAS RETIRED WITH THIS FILE (PLAN-retire-bash-oracles B5, W10). Before it went, both were driven side by side through a recording `npx` stub under nine environments (plain, a core grant, a reserve above MemAvailable, a grant capped by memory, a grant of one, a failing eslint, a preset NODE_OPTIONS, a worker size above memory, a negative budget): argv, stderr notices and exit status agreed in every one, except the MemAvailable figure inside a notice (the live kernel value moved between the two runs) and the one deliberate delta recorded below.

DELIBERATE DELTAS FROM THE BASH (Rule T), each with a test that fails on the bash behaviour:
  * NODE_OPTIONS is extended, not replaced (`test_node_options_survive`).
  * A non-numeric reserve, worker size or heap is a named refusal (`test_non_numeric_*`).
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import eslint_heap as eh

if TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
PORT = ROOT / ".ci" / "rediacc_ci" / "quality" / "eslint_heap.py"

STUB = """#!/bin/sh
echo "argv: $*"
echo "NODE_OPTIONS=$NODE_OPTIONS"
case "$STUB_MODE" in
  kill) kill -9 $$ ;;
esac
exit ${STUB_RC:-0}
"""


def _stub_dir(tmp_path: pathlib.Path) -> str:
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    npx = bindir / "npx"
    npx.write_text(STUB, encoding="utf-8")
    npx.chmod(npx.stat().st_mode | stat.S_IXUSR)
    return str(bindir)


def _run(tmp_path: pathlib.Path, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
    full = {
        "PATH": "%s:/usr/bin:/bin" % _stub_dir(tmp_path),
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    full.update(env)
    return subprocess.run(
        [sys.executable, str(PORT), *args],
        capture_output=True,
        text=True,
        env=full,
        check=False,
        timeout=60,
    )


def test_heap_is_never_raised_only_lowered() -> None:
    assert eh.plan_heap(8192, 20000, 1200) == (8192, None)
    heap, note = eh.plan_heap(8192, 4000, 1200)
    assert heap == 2800
    assert note is not None
    assert "clamping the requested 8192MB heap to 2800MB" in note


def test_heap_floor_and_unknown_memory() -> None:
    heap, _ = eh.plan_heap(8192, 1500, 1200)
    assert heap == eh.HEAP_FLOOR_MB
    assert eh.plan_heap(8192, None, 1200) == (8192, None)
    assert eh.plan_heap(8192, 0, 1200) == (8192, None)


def test_workers_follow_the_grant_and_are_capped_by_memory() -> None:
    env = {"CI_RUNNER_CORES": "8"}
    assert eh.plan_workers([], env, 40000, 1200) == (["--concurrency=8"], None)
    args, note = eh.plan_workers([], env, 10200, 1200)
    assert args == ["--concurrency=3"]
    assert note is not None
    assert "from the granted 8 to 3" in note


def test_workers_none_without_a_grant_or_with_one_core() -> None:
    assert eh.plan_workers([], {}, 40000, 1200) == ([], None)
    assert eh.plan_workers([], {"CI_RUNNER_CORES": "1"}, 40000, 1200) == ([], None)
    assert eh.plan_workers([], {"CI_RUNNER_CORES": "abc"}, 40000, 1200) == ([], None)


def test_callers_own_concurrency_is_kept() -> None:
    env = {"CI_RUNNER_CORES": "8"}
    assert eh.plan_workers(["--concurrency=2"], env, 40000, 1200) == ([], None)
    assert eh.plan_workers(["--concurrency", "2"], env, 40000, 1200) == ([], None)


def test_negative_memory_budget_is_zero_workers_not_minus_one() -> None:
    args, note = eh.plan_workers([], {"CI_RUNNER_CORES": "8"}, 500, 1200)
    assert args == []
    assert note is not None
    assert "to 1 (about 3000MB each)" in note


def test_node_options_survive() -> None:
    """Rule T delta: the bash replaced NODE_OPTIONS wholesale, discarding the caller's flags."""
    assert eh.node_options(None, 8192) == "--max-old-space-size=8192"
    assert eh.node_options("", 8192) == "--max-old-space-size=8192"
    assert eh.node_options("--trace-warnings", 8192) == "--trace-warnings --max-old-space-size=8192"


def test_node_options_end_to_end(tmp_path: pathlib.Path) -> None:
    proc = _run(
        tmp_path,
        "8192",
        "packages/cli",
        "--max-warnings",
        "0",
        NODE_OPTIONS="--trace-warnings",
        ESLINT_HEAP_RESERVE_MB="0",
    )
    assert proc.returncode == 0, proc.stderr
    assert "argv: eslint" in proc.stdout
    assert "packages/cli --max-warnings 0" in proc.stdout
    assert "NODE_OPTIONS=--trace-warnings --max-old-space-size=" in proc.stdout


def test_exit_status_is_eslints(tmp_path: pathlib.Path) -> None:
    assert _run(tmp_path, "8192", "x", STUB_RC="3").returncode == 3
    assert _run(tmp_path, "8192", "x", STUB_RC="0").returncode == 0


def test_signal_death_reads_137_not_zero(tmp_path: pathlib.Path) -> None:
    """The reason the runner exists: an OOM kill must never be swallowed into a pass."""
    assert _run(tmp_path, "8192", "x", STUB_MODE="kill").returncode == 137


def test_missing_heap_is_refused(tmp_path: pathlib.Path) -> None:
    proc = _run(tmp_path)
    assert proc.returncode == 1
    assert "requested heap in MB is required" in proc.stderr


@pytest.mark.parametrize(
    ("env", "name"),
    [
        ({"ESLINT_HEAP_RESERVE_MB": "lots"}, "ESLINT_HEAP_RESERVE_MB"),
    ],
)
def test_non_numeric_reserve_is_a_named_refusal(
    tmp_path: pathlib.Path, env: dict[str, str], name: str
) -> None:
    """Rule T delta: bash arithmetic read the word as an empty variable, so a typo meant a zero reserve."""
    proc = _run(tmp_path, "8192", "x", **env)
    assert proc.returncode == 2
    assert name in proc.stderr


def test_non_numeric_worker_size_is_a_named_refusal(tmp_path: pathlib.Path) -> None:
    proc = _run(tmp_path, "8192", "x", CI_RUNNER_CORES="8", ESLINT_WORKER_MB="big")
    assert proc.returncode == 2
    assert "ESLINT_WORKER_MB" in proc.stderr


def test_non_numeric_heap_is_a_named_refusal(tmp_path: pathlib.Path) -> None:
    proc = _run(tmp_path, "lots", "x")
    assert proc.returncode == 2
    assert "whole number of MB" in proc.stderr


def test_missing_npx_is_127(tmp_path: pathlib.Path) -> None:
    proc = subprocess.run(
        [sys.executable, str(PORT), "8192", "x"],
        capture_output=True,
        text=True,
        env={
            "PATH": str(tmp_path),
            "PYTHONPATH": str(ROOT / ".ci"),
            "HOME": os.environ.get("HOME", "/"),
        },
        check=False,
        timeout=60,
    )
    assert proc.returncode == 127
    assert "cannot run npx" in proc.stderr


def test_available_mb_reads_memavailable(tmp_path: pathlib.Path) -> None:
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal: 100 kB\nMemAvailable:   2097152 kB\n", encoding="utf-8")
    assert eh.available_mb(meminfo) == 2048
    meminfo.write_text("MemTotal: 100 kB\n", encoding="utf-8")
    assert eh.available_mb(meminfo) is None
    assert eh.available_mb(tmp_path / "absent") is None
