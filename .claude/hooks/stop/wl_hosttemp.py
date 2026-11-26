"""wl_hosttemp: the Stop segment `host-temp` (agent/plans/PLAN-host-temp-disposal.md D7, Design 6, box HT13).

WHAT IT DOES. SubagentStop leaves a marker `<common>/rediacc-worktrees/<lease id>.finished` when a lease's agent ends its turn (wl_worktrees.mark_finished). Each Stop runs `assess`, which decides whether a sweep is due and, when it is, starts ONE detached sweeper (`python3 -m rediacc_ci.dev.host_temp sweep --lock-held`). The sweeper re-judges every marker, kills a finished lease's leftover processes, deletes its temp and lets gc remove the tree, then appends what it did to `sweeps.jsonl`. The next stop of every session prints the rows that session has not printed yet, once.

THE INLINE BUDGET IS 150 MS AT P95 WITH 15 LEASES, so `assess` lists the records directory, reads the small marker files and stats the transcripts, the lock and the results file. No git, no `du`, no subprocess apart from the one sweeper start. Removing a multi-GB tree and checking gc's rules take seconds to minutes, which is why the sweeper runs detached and its summary prints one stop later.

DUE when no sweeper holds the lock, none started in the last RETRY_S, and either a marker ripened (finished and transcript quiet for GRACE_S) after the last start, or HOST_SWEEP_S passed since the last start (the dead run dirs of D10 need no marker). The sweeper's own re-judgement decides what is touched; `assess` only decides when to look. A transcript that cannot be stat'ed never ripens a marker, the rule host_temp.finished_problem applies too.

THE LOCK is host_temp's: `sweep.lock` holds `{"pid", "start", "token"}`, taken with O_EXCL under the flock on `sweep.guard`, a lock whose holder is dead (or older than LOCK_STALE_S) is taken over. The hook takes it for the sweeper, passes the token in HOST_TEMP_LOCK_HANDOFF, and rewrites the record with the sweeper's pid; the sweeper removes the lock only while it carries that token.

THE CURSOR. The rows are numbered (`seq`). Each session keeps the last number it printed in its own state doc (`host_temp_seq`), so every session prints every row once, a peer included. A session with no cursor yet prints only rows from the last NEW_SESSION_WINDOW_S, never the whole history.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time
import uuid

import wl_core as C

RECORD_DIR = "rediacc-worktrees"
MARKER_SUFFIX = ".finished"
SWEEPS = "sweeps.jsonl"
LOCK_NAME = "sweep.lock"
GUARD_NAME = "sweep.guard"
LAST_NAME = "sweep.last"
LOG_NAME = "sweep.log"
LOCK_HANDOFF_ENV = "HOST_TEMP_LOCK_HANDOFF"
SWEEPER_REL = ".ci/rediacc_ci/dev/host_temp.py"
GRACE_S = 1800
RETRY_S = 5 * 60
HOST_SWEEP_S = 60 * 60
LOCK_STALE_S = 60 * 60
NEW_SESSION_WINDOW_S = 60 * 60
TAIL_BYTES = 64 * 1024
MAX_LINES = 12
CURSOR_KEY = "host_temp_seq"


def common_dir(root):
    """The git common dir of `root`, read from files (wl_core._git_dirs), or None."""
    dirs = C._git_dirs(pathlib.Path(root))
    return dirs[1] if dirs else None


def _read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _start_time(pid):
    """Field 22 of /proc/<pid>/stat, or -1 when the process is gone or a zombie."""
    try:
        text = pathlib.Path("/proc/%d/stat" % pid).read_text(encoding="ascii", errors="replace")
    except (OSError, ValueError):
        return -1
    fields = text[text.rfind(")") + 2 :].split()
    if not fields or fields[0] == "Z":
        return -1
    try:
        return int(fields[19])
    except (IndexError, ValueError):
        return -1


def _lock_stale(path, now):
    """host_temp.lock_is_stale's rule, without importing rediacc_ci. Raises OSError when the lock vanished."""
    age = now - path.stat().st_mtime
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return True
    if not isinstance(rec, dict) or not isinstance(rec.get("pid"), int):
        return True
    start = _start_time(rec["pid"])
    if start < 0 or (
        isinstance(rec.get("start"), int) and rec["start"] >= 0 and start != rec["start"]
    ):
        return True
    return age >= LOCK_STALE_S


def lock_held(records, now):
    """True when a live sweeper holds the lock."""
    path = records / LOCK_NAME
    try:
        return not _lock_stale(path, now)
    except OSError:
        return False


@contextlib.contextmanager
def _guard(records):
    fd = os.open(str(records / GUARD_NAME), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _body(pid, token, now):
    return {"pid": pid, "start": _start_time(pid), "at": now, "token": token, "by": "wl_hosttemp"}


def take_lock(records, token, now):
    """O_EXCL lock with dead-pid takeover under the guard flock; True when this hook now holds it."""
    path = records / LOCK_NAME
    with _guard(records):
        for _ in range(2):
            try:
                fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                try:
                    stale = _lock_stale(path, now)
                except OSError:
                    continue
                if not stale:
                    return False
                with contextlib.suppress(OSError):
                    path.unlink()
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(_body(os.getpid(), token, now), fh)
            return True
    return False


def hand_over(records, token, child, now):
    """Rewrite the lock with the sweeper's pid while it still carries `token`. The file is opened without O_CREAT, so a sweeper that already released it is not followed by a recreated lock."""
    path = records / LOCK_NAME
    with _guard(records):
        rec = _read_json(path)
        if not isinstance(rec, dict) or rec.get("token") != token:
            return False
        try:
            fd = os.open(str(path), os.O_WRONLY | os.O_TRUNC)
        except OSError:
            return False
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(_body(child, token, now), fh)
        return True


def _last_start(records):
    rec = _read_json(records / LAST_NAME)
    at = rec.get("at") if isinstance(rec, dict) else None
    return float(at) if isinstance(at, int | float) else 0.0


def ripe_since(records, now, grace=GRACE_S):
    """The newest moment any marker ripened (finished_at and transcript mtime both GRACE_S old), or 0.0 when none has. A marker with an unreadable transcript never ripens."""
    newest = 0.0
    try:
        names = os.listdir(records)
    except OSError:
        return newest
    for name in names:
        if not name.endswith(MARKER_SUFFIX):
            continue
        marker = _read_json(records / name)
        if not isinstance(marker, dict):
            continue
        at = marker.get("finished_at")
        if not isinstance(at, int | float):
            continue
        moment = float(at)
        transcript = str(marker.get("transcript") or "")
        if transcript:
            try:
                moment = max(moment, os.stat(transcript).st_mtime)
            except OSError:
                continue
        if now - moment >= grace:
            newest = max(newest, moment + grace)
    return newest


def due(records, now):
    """(due, why): whether this stop starts a sweeper."""
    if lock_held(records, now):
        return False, "a sweeper is running"
    last = _last_start(records)
    # A clock stepped back puts `last` ahead of `now`: the distance either way counts, so a future `last` is mirrored to the same distance in the past for the retry window, the ripeness test and the host-sweep interval alike (review 2872d8fe.2).
    gap = abs(now - last)
    if gap < RETRY_S:
        return False, "a sweeper started %d s ago" % gap
    since = now - gap
    ripe = ripe_since(records, now)
    if ripe and ripe > since:
        return True, "a finished lease is past its grace"
    if gap >= HOST_SWEEP_S:
        return True, "no host sweep for %d min" % (gap // 60)
    return False, "nothing ripe"


def spawn(main, records, now, popen=None):
    """Take the lock and start ONE detached sweeper for `main` (the main checkout). True when this call started it. A root without host_temp.py (a hook-test sandbox) starts nothing."""
    if not (pathlib.Path(main) / SWEEPER_REL).is_file():
        return False
    token = uuid.uuid4().hex
    if not take_lock(records, token, now):
        return False
    with contextlib.suppress(OSError):
        (records / LAST_NAME).write_text(json.dumps({"at": now}), encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(pathlib.Path(main) / ".ci"), *([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])]
    )
    env[LOCK_HANDOFF_ENV] = token
    ionice = shutil.which("ionice")
    argv = [*([ionice, "-c3"] if ionice else []), sys.executable or "python3"]
    argv += ["-m", "rediacc_ci.dev.host_temp", "--root", str(main), "sweep", "--lock-held"]
    try:
        log_fd = os.open(str(records / LOG_NAME), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    except OSError:
        log_fd = subprocess.DEVNULL
    popen = subprocess.Popen if popen is None else popen
    try:
        proc = popen(
            argv,
            cwd=str(main),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log_fd,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except OSError:
        with contextlib.suppress(OSError):
            (records / LOCK_NAME).unlink()
        return False
    finally:
        if log_fd != subprocess.DEVNULL:
            with contextlib.suppress(OSError):
                os.close(log_fd)
    child = getattr(proc, "pid", None)
    if isinstance(child, int) and child > 0:
        hand_over(records, token, child, now)
    return True


def read_rows(records):
    """The rows of sweeps.jsonl, read from its last TAIL_BYTES only."""
    path = records / SWEEPS
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - TAIL_BYTES))
            blob = fh.read()
    except OSError:
        return []
    lines = blob.split(b"\n")
    if size > TAIL_BYTES:
        lines = lines[1:]
    rows = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and isinstance(row.get("seq"), int) and row.get("text"):
            rows.append(row)
    return rows


def unprinted(rows, cursor, now):
    """The rows a session with `cursor` has not printed. No cursor: the last NEW_SESSION_WINDOW_S only. A cursor beyond every row (the file was replaced) starts over."""
    if not rows:
        return []
    top = max(r["seq"] for r in rows)
    if not isinstance(cursor, int) or cursor > top:
        return [r for r in rows if now - float(r.get("ts") or 0) < NEW_SESSION_WINDOW_S]
    return [r for r in rows if r["seq"] > cursor]


def render(rows, path):
    """One `host-temp:` line per sweep run (the rows of one `ts`), at most MAX_LINES."""
    runs = {}
    for row in rows:
        runs.setdefault(row.get("ts"), []).append(str(row["text"]))
    lines = ["host-temp: " + "; ".join(texts) for texts in runs.values()]
    if len(lines) > MAX_LINES:
        more = len(lines) - MAX_LINES
        lines = [*lines[-MAX_LINES:], "host-temp: %d earlier sweep(s) in %s" % (more, path)]
    return lines


def assess(root, state_doc, now=None, popen=None):
    """What this stop owes for host temp: {"due": bool, "spawned": bool, "why": str, "print": [lines]}. Advances the session's cursor in `state_doc` past every row it returns. Never raises for a missing directory."""
    now = time.time() if now is None else now
    out = {"due": False, "spawned": False, "why": "", "print": []}
    common = common_dir(root)
    if common is None:
        out["why"] = "no git dir"
        return out
    records = common / RECORD_DIR
    if not records.is_dir():
        out["why"] = "no lease records"
        return out
    rows = read_rows(records)
    fresh = unprinted(rows, (state_doc or {}).get(CURSOR_KEY), now)
    if rows and isinstance(state_doc, dict):
        state_doc[CURSOR_KEY] = max(r["seq"] for r in rows)
    out["print"] = render(fresh, records / SWEEPS)
    out["due"], out["why"] = due(records, now)
    if out["due"]:
        out["spawned"] = spawn(common.parent, records, now, popen=popen)
    return out
