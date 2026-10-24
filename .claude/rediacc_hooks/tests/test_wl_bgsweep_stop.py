"""Background shell hygiene through the real Stop hook on the one-plan-per-PR loop (wl_bgsweep.findings, the `bg-orphan` key).

2026-10-24: twelve declared `until [ -s <task output> ]; do sleep 15; done` waiters a sub-agent armed lived for hours while every stop printed "Stood down: bg-orphan x158". Two defects: `wl_bgsweep.bookkept` excused every declared shell, and the PR_LOOP stand-down parked the check. Each case here spawns a REAL process tree under a holder pid the hook is pointed at (`WORKLIST_HARNESS_PID`), with the inner shell's stdout on a `tasks/<id>.output` the event declares, exactly the shape the harness gives a background Bash call.

Run: python3 -m pytest .claude/rediacc_hooks/tests/test_wl_bgsweep_stop.py -q
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import signal
import subprocess
import sys
import time

from rediacc_hooks import syspath
from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.test_wl_cap_wait import mutated_hook
from rediacc_hooks.tests.test_wl_pr_scope_stop import (
    PR_SCOPE,
    keys_of,
    loop_world,
    reason,
    run_stop,
)

POLL = "until [ -s %s ]; do sleep 1; done; cat %s"


def _children(pid: int) -> list[int]:
    # The process table comes from wl_liveness, which owns the /proc read and the `ps` fallback, so this test names no procfs path itself.
    stop_dir = wlfix.STOP_DIR
    spec = importlib.util.spec_from_file_location(
        "_wl_liveness_bgsweep", stop_dir / "wl_liveness.py"
    )
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    syspath.on_sys_path(stop_dir)
    spec.loader.exec_module(mod)
    return [row[0] for row in mod.proc_table() if row[1] == pid]


class Tree:
    """holder (the stand-in harness pid) -> inner bash running `cmd` through the harness's `eval '...' < /dev/null` shape, stdout on `<base>/tasks/<task>.output`."""

    def __init__(self, fix, cmd: str, task: str):
        out = fix.base / "tasks" / ("%s.output" % task)
        out.parent.mkdir(parents=True, exist_ok=True)
        inner = "eval '%s' < /dev/null" % cmd
        # A Python holder, so nothing but the task sits between it and the inner shell: a `bash` holder is itself a task-less shell (and, with a `bash` shim on PATH, two), which the sweep would rightly report as an undeclared orphan at a threshold of 0.
        holder_src = (
            "import subprocess, sys\n"
            "with open(sys.argv[2], 'w') as out:\n"
            "    subprocess.run(['bash', '-c', sys.argv[1]], stdout=out, stderr=subprocess.STDOUT)\n"
        )
        self.holder = subprocess.Popen(
            [sys.executable, "-c", holder_src, inner, str(out)],
            start_new_session=True,
        )
        deadline = time.time() + 5
        self.inner: int | None = None
        while time.time() < deadline and self.inner is None:
            kids = _children(self.holder.pid)
            self.inner = kids[0] if kids else None
            if self.inner is None:
                time.sleep(0.05)
        assert self.inner is not None, "SETUP: the inner shell never started"
        self.pid: int = self.inner
        fix.bg = json.dumps(
            [
                {
                    "id": task,
                    "type": "shell",
                    "status": "running",
                    "command": cmd,
                    "description": "wait for the output",
                }
            ]
        )
        self.env = {"WORKLIST_HARNESS_PID": str(self.holder.pid), "WORKLIST_BGSWEEP_AGE_MIN": "0"}

    def close(self):
        with contextlib.suppress(OSError):
            os.killpg(self.holder.pid, signal.SIGKILL)
        self.holder.wait(timeout=5)


def _target(fix) -> str:
    path = fix.base / "never-written.output"
    path.write_text("", encoding="utf-8")
    return str(path)


def test_a_declared_wait_loop_blocks_on_the_pr_loop_and_names_its_kill(wl):
    loop_world(wl)
    tgt = _target(wl)
    tree = Tree(wl, POLL % (tgt, tgt), "bpoll001")
    try:
        got = run_stop(wl, tree.env)
        text = reason(got)
        assert "bg-orphan" in keys_of(wl, got), text[:2500]
        line = next((ln for ln in text.splitlines() if PR_SCOPE in ln), "")
        assert "bg-orphan" not in line, "stood down on the PR loop: %s" % line
    finally:
        tree.close()


def test_the_message_names_pid_age_command_and_kill(wl):
    loop_world(wl)
    tgt = _target(wl)
    tree = Tree(wl, POLL % (tgt, tgt), "bpoll002")
    try:
        got = run_stop(wl, tree.env)
        text = reason(got)
        assert "NEED KILLING" in text, text[:2500]
        assert "pid %d" % tree.pid in text, text[:2500]
        assert "pure wait loop past 0 min, polling [ -s %s ]" % tgt in text, text[:2500]
        assert "until [ -s %s ]" % tgt in text, text[:2500]
        assert "kill %d" % tree.pid in text or "kill -- -%d" % tree.pid in text, text[:2500]
        assert "0 bytes" in text, text[:2500]
    finally:
        tree.close()


def test_control_a_declared_long_running_non_loop_does_not_fire(wl):
    loop_world(wl)
    tree = Tree(wl, "tail -f /dev/null", "btail001")
    try:
        got = run_stop(wl, tree.env)
        assert "bg-orphan" not in keys_of(wl, got), reason(got)[:2500]
    finally:
        tree.close()


def test_mutation_without_the_keep_list_entry_the_loop_stands_it_down(wl):
    loop_world(wl)
    tgt = _target(wl)
    tree = Tree(wl, POLL % (tgt, tgt), "bpoll003")
    try:
        mutated_hook(wl, "wl_standdown.py", '        "bg-orphan",\n', "")
        got = run_stop(wl, tree.env)
        assert "bg-orphan" not in keys_of(wl, got), reason(got)[:2500]
        line = next((ln for ln in reason(got).splitlines() if PR_SCOPE in ln), "")
        assert "bg-orphan" in line, "the parked key is not named: %s" % line
    finally:
        tree.close()
