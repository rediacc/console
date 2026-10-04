"""The session wake-up timer (wl_wake) and the Stop hook's `wake-timer` invariant (operator 2026-10-03).

A stop that waits on background work is re-invoked only when a task exits, so a wait on tasks that all hang never ends. The timer is one more task guaranteed to exit, at most one per session at the OS level, and the hook refuses a waiting stop without one. Each case below has a CONTROL that the same world without the trigger does not fire.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

ME = "0000cafe"
WATCH = {
    "id": "w1",
    "type": "shell",
    "status": "running",
    "description": "watch CI",
    "command": ".ci/scripts/ci/ci-trace.py --wait",
}
SAID = "waiting on CI\n\n## Remaining\n- nothing actionable"


def _wake(monkeypatch, tmp_path):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    return wlfix.import_wl("wl_wake")


def _spawn_timer(tmp_path, minutes="1"):
    """A real timer process, so the lock is judged against a live pid running wl_wake.py."""
    wake = wlfix.HOOK.parent / "wl_wake.py"
    env = {"TMPDIR": str(tmp_path), "PATH": "/usr/bin:/bin"}
    proc = subprocess.Popen(
        [sys.executable, str(wake), ME, "--minutes", minutes],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    lock = tmp_path / "claude-worklist" / "wake" / ("%s.json" % ME)
    deadline = time.time() + 10
    while not lock.exists() and time.time() < deadline:
        time.sleep(0.05)
    assert lock.exists(), "the spawned timer never took its lock"
    return proc, lock


def test_wk1_a_second_timer_is_refused_while_one_is_live_and_allowed_once_it_dies(
    monkeypatch, tmp_path
):
    wake = _wake(monkeypatch, tmp_path)
    proc, lock = _spawn_timer(tmp_path)
    try:
        taken, holder = wake.acquire(ME, 1, pid=999999)
        assert not taken, "a second timer took the lock while a live one held it"
        assert holder.get("pid") == proc.pid, holder
    finally:
        proc.kill()
        proc.communicate()
    # The killed timer left its lock behind (SIGKILL runs no atexit): stale, so the next start replaces it.
    assert lock.exists()
    taken, doc = wake.acquire(ME, 1, pid=424242)
    assert taken, doc
    assert doc["pid"] == 424242, doc


def test_wk2_a_lock_held_by_a_live_process_that_is_not_a_timer_is_stale(monkeypatch, tmp_path):
    """CONTROL for wk1: liveness alone is not enough, the pid must be running wl_wake.py, or a recycled pid would hold the lock forever."""
    wake = _wake(monkeypatch, tmp_path)
    wake.lock_path(ME).write_text(
        json.dumps({"pid": 1, "until": time.time() + 600}), encoding="utf-8"
    )
    taken, doc = wake.acquire(ME, 1, pid=555)
    assert taken, doc
    assert doc["pid"] == 555, doc


def test_wk3_release_drops_only_its_own_lock(monkeypatch, tmp_path):
    wake = _wake(monkeypatch, tmp_path)
    assert wake.acquire(ME, 1, pid=111)[0]
    wake.release(ME, pid=222)
    assert wake.lock_path(ME).exists(), "a release by another pid dropped a lock it did not hold"
    wake.release(ME, pid=111)
    assert not wake.lock_path(ME).exists()


def test_wk4_the_cli_refuses_a_second_start_and_fires_when_its_time_is_up(tmp_path):
    proc, _lock = _spawn_timer(tmp_path, minutes="0.05")
    second = subprocess.run(
        [sys.executable, str(wlfix.HOOK.parent / "wl_wake.py"), ME, "--minutes", "1"],
        capture_output=True,
        text=True,
        env={"TMPDIR": str(tmp_path), "PATH": "/usr/bin:/bin"},
        timeout=30,
        check=False,
    )
    assert second.returncode == 0, second.stdout + second.stderr
    assert "ALREADY ARMED" in second.stdout, second.stdout + second.stderr
    out, _err = proc.communicate(timeout=60)
    assert proc.returncode == 0
    assert "WAKE-UP after" in out.decode(), out
    assert not _lock.exists(), "a timer that fired left its lock behind"


def test_wk5_split_wakers_separates_the_timer_from_the_work():
    wake = wlfix.import_wl("wl_wake")
    others, wakers = wake.split_wakers([WATCH, dict(wlfix.WAKER_TASK)])
    assert [t["id"] for t in others] == ["w1"]
    assert [t["id"] for t in wakers] == ["wake0001"]


def test_wk8_the_harness_timeout_outlasts_the_sleep_and_stays_under_the_ceiling():
    wake = wlfix.import_wl("wl_wake")
    assert wake.harness_timeout_ms() > wake.WAKE_DEFAULT_MIN * 60000
    assert wake.harness_timeout_ms(wake.WAKE_MAX_MIN) <= 7200000
    assert wake.harness_timeout_ms(wake.WAKE_MAX_MIN) > wake.WAKE_MAX_MIN * 60000


def test_wk6_a_waiting_stop_without_a_timer_blocks_and_names_the_arm_command(wl):  # noqa: F811
    wl.setup()
    wl.brief_now()
    wl.hand_now()
    wl.waker = False
    wl.bg = json.dumps([WATCH])
    wl.say(SAID)
    got = wl.run()
    assert "NO WAKE-UP TIMER" in got.out, got.out[:600]
    assert "wl_wake.py deadbeef --minutes 30" in got.out, got.out[:600]
    # 2026-10-04: a 30-minute timer armed under the harness's 30-minute default timeout was killed before it fired, so the arm names a timeout above the sleep.
    assert "timeout: 2400000" in got.out, got.out[:600]
    # CONTROL: the same wait with the timer armed is not refused for it.
    wl.waker = True
    wl.newturn()
    wl.say(SAID)
    got = wl.run()
    assert "NO WAKE-UP TIMER" not in got.out, got.out[:600]


def test_wk7_no_background_work_needs_no_timer_and_a_timer_alone_is_not_a_wait(wl):  # noqa: F811
    wl.setup()
    wl.brief_now()
    wl.hand_now()
    wl.waker = False
    wl.say(SAID)
    got = wl.run()
    assert "NO WAKE-UP TIMER" not in got.out, got.out[:600]
    # Only the timer running: nothing is being waited on, so the timer check stays silent (a timer never demands a timer).
    wl.bg = json.dumps([dict(wlfix.WAKER_TASK)])
    wl.newturn()
    wl.say(SAID)
    got = wl.run()
    assert "NO WAKE-UP TIMER" not in got.out, got.out[:600]
