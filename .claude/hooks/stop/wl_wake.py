"""wl_wake: the session's wake-up timer, so a stop that waits on background work cannot wait forever.

THE DEADLOCK THIS CLOSES (operator 2026-10-03). The Stop hook lets a session stop while background work runs: a CI watch, a writer, a reviewer. The harness re-invokes the session only when a background task EXITS. If every task hangs (a watch wedged on a dead socket, a writer stuck in a loop), nothing exits, nothing re-invokes the session, and the session and the work it
waits on are both stuck with no one looking. The hook's own 15-minute check-in (wl_liveness.BG_REPORT_MIN) cannot help, because it only runs when the session is already at a stop.

THE TIMER IS ONE MORE BACKGROUND TASK, one that is guaranteed to exit. Run in the background, it sleeps (WAKE_DEFAULT_MIN by default), then prints where to look and exits, and the harness's exit notification is the wake-up. The Stop hook requires one whenever it allows a stop with other background work still running (`wl_checks`, key `wake-timer`).

ONE PER SESSION, enforced at the OS level and not by convention. The lock is `<tmp>/claude-worklist/wake/<me>.json`, created with O_CREAT|O_EXCL and holding the timer's pid. A second start while a live timer holds it prints ALREADY ARMED and exits at once, so the OS never carries two sleeping timers for one session. A lock whose pid is gone, or is not a wl_wake process, is stale and replaced.

  python3 .claude/hooks/stop/wl_wake.py <me> [--minutes N]     (always with run_in_background)

No environment reads: the session prefix is an argument, like every worklist verb, and the temp root comes from `tempfile`.
"""

from __future__ import annotations

import atexit
import json
import os
import pathlib
import re
import signal
import subprocess
import sys
import tempfile
import time

WAKE_DEFAULT_MIN = 30
# Inside the harness's own background-task ceiling (2 hours), so the harness never kills a timer before it fires.
WAKE_MAX_MIN = 110
# A background task whose command runs this file is the session's timer, whatever arguments it carries.
WAKER_RE = re.compile(r"\bwl_wake\.py\b")
SESSION_RE = re.compile(r"^[0-9a-f]{8}$")


def lock_dir() -> pathlib.Path:
    d = pathlib.Path(tempfile.gettempdir()) / "claude-worklist" / "wake"
    d.mkdir(parents=True, exist_ok=True)
    return d


def lock_path(me: str) -> pathlib.Path:
    return lock_dir() / ("%s.json" % me)


def is_waker_pid(pid) -> bool:
    """True when `pid` is a live process running this file: the liveness test a lock is judged by."""
    try:
        pid = int(pid)
        os.kill(pid, 0)
    except (TypeError, ValueError, OSError):
        return False
    try:
        return b"wl_wake" in pathlib.Path("/proc/%d/cmdline" % pid).read_bytes()
    except OSError:
        return False


def read_lock(me: str):
    try:
        doc = json.loads(lock_path(me).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def acquire(me: str, minutes: float, pid: int | None = None, now: float | None = None):
    """Take the session's timer lock. Returns (True, doc) when taken, (False, holder) when a live timer holds it."""
    pid = os.getpid() if pid is None else pid
    now = time.time() if now is None else now
    doc = {"pid": pid, "start": now, "until": now + minutes * 60, "minutes": minutes}
    path = lock_path(me)
    for _ in range(2):
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            holder = read_lock(me)
            if holder is not None and is_waker_pid(holder.get("pid")):
                return False, holder
            # Stale: its process is gone or is not a timer. Replaced once; a second collision means a live start raced this one.
            path.unlink(missing_ok=True)
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(doc, handle)
        return True, doc
    holder = read_lock(me)
    return False, holder or {}


def release(me: str, pid: int | None = None) -> None:
    """Drop the lock, only when it is still this process's: a replaced lock belongs to the timer that replaced it."""
    pid = os.getpid() if pid is None else pid
    holder = read_lock(me)
    if holder is not None and holder.get("pid") == pid:
        lock_path(me).unlink(missing_ok=True)


def split_wakers(live_bg):
    """(the background tasks that are not timers, the timers). The Stop hook judges the wait on the first and the coverage on the second."""
    others, wakers = [], []
    for task in live_bg or []:
        blob = "%s %s" % (task.get("command") or "", task.get("description") or "")
        (wakers if WAKER_RE.search(blob) else others).append(task)
    return others, wakers


def arm_command(me: str, minutes: int = WAKE_DEFAULT_MIN) -> str:
    return "python3 .claude/hooks/stop/wl_wake.py %s --minutes %d" % (me, minutes)


def _hhmm(epoch: float) -> str:
    return time.strftime("%H:%MZ", time.gmtime(epoch))


def wake_report(me: str, minutes: float, root: pathlib.Path) -> str:
    """What the session reads when the timer fires: the open slice of its worklist, then the order to look and re-arm."""
    listing = ""
    try:
        out = subprocess.run(
            [sys.executable, str(root / ".claude/hooks/stop/worklist.py"), "--list", "--open", me],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        listing = (out.stdout or out.stderr or "").strip()[:4000]
    except (OSError, subprocess.SubprocessError) as exc:
        listing = "(worklist listing failed: %s)" % exc
    return (
        "WAKE-UP after %g min (session %s). The stop waited on background work; check that each task "
        "is still moving (its output file growing, its process alive) before stopping again, and "
        "re-arm this timer if the wait continues:\n    %s\n\n%s"
    ) % (minutes, me, arm_command(me), listing)


def main(argv) -> int:
    args = list(argv[1:])
    if not args or not SESSION_RE.match(args[0]):
        print("usage: wl_wake.py <session-prefix-8hex> [--minutes N]", file=sys.stderr)
        return 2
    me = args[0]
    minutes: float = WAKE_DEFAULT_MIN
    if "--minutes" in args:
        try:
            minutes = float(args[args.index("--minutes") + 1])
        except (IndexError, ValueError):
            print("--minutes needs a number", file=sys.stderr)
            return 2
    if not 0 < minutes <= WAKE_MAX_MIN:
        print("--minutes must be in (0, %d]" % WAKE_MAX_MIN, file=sys.stderr)
        return 2
    taken, doc = acquire(me, minutes)
    if not taken:
        print(
            "ALREADY ARMED: session %s's timer (pid %s) fires at %s; not starting a second one."
            % (me, doc.get("pid"), _hhmm(float(doc.get("until") or 0)))
        )
        return 0
    atexit.register(release, me)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    print(
        "ARMED: session %s wakes at %s (%g min)." % (me, _hhmm(doc["until"]), minutes), flush=True
    )
    while time.time() < doc["until"]:
        time.sleep(min(30.0, max(0.0, doc["until"] - time.time())))
    root = pathlib.Path(__file__).resolve().parents[3]
    print(wake_report(me, minutes, root), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
