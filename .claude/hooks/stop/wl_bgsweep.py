"""wl_bgsweep: a notify-only sweep for orphan background shells this session's own harness left behind.

WHY THIS EXISTS. The operator: "too many background shells in the background" accumulating over a very long session. Verified live on this machine: this session's own harness process had 10 leftover `bash -B -c source .../shell-snapshots/...` processes still alive as direct descendants, aged from 61.6 to 202.9 minutes, none of them killed. `wl_liveness.py` only ages tasks the harness's own event payload (`live_bg`) currently lists, or the output-file mtime for those same declared tasks.
Nothing walks the OS process tree independently to ask "is there a live shell under this session that nothing is currently bookkeeping?" That is the gap this module closes: a pure safety-net sweep, notify-only, that cannot be tricked (or trick itself) into looking at a different session's processes.

WHY A SEPARATE MODULE, not folded into `wl_liveness.py`. That module's own docstring frames its job as checking a claim the harness ITSELF already makes ("the event payload is authoritative for EXISTENCE"). This sweep is the opposite shape: an unconditional, bookkeeping-agnostic walk of every OS descendant, whether or not anything currently declares it. Folding the two together would blur that boundary. Mirrors the `wl_deflect.py`/`wl_admit.py` precedent of a small, testable sibling module.

THE ANCHOR IS A SINGLE PID, NOT `wl_liveness.harness_ancestors()`'s MULTI-HOP SET, and this is the one deliberate departure from a naive reading of the ask. That function's 8-hop walk reaches the terminal shell, the session leader, and eventually `init` -- nodes that CAN be legitimately shared with a sibling Claude session launched from the same terminal. Descending from the whole ancestor set would then pull in a sibling's entire subtree. Descending from only the harness's own single pid cannot: a process has exactly one parent, so two distinct `claude`-comm harness processes are structurally guaranteed to be in disjoint subtrees (subagents run in-process; background tasks spawn shells, not new harness processes). Verified live: 4 distinct `comm=claude` processes on the machine this was designed on shared no ancestor below `pid 2`.

ANCHOR RESOLUTION IS CROSS-VALIDATED, NEVER TRUSTED BLIND. `CLAUDE_PID` is harness-reported and not referenced anywhere else in this repo, so it is used only after agreeing with an independent comm-walk from this hook's own pid. Disagreement, or either one failing to resolve, refuses (reports nothing for that stop) rather than guessing -- an unresolved anchor is exactly the situation where a wrong guess could reach outside this session.

THE THRESHOLD IS A NEW, DISTINCT CONSTANT (`WORKLIST_BGSWEEP_AGE_MIN`, default 20), never a rename or reuse of `wl_liveness.BG_STALE_MIN` (15). They measure different things: `BG_STALE_MIN` is quiescence (has a DECLARED task stopped writing output, which can fire on a 2-minute-old process with no stdout yet or stay silent on an hours-old process streaming continuously); this constant is raw wall age since process start, independent of output activity and independent of whether the harness still declares the task at all.

NOTIFICATION, NOT ACTION. No code here calls `os.kill`/`terminate()` against a discovered process. `worklist.py --reap` is the existing "retire a roster entry" verb and it only ever mutates bookkeeping; a future, separate `--reap-pid` verb is where a kill step would plug in, requiring an explicit operator invocation and a fresh re-resolution of the anchor at the moment of the kill (a TOCTOU guard, since the pid could have been reaped and reused between notify and act).
"""

import os
import re
import subprocess
from typing import Any

import wl_liveness

#: Raw wall age since process start, independent of BG_STALE_MIN's output-quiescence question -- see this module's own docstring for why the two are not merged.
BGSWEEP_AGE_MIN = int(os.environ.get("WORKLIST_BGSWEEP_AGE_MIN", "20"))


def _read_comm(pid):
    """The bare comm string for `pid`, or "" on any failure. Never raises."""
    try:
        with open("/proc/%d/comm" % pid, encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except OSError:
        return ""


def _clk_tck():
    try:
        return os.sysconf("SC_CLK_TCK")
    except (ValueError, OSError, AttributeError):
        return 100


def _proc_table_with_age_linux(uptime_s):
    """[(pid, ppid, cmdline, age_seconds_or_None)] -- the Linux path, one extra `/proc/<pid>/stat` field (starttime, field 22) beyond what `wl_liveness._proc_table_linux` reads, plus `/proc/uptime`.

    `st_mtime` is never used for age: it is not process start time. `uptime_s` is a parameter, not read internally, so the real end-to-end smoke test can inject an artificially large value and prove the age arithmetic on a REAL short-lived child without an actual 20-minute wait.
    """
    clk = _clk_tck()
    out: list[Any] = []
    try:
        entries = os.listdir("/proc")
    except OSError:
        return out
    for name in entries:
        if not name.isdigit():
            continue
        try:
            with open("/proc/%s/stat" % name, "rb") as f:
                stat = f.read().decode("utf-8", "replace")
            after = stat.rsplit(")", 1)[-1].split()
            ppid = int(after[1])
            starttime_ticks = int(after[19])
            with open("/proc/%s/cmdline" % name, "rb") as f:
                cmd = f.read().replace(b"\0", b" ").decode("utf-8", "replace")
        except (OSError, ValueError, IndexError):
            continue
        age = (uptime_s - starttime_ticks / clk) if uptime_s is not None else None
        out.append((int(name), ppid, cmd, age))
    return out


def _proc_table_with_age_ps():
    """[(pid, ppid, cmdline, age_seconds_or_None)] -- the no-/proc fallback (macOS), `etimes=` added to `wl_liveness._proc_table_ps`'s own invocation so age arrives with no uptime arithmetic needed on this path.

    A row whose `etimes` field fails to parse degrades to age=None ("OS-visible, age unknown"), never a crash and never a guessed zero -- older BSD `ps` builds report `etime=` as a `[[dd-]hh:]mm:ss` string instead, which this deliberately does not attempt to parse.
    """
    try:
        r = subprocess.run(
            ["ps", "-axo", "pid=,ppid=,etimes=,args="],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if r.returncode != 0:
        return []
    out = []
    for line in r.stdout.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 3 or not parts[0].isdigit() or not parts[1].isdigit():
            continue
        age = int(parts[2]) if parts[2].isdigit() else None
        cmd = parts[3] if len(parts) > 3 else ""
        out.append((int(parts[0]), int(parts[1]), cmd, age))
    return out


def proc_table_with_age(uptime_s=None):
    """[(pid, ppid, cmdline, age_seconds_or_None)] for every readable process, Linux or the `ps` fallback."""
    if os.path.isdir("/proc"):
        if uptime_s is None:
            try:
                with open("/proc/uptime", encoding="utf-8") as f:
                    uptime_s = float(f.read().split()[0])
            except (OSError, ValueError, IndexError):
                uptime_s = None
        return _proc_table_with_age_linux(uptime_s)
    return _proc_table_with_age_ps()


def resolve_anchor(table=None):
    """The single pid this sweep may descend from, or None (refuse) -- never a guess.

    `WORKLIST_HARNESS_PID` overrides for tests, matching `wl_liveness.harness_ancestors`'s own convention. Otherwise `CLAUDE_PID` (harness-reported) must AGREE with an independent comm-walk from this hook's own pid before either is trusted; disagreement or either one failing to resolve refuses.
    """
    override = os.environ.get("WORKLIST_HARNESS_PID", "")
    if override.isdigit():
        return int(override)
    if table is None:
        table = wl_liveness.proc_table()
    if not table:
        return None
    parents = {pid: ppid for pid, ppid, _cmd in table}
    claude_pid_env = os.environ.get("CLAUDE_PID", "")
    env_pid = int(claude_pid_env) if claude_pid_env.isdigit() else None
    walk_pid = None
    cur: int | None = os.getpid()
    for _ in range(8):
        cur = parents.get(cur)
        if not cur or cur <= 1:
            break
        if _read_comm(cur) == "claude":
            walk_pid = cur
            break
    if env_pid is not None and walk_pid is not None and env_pid == walk_pid:
        return env_pid
    return None


def descendants(anchor_pid, table_with_age):
    """[(pid, ppid, cmdline, age)] for every transitive descendant of `anchor_pid`, BFS over the ppid->children map. `anchor_pid` itself is never included."""
    children: dict[Any, Any] = {}
    for pid, ppid, cmdline, age in table_with_age:
        children.setdefault(ppid, []).append((pid, ppid, cmdline, age))
    out, seen, queue = [], {anchor_pid}, [anchor_pid]
    while queue:
        cur = queue.pop()
        for row in children.get(cur, ()):
            pid = row[0]
            if pid in seen:
                continue
            seen.add(pid)
            out.append(row)
            queue.append(pid)
    return out


_TASK_OUTPUT = re.compile(r"/tasks/([A-Za-z0-9_-]+)\.output$")


def _stdout_task(pid):
    """The background task id whose `tasks/<id>.output` this pid writes to (fd 1 or 2), or None."""
    for fd in (1, 2):
        try:
            target = os.readlink("/proc/%d/fd/%d" % (pid, fd))
        except OSError:
            continue
        m = _TASK_OUTPUT.search(target)
        if m:
            return m.group(1)
    return None


def bookkept(rows, live_ids, stdout_task=_stdout_task):
    """The pids that belong to a task the harness lists as running: a process whose stdout (or an ancestor's, within `rows`) is that task's `tasks/<id>.output`.

    2026-09-24: the sweep reported 21 "orphans" that were the process trees of two LISTED tasks (an M-live run's `devbox exec -> run-legacy.sh -> docker exec` chain and a writer's `pytest -n 8`), and blocked every stop on them.
    """
    if not live_ids:
        return set()
    parent = {pid: ppid for pid, ppid, _c, _a in rows}
    owned: dict[Any, bool] = {}

    def is_owned(pid, depth=0):
        if pid in owned:
            return owned[pid]
        task = stdout_task(pid)
        if task is not None:
            owned[pid] = task in live_ids
            if owned[pid]:
                return True
        up = parent.get(pid)
        owned[pid] = bool(
            up is not None and up in parent and depth < 64 and is_owned(up, depth + 1)
        )
        return owned[pid]

    return {pid for pid, _pp, _c, _a in rows if is_owned(pid)}


def sweep(table_with_age=None, anchor_table=None, live_ids=None, stdout_task=_stdout_task):
    """[(pid, age_min_or_None, cmdline)] -- orphan rows to report, or [] when the anchor cannot be resolved or nothing qualifies.

    A row with age >= BGSWEEP_AGE_MIN is flagged. A row with age=None (unreadable start time) is ALSO flagged, labelled "age unknown" by the caller -- never silently dropped and never treated as 0 or as infinite, per this module's own design note.
    """
    if table_with_age is None:
        table_with_age = proc_table_with_age()
    if not table_with_age:
        return []
    anchor_source = (
        anchor_table
        if anchor_table is not None
        else [(p, pp, c) for p, pp, c, _a in table_with_age]
    )
    anchor = resolve_anchor(anchor_source)
    if anchor is None:
        return []
    out = []
    rows = descendants(anchor, table_with_age)
    owned = bookkept(rows, set(live_ids or ()), stdout_task)
    for pid, _ppid, cmdline, age in rows:
        if pid in owned:
            continue
        if age is None or age >= BGSWEEP_AGE_MIN * 60:
            age_min = (age / 60.0) if age is not None else None
            out.append((pid, age_min, cmdline))
    return out
