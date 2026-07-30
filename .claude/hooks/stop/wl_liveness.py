"""wl_liveness: worker verification and the 45/90/120 ladder (v10).

THE ASK (operator, 2026-07-30): "stale background shells and stale 'ongoing'
statements... catch the gaps like 'ongoing' but there is no working
background agent or background shell to trace... 45 mins check that ping, 90
mins investigate, 120 think about stopping it."

WHAT IS ACTUALLY VERIFIABLE, measured on this machine rather than assumed:

  * Background SHELL tasks are direct children of the harness process, and
    each child's cmdline embeds the declared `command` text verbatim inside
    the snapshot-sourcing eval wrapper. The harness is found by walking
    /proc ppid ancestry from this very hook (hook -> sh -> claude). So a
    shell task's claim to be running is CHECKABLE: a live child whose
    cmdline carries a distinctive substring of that command exists or not.
  * Teammate/agent tasks have NO OS process (they run inside the node
    harness). Their only oracle is the task output file in the session task
    dir (a symlink to the subagent transcript), whose mtime advances while
    the agent works.
  * On a machine without /proc, `ps -axo pid=,ppid=,args=` substitutes; if
    that also fails, the OS layer is honestly blind.

THE HONESTY RULE, which is the whole design: the event payload is
authoritative for EXISTENCE (a task the harness lists as running will wake
the session when it ends, whatever the OS says), and the OS layer only ever
ADDS facts. A worker the OS cannot find is SUSPECT, reported in those words;
it is never demoted to dead, because "your worker is dead" said wrongly is
worse than no check at all. The only verdict that says a delegate is gone --
GONE -- requires the harness itself to no longer list the declared worker
id, which the OS cannot contradict into a false accusation.

THE LADDER, and why it cannot deadlock (the poll_fast_path lesson, fixed by
operator decision in 860f47b04: a gate needing a state only an allowed stop
could write pinned a session all night):
  * every rung's exit is an action the session completes ALONE: refresh the
    item with evidence (--update), restart or replace the worker, or defer
    with a DEFAULT -- the last is unconditionally executable;
  * all bookkeeping is written on EVERY stop, blocked or allowed;
  * each blocking rung fires ONCE per (item, updated-stamp): any update
    resets the clock, and an ignored top rung hands over to the stuck and
    idle detectors rather than repeating forever;
  * rung 1 (45 min) never blocks. A blocking ping would burn a turn every
    45 minutes per long-running delegate; it rides the report instead.
"""

import os
import re
import subprocess
import time

import wl_core as C

LADDER_PING_MIN = int(os.environ.get("WORKLIST_LADDER_PING_MIN", "45"))
LADDER_INVESTIGATE_MIN = int(os.environ.get("WORKLIST_LADDER_INVESTIGATE_MIN", "90"))
LADDER_RESOLVE_MIN = int(os.environ.get("WORKLIST_LADDER_RESOLVE_MIN", "120"))


def blocking_rung_due(state_doc, key, age_min, stampkey, gone=False):
    """Would the ladder actually FIRE a blocking rung for this subject?

    WHY THIS EXISTS. The ladder is latched: `fire_once` records each rung
    against the subject's stamp, so "investigate" fires ONCE and then stays
    quiet until the stamp moves. `poll_fast_path` forfeited on raw age
    instead, never consulting that latch, so the two disagreed: the report
    went silent while the forfeit kept firing.

    Measured 2026-07-30. Task #20 sat in_progress for 298 minutes, legitimately,
    waiting on an operator decision and a running agent. Its rung had long since
    fired, yet EVERY five-minute inbox poll forfeited the silent path and
    demanded the full battery and a full report. There was no way to discharge
    it short of finishing or abandoning a task that was not the session's to
    finish. That is precisely the "a gate that cannot be satisfied deadlocks
    the session" trap the v10 brief warned any new time-based check to avoid,
    and it was reintroduced by a threshold comparison that looked harmless.

    The 45-minute ping is deliberately NOT a blocking rung: it is report-only,
    the horizon bounds how long it can be deferred, and forfeiting a silent
    poll for it would reinstate the same noise at a lower threshold.
    """
    if age_min is None:
        return False
    fired = (state_doc.get("ladder") or {}).get(key) or {}
    if gone:
        return fired.get("gone") != stampkey
    if age_min >= LADDER_RESOLVE_MIN:
        return fired.get("resolve") != stampkey
    if age_min >= LADDER_INVESTIGATE_MIN:
        return fired.get("investigate") != stampkey
    return False


# ---- process inspection -----------------------------------------------------

def _proc_table_linux():
    """[(pid, ppid, cmdline)] for every readable /proc entry. A few ms for a
    few hundred processes; never raises."""
    out = []
    try:
        entries = os.listdir("/proc")
    except OSError:
        return None
    for name in entries:
        if not name.isdigit():
            continue
        try:
            with open("/proc/%s/stat" % name, "rb") as f:
                stat = f.read().decode("utf-8", "replace")
            # field 4 is ppid; the comm field (2) may contain spaces inside
            # parens, so split after the LAST ')'.
            after = stat.rsplit(")", 1)[-1].split()
            ppid = int(after[1])
            with open("/proc/%s/cmdline" % name, "rb") as f:
                cmd = f.read().replace(b"\0", b" ").decode("utf-8", "replace")
        except (OSError, ValueError, IndexError):
            continue
        out.append((int(name), ppid, cmd))
    return out


def _proc_table_ps():
    """The no-/proc fallback (macOS). One bounded subprocess; None on failure."""
    try:
        r = subprocess.run(
            ["ps", "-axo", "pid=,ppid=,args="],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    out = []
    for line in r.stdout.splitlines():
        parts = line.split(None, 2)
        if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
            continue
        out.append((int(parts[0]), int(parts[1]), parts[2] if len(parts) > 2 else ""))
    return out


def proc_table():
    if os.path.isdir("/proc"):
        t = _proc_table_linux()
        if t is not None:
            return t
    return _proc_table_ps()


def harness_ancestors(table):
    """The pid set of this process's ancestors (a few hops: hook -> sh ->
    harness -> ...). WORKLIST_HARNESS_PID overrides for tests and for setups
    where the walk cannot see the harness. Matching workers against ANY
    ancestor is deliberate: it needs no knowledge of which ancestor is the
    harness binary, and a false positive requires an unrelated ancestor to
    have spawned a child whose cmdline embeds this exact command text."""
    override = os.environ.get("WORKLIST_HARNESS_PID", "")
    if override.isdigit():
        return {int(override)}
    if table is None:
        return set()
    parents = {pid: ppid for pid, ppid, _cmd in table}
    out, cur = set(), os.getpid()
    for _ in range(8):
        cur = parents.get(cur)
        if not cur or cur <= 1:
            break
        out.add(cur)
    return out


def _needle(command):
    """A distinctive, quote-free substring of a declared command, or ''.
    The harness wraps the command in an eval with shell re-quoting, so any
    line containing quote characters may be rewritten in the child cmdline;
    a quote-free line survives verbatim."""
    best = ""
    for line in (command or "").splitlines():
        line = line.strip()
        if "'" in line or '"' in line:
            continue
        if len(line) > len(best):
            best = line
    return best if len(best) >= 12 else ""


def verify_background(event_bg, table=None, ancestors=None):
    """{task_id: verdict} for RUNNING background tasks.

    Verdicts: 'confirmed' (a live descendant-of-harness process carries the
    command), 'suspect' (shell task, OS visible, no matching process found),
    'unverifiable' (teammate task, unusable needle, or no OS view). Only
    ever ADDS information; existence remains the event's word.
    """
    if table is None:
        table = proc_table()
    if ancestors is None:
        ancestors = harness_ancestors(table)
    out = {}
    for b in event_bg or []:
        tid = str(b.get("id") or "")
        if not tid:
            continue
        if b.get("type") != "shell" or not b.get("command"):
            out[tid] = "unverifiable"
            continue
        needle = _needle(b.get("command"))
        if not needle or table is None or not ancestors:
            out[tid] = "unverifiable"
            continue
        hit = any(
            ppid in ancestors and needle in cmd for _pid, ppid, cmd in table
        )
        out[tid] = "confirmed" if hit else "suspect"
    return out


def output_quiet_min(session_id, task_id):
    """Minutes since the task's output file (or its symlink target, the
    subagent transcript) last grew, or None if unreadable. The freshest
    signal wins; a symlink whose target moved is read through."""
    if not session_id or not task_id:
        return None
    scratch_roots = []
    tmp = os.environ.get("TMPDIR", "/tmp")
    # The observed layout: $TMPDIR/claude-<uid>/<proj-slug>/<session-id>/tasks/<id>.output
    try:
        uid = os.getuid()
    except AttributeError:
        uid = ""
    base = os.path.join(tmp, "claude-%s" % uid)
    if os.path.isdir(base):
        scratch_roots.append(base)
    newest = None
    for root in scratch_roots:
        try:
            for proj in os.listdir(root):
                p = os.path.join(root, proj, session_id, "tasks", task_id + ".output")
                try:
                    mtime = os.stat(p).st_mtime  # stat() follows symlinks
                except OSError:
                    continue
                if newest is None or mtime > newest:
                    newest = mtime
        except OSError:
            continue
    if newest is None:
        return None
    return (time.time() - newest) / 60.0


def worker_facts(event, session_id):
    """One human line per RUNNING background task, with everything the OS
    could add. This is the raw material for the ladder messages: facts, not
    verdicts, in the submodule_pointer_moves handover style."""
    live_bg = [b for b in (event.get("background_tasks") or []) if b.get("status") == "running"]
    verdicts = verify_background(live_bg)
    rows = []
    for b in live_bg:
        tid = str(b.get("id") or "?")
        v = verdicts.get(tid, "unverifiable")
        quiet = output_quiet_min(event.get("session_id", ""), tid)
        if v == "confirmed":
            osword = "OS process confirmed"
        elif v == "suspect":
            osword = "harness lists it as running but NO matching process was found (it may have just finished; check its output)"
        else:
            osword = "no OS-level check possible for this task type"
        rows.append(
            "%s (%s) %s; %s%s"
            % (
                tid,
                b.get("type") or "?",
                (b.get("description") or "")[:60],
                osword,
                "" if quiet is None else "; output quiet %dm" % quiet,
            )
        )
    return rows, verdicts


# ---- the ladder -------------------------------------------------------------

def _age_min(stamp):
    a = C.stamp_age_min(stamp)
    return a if a is not None else 0.0


def ladder(fold, session_id, event, state_doc):
    """(pings, investigates, resolves, doc_changed).

    Subjects: my fresh [>] items (age = minutes since their last store
    event) and my in_progress harness tasks (age = minutes since the status
    was first seen by this session, tracked in the state doc). A [>] whose
    declared worker: id is no longer listed by the harness enters
    investigate immediately, whatever its age -- that is the "ongoing with
    no worker to trace" gap this exists to catch.

    Once-per-rung: fired rungs are recorded against the stamp they fired at;
    the same rung re-fires only after the item's stamp moves (which also
    resets its age, so in practice it fires once per generation).
    """
    now_bg = {
        str(b.get("id") or ""): b
        for b in (event.get("background_tasks") or [])
        if b.get("status") == "running"
    }
    tasks_seen = state_doc.setdefault("tasks_seen", {})
    fired = state_doc.setdefault("ladder", {})
    changed = False

    subjects = []  # (key, label, age_min, stampkey, gone_worker)
    for rec in fold.items:
        if rec["state"] != ">" or not C.owned_by_me(rec["owner"], session_id):
            continue
        if C.lease_state(rec["line"]) != "fresh":
            continue  # expired leases are open items already
        wm = C.WORKER.search(rec["line"])
        wid = rec.get("worker") or (wm.group(1) if wm else "")
        gone = bool(wid) and wid not in now_bg
        subjects.append(
            ("item:" + rec["id"], rec["line"][:110], _age_min(rec.get("upd", "")), rec.get("upd", ""), gone, wid)
        )
    for tid, (status, subject) in sorted(C.task_statuses(event.get("session_id", "")).items()):
        prev = tasks_seen.get(tid)
        if prev is None or prev.get("status") != status:
            tasks_seen[tid] = {"status": status, "since": C.stamp_now()}
            changed = True
            prev = tasks_seen[tid]
        if status == "in_progress":
            subjects.append(
                ("task:" + tid, "task #%s %s" % (tid, subject), _age_min(prev.get("since", "")), prev.get("since", ""), False, "")
            )

    _ = blocking_rung_due  # the poll fast path's forfeit must agree with fire_once below
    pings, investigates, resolves = [], [], []
    for key, label, age, stampkey, gone, wid in subjects:
        rung_rec = fired.get(key) or {}

        def fire_once(rung):
            nonlocal changed
            if rung_rec.get(rung) == stampkey:
                return False
            rung_rec[rung] = stampkey
            fired[key] = rung_rec
            changed = True
            return True

        if gone:
            if fire_once("gone"):
                investigates.append(
                    "%s   <- its declared worker:%s is NOT in the harness background list any more "
                    "(finished or stopped); read its output, then finish the item, re-delegate with "
                    "a new worker id, or reclassify it" % (label, wid)
                )
            continue
        if age >= LADDER_RESOLVE_MIN:
            if fire_once("resolve"):
                resolves.append("%s   (no update for %dm)" % (label, age))
        elif age >= LADDER_INVESTIGATE_MIN:
            if fire_once("investigate"):
                investigates.append("%s   (no update for %dm)" % (label, age))
        elif age >= LADDER_PING_MIN:
            pings.append("%s   (no update for %dm)" % (label, age))
    return pings, investigates, resolves, changed
