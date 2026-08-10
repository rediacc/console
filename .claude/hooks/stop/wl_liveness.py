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

import json
import os
import re
import subprocess
import tempfile
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
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
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
    The harness wraps the command in an eval with shell re-quoting, so quote
    characters may be rewritten in the child cmdline; but re-quoting only
    inserts or replaces QUOTE characters, so any maximal quote-free run of
    the original text survives contiguously. Segments, not whole lines: the
    CI-watch poll loop is one long line with a quoted middle, and requiring
    the whole line quote-free left exactly that worker unverifiable, which
    let the pure-wait check-in call a healthy silent poll loop POSSIBLY
    STUCK (2026-07-31)."""
    best = ""
    for line in (command or "").splitlines():
        for raw_seg in re.split(r"['\"]", line):
            seg = raw_seg.strip()
            if len(seg) > len(best):
                best = seg
    return best if len(best) >= 12 else ""


def bg_output_facts(cwd, session_id, live_bg):
    """[(id, desc, age_min, size, stale)] for each running background task.

    v15 (operator, 2026-07-31): a session whose only remaining work is
    waiting on background jobs is in a LEGITIMATE state, but the hook must
    still know whether those jobs are alive. The harness writes each task's
    stream to <tmp>/<munged-cwd>/<session>/tasks/<id>.output; the mtime of
    that file is direct evidence of progress no self-report can fake. age is
    minutes since the last write (None when the file does not exist, e.g. a
    teammate agent that reports only at completion); stale is True when the
    file exists and has not grown for BG_STALE_MIN minutes.
    """
    base = os.environ.get("WORKLIST_BG_OUTPUT_DIR")
    if not base:
        munged = re.sub(r"[^A-Za-z0-9]", "-", str(cwd or ""))
        # The harness scratch root is <tmp>/claude-<uid>/ on this platform,
        # not <tmp>/ itself; the plain-gettempdir form is kept as a fallback
        # for setups where TMPDIR already points inside the scratch root.
        # Found live on the check-in's FIRST real firing: a shell task with a
        # growing output stream read as "no output stream yet" because the
        # derivation missed the claude-<uid> segment.
        tails = [str(session_id or ""), "tasks"]
        candidates = [
            os.path.join(tempfile.gettempdir(), "claude-%d" % os.getuid(), munged, *tails),
            os.path.join(tempfile.gettempdir(), munged, *tails),
        ]
        base = next((c for c in candidates if os.path.isdir(c)), candidates[0])
    rows = []
    for b in live_bg or []:
        tid = str(b.get("id") or "?")
        desc = (b.get("description") or b.get("command") or "")[:70]
        p = os.path.join(base, tid + ".output")
        try:
            st = os.stat(p)
            age = (time.time() - st.st_mtime) / 60.0
            rows.append((tid, desc, int(age), st.st_size, age >= BG_STALE_MIN))
        except OSError:
            rows.append((tid, desc, None, 0, False))
    return rows


BG_STALE_MIN = int(os.environ.get("WORKLIST_BG_STALE_MIN", "15"))
BG_REPORT_MIN = int(os.environ.get("WORKLIST_BG_REPORT_MIN", "15"))


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
        hit = any(ppid in ancestors and needle in cmd for _pid, ppid, cmd in table)
        out[tid] = "confirmed" if hit else "suspect"
    return out


# The inbox waiter (wl_wait.py) launched as a background shell task. Matched on
# the SCRIPT NAME in the declared command, which is the only stable marker: the
# task id is per-launch and the description is free text.
WAITER_MARK = "wl_wait.py"


def waiter_tasks(live_bg):
    """Running background tasks that are inbox waiters."""
    return [
        b
        for b in live_bg or []
        if isinstance(b, dict)
        and b.get("type") == "shell"
        and WAITER_MARK in str(b.get("command") or "")
    ]


def confirmed_waiters(live_bg, verdicts):
    """Waiters whose liveness the OS has CONFIRMED, never merely claimed.

    Both callers in wl_checks trade a supervision demand for this verdict, so
    `confirmed` is the only verdict that may buy the trade. A waiter that is
    `suspect` or `unverifiable` is treated exactly as any other background task:
    it still owes the check-in and it still does not substitute for a poll cron.
    That is the safe direction -- the whole argument for relaxing those checks is
    that this process's EXIT is itself the wake-up, which is worth nothing if
    nobody can see the process.
    """
    return [
        b
        for b in waiter_tasks(live_bg)
        if (verdicts or {}).get(str(b.get("id") or "")) == "confirmed"
    ]


TEAMMATE_FRESH_MIN = float(os.environ.get("WORKLIST_TEAMMATE_FRESH_MIN", "15"))


def live_teammate_transcripts(cwd, fresh_min=None, session_id=""):
    """How many in-process teammates have a transcript that is still growing.

    THE ONLY AUTOMATIC LIVENESS SIGNAL THAT EXISTS FOR TEAMMATES, and it exists
    because `verify_background` cannot help: it returns `unverifiable` for
    anything whose type is not "shell", and a teammate has no OS process of its
    own to find. A teammate that is working writes to its transcript; one that
    stopped does not.

    Deliberately a COUNT and not a mapping. There is no join from a background
    task id to an agent: the task carries only {id, type, status, description},
    the description is the PROMPT truncated to ~50 characters, and that prefix is
    provably not unique -- measured on a live roster, 10 of 19 teammate tasks
    collided on it ("You are an Opus writer sub-agent in /home/muh..." matched
    five different agents). The disambiguating text is exactly what the
    truncation removes, so no amount of care recovers it.

    Reads the filesystem, never the session's memory, so it is unaffected by a
    compaction -- which is the case this exists for.
    """
    import wl_report as RPT  # noqa: PLC0415 -- stdlib-only sibling, no cycle

    fresh_min = TEAMMATE_FRESH_MIN if fresh_min is None else fresh_min
    proj = RPT._projects_dir() / RPT._munged(C.project_root(C.project_start({"cwd": cwd})))
    if not proj.is_dir():
        return None  # cannot tell: NOT the same as zero, and callers must differ
    # SCOPED TO THE CALLING SESSION. It previously globbed `*/subagents/*` --
    # every session directory under the project -- so ANY unrelated session with
    # a teammate transcript touched in the last fresh_min made `fresh > 0` here,
    # for a session whose own roster might be 100% phantom. That silently
    # defeated the certainty branch in prune_background (fresh == 0 is what
    # licenses the auto-reap) in exactly the situation it was built for: a
    # session resumed after compaction, which is when OTHER sessions are most
    # likely to be active in the same tree. It also deflated the `unknown`
    # overclaim count reported to the operator. This tree runs concurrent
    # sessions as a matter of course, so the collision was routine, not exotic.
    scope = proj / session_id / "subagents" if session_id else None
    if scope is not None and not scope.is_dir():
        # FAIL TO "CANNOT TELL", NEVER TO ZERO. Zero is the value that licenses
        # reaping the whole teammate roster, so a session id that does not
        # resolve to a directory (a prefix instead of a full uuid, a store not
        # yet created) must not be read as "no teammates are alive".
        return None
    metas = scope.glob("*.meta.json") if scope is not None else proj.glob("*/subagents/*.meta.json")
    now, fresh = time.time(), 0
    for meta in metas:
        try:
            info = json.loads(meta.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            continue
        if not isinstance(info, dict) or info.get("taskKind") != "in_process_teammate":
            continue
        jsonl = meta.with_name(meta.name[: -len(".meta.json")] + ".jsonl")
        try:
            if (now - jsonl.stat().st_mtime) / 60.0 <= fresh_min:
                fresh += 1
        except OSError:
            continue
    return fresh


def reaped_path(worklist, session_id):
    return worklist.with_suffix(".reaped-%s" % (session_id or "unknown")[:8])


def read_reaped(worklist, session_id):
    """Task ids this session has declared dead. Append-only, one id per line."""
    try:
        return {
            ln.strip()
            for ln in reaped_path(worklist, session_id)
            .read_text(encoding="utf-8", errors="replace")
            .splitlines()
            if ln.strip()
        }
    except OSError:
        return set()


def prune_background(event_bg, worklist, session_id, cwd):
    """(live, dropped, unknown) -- the roster with provably-dead entries removed.

    TWO MECHANISMS, and the split is the whole safety argument.

    AUTOMATIC, and only where it is a CERTAINTY: when NOT ONE teammate transcript
    is fresh, every teammate task in the roster is dead, whatever its id. No join
    is needed to know that, and nothing live can be hidden by it -- if even one
    teammate were working, its transcript would be growing and this branch would
    not be taken. This is the compaction case: a session reopened hours later
    inherits a roster of twenty and none of them exist.

    MANUAL for the in-between. With some transcripts fresh but fewer than the
    roster claims, at least (claimed - fresh) are dead and NOTHING CAN SAY WHICH.
    Guessing there would mean dropping a live worker's supervision, which is
    worse than a stale entry, so those are KEPT and reported as `unknown` -- and
    the session can retire specific ids by hand with `worklist.py --reap`.
    """
    bg = [b for b in (event_bg or []) if isinstance(b, dict)]
    reaped = read_reaped(worklist, session_id)
    bg = [b for b in bg if str(b.get("id") or "") not in reaped]
    mates = [b for b in bg if b.get("type") == "teammate"]
    if not mates:
        return bg, [], 0
    fresh = live_teammate_transcripts(cwd, session_id=session_id)
    if fresh is None:
        return bg, [], 0  # cannot see the store: claim nothing, change nothing
    if fresh == 0:
        return [b for b in bg if b.get("type") != "teammate"], mates, 0
    unknown = max(0, len(mates) - fresh)
    return bg, [], unknown


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
        # The PARAMETER, not a second read of the event. Both carry the same
        # value today (wl_checks.py:1471 derives it from this very event), but
        # one source at the call boundary cannot drift from the other.
        quiet = output_quiet_min(session_id, tid)
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
    """(pings, investigates, resolves, gones, doc_changed).

    `gones` is kept apart from `investigates` because a verifiably dead worker
    needs a different remedy than a merely quiet one; see the gone branch.

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
            (
                "item:" + rec["id"],
                rec["line"][:110],
                _age_min(rec.get("upd", "")),
                rec.get("upd", ""),
                gone,
                wid,
            )
        )
    for tid, (status, subject) in sorted(
        C.task_statuses(event.get("session_id", ""), event.get("transcript_path")).items()
    ):
        prev = tasks_seen.get(tid)
        if prev is None or prev.get("status") != status:
            tasks_seen[tid] = {"status": status, "since": C.stamp_now()}
            changed = True
            prev = tasks_seen[tid]
        if status == "in_progress":
            subjects.append(
                (
                    "task:" + tid,
                    "task #%s %s" % (tid, subject),
                    _age_min(prev.get("since", "")),
                    prev.get("since", ""),
                    False,
                    "",
                )
            )

    _ = blocking_rung_due  # the poll fast path's forfeit must agree with fire_once below
    pings, investigates, resolves, gones = [], [], [], []
    for key, label, age, stampkey, gone, wid in subjects:
        rung_rec = fired.get(key) or {}

        # The loop variables are bound as DEFAULTS, not closed over. B023 is a
        # false positive at this particular site -- fire_once is only ever
        # called inside the same iteration that defines it, never stored or
        # deferred, so the late-binding bug it warns about cannot happen here.
        # Binding them anyway is free and provably equivalent, and it keeps
        # B023 enabled for the sites where the warning WOULD be real; turning
        # the rule off to clear six known-safe uses is how the next genuine
        # late-binding bug ships unnoticed.
        def fire_once(rung, rung_rec=rung_rec, stampkey=stampkey, key=key):
            nonlocal changed
            if rung_rec.get(rung) == stampkey:
                return False
            rung_rec[rung] = stampkey
            fired[key] = rung_rec
            changed = True
            return True

        if gone:
            # SEPARATE from `investigates` on purpose. Both are 90-minute-rung
            # blocks, but they have DIFFERENT remedies, and merging them meant
            # the caller printed one footer for both: `--update`, which is the
            # one command that cannot resolve a dead worker. It refreshes the
            # text and the liveness clock and leaves the false worker:<id> in
            # place, so the identical complaint fires on the very next stop.
            # Measured, not theorised: it cost a session a full round trip.
            if fire_once("gone"):
                gones.append(
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
    return pings, investigates, resolves, gones, changed
