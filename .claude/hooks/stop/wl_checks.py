"""wl_checks: the static check battery and the Stop-path orchestration.

This is the v5-v9 main() stop path, extracted, consuming the v10 store fold
instead of raw markdown lines, plus the v10 additions: the liveness ladder,
the deferral autonomy window, and the judge verdict cache. Ordering is
load-bearing throughout -- emit() exits the process, so anything after a
block never runs -- and every WHY comment travels with its check.
"""

import hashlib
import json
import os
import pathlib
import re
import time

import wl_ci
import wl_core as C
import wl_email
import wl_judge
import wl_liveness
import wl_reggate
import wl_report
import wl_wait
import wl_requests
import wl_store as S
import worklist_messages as M

# Heading, any level, so "## Remaining" and "### Remaining work" both count.
REMAINING_HEADING = re.compile(r"^[ \t]{0,3}#{1,4}[ \t]*Remaining\b", re.M | re.I)

# Consecutive stops that may move nothing before the hook demands a planning or
# investigation agent. Three is the operator's number, not a guess.
STUCK_ROUNDS = int(os.environ.get("WORKLIST_STUCK_ROUNDS", "3"))
# How recently the in-flight item must have been refreshed for the session to count as
# SUPERVISING a long background job rather than having forgotten it.
#
# 70, matching POLL_FULL_MAX_MIN below and for the same reason: JUST OVER the hourly
# work loop. A session on an hourly cron refreshes its item once an hour, so any
# threshold under 60 leaves a window every hour where a perfectly healthy campaign
# reads as unsupervised. It was 45 for exactly one evening and fired twice that way --
# at 46 and 48 minutes, both times on a batch that was running fine and reported again
# minutes later. A threshold tighter than the reporting cadence does not detect
# neglect, it just re-times the false alarm.
STUCK_SUPERVISED_MAX_MIN = int(os.environ.get("WORKLIST_STUCK_SUPERVISED_MAX_MIN", "70"))

# v12 CI-WAITING FORCE (operator, 2026-07-30: "is current session sitting for
# CI pipeline? If so, it should FORCE current session to work on waiting
# items!!! There is no valid reason to wait."). When every running background
# task is a CI watch, deferrals that have sat at least CI_FORCE_MIN_AGE are
# demanded, CI_FORCE_PER_STOP at a time. The age floor is itself an exit: a
# deferral re-justified with a fresh WHY/HOW leaves the demand window, so an
# honest answer -- not only doing the work -- always reaches an allowed stop.
CI_FORCE_MIN_AGE = int(os.environ.get("WORKLIST_CI_FORCE_MIN_AGE", "15"))
CI_FORCE_PER_STOP = int(os.environ.get("WORKLIST_CI_FORCE_PER_STOP", "3"))

DESIGN_DOCS = os.environ.get("WORKLIST_DESIGN_DOCS", "docs/ci-overhaul")
DOCS_DRIFT_MAX = int(os.environ.get("WORKLIST_DOCS_DRIFT_MAX", "10"))
# What counts as "the program surface": changing these is changing the thing the
# design docs describe.
PROGRAM_SURFACE = os.environ.get("WORKLIST_PROGRAM_SURFACE", ".ci .github .claude").split()

# ---- v9 poll constants ------------------------------------------------------
# The poll cron is recognised by SCHEDULE SHAPE, not by id or prompt text:
# schedules are structural, survive restarts, and a work cron cannot claim the
# shape without also BECOMING a 5-minute loop.
# A BACKOFF LADDER, not a single cadence: 5 -> 10 -> 20 -> 40 -> 60 minutes.
#
# The cadence was a bare literal while its two immediate neighbours below are both env-backed,
# which made it the one knob in this block nobody could turn -- and it is the expensive one. A
# quiet session at `*/5` pays 12 poll firings an hour forever, and this session ran ~25
# consecutive empty polls before anyone noticed the cost.
#
# Each rung DOUBLES, so a session that keeps finding an empty inbox keeps halving its own
# overhead: 12/hr -> 6 -> 3 -> 1.5 -> 1. The ladder is capped at 60 minutes because the
# fast-path horizon is 70 (POLL_FULL_MAX_MIN below) -- a poll slower than that could never
# take the silent path, so every firing would pay the full battery and the backoff would
# start costing more than it saves. `0 * * * *` is the hourly top rung; `*/60` is not valid
# cron for it.
#
# Escalation is not automatic: the Stop hook TELLS the session when a doubling is due (see
# poll_backoff_tip) and the session performs the CronDelete/CronCreate itself, so the change
# is visible in the transcript rather than happening behind the operator's back. A session
# that receives a real request should drop back to `*/5` by the same mechanism.
#
# Deliberately an allowlist of the ladder rungs, not an open dial: an arbitrary `*/7` would
# silently desynchronise from the windows that assume this shape.
POLL_SCHEDULE_RE = re.compile(
    os.environ.get("WORKLIST_POLL_SCHEDULE_RE", r"^(\*/(5|10|20|40)( \*){4}|0( \*){4})$")
)

#: The rungs, in order, for poll_backoff_tip. Minutes -> the cron schedule that expresses it.
POLL_BACKOFF_LADDER = [
    (5, "*/5 * * * *"),
    (10, "*/10 * * * *"),
    (20, "*/20 * * * *"),
    (40, "*/40 * * * *"),
    (60, "0 * * * *"),
]
# A poll marker older than this cannot vouch for THIS stop. The marker is
# single-use (consumed on first sight), so the window only needs to cover one
# poll turn; too small merely costs one full battery, the safe direction.
POLL_WINDOW_S = int(os.environ.get("WORKLIST_POLL_WINDOW_S", "600"))
# The fast path expires: at most this many minutes since the last banked
# baseline before a poll stop pays the battery again. Just over the hourly
# work loop, so the shape is one full report per hour with free polls
# between, and a session cannot live on polls alone.
POLL_FULL_MAX_MIN = int(os.environ.get("WORKLIST_POLL_FULL_MAX_MIN", "70"))
# Request ids are sha1[:8], so 8 hex chars; a #id on a Remaining line is only
# accepted if it also resolves in the .requests log, so a task id that happens
# to be 8 digits cannot satisfy the state by shape alone.
XSESSION_ID_RE = re.compile(r"#([0-9a-f]{8})\b")


def poll_backoff_tip(live_crons, quiet_min, has_open_requests):
    """One line telling the session to move a rung on POLL_BACKOFF_LADDER, or "".

    ADVISORY, never blocking. The session performs the CronDelete/CronCreate itself, so a
    cadence change is visible in the transcript instead of happening behind the operator's
    back -- and a session that disagrees can simply not act on it.

    Escalates after `quiet_min` exceeds 4x the current rung (at */5 that is 20 minutes of an
    empty inbox), which is slow enough that one straggling request does not immediately
    double the latency for the next one. De-escalates straight back to the bottom rung the
    moment a real request is waiting, because latency matters again exactly then.
    """
    polls = [c for c in live_crons if is_poll_cron(c)]
    if len(polls) != 1:
        return ""  # the shape checks own this case; do not pile on
    sched = " ".join(str(polls[0].get("schedule", "")).split())
    rungs = [s for _, s in POLL_BACKOFF_LADDER]
    if sched not in rungs:
        return ""
    i = rungs.index(sched)
    cur_min = POLL_BACKOFF_LADDER[i][0]

    if has_open_requests:
        if i == 0:
            return ""
        return M.N_POLL_BACKOFF_RESET % (sched, POLL_BACKOFF_LADDER[0][1])
    if i + 1 >= len(POLL_BACKOFF_LADDER):
        return ""  # already at the 60-minute cap
    if quiet_min < cur_min * 4:
        return ""
    nxt_min, nxt = POLL_BACKOFF_LADDER[i + 1]
    return M.N_POLL_BACKOFF % (int(quiet_min), cur_min, sched, nxt, nxt_min)


# ---- v17: the NO-OP WAKE LADDER ---------------------------------------------
# WHY (operator, 2026-08-04): "normally there is exponential backoff for the
# stop hook. It seems it's running every 5 mins." The ladder above existed and
# never fired usefully during a pure background wait: it measures INBOX quiet
# time, so it says nothing about a session whose wakes are empty for every
# other reason, and it is queued behind the very report it is trying to
# replace at one advisory section per stop.
#
# This is the missing half: the hook counts wakes on which it can PROVE
# nothing moved, and once it has three in a row the whole stop collapses to
# one line asking for the next rung. Three, not one, because the streak is
# what makes the claim honest -- a single quiet wake happens constantly
# between two real ones -- and because at */5 three wakes is 15 minutes, the
# same window as the background check-in it stands in for, so the collapsed
# message can never arrive sooner than the report it replaces.
QUIET_WAKES_TO_RESCHEDULE = int(os.environ.get("WORKLIST_QUIET_WAKES", "3"))


def quiet_wake_sig(st_sig, fold, session_id, live_bg, bg_facts, bg_verdicts):
    """Everything a wake could have changed, in one key.

    st_sig carries item STRUCTURE, task statuses and HEAD. Added on top for
    this session's OWN items: the update stamp AND the latest note. The stamp
    alone is not enough and the suite caught it -- stamps are second
    resolution, so an --update landing in the same second as the lease it
    follows moves nothing, and a session doing exactly what the liveness
    ladder asks of it read as silent. The note is content, so it moves
    whenever the session actually said something new.

    The worker half is the OUTPUT SIZE rather than the stream's mtime-age
    (which advances on its own and would reset the streak every stop by simply
    existing), plus the live id set, plus each worker's OS-liveness verdict.
    The verdict is in here because it is the one thing about a background wait
    that can change while every byte on disk stays identical: a worker that
    was confirmed alive and is now suspect must never be silenced by a streak
    counter."""
    rows = sorted(
        "%s:%s:%s" % (tid, "?" if size is None else size, bg_verdicts.get(tid, "?"))
        for tid, _desc, _age, size, _stale in bg_facts
    )
    ids = ",".join(sorted(str(b.get("id") or "") for b in live_bg))
    try:
        own = ";".join(
            "%s:%s:%s:%s" % (
                r["id"], r["state"], r.get("upd") or "",
                hashlib.sha1(
                    str(r.get("lastnote") or "").encode("utf-8", "replace")
                ).hexdigest()[:8],
            )
            for r in sorted(fold.items, key=lambda x: x["id"])
            if C.owned_by_me(r.get("owner"), session_id)
        )
    except Exception:  # noqa: BLE001 -- an unreadable store must not wedge a stop
        own = "unreadable"
    return hashlib.sha1(
        ("%s|%s|%s|%s" % (st_sig, own, ids, ";".join(rows))).encode("utf-8", "replace")
    ).hexdigest()[:16]


def quiet_wake_bump(state_doc, sig, quiet):
    """The consecutive-no-op-wake counter, and it persists in the per-session
    state doc so it survives the process, a restart and a compaction. Any real
    event -- a changed signature or a stop that had something to say -- resets
    it to zero, so the streak can only ever describe consecutive silence."""
    q = state_doc.setdefault("quietwake", {})
    if not quiet:
        q["n"], q["sig"] = 0, sig
    elif q.get("sig") != sig:
        q["n"], q["sig"] = 1, sig
    else:
        q["n"] = int(q.get("n") or 0) + 1
    return int(q["n"])


def quiet_wake_note(live_crons, streak):
    """The ONE message a proven-quiet wake gets, or "" to fall through to the
    normal report.

    Empty when the poll cron is not a single recognisable rung: the cron-shape
    checks own that case, and collapsing the report to a reschedule
    instruction the session cannot act on would hide the real output and offer
    nothing back."""
    polls = [c for c in live_crons if is_poll_cron(c)]
    if len(polls) != 1:
        return ""
    sched = " ".join(str(polls[0].get("schedule", "")).split())
    rungs = [s for _, s in POLL_BACKOFF_LADDER]
    if sched not in rungs:
        return ""
    i = rungs.index(sched)
    cur_min = POLL_BACKOFF_LADDER[i][0]
    if i + 1 >= len(POLL_BACKOFF_LADDER):
        return M.N_QUIET_WAKE_CAPPED % (streak, cur_min)
    nxt_min, nxt = POLL_BACKOFF_LADDER[i + 1]
    return M.N_QUIET_WAKE % (streak, cur_min, sched, nxt, nxt_min)


def broken_schedules(event, now=None):
    """The scheduled tasks whose schedule this hook cannot parse, as
    "<schedule> -- <label>" rows. Empty when every schedule is readable.

    THIS IS WHAT SURVIVES the v18 deletion of the NEXT WAKEUPS section
    (operator, 2026-08-04: "we don't need to print next wakeup times. We
    should just track the hook moments and notify/warn when needed. let's go
    for efficient ai context usage"). The section printed every task's next
    firing on every single stop, which is context spent on a fact nobody acts
    on -- the schedules are in the harness, and a session that wants them can
    read them there.

    One line of it WAS actionable and does not survive deletion on its own: a
    schedule the hook cannot parse. That task will never be reasoned about by
    the cron-shape checks, the backoff ladder or the loop-death detector, and
    a list that silently omitted it would read as "nothing else is scheduled"
    -- the pass-quietly failure this hook bans. So the timing display is gone
    and the warning stays, which is exactly the trade the instruction asks
    for: silent when there is nothing to act on, one focused message when
    there is."""
    rows = []
    for c in event.get("session_crons") or []:
        sched = str(c.get("schedule", ""))
        if C.cron_next(sched, now) is not None:
            continue
        stripped_prompt = str(c.get("prompt", "")).strip()
        label = stripped_prompt.splitlines()[0][:90] if stripped_prompt else "(no prompt)"
        rows.append("    %r -- %s" % (sched, label))
    return rows


def is_poll_cron(c):
    if not isinstance(c, dict):
        return False
    sched = " ".join(str(c.get("schedule", "")).split())
    return bool(POLL_SCHEDULE_RE.match(sched))


def pollmark_path(worklist, prefix):
    return worklist.with_suffix(".pollmark-%s" % (prefix or "unknown")[:8])


def pollbase_path(worklist, session_id):
    return worklist.with_suffix(".pollbase-%s" % (session_id or "unknown")[:8])


def bank_pollbase(worklist, session_id, sig):
    """Record the world as the poll fast path's baseline.

    OPERATOR DECISION, 2026-07-30, overriding the original v9 rule that only an
    ALLOWED stop may bank. The original rule deadlocked in practice: a session
    with any open task blocks on the Remaining check, a blocked stop never
    reached the write, and with no baseline every five-minute poll paid the full
    battery -- while each of those polls was itself another stop that moved
    nothing, feeding the stuck detector. Measured on that session: pollbase was
    never created once across an entire night.

    Banking on a blocked stop is deliberately NOT an escape hatch, because the
    baseline is only half the fast path. poll_fast_path still recomputes every
    other condition from artifacts (single-use marker, horizon, unchanged world
    signature, cron shape, no open or undefaulted or expired-lease items, empty
    inbox). What banking buys is only this: a poll that changes nothing can
    recognise that nothing changed. The moment real work lands, the signature
    moves and the battery returns on its own.
    """
    try:
        pollbase_path(worklist, session_id).write_text(
            json.dumps({"sig": sig, "at": C.stamp_now()}), encoding="utf-8"
        )
    except OSError:
        pass


# ---- stuck detection --------------------------------------------------------

def stuck_rounds(worklist, session_id, tasks, head, exempt, supervised=False, own_stamp=""):
    """(count, fired, why) -- how many consecutive stops have moved NOTHING?

    THE OPERATOR'S RULE, IN THEIR WORDS: "I'd go with employing a
    planning/investigation agent if we cannot solve in last 3 round." Three
    identical stops means the APPROACH is wrong, not that it deserves a fourth
    attempt. The remedy is prescribed rather than left open, because "try
    harder" is what a stuck session already believes it is doing.

    The signature is deliberately COARSE: the harness task list plus HEAD. A
    commit moves it, ticking a task moves it, changing a task's status moves
    it. Talking does not. That is the point, since every one of the failures
    this catches involved a session that was producing text and no artifacts.

    It fires and then RESETS, so it nags at 3, 6, 9 rather than every stop once
    stuck. A session needs room to actually run the agent it was told to run,
    and a check that fires forever is one the session learns to route around.

    TWO TIERS, because a single signature can be bought off. The first version
    of this shipped with a DEAD head leg (it resolved the repo from the
    worklist's own tmp directory, so git returned nothing and the docstring's
    "a commit moves it" was false for every real stop). Fixing that naively
    would have been worse than the bug: any commit, including a one-line doc
    tweak, would reset the counter, so the commit-trivia treadmill and the
    eleven-push storm would both escape. So:

      * TASKS-ONLY signature, threshold 2x. Commits cannot touch it. This is
        what catches a session committing noise while the real problem sits.
      * TASKS+HEAD signature, threshold 1x. Real progress resets this sooner.

    Commits buy slack, never immunity.

    `exempt` (a live background task) suppresses the ordinary fire, because the
    remedy is already running. It does NOT stop the counting: a watch left
    running forever would otherwise silence this permanently, so at 3x the
    threshold it fires anyway to say the remedy itself has stalled.

    `supervised` is the ONE case where that 3x overrun is wrong. The overrun
    exists to catch a FORGOTTEN watch -- the deadlocked-poller failure, where a
    background task is alive but nobody is reading it. It cannot, on its own,
    tell that apart from a long job the session is actively supervising: a
    multi-hour render or migration legitimately changes no task status for
    hours, and firing at it every stop teaches the session to argue with this
    check rather than act on it, which is how a check stops being believed.

    So the caller passes supervised=True only when BOTH hold: a background task
    is live AND the session's in-flight worklist item was refreshed recently.
    That second half is what a forgotten watch can never satisfy, because
    refreshing the item is exactly the thing nobody is doing. Counting still
    continues, and the moment the session stops reporting, the item goes quiet
    and this fires as designed.
    """
    # tasks are (id, subject, status); the STATUS is what has to move.
    # v14 gap 2: `own_stamp` (the newest upd stamp across this session's own
    # worklist items) rides both signatures. The v13 night proved the harness
    # task list alone is too narrow an evidence base: a session shipping
    # commits and ticking worklist items hourly read as "stuck 92 stops"
    # because its long-horizon harness tasks legitimately never flipped.
    # Worklist activity is real movement; a genuinely stuck session produces
    # none, so the catch is intact.
    base = "|".join(sorted("%s:%s" % (i, st) for i, _, st in tasks)) + "@" + (own_stamp or "")

    def dig(s):
        return hashlib.sha1(s.encode("utf-8", "replace")).hexdigest()[:12]

    sigs = (dig(base), dig(base + "#" + (head or "")))
    p = worklist.with_suffix(".stuck-%s" % (session_id or "unknown")[:8])
    try:
        parts = p.read_text().strip().split()
        prev, counts = (parts[0], parts[1]), [int(parts[2]), int(parts[3])]
    except (OSError, ValueError, IndexError):
        prev, counts = ("", ""), [0, 0]
    counts = [c + 1 if sigs[i] == prev[i] else 1 for i, c in enumerate(counts)]

    # thresholds: tasks-only is slower to fire, tasks+HEAD is the normal one
    limits = (STUCK_ROUNDS * 2, STUCK_ROUNDS)
    hit = [i for i in (0, 1) if counts[i] >= limits[i]]
    why = ""
    if hit and exempt:
        # A running agent excuses the ordinary fire, but not forever.
        hit = [i for i in hit if counts[i] >= limits[i] * 3]
        # ...unless the session is demonstrably watching it. See the docstring:
        # the overrun targets a forgotten watch, not a supervised long job.
        if supervised:
            hit = []
        why = "exempt-overrun" if hit else ""
    elif hit:
        why = "tasks-only" if 0 in hit else "tasks+head"
    fired = bool(hit)
    try:
        p.write_text(
            "%s %s %d %d"
            % (sigs[0], sigs[1], *[0 if i in hit else counts[i] for i in (0, 1)])
        )
    except OSError:
        pass
    return max(counts), fired, why


# ---- citations and completion evidence --------------------------------------

CITE_RE = re.compile(
    # LEADING DOT ALLOWED. `\b[\w]` cannot start on a dot, so `.ci/x.sh:9`
    # matched but CAPTURED `ci/x.sh`, which resolves to nothing on disk. That
    # silently excluded `.ci/`, `.github/` and `.claude/`, which is most of this
    # program's surface: a citation check that looked strict was unsatisfiable
    # for exactly the paths it most needed to accept. Caught by the check firing
    # on a tick of mine that cited .ci/scripts/autopilot/autopilot-gate.sh.
    r"(?<![\w./-])(\.?[\w][\w./-]*\.(?:py|ts|tsx|js|cjs|mjs|sh|json|md|ya?ml|go|toml))"
    r":(\d+)(?:-\d+)?\b"
)


def citation_state(root, text):
    """(ok, detail) -- does this line cite a source that REALLY says so?

    The Wave C failure was a blocker nobody had verified: "blocked on Wave B
    landing", when 05-execution-guide.md:108 says the opposite in plain words.
    Nothing in the hook challenged it, because the shape of the report was
    valid and only its content was wrong.

    Requiring a <path>:<line> is not bureaucracy, it is a FORCING FUNCTION:
    producing the citation means opening the file, and opening that file is the
    exact moment the claim collapses. So the check is deliberately cheap and
    deliberately not clever. It proves the file exists and the line is real,
    nothing more. Whether the cited text actually SUPPORTS the claim is the
    judge's question, and the citation is what lets the judge read it.
    """
    m = CITE_RE.search(text or "")
    if not m:
        return False, "carries no <path>:<line> citation"
    rel, line = m.group(1), int(m.group(2))
    p = pathlib.Path(root) / rel
    if not p.is_file():
        return False, "cites %s, which does not exist" % rel
    try:
        n = len(p.read_text(errors="replace").splitlines())
    except OSError:
        return False, "cites %s, which cannot be read" % rel
    if line > n:
        return False, "cites %s:%d but that file has only %d lines" % (rel, line, n)
    return True, "%s:%d" % (rel, line)


def cited_excerpts(root, message, limit=3, span=4):
    """Quote what the session cited, so the judge can check it rather than guess.

    The citation check (citation_state) only proves a source EXISTS. That is the
    cheap half, and on its own it is gameable: any real file and any in-range
    line satisfies it, including one that says the opposite of the claim. This
    supplies the text so the expensive half can happen in the judge, which is
    already being paid for on quiet stops.

    Bounded on purpose. At most `limit` citations, +/- `span` lines each, so the
    prompt grows by a few hundred tokens rather than with the size of the
    program. Whole-document injection was considered and rejected: docs/ alone
    is thousands of lines and the cost would scale with the repo.
    """
    out, seen = [], set()
    for m in CITE_RE.finditer(message or ""):
        rel, line = m.group(1), int(m.group(2))
        if (rel, line) in seen:
            continue
        seen.add((rel, line))
        p = pathlib.Path(root) / rel
        try:
            lines = p.read_text(errors="replace").splitlines()
        except OSError:
            continue
        if line > len(lines):
            continue
        lo, hi = max(0, line - 1 - span), min(len(lines), line + span)
        body = "\n".join(
            "    %s%d| %s" % (">" if n == line else " ", n, lines[n - 1])
            for n in range(lo + 1, hi + 1)
        )
        out.append("  %s:%d\n%s" % (rel, line, body))
        if len(out) >= limit:
            break
    return "\n".join(out)


RUN_ID_RE = re.compile(r"\b\d{9,}\b")
EXIT_RE = re.compile(r"\bexit(?:\s+code)?\s*[:=]?\s*\d+\b", re.I)
URL_RE = re.compile(r"https?://\S+")
SHA_RE = re.compile(r"\b[0-9a-f]{7,40}\b")


def completion_evidence(root, text):
    """Does `text` carry something evidence-shaped for a completion claim?

    Shapes, cheapest first: a run-id-sized number, an exit code, a URL, a
    file:line that RESOLVES (citation_state, so a fabricated path or line
    fails), or a hex string naming a REAL git object (verified, so a
    decorative 'deadbee' cannot pass; at most five candidates checked to
    bound the git calls). Deliberately shape-based: whether the evidence
    SUPPORTS the claim is the reggate judge's question, since every new tick
    already flows into it. This check only guarantees a completion leaves a
    RECORD, which is exactly what S-2 lacked."""
    if RUN_ID_RE.search(text) or EXIT_RE.search(text) or URL_RE.search(text):
        return True
    if citation_state(root, text)[0]:
        return True
    for m in list(SHA_RE.finditer(text))[:5]:
        if C._git(root, "rev-parse", "--verify", "--quiet", m.group(0) + "^{object}"):
            return True
    return False


# v16: an issue reference is a URL, and completion_evidence passes on ANY URL
# by shape, so `--tick <me> <id> 'filed as .../issues/560'` closed a finding.
# That is the loophole the fix-in-session rule outlaws: filing settles nothing
# unless one of the three last-resort doors applies, and the tick has to say
# WHICH. Shape-only, the same division of labor as the WHY/HOW gate: whether
# the named door is TRUE is the judge's question, and every new tick already
# flows into the reggate/judge path.
ISSUE_REF_RE = re.compile(
    r"\S*github\.com/\S+/issues/\d+\S*|\bissues?\s+#\d+", re.I
)
DOOR_RE = re.compile(r"door:(operator-only|operator-deferred|no-write-access)")


def issue_only_evidence(root, text):
    """True iff the evidence is ONLY an issue reference.

    Three conditions, all required: an issue reference is present, no door is
    named, and the text with issue references stripped carries no other
    evidence shape. So a tick that ALSO cites the fix (a real sha, an exit
    code, a run URL, a resolving file:line) passes, and only "I filed it"
    is refused.
    """
    if not ISSUE_REF_RE.search(text):
        return False
    if DOOR_RE.search(text):
        return False
    return not completion_evidence(root, ISSUE_REF_RE.sub(" ", text))


def deferral_is_justified(rec):
    """Does this [?] carry a usable WHY and HOW (event field or inline
    tokens)? The shape test only; whether the justification is TRUE is the
    judge audit's question."""
    j = S.deferral_justification(rec)
    return bool(j.get("why") and j.get("how"))


# ---- cron memory and docs drift --------------------------------------------

def loop_finished_declared(last_msg):
    """True when the session explicitly declares its work loop is over.

    V_LOOP_DIED offers two ways out: recreate the cron, OR "say out loud in your
    message that the loop is deliberately finished". The second branch DID NOT
    EXIST -- cron_memory compared a high-water mark and never read the message.
    A session that finished its campaign, retired its cron on purpose and said
    so plainly was blocked again on the very next stop, with no wording that
    could ever satisfy the check. The block text promised an affordance the code
    did not implement, which is worse than not offering it: it sends the session
    hunting for the right phrase instead of telling it to recreate the cron.

    Backticked and quoted spans are stripped before matching, following the
    V_FOUND_NOT_FIXED precedent that a gate which cannot survive being written
    about is too broad. It matters more here than there: this is an OPT-OUT, so
    a message merely QUOTING the instruction (as any message discussing this
    check does) must not silently switch the check off.
    """
    if not last_msg:
        return False
    stripped = re.sub(r"`[^`]*`|\"[^\"]*\"|“[^”]*”", " ", last_msg)
    done = r"(?:finished|done|completed?|retired|ended|over)"
    how = r"(?:deliberately|intentionally|on purpose)"
    return bool(
        re.search(r"\bloop\b[^.\n]{0,60}?\b%s\s+%s\b" % (how, done), stripped, re.I)
        or re.search(r"\b%s\s+%s\b[^.\n]{0,60}?\bloop\b" % (how, done), stripped, re.I)
    )


def cron_memory(worklist, session_id, live_count, declared_done=False):
    """(died, remembered_max) -- was a loop running before that is gone now?

    WHY THIS REPLACED A DECLARATION. v5 first made the session declare its next
    cron fire and blocked when that timestamp went stale. That check fired on its
    author twice: once on genuinely bad date arithmetic, and once simply because
    the loop had fired and the declaration had not been renewed yet. The second
    is not a defect, it is the design demanding maintenance of a fact the harness
    already reports.

    `session_crons` in the Stop event is authoritative, so the only thing worth
    remembering is the HIGH-WATER count. A session that once had a cron and now
    has none has lost its loop, which is the failure the operator actually cares
    about ("sometimes you stop the hourly loop and never start it again"). A
    session that never had one is not doing anything wrong.

    v9: the caller passes the WORK-cron count, not the total. With the
    5-minute poll enforced, a total-count high-water mark would read a dead
    work loop behind a surviving poll as "still has a cron" -- exactly the
    loss this check exists to catch.
    """
    p = worklist.with_suffix(".croncount-%s" % (session_id or "unknown")[:8])
    try:
        remembered = int(p.read_text().strip())
    except (OSError, ValueError):
        remembered = 0
    if live_count > remembered:
        try:
            p.write_text(str(live_count))
        except OSError:
            pass
        remembered = live_count
    if declared_done and live_count == 0 and remembered >= 1:
        # FORGET the high-water mark, do not merely skip this one stop. Without
        # the reset the declaration would clear the block once and the check
        # would fire again on the next stop, and the next, forever -- which is
        # exactly what happened to the session that found this. A loop declared
        # finished is finished; if a new one starts, live_count climbs above 0
        # again and the mark rebuilds itself on its own.
        try:
            p.write_text("0")
        except OSError:
            pass
        return False, remembered
    return (remembered >= 1 and live_count == 0), remembered


def docs_drift(root):
    """(state, drift_commits, docs_dir) -- how far the code has moved past the docs.

    THE FAILURE THIS CATCHES, measured on the session that asked for it: 44
    commits touching .ci/.github/.claude since the design docs were last updated.
    Those documents are how a NEW or freshly-compacted session understands what
    is being built and why, so code moving without them does not merely leave
    stale prose behind, it deletes the next session's starting context.

    'absent' when there is no such directory, so the check scopes itself to
    projects that actually keep design docs and says so rather than passing
    quietly.
    """
    docs = pathlib.Path(root) / DESIGN_DOCS
    if not docs.is_dir():
        return "absent", 0, str(docs)
    last_docs = C._git(root, "log", "-1", "--format=%H", "--", DESIGN_DOCS)
    base = last_docs or C._git(root, "merge-base", "HEAD", "origin/main")
    if not base:
        return "absent", 0, str(docs)
    n = C._git(root, "rev-list", "--count", "%s..HEAD" % base, "--", *PROGRAM_SURFACE)
    drift = int(n) if n.isdigit() else 0
    return ("drifted" if drift > DOCS_DRIFT_MAX else "ok"), drift, str(docs)


# ---- v16: the plan-file convention (docs/agent/<branch>/PLAN-<slug>.md) -----
#
# A plan is the DURABLE design record: committed with its branch, so it
# survives compaction and a lost machine. That is what distinguishes it from
# the gitignored .agent/<branch>/ tree, whose STATE.md is the volatile cursor.
# Plans are historical once executed, so only draft/executing/UNKNOWN ones are
# surfaced; done and superseded appear as a count. An unparseable Status line
# reads as UNKNOWN and is shown LOUDLY, per the V_PR_UNREADABLE convention
# that a check which cannot read must say so rather than pass quietly.
#
# Cost: SessionStart and PostCompact only. The Stop battery and the poll fast
# path never read plan files; the guide's single os.path.exists probe per
# TRIAGED item is the only plan-related work on the stop path.

PLAN_STATUS_RE = re.compile(r"^Status:\s*([A-Za-z-]+)\s*$", re.M)
PLAN_HEADER_LINES = 10
PLAN_DONE_STATES = ("done", "superseded")
PLAN_EXCERPT_CHARS = 1500


def plan_dir(root, branch):
    return pathlib.Path(root) / "docs" / "agent" / (branch or "")


def plan_records(root, branch):
    """[(relpath, status, lines)] for docs/agent/<branch>/PLAN-*.md.

    status is the parsed value lowercased, or 'UNKNOWN' when no Status line
    sits in the first PLAN_HEADER_LINES lines. Newest mtime first. Empty list
    when the branch or the directory is absent, so callers never have to know
    whether this project uses the convention.
    """
    if not branch:
        return []
    d = plan_dir(root, branch)
    if not d.is_dir():
        return []
    rows = []
    for f in sorted(d.glob("PLAN-*.md")):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
            mtime = f.stat().st_mtime
        except OSError:
            continue
        lines = text.splitlines()
        m = PLAN_STATUS_RE.search("\n".join(lines[:PLAN_HEADER_LINES]))
        status = m.group(1).lower() if m else "UNKNOWN"
        try:
            rel = str(f.relative_to(root))
        except ValueError:
            rel = str(f)
        rows.append((rel, status, len(lines), mtime))
    rows.sort(key=lambda r: -r[3])
    return [(rel, status, n) for rel, status, n, _mt in rows]


def plans_block(root, branch):
    """(listing, live_records): the non-done plans, one line each, plus one
    count line for the executed ones. ("", []) when there is nothing to say,
    so a project without plans emits no block at all."""
    recs = plan_records(root, branch)
    live = [r for r in recs if r[1] not in PLAN_DONE_STATES]
    if not live:
        return "", []
    lines = ["  %s [%s] (%d lines)" % (rel, status, n) for rel, status, n in live]
    done = len(recs) - len(live)
    if done:
        lines.append(
            "  (+%d done or superseded plan(s) in the same directory: historical "
            "record, read one only if you need the reasoning behind it)" % done
        )
    return "\n".join(lines), live


def plan_status_excerpt(root, live):
    """(relpath, body) of the newest non-done plan's '## Status' section,
    capped. ("", "") when there is none, which is the honest answer for a
    draft that has not been taken over yet."""
    if not live:
        return "", ""
    rel = live[0][0]
    try:
        text = (pathlib.Path(root) / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return rel, ""
    for chunk in text.split("\n## ")[1:]:
        title, _nl, body = chunk.partition("\n")
        if title.strip().lower() == "status":
            return rel, body.strip()[:PLAN_EXCERPT_CHARS]
    return rel, ""


def triage_context(root, worklist, session_id=""):
    """The facts the CLI can honestly gather about a finding's blast radius.

    Passed to the triage judge AND printed in degraded mode, so the session
    self-assesses on exactly the same facts the model would have seen.
    `git status --porcelain` is the load-bearing one: it names the files this
    session already has in flight, which is what makes "is the fix's file set
    disjoint" an answerable question rather than a guess.
    """
    branch = C.git_branch(root)
    d = plan_dir(root, branch)
    recs = plan_records(root, branch)
    if not branch:
        plans = "no branch resolvable, so there is no plan directory to use"
    elif not d.is_dir():
        plans = "%s does not exist yet (creating it is part of writing a plan)" % d
    else:
        plans = "%s exists, %d plan file(s)" % (d, len(recs))
    status = C._git(root, "status", "--porcelain") or ""
    rows = [ln for ln in status.splitlines() if ln.strip()][:40]
    files = "\n".join("    " + ln for ln in rows) or "    (working tree clean)"
    try:
        fold = S.load(worklist, sync=False)
        open_n = sum(
            1 for r in fold.items
            if r["state"] in (" ", ">", "?")
            and (not session_id or C.owned_by_me(r["owner"], session_id))
        )
        opens = "%d" % open_n
    except Exception:  # noqa: BLE001 -- a context fact must never break the verb
        opens = "unknown (the store could not be read)"
    return (
        "  branch: %s\n"
        "  plan directory: %s\n"
        "  files this session already has in flight (git status --porcelain, "
        "first 40):\n%s\n"
        "  open items this session is already tracking: %s"
        % (branch or "(none)", plans, files, opens)
    )


def xsession_ok(line, reqs, session_id):
    """(ok, why) for a 'waiting-cross-session' Remaining line.

    The state must EARN its place or it is a synonym for 'blocked': the line
    must name an OPEN request id from the .requests log that THIS session
    asked. That id is checkable across its whole lifecycle, so it substitutes
    for the <path>:<line> citation the blocked/parked states require -- the
    request IS the citation. Fails loudly on a stale id: an answered request
    means the wait is over, an escalated one means the operator holds it now.
    """
    known = [i for i in XSESSION_ID_RE.findall(line) if i in reqs]
    if not known:
        return False, (
            "names no request id from the log; post the ask with --ask and put "
            "its #id on the line"
        )
    why = ""
    for rid in known:
        r = reqs[rid]
        if not C.same_session(r["from"], session_id):
            why = (
                "#%s was asked by %s, not by you; only your own outstanding "
                "request is your waiting state" % (rid, r["from"] or "unknown")
            )
        elif r["escalated"]:
            why = (
                "#%s already ESCALATED to the operator; the [?] item carries it "
                "now, so update this line" % rid
            )
        elif wl_requests.request_resolved(r):
            why = (
                "#%s is already ANSWERED; the wait is over, act on the answer "
                "and --ack it" % rid
            )
        else:
            return True, rid
    return False, why


# ---- the v9 poll fast path --------------------------------------------------

def poll_fast_path(worklist, session_id, event):
    """True iff this stop is a PROVEN no-op inbox poll (WHY v9).

    Every condition is recomputed here from artifacts; nothing is trusted
    from the poll command, whose only contributions are the single-use
    marker (the structural declaration that this turn WAS a poll) and the
    printed inbox. Every failure path returns False, which means the FULL
    battery -- the fast path can never fail into a silent allow.

    v10 adds forfeits for the new obligations: a deferral past its autonomy
    window, and an in-flight subject old enough for a blocking ladder rung.
    A skipped 45-minute ping is the accepted residual (it is report-only and
    the horizon bounds the delay); anything that could BLOCK forfeits.
    """
    mark = pollmark_path(worklist, (session_id or "unknown")[:8])
    try:
        fresh = time.time() - mark.stat().st_mtime <= POLL_WINDOW_S
        # CONSUMED either way, before any other verdict: one poll vouches for
        # at most one stop, and a marker lingering into an operator-facing
        # turn must not silence that turn's report.
        mark.unlink()
    except OSError:
        return False
    if not fresh:
        return False
    base_p = pollbase_path(worklist, session_id)
    try:
        base_sig = json.loads(base_p.read_text(encoding="utf-8"))["sig"]
        if time.time() - base_p.stat().st_mtime > POLL_FULL_MAX_MIN * 60:
            return False  # the horizon: a poll stop now pays the battery
    except (OSError, ValueError, KeyError, TypeError):
        return False
    root = C.project_root(event.get("cwd") or os.getcwd())
    # The fold is loaded BEFORE the signature check since v17, because the
    # signature is now derived from this session's items rather than from the
    # shared files' bytes; passing it here keeps the store parsed once.
    fold = S.load(worklist, sync=False)
    if S.world_sig(root, worklist, session_id, fold=fold) != base_sig:
        return False  # tracked work happened since the last full stop
    crons = event.get("session_crons") or []
    if len([c for c in crons if is_poll_cron(c)]) != 1:
        return False
    if len([c for c in crons if not is_poll_cron(c)]) > 1:
        return False
    state_doc = S.load_state(worklist, session_id)
    live_bg = [
        b for b in (event.get("background_tasks") or []) if b.get("status") == "running"
    ]
    ci_watching, _watch_desc = wl_ci.ci_watch_only(live_bg)
    for rec in fold.items:
        if not C.owned_by_me(rec["owner"], session_id):
            continue
        state = rec["state"]
        if state == " ":
            return False
        if state == "?":
            if not C.DEFAULT_TOKEN.search(rec["line"]):
                return False
            age = C.stamp_age_min(rec.get("upd", ""))
            if age is not None and age >= S.DEFER_WINDOW_MIN:
                return False  # the autonomy window closed; the battery says so
            # v12 forfeits: anything that could BLOCK on the full battery
            # (the justification demand, the CI-waiting force) forfeits the
            # silent path; the report-only audit rides the hourly horizon.
            if age is not None and age >= S.JUSTIFY_AGE_MIN and not deferral_is_justified(rec):
                return False
            if ci_watching and age is not None and age >= CI_FORCE_MIN_AGE:
                return False
        if state == ">":
            _ls = C.lease_state(rec["line"])
            if _ls != "fresh":
                # v14 gap 4: an EXPIRED lease whose worker the OS still shows
                # running is supervision, not abandonment; it keeps the silent
                # path exactly as classify_items keeps it in-flight.
                _wid = rec.get("worker") or ""
                if not (
                    _ls == "expired"
                    and _wid
                    and any(str(b.get("id") or "") == _wid for b in live_bg)
                ):
                    return False  # an expiring lease is a wake-up; the battery says so
            if wl_liveness.blocking_rung_due(
                state_doc, "item:" + rec["id"],
                C.stamp_age_min(rec.get("upd", "")), rec.get("upd", ""),
            ):
                return False  # a blocking rung is DUE, not merely past its age
    # Ask whether a rung would actually FIRE, never whether the age is past a
    # threshold. The ladder is latched, so a long-lived subject fires once and
    # then goes quiet; comparing raw age here made the forfeit outlive the
    # report and pinned a 298-minute task's poll stops to the full battery
    # forever. See wl_liveness.blocking_rung_due.
    for tid, seen in (state_doc.get("tasks_seen") or {}).items():
        if seen.get("status") == "in_progress" and wl_liveness.blocking_rung_due(
            state_doc, "task:" + tid,
            C.stamp_age_min(seen.get("since", "")), seen.get("since", ""),
        ):
            return False
    to_me, bcast, answered, _mine = wl_requests.classify_requests(
        wl_requests.read_requests(worklist), session_id
    )
    if to_me or bcast or answered:
        return False  # the inbox is the poll's whole subject; deliver it loudly
    if wl_requests.escalate_requests(worklist, session_id, dry_run=True):
        return False  # due escalations happen on a full stop that reports them
    # v15: in a pure background wait the 15-minute worker check-in rides the
    # full battery, so a due check-in forfeits the silent path. By this point
    # in the function no open item and no expired deferral survived, which is
    # exactly the pure-wait shape.
    if live_bg:
        _bg_age = C.stamp_age_min((state_doc.get("bgwait") or {}).get("at", ""))
        # An unseeded clock stays silent (seeding happens on full stops, and
        # the poll horizon bounds how long that can take); a due one forfeits.
        if _bg_age is not None and _bg_age >= wl_liveness.BG_REPORT_MIN:
            return False  # the background check-in is due; the battery delivers it
    return True


# ---- v11: the store-derived stop guide --------------------------------------
# WHY (operator, 2026-07-30): "--list should be used always on stop hook to
# output enforced guided instructions." The defect this fixes is structural:
# v10 stamped every item and the hand-authored Remaining prose never read the
# store, so the tracing existed and the report ignored it. The guide is
# emitted on EVERY full stop, allow and block alike, so the session bases its
# report on the store instead of memory.
#
# BOUNDED HARD, because the live store folds 831 items (550 KB as a raw
# --list) and this hook fires from a 5-minute poll cron: only the ACTIONABLE
# slice is emitted (open, in-flight, deferrals and expired leases -- never
# [x]), at most GUIDE_MAX lines, each capped, and a cap that drops anything
# SAYS SO with the count, because a silent cap reads as "that is everything".

# How many unheeded PostToolUse nudges before the Stop hook blocks. Three at the
# 10-minute throttle is half an hour of being asked and not complying, which is
# well past any legitimate relaunch window.
WAITER_GRACE_NUDGES = int(os.environ.get("WORKLIST_WAITER_GRACE_NUDGES", "3"))
GUIDE_MAX = int(os.environ.get("WORKLIST_GUIDE_MAX", "12"))
# How long a SUBMODULE POINTER MOVED warning stays latched for one (path, sha)
# signature. Time-boxed on purpose: a permanent acknowledgement would go silent
# on a pointer somebody forgot, and a forgotten pointer ships whatever the
# parent last recorded. A move to a new sha re-fires immediately regardless.
SUBMODULE_LATCH_MIN = int(os.environ.get("WORKLIST_SUBMODULE_LATCH_MIN", "15"))
GUIDE_TEXT_CHARS = 90

# The allow-report diet (operator, 2026-07-31: "Why I see such a big
# output?"). Slow-moving advisory sections re-show only when their content
# changes or after this many minutes, whichever comes first.
REPORT_REFRESH_MIN = int(os.environ.get("WORKLIST_REPORT_REFRESH_MIN", "360"))
BACKOFF_NOTE_MIN = int(os.environ.get("WORKLIST_BACKOFF_NOTE_MIN", "60"))

# ---- the allow-report OUTPUT QUEUE ------------------------------------------
# The diet above deduplicated sections; this bounds how many reach one stop.
# Sections are ENQUEUED AT COMPUTE TIME, at their producer's call site, never
# in the emit block -- because emit() exits the process, and three producers
# (the liveness ladder, dead-session archiving, request escalation) spend a
# one-shot budget BEFORE the block emit at run_stop's violations branch. Their
# text was only ever appended on the allow path, so a stop that blocked for an
# unrelated reason swallowed them for good: the rung is recorded, the item is
# already [~], the [?] is already appended, and nothing re-fires. An entry
# that lands in the state doc the moment its producer spends that budget
# survives a block, a judge block, a crash and a restart.
OUTQ_PER_STOP = int(os.environ.get("WORKLIST_REPORT_PER_STOP", "1"))
OUTQ_MAX = int(os.environ.get("WORKLIST_OUTQ_MAX", "40"))


def _outq(state_doc):
    """The queue sub-doc, seeded from the v11 report_seen ledger on first sight.

    Without the seed the first upgraded stop re-shows every already-latched
    advisory at once, which is precisely the symptom being fixed. report_seen
    is left in place unread rather than deleted: a sole-operator clean break
    still should not make that stop the noisiest one the session ever saw."""
    q = state_doc.get("outq")
    if not isinstance(q, dict):
        q = {"seq": 0, "items": [], "shown": dict(state_doc.get("report_seen") or {})}
        state_doc["outq"] = q
    q.setdefault("seq", 0)
    q.setdefault("items", [])
    q.setdefault("shown", {})
    return q


def _outq_cap(q):
    """Hold OUTQ_MAX by dropping non-sticky entries, lowest priority first
    then oldest first. A sticky entry is NEVER dropped, even when stickies
    alone exceed the cap: a one-shot the cap ate is a one-shot lost."""
    items = q["items"]
    if len(items) <= OUTQ_MAX:
        return
    for e in sorted(
        (e for e in items if not e.get("sticky")),
        key=lambda e: (-int(e.get("prio") or 0), int(e.get("seq") or 0)),
    ):
        if len(items) <= OUTQ_MAX:
            break
        items.remove(e)


def outq_add(worklist, session_id, state_doc, key, text, prio,
             sticky=False, refresh_min=None, on_change=True):
    """Queue one allow-report section. Persists the state doc immediately.

    Returns True when an entry was added or refreshed, False when the call was
    absorbed (unchanged content inside its refresh window, or already queued).
    The return value is for the suite and for a caller that wants to skip
    building an expensive body; nothing in run_stop needs it.

    PERSISTS ON EVERY CALL, deliberately. Six of run_stop's emit paths do not
    save the state doc before emitting, so a "save at the end" contract would
    lose exactly what this queue exists to keep. The cost is at most about ten
    tempfile+os.replace writes on a path that already runs git and gh
    subprocesses."""
    q = _outq(state_doc)
    items = q["items"]
    sig = hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()[:12]
    # A one-shot's entry key carries its own sig, so two different bodies under
    # one section name never overwrite each other. There is deliberately NO
    # shown-ledger for sticky keys: a one-shot producer cannot re-fire, so a
    # ledger that could suppress one is a way to lose it. Showing one twice is
    # cosmetic; dropping one is the failure this queue exists to prevent.
    ekey = "%s:%s" % (key, sig) if sticky else key
    cur = next((e for e in items if e.get("key") == ekey), None)
    added = False
    if sticky:
        if cur is None:
            q["seq"] = int(q.get("seq") or 0) + 1
            items.append({"key": ekey, "prio": prio, "sticky": True, "sig": sig,
                          "text": text, "at": C.stamp_now(), "seq": q["seq"]})
            added = True
    elif cur is not None and not on_change:
        # Identity is the KEY alone: the backoff tip's wording carries a live
        # minute counter, so a content hash would re-enqueue it every stop.
        # The freshest wording rides the position the entry already earned.
        if cur.get("text") != text:
            cur["text"], cur["sig"] = text, sig
            added = True
    elif cur is not None:
        if cur.get("sig") != sig:
            # Changed content re-enqueues AT ITS PRIORITY: a new seq sends it
            # to the back of its own class rather than jumping the queue.
            q["seq"] = int(q.get("seq") or 0) + 1
            cur["text"], cur["sig"], cur["seq"] = text, sig, q["seq"]
            cur["at"] = C.stamp_now()
            added = True
    else:
        window = REPORT_REFRESH_MIN if refresh_min is None else refresh_min
        prev = q["shown"].get(key) or {}
        age = C.stamp_age_min(prev.get("at", ""))
        fresh = age is not None and age < window
        if not (fresh and (prev.get("sig") == sig or not on_change)):
            q["seq"] = int(q.get("seq") or 0) + 1
            items.append({"key": key, "prio": prio, "sticky": False, "sig": sig,
                          "text": text, "at": C.stamp_now(), "seq": q["seq"]})
            added = True
    if added:
        _outq_cap(q)
        S.save_state(worklist, session_id, state_doc)
    return added


def outq_drain(worklist, session_id, state_doc, n):
    """(texts, remaining): the n highest-priority entries, FIFO inside a class.

    Removes exactly those entries BY IDENTITY (never by slicing or clearing --
    a clear silently eats every one-shot that had not reached its turn),
    records shown[] for the volatile ones, and persists before returning,
    because the caller emits and emit() exits the process."""
    q = _outq(state_doc)
    take = sorted(
        q["items"], key=lambda e: (int(e.get("prio") or 0), int(e.get("seq") or 0))
    )[: max(0, n)]
    picked = {id(e) for e in take}
    for e in take:
        if not e.get("sticky"):
            q["shown"][e["key"]] = {"sig": e.get("sig", ""), "at": C.stamp_now()}
    q["items"] = [e for e in q["items"] if id(e) not in picked]
    S.save_state(worklist, session_id, state_doc)
    return [e.get("text", "") for e in take], len(q["items"])


def guided_slice(fold, session_id, verdicts=None, me=None, root=None, full=False):
    """The bounded, guided, store-derived instruction block.

    One line per actionable item: state, #id, age from the store's own
    stamps, the capped text, and the EXACT verb that moves it -- an open
    item gets --tick, a live lease gets --update, an undefaulted [?] gets
    --defer, an expired-window [?] gets its default-execution order. Sorted
    by priority (obligations first) so truncation drops the least urgent.
    `verdicts` (from wl_liveness.verify_background) annotates lease workers
    when the caller has an event to verify against; the CLI does not.

    v16 FOLLOW-THROUGH: an item triaged 'plan-subagent' whose recorded plan
    file is NOT on disk is promoted to priority 0 with the demand to write
    it, and one whose plan EXISTS advertises the path. This is one
    os.path.exists per triaged item, bounded by the fold, and it is
    report-only: a guide line, never a new block, so the stop path stays
    cheap and the guide's no-new-block invariant holds. `root` is passed by
    both callers; None derives it, which the direct-library callers rely on.

    `full=True` LIFTS the GUIDE_MAX cap. The cap exists to bound the Stop
    hook's payload, so the hook keeps it; the CLI does not, and until now it
    silently inherited it -- which made GUIDE_TRUNCATED's own advice a loop,
    since it points at `--list --open` "for the full slice" and that command
    re-rendered the same 12 rows. A human asking for the slice by hand gets
    every row and no truncation footer.
    """
    me_arg = (me or "<me>")[:8] if me else "<me>"
    verdicts = verdicts or {}
    rows = []  # (priority, line)
    for rec in fold.items:
        if session_id and not C.owned_by_me(rec["owner"], session_id):
            continue
        st = rec["state"]
        if st == "x":
            continue
        txt = S.brief_text(rec, GUIDE_TEXT_CHARS)
        upd = C.stamp_age_min(rec.get("upd", ""))
        age = "?" if upd is None else "%dm" % upd
        rid = rec["id"]
        tri = rec.get("triage") or {}
        plan = tri.get("plan", "") if tri.get("v") == "plan-subagent" else ""
        if plan and st in (" ", ">"):
            if root is None:
                root = C.project_root(
                    os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
                )
            if not os.path.exists(os.path.join(root, plan)):
                rows.append((0, "  - [%s] #%s (upd %s) %s\n        TRIAGED BIG, plan file missing: %s\n        NEXT: write the plan (Plan agent) or re-triage: --triage %s --id %s <finding>"
                             % (st, rid, age, txt, plan, me_arg, rid)))
                continue
        else:
            plan = ""
        before = len(rows)
        if st == " ":
            rows.append((0, "  - [ ] #%s (upd %s) %s\n        NEXT: do it, then --tick %s %s '<evidence>'"
                         % (rid, age, txt, me_arg, rid)))
        elif st == ">":
            wm = C.WORKER.search(rec["line"])
            wid = rec.get("worker") or (wm.group(1) if wm else "")
            if C.lease_state(rec["line"]) == "fresh" or rec.get("lease_tolerated"):
                osw = verdicts.get(wid, "")
                wtag = "worker:%s%s" % (wid or "?", " [%s]" % osw if osw else "")
                if rec.get("lease_tolerated"):
                    wtag += " (lease expired, worker verified alive: auto-honored; renew or tick when it lands)"
                rows.append((3, "  - [>] #%s (quiet %s, %s) %s\n        NEXT: --update %s %s '<one line of what moved>'"
                             % (rid, age, wtag, txt, me_arg, rid)))
            else:
                rows.append((0, "  - [>] #%s LEASE DEAD (quiet %s) %s\n        NEXT: finish it and --tick %s %s '<evidence>', or re-lease: --lease %s %s +60 worker:<bg-id>"
                             % (rid, age, txt, me_arg, rid, me_arg, rid)))
        elif st == "?":
            if not C.DEFAULT_TOKEN.search(rec["line"]):
                rows.append((2, "  - [?] #%s (age %s, NO DEFAULT) %s\n        NEXT: --defer %s %s '<question> DEFAULT: <action> WHY: <reason> HOW: <resolution>'"
                             % (rid, age, txt, me_arg, rid)))
            elif upd is not None and upd >= S.DEFER_WINDOW_MIN:
                rows.append((1, "  - [?] #%s WINDOW CLOSED (waited %s) %s\n        NEXT: execute its DEFAULT now, then --tick %s %s '<evidence>'"
                             % (rid, age, txt, me_arg, rid)))
            else:
                left = "?" if upd is None else "%dm" % max(0, S.DEFER_WINDOW_MIN - upd)
                rows.append((4, "  - [?] #%s (age %s) %s\n        operator may answer; its DEFAULT executes in %s"
                             % (rid, age, txt, left)))
        # The design EXISTS: advertise where it lives, so the guide points at
        # the plan instead of leaving the next session to find it.
        if plan and len(rows) > before:
            prio, line = rows[-1]
            rows[-1] = (prio, line + "\n        plan: %s" % plan)
    if not rows:
        return M.GUIDE_EMPTY
    rows.sort(key=lambda r: r[0])
    shown = rows if full else rows[:GUIDE_MAX]
    out = [M.GUIDE_HEADER] + [line for _p, line in shown]
    if len(rows) > len(shown):
        out.append(M.GUIDE_TRUNCATED % (len(rows) - len(shown), GUIDE_MAX))
    return "\n".join(out)


# ---- SessionStart / PostCompact ---------------------------------------------

def mark_context_fresh(event, why):
    """Record that this session's context was just (re)built, so the next
    judged stop states the judge's FULL approval reason instead of the bare
    stamp. Never raises: a context marker must not be able to wedge a
    SessionStart."""
    try:
        wl = C.worklist_for(
            os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or os.getcwd()
        )
        sid = event.get("session_id", "")
        doc = S.load_state(wl, sid)
        doc["ctx_fresh"] = {"why": why, "at": C.stamp_now()}
        S.save_state(wl, sid, doc)
    except Exception:  # noqa: BLE001 -- a marker must never wedge a SessionStart
        pass


def handle_session_start(event):
    # FIRST statement, not last: the design-docs/plans blocks below return
    # early when a project has neither, and such a project would otherwise
    # never be marked.
    source = str(event.get("source") or "").strip().lower()
    mark_context_fresh(event, "session-start:" + (source or "unknown"))
    # COMPACT IS NOT A NEW SESSION. Claude Code fires SessionStart with
    # source=compact on every compaction, on TOP of the PostCompact hook, and
    # this handler used to ignore the source entirely: a session working on
    # something else got "READ ALL OF THEM before acting" pointed at the
    # standing program docs, mid-task, as if it had just started. It is also
    # a straight duplicate -- handle_post_compact already re-points at
    # DESIGN_DOCS and already hands back the branch's plans, plus STATE.md,
    # RULES.md and the trap titles, which is the briefing a compacted session
    # actually needs. So compaction is handled in exactly one place: mark the
    # context fresh (the judge stamp depends on it) and say nothing here.
    if source == "compact":
        return
    # TWO INDEPENDENT BLOCKS, and the structure is the point. This used to
    # RETURN EARLY when the design-docs directory was absent, which meant a
    # project keeping plans but no docs/ci-overhaul got nothing at all: the
    # plans block would have been eaten by a check about a different thing.
    # Each block is built on its own and the hook emits when EITHER has
    # something to say.
    root = C.project_root(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or os.getcwd())
    docs = pathlib.Path(root) / DESIGN_DOCS
    blocks, summary = [], []
    if docs.is_dir():
        files = sorted(f for f in docs.iterdir() if f.is_file() and f.suffix == ".md")
        listing = "\n".join(
            "  %s (%d lines)"
            % (f.relative_to(root), len(f.read_text(errors="replace").splitlines()))
            for f in files
        )
        state, drift, _ = docs_drift(root)
        stale = (
            ""
            if state != "drifted"
            else M.CTX_SESSION_START_STALE % (drift, " ".join(PROGRAM_SURFACE))
        )
        blocks.append(
            M.CTX_SESSION_START % (" ".join(PROGRAM_SURFACE), DESIGN_DOCS, listing, stale)
        )
        summary.append(
            "%d standing program doc(s) in %s%s"
            % (
                len(files),
                DESIGN_DOCS,
                "" if state != "drifted" else " (DRIFTED by %d commits)" % drift,
            )
        )
    branch = C.git_branch(root)
    listing, live = plans_block(root, branch)
    if listing:
        blocks.append(M.CTX_PLANS % (branch, listing))
        summary.append("%d open plan(s) in docs/agent/%s" % (len(live), branch))
    if not blocks:
        return
    C.emit(
        {
            "systemMessage": "SessionStart: " + ", ".join(summary),
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": "\n\n".join(blocks),
            },
        }
    )


def handle_post_compact(event):
    # FIRST statement, for the same reason as handle_session_start, and this
    # is the case the marker is genuinely load-bearing for: a compacted
    # session KEEPS its state doc, so the judge-reason signature below would
    # otherwise read as unchanged and hand it the stamp alone.
    mark_context_fresh(event, "post-compact")
    # PostCompact hook: the model has just lost its context. Hand the
    # documents straight back as additionalContext so continuity does not
    # depend on it remembering to go looking. Since the .agent/ split this
    # returns MORE than the old handover ever could: STATE.md in full,
    # RULES.md in full, and the TRAPS.md titles -- the first time a compacted
    # session gets the standing rules at all, delivered exactly once per
    # compaction. Full TRAPS.md is deliberately excluded (designed to grow);
    # titles plus the path is the same economy the judge uses.
    root = C.project_root(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or os.getcwd())
    sid = event.get("session_id", "")
    branch = C.git_branch(root)
    traps = S.trap_headings(root)
    traps_block = "\n".join("  - " + h for h in traps) or "  (none recorded)"
    if not branch:
        state = "no-branch"
        msg = M.CTX_POSTCOMPACT_NO_BRANCH % traps_block
    else:
        state, _age, text = S.agent_state_state(root, branch)  # shape + presence only
        if state in ("missing", "no-dir"):
            msg = M.CTX_POSTCOMPACT_MISSING % (
                S.agent_state_path(root, branch), branch, (sid or "unknown")[:8]
            )
        else:
            try:
                rules = S.agent_rules_path(root, branch).read_text(
                    encoding="utf-8", errors="replace"
                ).strip()
            except OSError:
                rules = "(none for this branch)"
            msg = M.CTX_POSTCOMPACT_BRIEFING % (
                DESIGN_DOCS, text.strip(), rules, S.agent_traps_path(root), traps_block
            )
    # v16: the durable half of the briefing, appended to ALL THREE branches
    # above. STATE.md says what is true right now and can be missing or
    # stale; a plan file says what was DESIGNED and is committed, so it is
    # the one artifact a compacted session can always fall back on. The
    # newest non-done plan's '## Status' section rides along, capped, because
    # that section is exactly the progress cursor the lost context held.
    listing, live = plans_block(root, branch)
    if listing:
        msg += "\n\n" + M.CTX_PLANS % (branch, listing)
        rel, body = plan_status_excerpt(root, live)
        if body:
            msg += "\n\n" + M.CTX_PLANS_EXCERPT % (rel, body)
    C.emit(
        {
            "systemMessage": "PostCompact: STATE.md %s (.agent/%s/STATE.md)"
            % (state, branch or "<no-branch>"),
            "hookSpecificOutput": {
                "hookEventName": "PostCompact",
                "additionalContext": msg,
            },
        }
    )


PHANTOM_MIN = float(os.environ.get("WORKLIST_PHANTOM_MIN", "30"))
# Writers in the event log that are not identities at all. `compact` is stamped
# by S.compact when it rewrites history; the others are the store's own
# fallbacks. Naming them here beats inferring intent from shape.
PHANTOM_NOT_IDENTITIES = frozenset({"compact", "unknown", "md"})


def phantom_identities(worklist, session_id, fold, reqs):
    """([(prefix, events, age_min, owns)], blind_reason) for identities that
    WRITE to this store but have never stopped.

    THE BACKSTOP for what the CLI check cannot reach: history already written,
    and the deliberate hole where the environment cannot name the caller. Both
    are real -- the incident put 240 events into the live store under an
    identity that never existed, and a plain operator terminal has no session id
    to check against.

    THE SIGNATURE IS EXACT AND BINARY. `<worklist>.lastevent-<prefix>.json` is
    written at exactly ONE place, inside run_stop below; worklist.py's --lease
    and --reap only READ it. So an identity with no `.lastevent-` file is one
    for which a Stop hook has NEVER RUN, and a real session always stops. The
    byte-size asymmetry on `.state-` (the CLI writes only state_sig, the hook
    writes the whole document) says the same thing less reliably; this is the
    better test.

    FOUR GATES, and each one is a false positive that was measured in the live
    store rather than imagined:
      1. not me                -- obviously
      2. no `.lastevent-`      -- the signature above
      3. older than PHANTOM_MIN -- a brand-new session writes before its first
         stop, and that window is not a phantom
      4. owns OPEN work        -- `state-spotchk1`, `state-spotchk2` and a
         session that died before its first stop all sit in the live store with
         no `.lastevent-`. A phantom that owns nothing is not worth a word.

    THE INSTRUMENT CONTROL IS INSIDE THE CHECK. If the store holds ZERO
    `.lastevent-*` files the test is blind -- a wiped TMPDIR, a fresh worktree --
    and it would otherwise indict every identity at once. It reports the
    BLINDNESS in words and flags nobody. A check that cannot fail must say so.
    """
    try:
        seen = list(worklist.parent.glob(worklist.stem + ".lastevent-*.json"))
    except OSError:
        return [], ""
    if not seen:
        return [], (
            "no .lastevent-*.json exists in %s, so the phantom-identity check "
            "is BLIND this stop (it recognises a phantom by the ABSENCE of one, "
            "and with none present every identity would look like one). Nothing "
            "is being flagged. A wiped TMPDIR is the usual cause."
            % worklist.parent
        )
    stopped = {p.name.split(".lastevent-")[-1][:-5] for p in seen}
    counts, first_at = {}, {}
    try:
        raw = S.events_path(worklist).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [], ""
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        by = str(ev.get("by") or "")
        if not by or by in PHANTOM_NOT_IDENTITIES or not C.PREFIX_RE.match(by):
            continue
        counts[by] = counts.get(by, 0) + 1
        at = ev.get("at") or ""
        if by not in first_at or (at and at < first_at[by]):
            first_at[by] = at
    out = []
    for by, n in sorted(counts.items()):
        if C.same_session(by, session_id) or by[:8] in stopped:
            continue
        age = C.stamp_age_min(first_at.get(by, ""))
        if age is None or age < PHANTOM_MIN:
            continue
        owns = []
        n_items = sum(
            1 for rec in fold.items
            if rec["state"] in (" ", "?", ">") and rec["owner"] is not None
            and C.same_session(rec["owner"], by)
        )
        if n_items:
            owns.append("%d open item(s)" % n_items)
        n_reqs = sum(
            1 for r in (reqs or {}).values()
            if not r["acked"] and not wl_requests.request_resolved(r)
            and (C.same_session(r["from"], by) or C.same_session(r["to"], by))
        )
        if n_reqs:
            owns.append("%d open request(s)" % n_reqs)
        if not owns:
            continue
        out.append((by, n, age, " and ".join(owns)))
    return out, ""


# ---- the Stop battery -------------------------------------------------------

def run_stop(event, event_ok, worklist, hook_file):
    """The full stop battery. Gathers EVERY static violation, then emits ONE
    block (five independent blocking checks would cost five turns to clear,
    which is the "stuck in a loop" the old MAX_BLOCKS existed to paper over),
    then consults the judge on stops where work remains, then allows with a
    report."""
    counter = worklist.with_suffix(".blocks")
    session_id = event.get("session_id", "")
    me8 = (session_id or "unknown")[:8]
    root = C.project_root(event.get("cwd") or os.getcwd())

    # ---- v9: the no-op inbox-poll fast path (see WHY v9) --------------------
    # SILENT by design: a verified no-op poll stop exits 0 with NO output at
    # all, because at a 5-minute cadence even a one-line systemMessage is a
    # context fire-hose. Every condition inside is recomputed from artifacts;
    # any exception falls through to the full battery, never into an allow.
    # (A silent stop deliberately skips the .lastevent capture below, so the
    # last FULL stop's event stays available for debugging.)
    if event_ok:
        try:
            if poll_fast_path(worklist, session_id, event):
                raise SystemExit(0)
        except SystemExit:
            raise
        except Exception:  # noqa: BLE001 -- a broken fast path must cost, not excuse
            pass

    fold = S.load(worklist, sync=True)
    state_doc = S.load_state(worklist, session_id)

    archived, orphaned = [], []
    # Dead-session cleanup runs before classification so a tombstoned item is
    # invisible to this very pass. Never let it break the gate.
    projects_dir = os.environ.get("WORKLIST_PROJECTS_DIR") or (
        os.path.dirname(event["transcript_path"]) if event.get("transcript_path") else ""
    )
    try:
        archived, orphaned, cleaned = S.cleanup_dead_sessions(
            worklist, fold, session_id, projects_dir
        )
        if cleaned:
            fold = S.load(worklist, sync=True)
    except Exception:  # noqa: BLE001 -- cleanup must never break gating
        archived, orphaned = [], []
    if archived:
        # STICKY, and queued HERE rather than in the allow tail: the store is
        # already flipped to [~], so an archived item never reports twice.
        outq_add(
            worklist, session_id, state_doc, "archived",
            "Worklist: archived %d dead-session item(s) (state -> [~]):\n%s"
            % (len(archived), "\n".join("  " + a for a in archived)),
            1, sticky=True,
        )

    # v6: escalate unanswerable requests BEFORE classifying items, so a
    # freshly appended `- [?]` is classified by this very stop. Then classify
    # the log for this session's own obligations. Neither may break gating.
    req_escalated = []
    try:
        req_escalated = wl_requests.escalate_requests(worklist, session_id)
        if req_escalated:
            fold = S.load(worklist, sync=True)
    except Exception:  # noqa: BLE001 -- escalation must never break gating
        req_escalated = []
    if req_escalated:
        # STICKY: escalate_requests appends the event and the [?] exactly once.
        outq_add(
            worklist, session_id, state_doc, "req-escalated",
            "Requests ESCALATED to operator-visible [?] items (nobody left to block):\n"
            + "\n".join("  " + e for e in req_escalated),
            1, sticky=True,
        )
    all_reqs = {}
    try:
        all_reqs = wl_requests.read_requests(worklist)
        req_to_me, req_bcast, req_answered, req_open_mine = wl_requests.classify_requests(
            all_reqs, session_id
        )
    except Exception:  # noqa: BLE001 -- a corrupt log must not wedge every stop
        all_reqs = {}
        req_to_me, req_bcast, req_answered, req_open_mine = [], [], [], []

    # v13 F2: push operator-only questions OUT over email. Placed beside the
    # escalation pass because it answers the same question ("who can settle
    # this?") for the one recipient escalation cannot reach, and BELOW the
    # poll fast path (which exits the process above), so a 5-minute no-op poll
    # never pays for it. Wrapped, because a mail transport that can wedge the
    # gate would be a worse bug than the silence it fixes.
    email_note = ""
    try:
        email_note = wl_email.pump(root, worklist, session_id, fold)
    except Exception:  # noqa: BLE001 -- the mail channel must never break gating
        email_note = ""
    if email_note:
        # STICKY: pump() has already appended the ledger and SENT, or latched
        # its unconfigured/failed warning on a marker file.
        outq_add(worklist, session_id, state_doc, "email", email_note, 1, sticky=True)

    lines = fold.lines()
    # v14 gap 4: computed HERE (it used to sit below) so classification can
    # tolerate an expired lease whose worker the OS still shows RUNNING: a
    # full CI battery legitimately outlives the 120-minute lease cap, and the
    # v13 night cost three manual renewals for a watcher that was verifiably
    # alive the whole time. A worker the OS cannot see keeps failing closed.
    live_bg = [b for b in (event.get("background_tasks") or []) if b.get("status") == "running"]
    # v18: REAP A ROSTER THE SESSION CANNOT VERIFY. After a compaction, or an
    # operator reopening the session, the harness still reports every teammate
    # ever spawned as `running` -- measured: 20 claimed, exactly 1 transcript
    # still growing. That roster drives real checks (_in_pure_wait, the
    # 15-minute BG_REPORT_MIN obligation, confirmed_waiters), so a permanently
    # stale one means a session is told it supervises twenty workers forever and
    # confirms phantoms every fifteen minutes -- ritual without signal.
    _bg_dropped, _bg_unknown = [], 0
    try:
        live_bg, _bg_dropped, _bg_unknown = wl_liveness.prune_background(
            live_bg, worklist, session_id, event.get("cwd"))
    except Exception:  # noqa: BLE001 -- a roster heuristic must never wedge a stop
        pass
    _live_worker_ids = {str(b.get("id") or "") for b in live_bg}
    open_items, others, deferred_recs, in_flight_recs = S.classify_items(
        fold, session_id, live_worker_ids=_live_worker_ids
    )
    deferred = [r["line"] for r in deferred_recs]
    in_flight = [r["line"] for r in in_flight_recs]

    def other_sessions_note():
        if not others:
            return ""
        return "\n".join(
            "  %d open item(s) owned by session %s" % (len(v), k) for k, v in sorted(others.items())
        )

    # ---- v7: regression-gate detection (see wl_reggate). Never breaks gating.
    reg_marker = wl_reggate.reggate_path(worklist, session_id)
    reg_signals, reg_ids, reg_new_ticks, reg_sig, reg_head = [], [], [], "", ""
    reg_state, reg_forgot, reg_settled = None, False, None
    reg_done_tasks, reg_flood = [], 0
    try:
        reg_state, reg_forgot = wl_reggate.load_reggate(reg_marker)
        if reg_forgot:
            # STICKY: load_reggate has already discarded the marker, so the
            # flag is true only on the discovering pass.
            outq_add(
                worklist, session_id, state_doc, "reg-forgot",
                "Regression marker was corrupt and has been re-initialised; previously "
                "settled verdicts were forgotten, so an old fix-set may be asked once more.",
                1, sticky=True,
            )
        reg_cur_tasks = C.task_statuses(session_id)
        if not reg_state["head"]:
            # FAIL SAFE: first sight (or a corrupt marker just discarded)
            # initialises to the present and asks nothing this stop. Seeding
            # the check-script hashes here is what keeps prove_new_gate from
            # ever treating the ~90 pre-existing gates as candidates, and
            # seeding task statuses is what keeps I7 from demanding evidence
            # for completions that predate the marker.
            reg_state["head"] = C._git(root, "rev-parse", "HEAD")
            reg_state["seen_ticks"] = wl_reggate.mine_tick_ids(lines, session_id)
            reg_state["gate_runs"] = wl_reggate.seed_gate_hashes(root)
            reg_state["task_status"] = {i: st for i, (st, _s) in reg_cur_tasks.items()}
            wl_reggate.save_reggate(reg_marker, reg_state)
        else:
            # I7: a task that FLIPPED to completed since the last stop must
            # carry evidence (checked in the violations pass below).
            prev_ts = reg_state.get("task_status") or {}
            reg_done_tasks = [
                (i, sub)
                for i, (st, sub) in sorted(reg_cur_tasks.items())
                if st == "completed" and prev_ts.get(i) in ("pending", "in_progress")
            ]
            reg_signals, reg_ids, reg_new_ticks, reg_head = wl_reggate.fix_signals(
                root, lines, session_id, reg_state
            )
            if len(reg_new_ticks) > wl_reggate.TICK_FLOOD:
                # The v10 upgrade guard: a flood of "new" ticks is rendering
                # drift, not a burst of fixes. Absorb, say so once, keep any
                # commit-derived signals.
                reg_flood = len(reg_new_ticks)
                reg_state["seen_ticks"] = sorted(
                    set(reg_state["seen_ticks"]) | {t for t, _ln in reg_new_ticks}
                )
                wl_reggate.save_reggate(reg_marker, reg_state)
                tick_ids = {t for t, _ln in reg_new_ticks}
                reg_new_ticks = []
                reg_ids = [i for i in reg_ids if i not in tick_ids]
                reg_signals = [s for s in reg_signals if not s.startswith("tick: ")]
                # STICKY: the absorbed ticks are already banked in seen_ticks.
                outq_add(
                    worklist, session_id, state_doc, "reg-flood",
                    "Regression gate: %d historical ticks were absorbed as bookkeeping "
                    "(store-format change), not asked about." % reg_flood,
                    1, sticky=True,
                )
            if reg_ids:
                reg_sig = hashlib.sha1("|".join(reg_ids).encode("utf-8")).hexdigest()[:12]
            if reg_ids and reg_sig in reg_state["fixsets"]:
                # Already settled: absorb and never re-ask. The whole cost story.
                reg_state["head"] = reg_head or reg_state["head"]
                reg_state["seen_ticks"] = sorted(
                    set(reg_state["seen_ticks"]) | {t for t, _ln in reg_new_ticks}
                )
                wl_reggate.save_reggate(reg_marker, reg_state)
                reg_signals, reg_ids = [], []
            elif not reg_ids and reg_head and reg_head != reg_state["head"]:
                # Only non-fix or doc-only-fix commits landed: nothing to ask,
                # ever, so the marker just advances.
                reg_state["head"] = reg_head
                wl_reggate.save_reggate(reg_marker, reg_state)
    except Exception:  # noqa: BLE001 -- detection must never break gating
        reg_signals, reg_ids, reg_sig, reg_done_tasks = [], [], "", []
        if reg_state is None:
            reg_state = {"head": "", "seen_ticks": [], "fixsets": {}, "gate_runs": {}}

    # ---- gather EVERY static violation, then emit ONE block -----------------
    judged_ok = None
    verdict = None
    tasks = C.pending_tasks(session_id)
    # THE EVENT ALREADY CARRIES ALL OF THIS. Transcript parsing, a flush retry
    # and a whole-turn accumulator were built before a captured Stop payload
    # showed `last_assistant_message`, `session_crons` and `background_tasks`
    # sitting in it. The transcript path stays as a FALLBACK for older payloads,
    # but the event is authoritative: it is exact, unraced, and immune to the
    # narration-block bug that made this check fire on its own author.
    last_msg = event.get("last_assistant_message") or ""
    msg_readable = bool(last_msg)
    if not msg_readable:
        last_msg, _tools, msg_readable = C.transcript_tail(
            event.get("transcript_path", ""), want=REMAINING_HEADING
        )
    live_crons = event.get("session_crons") or []
    # v9: the two-cron shape. The poll cron is identified by schedule shape
    # and is deliberately NOT a work wake-up: it wakes the session only when
    # another session acts.
    live_poll_crons = [c for c in live_crons if is_poll_cron(c)]
    live_work_crons = [c for c in live_crons if not is_poll_cron(c)]
    # live_bg is computed above, beside classify_items, since v14 gap 4.
    # Keep the raw event: when a check fires wrongly the first question is always
    # "what did the hook actually receive", and that is unanswerable afterwards.
    try:
        worklist.with_suffix(".lastevent-%s.json" % me8).write_text(
            json.dumps({k: v for k, v in event.items() if k != "transcript"}, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass
    briefs = S.read_briefs(worklist)
    bstate, bage, others_briefs = S.brief_state(worklist, session_id, briefs)
    lstate, lnext, llabel, _others_loops, lcrons = S.loop_state(worklist, session_id)
    # The world signature is computed ONCE, after every shared-state write of
    # this stop (sync, cleanup, escalation), and reused by the STATE.md check,
    # the poll baseline and the judge cache, so all three describe one world.
    cur_sig = S.world_sig(root, worklist, session_id, fold=fold)
    # v14 gap 5: STATE.md staleness keys on STRUCTURE, not bytes, so a
    # session's own bookkeeping (lease renewals, update notes) does not stale
    # the document it just refreshed. Polls and the judge keep cur_sig.
    st_sig = S.state_world_sig(root, worklist, session_id, fold=fold)
    agent_branch = C.git_branch(root)
    astate, aage, _atext = S.agent_state_state(
        root, agent_branch, cur_sig=st_sig, saved_sig=state_doc.get("state_sig")
    )
    if astate == "ok":
        # ADOPT: an "ok" verdict banks the signature so a second session
        # arriving on the branch inherits the document instead of being
        # ordered to rewrite it. The adopt fires ONLY on "ok" -- banking on a
        # "stale" verdict would let the next stop compare cur_sig against a
        # signature recorded DURING the block, find them equal, and allow: a
        # gate that clears itself without a rewrite (control T7b pins this by
        # asserting it blocks TWICE on an unchanged world). Must sit above
        # S.save_state below; emit() exits, so anything written after a later
        # emit path never lands.
        state_doc["state_sig"] = st_sig

    remaining_lines = (
        ["[ ] " + i for i in open_items]
        + ["task #%s [%s] %s" % (i, st, sub) for i, sub, st in tasks]
        + ["[?] " + d for d in deferred]
        + ["[>] " + f for f in in_flight]
    )
    something_remains = bool(remaining_lines)
    # v14 gap 6: BANK a message that carries a '## Remaining' section, keyed
    # to the structural world sig. A later stop on an UNCHANGED world (a
    # forfeited poll, a bookkeeping-only turn) is then not ordered to re-type
    # a byte-identical table; any real move changes st_sig and the demand
    # returns. Banked before the battery so the stop that writes the report
    # banks it even when it blocks for some other reason.
    if msg_readable and REMAINING_HEADING.search(last_msg or ""):
        state_doc["last_report_sig"] = st_sig

    # ---- v15 PURE BACKGROUND WAIT (operator, 2026-07-31): "sometimes you
    # only have background jobs and wait for them without any other pending
    # task. The hook should respect that but have information about them,
    # with a 15 min timeout to have a report, since they may stuck."
    # The state: live background work, no open items, no expired deferral.
    # In it, waiting is LEGITIMATE (the judge is told so below), and the
    # hook's demand shrinks to a bounded 15-minute check-in whose facts the
    # hook gathers ITSELF from each worker's output stream (mtime/size),
    # because file growth is evidence no self-report can fake. Latched on
    # fire, so the check-in costs one focused block per window, never a
    # drumbeat.
    bg_facts, bgwait_due, bgwait_prev, bgwait_next = [], False, "", ""
    bg_verdicts = {}
    _in_pure_wait = False
    # v18: A CONFIRMED INBOX WAITER IS A PUSH CHANNEL, NOT A JOB TO SUPERVISE.
    # wl_wait.py blocks until something new arrives for this session and then
    # EXITS, and its exit is the harness notification that wakes the session. So
    # its liveness IS its report: there is nothing a 15-minute check-in could
    # learn that the waiter's own exit will not deliver, and nothing a poll cron
    # delivers that it does not deliver sooner. Both relaxations below are keyed
    # on `confirmed` and on nothing weaker, because a waiter nobody can see on
    # the OS is exactly the case where those checks still earn their keep.
    #
    # Computed only when a waiter is actually declared, so the ordinary busy stop
    # pays no extra process-table read.
    _waiters_confirmed = []
    if live_bg:
        try:
            if wl_liveness.waiter_tasks(live_bg):
                bg_verdicts = wl_liveness.verify_background(live_bg)
                _waiters_confirmed = wl_liveness.confirmed_waiters(live_bg, bg_verdicts)
        except Exception:  # noqa: BLE001 -- a suppression heuristic must never wedge a stop
            _waiters_confirmed = []
    # EVERY live task must be a confirmed waiter, not merely one of them. A
    # session waiting on a real long job AND holding a waiter still owes the
    # check-in for the real job; relaxing on "any waiter present" would let one
    # waiter silence supervision of everything else running beside it.
    _only_waiters = bool(_waiters_confirmed) and len(_waiters_confirmed) == len(live_bg)
    if live_bg and not open_items:
        _expired_any = any(
            C.DEFAULT_TOKEN.search(r["line"])
            and (C.stamp_age_min(r.get("upd", "")) or 0) >= S.DEFER_WINDOW_MIN
            for r in deferred_recs
        )
        if not _expired_any:
            _in_pure_wait = True
            try:
                bg_facts = wl_liveness.bg_output_facts(
                    event.get("cwd"), session_id, live_bg
                )
            except Exception:  # noqa: BLE001 -- a fact-gatherer must never wedge a stop
                bg_facts = []
            try:
                # Read on EVERY pure-wait stop since v17, not only when the
                # check-in is due: the no-op ladder keys on it, and a worker
                # dying is the one change a byte-level view cannot see.
                # v18: reuse the read the waiter probe above already paid for.
                if not bg_verdicts:
                    bg_verdicts = wl_liveness.verify_background(live_bg)
            except Exception:  # noqa: BLE001 -- a fact-gatherer must never wedge a stop
                bg_verdicts = {}
            _bgw = state_doc.get("bgwait") or {}
            _last = _bgw.get("at", "")
            _age = C.stamp_age_min(_last)
            bgwait_prev = _bgw.get("fired", "")
            if _age is None:
                # First sight of the wait state SEEDS the clock silently: the
                # check-in is "you have been waiting 15 minutes, report",
                # never "you started waiting, report".
                _bgw["at"] = C.stamp_now()
                state_doc["bgwait"] = _bgw
            elif _age >= wl_liveness.BG_REPORT_MIN:
                # RESTAMPED EITHER WAY, fired only when something other than a
                # confirmed waiter is running. Suppressing without restamping
                # would leave the clock expired, so the first stop after any
                # ordinary background job joined the waiter would fire the
                # check-in INSTANTLY -- the "you started waiting, report"
                # behaviour the seed above exists to prevent, reintroduced
                # through the back door.
                _bgw["at"] = C.stamp_now()
                state_doc["bgwait"] = _bgw
                if not _only_waiters:
                    bgwait_due = True
            bgwait_next = C.stamp_ahead(wl_liveness.BG_REPORT_MIN)
    if not _in_pure_wait:
        # v17 THE LATCH RESET, and it is a fix not a tidy-up. The clock was
        # only ever WRITTEN inside the wait state, so leaving it (an open item
        # appears, a deferral expires, the workers finish) froze the stamp.
        # Re-entering a wait an hour later then found _age >= 15 on the FIRST
        # stop back and fired the check-in immediately -- precisely the "you
        # started waiting, report" behaviour the seed above exists to prevent,
        # and the reason a session that flickers in and out of waiting saw the
        # roster demand over and over. Dropping the key re-seeds it silently.
        state_doc.pop("bgwait", None)

    # STUCK DETECTION. Runs before the others so the count advances on every
    # stop, including the ones where something else already fired: a session
    # blocked three times running on the same check has also moved nothing.
    # SUPERVISED = a live background task AND an in-flight item the session is still
    # refreshing. Only that pair distinguishes "watching a long job" from "left a watch
    # running and wandered off"; a forgotten watch cannot refresh the item, because
    # refreshing it is precisely what nobody is doing.
    # CORRELATED, not just "some [>] item is fresh": a session can hold two
    # concurrent leases, one genuinely tracking the live background task and
    # one unrelated and still being renewed for some other reason. Taking the
    # freshest across ALL in-flight records let the unrelated one silence the
    # exempt-overrun even while the item tracking the ACTUAL watched job had
    # gone stale -- exactly the forgotten-watch case this exemption exists to
    # exclude. Only records whose worker:<id> tag names a task in live_bg can
    # supervise it (mirrors wl_liveness.ladder's wid-not-in-now_bg check).
    # v14 addendum: AN OPEN OPERATOR REQUEST IS SUPERVISION. When this
    # session's own question to the operator is posted, unanswered, and
    # unresolved, the ball is verifiably out of its court; a terminal-hold
    # state (all work done, DEFAULT: hold) otherwise re-fires the
    # exempt-overrun every 3x rounds forever off long-lived teammate tasks.
    # Counting continues; the moment the request is answered or acked the
    # suppression lifts by itself.
    _supervised = False
    try:
        _supervised = any(
            r.get("to") == "operator" and not r.get("acked") and not wl_requests.request_resolved(r)
            for r in req_open_mine
        )
    except Exception:  # noqa: BLE001 -- a suppression heuristic must never wedge a stop
        _supervised = False
    if live_bg and not _supervised:
        try:
            _live_ids = {str(b.get("id") or "") for b in live_bg}
            _correlated = []
            for r in in_flight_recs:
                wm = C.WORKER.search(r["line"])
                wid = r.get("worker") or (wm.group(1) if wm else "")
                if wid and wid in _live_ids:
                    _correlated.append(r)
            if _correlated:
                _freshest = min(
                    wl_liveness._age_min(r.get("upd", "")) for r in _correlated
                )
                _supervised = _freshest is not None and _freshest <= STUCK_SUPERVISED_MAX_MIN
        except Exception:  # noqa: BLE001 -- never let a suppression heuristic wedge a stop
            _supervised = False

    # Newest own stamp PLUS the own item set (id+state): stamps are
    # second-resolution, so two moves inside one second would otherwise read
    # as none, and an added-then-ticked item is movement even when the clock
    # cannot show it.
    _mine = [r for r in fold.items if C.owned_by_me(r.get("owner"), session_id)]
    _own_stamp = "%s#%s" % (
        max((str(r.get("upd") or "") for r in _mine), default=""),
        ",".join(sorted("%s%s" % (r["id"], r["state"]) for r in _mine)),
    )
    stuck_n, stuck_fired, stuck_why = stuck_rounds(
        worklist, session_id, tasks, C._git(root, "rev-parse", "HEAD"), bool(live_bg),
        supervised=_supervised, own_stamp=_own_stamp,
    )

    # ---- v10: the liveness ladder. Bookkeeping runs on EVERY stop (blocked
    # or allowed: the poll-baseline lesson), and the state doc is saved before
    # any emit below.
    ladder_pings, ladder_inv, ladder_res = [], [], []
    worker_rows, worker_verdicts = [], {}
    try:
        worker_rows, worker_verdicts = wl_liveness.worker_facts(event, session_id)
        ladder_pings, ladder_inv, ladder_res, _lchanged = wl_liveness.ladder(
            fold, session_id, event, state_doc
        )
    except Exception:  # noqa: BLE001 -- liveness must never break gating
        ladder_pings, ladder_inv, ladder_res = [], [], []
    if ladder_pings:
        # STICKY AND CLASS 0. Sticky because ladder() has already recorded the
        # fired rung against the item's stamp, so the text cannot be
        # regenerated until the item moves; class 0 because the wording is a
        # direct instruction that becomes a block at the 90-minute rung.
        outq_add(
            worklist, session_id, state_doc, "ladder",
            M.N_LADDER_PING % ("\n".join("  " + p for p in ladder_pings), me8),
            0, sticky=True,
        )
    S.save_state(worklist, session_id, state_doc)

    # ---- v11: the store-derived guide, present on EVERY full stop (allow
    # and block alike), so the session reports from the store, not memory.
    # Never breaks gating, and a broken guide SAYS SO rather than vanishing.
    try:
        guide = guided_slice(fold, session_id, worker_verdicts, me8, root)
    except Exception as exc:  # noqa: BLE001
        guide = "WORKLIST GUIDE unavailable (hook bug, fix wl_checks.guided_slice): %s" % (
            str(exc)[:160]
        )
    # v18: AN EMPTY GUIDE IS NOT INFORMATION. "no actionable items in the
    # store" was a deliberate v11 choice -- "a short honest line, never
    # ambiguous silence" -- and the operator has now overruled it on the same
    # breath as the wakeup section ("silent when there is nothing to act on...
    # efficient ai context usage"), quoting a stop whose entire output was this
    # line followed by the wakeup times. The ambiguity argument has also aged
    # out: the poll fast path already exits with zero bytes many times an hour,
    # so silence is the session's normal signal for "nothing to do" rather than
    # something it has to guess about. The line is dropped from every emit
    # path; a guide with real rows, and the unavailable-guide bug report, are
    # both untouched.
    guide_empty = guide == M.GUIDE_EMPTY
    if guide_empty:
        guide = ""
    # Every block path appends the guide as a trailing section; this keeps the
    # separator with the content, so a suppressed guide leaves no blank tail.
    guide_tail = "" if guide_empty else "\n\n" + guide
    # THE NEXT WAKEUPS SECTION USED TO RIDE THE GUIDE HERE, and it is deleted
    # rather than shortened (operator, 2026-08-04: "we don't need to print next
    # wakeup times. We should just track the hook moments and notify/warn when
    # needed. let's go for efficient ai context usage"). It printed every
    # scheduled task's next firing and prompt label on EVERY full stop, which
    # is a recurring context cost for a fact that is already in the harness and
    # that no reader ever had to act on. The schedules are still tracked -- the
    # cron-shape checks, the poll backoff ladder, the loop-death detector and
    # the judge's loop line all read session_crons directly -- and the one
    # genuinely actionable thing the section carried is now its own warning
    # (broken_schedules, below), which is silent when there is nothing wrong.

    # ---- v13: keyed, tiered violations (operator, 2026-07-31: "single and
    # focused message at a time"). Each entry is (key, always, text). `always`
    # marks the tier that can never be rotated away: latched one-shots (their
    # producers spend a budget or mark state at COMPUTE time, so hiding the
    # text swallows it forever) and hook-integrity failures. Everything else
    # is recomputed from artifacts each stop, so showing one at a time loses
    # nothing. Terse per-check wording rides the text itself.
    violations = []

    def vadd(key, always, text):
        violations.append((key, always, text))

    if bgwait_due:
        # A silent stream alone cannot distinguish "stuck" from "a poll loop
        # that prints only at the end", so OS-verify before accusing: a
        # worker whose process is confirmed alive is reported in those
        # words. Fired live 2026-07-31 on a healthy `until ... completed`
        # CI watch, 29 minutes silent by design.
        _bg_verd = bg_verdicts
        _rows = []
        for tid, desc, age, size, stale in bg_facts:
            if age is None:
                _rows.append(
                    "    %s (%s): no output stream yet (a teammate agent reports at completion)"
                    % (tid, desc)
                )
            else:
                if stale and _bg_verd.get(tid) == "confirmed":
                    _suffix = ("  <- silent but its OS process is VERIFIED ALIVE"
                               " (a loop that prints only at the end is healthy)")
                elif stale:
                    _suffix = "  <- POSSIBLY STUCK, investigate or restart"
                else:
                    _suffix = ""
                _rows.append(
                    "    %s (%s): output last grew %dm ago, %d bytes%s"
                    % (tid, desc, age, size, _suffix)
                )
        if _bg_unknown:
            _mates = len([b for b in live_bg if b.get("type") == "teammate"])
            _rows.append(M.N_ROSTER_STALE % (
                _mates, _mates - _bg_unknown, _bg_unknown,
                str(pathlib.Path(__file__).resolve().parent / "worklist.py"), me8))
        vadd("bg-report", True, M.V_BG_REPORT % (
            bgwait_prev or "never (this is the first one of this wait)",
            bgwait_next, wl_liveness.BG_REPORT_MIN, len(live_bg), "\n".join(_rows),
        ))
    if stuck_fired and something_remains:
        # TIER-ACCURATE HEADLINE. This used to assert "not one task changed
        # status AND HEAD did not advance" for every tier, which is FALSE for
        # the tasks-only tier: that one fires precisely BECAUSE commits do not
        # count, so it fires while HEAD is moving. A blocker that overstates
        # its own evidence teaches the session to distrust it.
        vadd('stuck', True,
            M.V_STUCK
            % (
                M.STUCK_HEADLINES.get(stuck_why, "NOTHING HAS MOVED"),
                stuck_n,
                M.STUCK_DETAILS.get(stuck_why, ""),
            )
        )
    if not event_ok:
        vadd('event-unparseable', True,M.V_EVENT_UNPARSEABLE % hook_file)
    if open_items:
        vadd('open-items', False,
            M.V_OPEN_ITEMS % (len(open_items), "\n".join("    " + i for i in open_items))
        )
    undefaulted = [d for d in deferred if not C.DEFAULT_TOKEN.search(d)]
    if undefaulted:
        vadd('undefaulted', False,
            M.V_UNDEFAULTED
            % (len(undefaulted), "\n".join("    " + d[:150] for d in undefaulted))
        )
    # ---- v10 AUTONOMY: a DEFAULT past its window is EXECUTED, not restated.
    # The operator: "usually I went through the 'Recommended' action". So the
    # recommendation IS the decision once the window closes; the block demands
    # the execution (bounded per stop, so a migrated backlog drains as a queue
    # rather than a wall). Fresh deferrals still just report.
    expired = [
        r for r in deferred_recs
        if C.DEFAULT_TOKEN.search(r["line"])
        and (C.stamp_age_min(r.get("upd", "")) or 0) >= S.DEFER_WINDOW_MIN
    ]
    if expired:
        shown = expired[:S.DEFER_EXEC_PER_STOP]
        vadd('defer-expired', False,
            M.V_DEFER_EXPIRED
            % (
                len(expired),
                S.DEFER_WINDOW_MIN,
                "\n".join(
                    "    #%s %s" % (r["id"], S.brief_text(r, 150)) for r in shown
                ),
                "" if len(expired) <= len(shown) else
                "    (and %d more, held back so this drains %d per stop)\n"
                % (len(expired) - len(shown), S.DEFER_EXEC_PER_STOP),
                me8,
            )
        )
    # ---- v12 JUSTIFICATION: a [?] must earn its seat. New deferrals are
    # gated at --defer; the markdown inbox and older sessions can still park
    # one without a WHY/HOW, so those are demanded once aged -- bounded, the
    # same drain shape as the expired queue. Expired items are excluded: they
    # already carry the stronger execute-the-DEFAULT demand above.
    expired_ids = {r["id"] for r in expired}
    unjustified = [
        r for r in deferred_recs
        if r["id"] not in expired_ids
        and C.DEFAULT_TOKEN.search(r["line"])
        and (C.stamp_age_min(r.get("upd", "")) or 0) >= S.JUSTIFY_AGE_MIN
        and not deferral_is_justified(r)
    ]
    if unjustified:
        shown = unjustified[:S.JUSTIFY_PER_STOP]
        vadd('unjustified', False,
            M.V_UNJUSTIFIED
            % (
                len(unjustified),
                S.JUSTIFY_AGE_MIN,
                "\n".join("    #%s %s" % (r["id"], S.brief_text(r, 150)) for r in shown),
                "" if len(unjustified) <= len(shown) else
                "    (and %d more, held back so this drains %d per stop)\n"
                % (len(unjustified) - len(shown), S.JUSTIFY_PER_STOP),
                me8,
                me8,
            )
        )
    if req_to_me or req_bcast:
        rows = []
        for r in req_to_me + req_bcast:
            seen = S.brief_age_min(worklist, r["from"], briefs)
            rows.append(
                "    #%s from %s (%s, asked %s; asker %s): %s"
                % (
                    r["id"],
                    r["from"],
                    "to you" if r["to"] != "*" else "broadcast",
                    r["at"],
                    "never briefed" if seen is None else "last seen %dm ago" % seen,
                    # THE WHOLE BODY, deliberately. The operator relayed a finding
                    # by hand because it lived in a commit message nobody reads;
                    # a truncated block that points at --requests re-creates that
                    # defect, because reading the rest is again a choice. The
                    # payload rides inside the obstacle. Bounded by
                    # REQUEST_BODY_MAX at write time, so this cannot balloon.
                    r["body"],
                )
            )
        vadd('requests', False,
            M.V_REQUESTS_WAITING % (len(req_to_me) + len(req_bcast), "\n".join(rows), me8, me8)
        )
    if req_answered:
        rows = []
        for r in req_answered:
            rows.append("    #%s (you asked: %s)" % (r["id"], r["body"][:120]))
            # Full answer/decline text, same reasoning as the request body
            # above: this block IS the delivery, and a truncation would make
            # the crucial detail depend on the asker choosing to run
            # --requests. Both are REQUEST_BODY_MAX-bounded at write time.
            for a in r["answers"]:
                rows.append(
                    "      ANSWER by %s at %s: %s"
                    % (a.get("by", "?"), a.get("at", "?"), str(a.get("body", "")))
                )
            for d in r["declines"]:
                rows.append(
                    "      DECLINED by %s at %s: %s"
                    % (d.get("by", "?"), d.get("at", "?"), str(d.get("reason", "")))
                )
        vadd('answers', False,M.V_ANSWERS_UNACKED % ("\n".join(rows), me8))
    # ---- I7: a completion claim must leave a RECORD (see wl_reggate) --------
    ev_ticks = [
        line[:150]
        for _tid, line in reg_new_ticks
        if not completion_evidence(root, line)
    ]
    ev_tasks = []
    for i, sub in reg_done_tasks:
        row = next(
            (ln for ln in (last_msg or "").splitlines() if re.search(r"#%s\b" % re.escape(i), ln)),
            "",
        )
        if not (row and completion_evidence(root, row)):
            ev_tasks.append("#%s %s" % (i, sub))
    if ev_ticks or ev_tasks:
        vadd('completion', False,
            M.V_COMPLETION_EVIDENCE
            % (
                ""
                if not ev_ticks
                else M.V_COMPLETION_TICKS % "\n".join("    " + t for t in ev_ticks),
                ""
                if not ev_tasks
                else M.V_COMPLETION_TASKS % "\n".join("    " + t for t in ev_tasks),
            )
        )
    # Persist ONLY the transitions that passed: an unevidenced completion
    # keeps its previous status in the marker, so it is re-detected and
    # re-checked next stop rather than slipping through on a later block.
    if reg_state is not None and reg_state.get("head"):
        try:
            held = {t.split()[0].lstrip("#") for t in ev_tasks}
            prev_ts = reg_state.get("task_status") or {}
            new_ts = {i: st for i, (st, _s) in C.task_statuses(session_id).items()}
            for i in held:
                if i in prev_ts:
                    new_ts[i] = prev_ts[i]
            if new_ts != prev_ts:
                reg_state["task_status"] = new_ts
                wl_reggate.save_reggate(reg_marker, reg_state)
        except Exception:  # noqa: BLE001 -- bookkeeping must never break gating
            pass
    # ---- I6 static idle detection sits BELOW the Remaining scan since v9,
    # because a VERIFIED waiting-cross-session task counts as having a wake-up.
    if bstate != "ok":
        vadd('brief', False,
            M.V_BRIEF
            % (
                bstate,
                "" if bage is None else " (%d min old, limit %d)" % (bage, S.SESSION_BRIEF_STALE_MIN),
                me8,
            )
        )
    pstate, pahead, pref = wl_ci.publish_divergence(root)
    if pstate == "stale-local":
        vadd('stale-local', False,M.V_STALE_LOCAL % (pref, pahead))
    if pstate == "diverged":
        vadd('diverged', False,M.V_DIVERGED % (pref, pahead, pref))
    # Before the PR checks, because a moved pointer changes what the PR IS.
    moves = wl_ci.submodule_pointer_moves(root)
    if moves:
        # LATCHED PER (path, target sha), NOT silenced. Before this, an
        # unpushed pointer re-fired on EVERY stop, including after a deliberate
        # decision to keep it unpushed for now -- so a session doing exactly the
        # right thing was told off once a minute, which is how a real warning
        # becomes wallpaper.
        #
        # The latch is TIME-BOXED, never permanent, and that distinction is the
        # whole design. A permanent "I acknowledged this" flag would go silent
        # on a pointer somebody genuinely forgot, which is worse than the noise
        # it removes: the check exists because a forgotten pointer ships whatever
        # the parent last recorded. So it re-fires every SUBMODULE_LATCH_MIN, and
        # a pointer moving to a NEW sha re-fires immediately because the
        # signature changes.
        _sub_sig = hashlib.sha1(
            "|".join("%s@%s" % (p, b) for p, _a, b, _w in moves).encode("utf-8")
        ).hexdigest()[:12]
        _sub = state_doc.get("subptr") or {}
        _same = _sub.get("sig") == _sub_sig
        _sub_age = C.stamp_age_min(_sub.get("at")) if _same else None
        _due = (not _same) or _sub_age is None or _sub_age >= SUBMODULE_LATCH_MIN
        if _due:
            vadd('submodule', False,
                M.V_SUBMODULE_POINTER
                % (
                    len(moves),
                    "; ".join("%s %s -> %s, %s" % (p, a, b, w) for p, a, b, w in moves),
                )
            )
            state_doc["subptr"] = {"sig": _sub_sig, "at": C.stamp_now()}
    elif state_doc.get("subptr"):
        # Pointers match again (pushed, or reverted): drop the latch so the next
        # genuine move fires at once rather than inheriting a stale window.
        state_doc.pop("subptr", None)
    # ---- v13: CI-queue backpressure (operator, 2026-07-31). Computed before
    # the freshness check because a saturated queue changes what that check
    # should say. A slack-granter must fail toward pressure: any error here
    # reads as "unknown", which is exactly today's behavior.
    try:
        qstate, qdetail = wl_ci.ci_queue_state(root, worklist, session_id)
    except Exception:  # noqa: BLE001 -- blindness must not grant slack
        qstate, qdetail = "unknown", None
    queue_note = ""
    fstate, fdetail = wl_ci.pr_body_freshness(root)
    pr_stale_folded = False
    if fstate == "stale":
        if qstate == "saturated":
            # Its whole rationale is saving a CI round; mid-jam there is no
            # round to save yet. The reminder folds into the queue note below.
            pr_stale_folded = True
        else:
            vadd('pr-stale', False, M.V_PR_STALE % fdetail)
    elif fstate == "unreadable":
        vadd('pr-unreadable', True, M.V_PR_UNREADABLE % fdetail)
    if qstate == "saturated" and qdetail:
        queue_note = M.N_CI_QUEUE % (
            qdetail.get("ref", "?"),
            qdetail.get("queued", 0),
            qdetail.get("newest_age_min", 0),
            M.N_CI_QUEUE_PR_STALE_LINE if pr_stale_folded else "",
        )
        # Class 0, volatile, and refresh_min=0 so the shown-ledger NEVER
        # suppresses it: a jam that is still a jam must say so on every stop.
        # The change-or-window latch is for slow-moving advisories; applying it
        # here would mute an actionable note for six hours after one showing.
        outq_add(worklist, session_id, state_doc, "ci-queue", queue_note, 0, refresh_min=0)
    # v10: CI trouble on the open PR. Structurally BELOW the poll fast path
    # (which exits the process above), so a 5-minute no-op poll never pays for
    # it. `live_bg` is already running-only, which ci_watch_armed relies on.
    # ci_report is a non-blocking note; it rides the allow path AND is appended
    # to the block body, so a downgraded CI failure cannot vanish behind an
    # unrelated violation.
    ci_report = ""
    try:
        cistate, cidetail = wl_ci.ci_trouble(
            root,
            worklist,
            session_id,
            live_bg,
            (last_msg or "") + "\n" + "\n".join(deferred),
        )
    except Exception as exc:  # noqa: BLE001 -- a broken CI check must SAY SO, not vanish
        cistate, cidetail = "unreadable", "%s: %s" % (type(exc).__name__, str(exc)[:120])
    if cistate == "unreadable":
        vadd('ci-unreadable', True,M.V_CI_UNREADABLE % cidetail)
    elif cistate in ("trouble", "downgraded", "soft"):
        _rows = cidetail["hard"] or cidetail["soft"]
        _txt = wl_ci.ci_rows_text(_rows, cidetail["info"])
        _pr = cidetail["info"].get("pr", "?")
        if cistate == "trouble":
            vadd('ci-red', True,
                M.V_CI_RED
                % (
                    _pr,
                    len(cidetail["hard"]),
                    "(per-JOB conclusions, never the run rollup -- a cancelled run with no "
                    "failed job is not counted here). The run is still %s.%s"
                    % (
                        "in progress, so more jobs may appear" if cidetail["live"] else "final",
                        # Partial sight is still partial: say so rather than let
                        # the list read as complete.
                        ""
                        if not cidetail["info"].get("truncated")
                        else " NOTE: only the first %d of %s checks were read, so this list may be incomplete."
                        % (len(cidetail["info"]["contexts"]), cidetail["info"].get("total", "?")),
                    ),
                    _txt,
                    wl_ci.CI_MAX_BLOCKS,
                    cidetail["n"],
                    me8,
                )
            )
        elif cistate == "soft":
            ci_report = M.CI_NOTE_RETRYABLE % (
                _pr,
                len(cidetail["soft"]),
                ", ".join(wl_ci.CI_RETRY_PATTERNS),
                _txt,
            )
        else:
            ci_report = M.CI_NOTE_DOWNGRADED % (
                _pr,
                len(cidetail["hard"]),
                cidetail["n"],
                " (you named %s, which counts as acknowledged)" % ", ".join(cidetail["acked"])
                if cidetail["acked"]
                else "",
                _txt,
            )
    if ci_report:
        # Class 0, volatile, refresh_min=0 for the same reason as the queue
        # note: ci_trouble recomputes this from the live run every stop, and a
        # PR that is still red must keep saying so. Case 128 pins it: the
        # downgraded note is what remains after the block budget is spent, so
        # latching it would leave a red PR reported exactly once.
        outq_add(worklist, session_id, state_doc, "ci-report", ci_report, 0, refresh_min=0)
    # v9: count WORK crons only. With two crons, a dead work loop behind a
    # surviving 5-minute poll was invisible to a total-count high-water mark,
    # and the work loop dying quietly is the exact failure the operator named.
    loop_died, had_crons = cron_memory(
        worklist, session_id, len(live_work_crons), loop_finished_declared(last_msg)
    )
    if loop_died:
        vadd('loop-died', False,M.V_LOOP_DIED % had_crons)
    # Explicit state mapping, NOT `!= "ok"`: a detached HEAD ("no-branch")
    # must be report-only (operator decision 2026-07-30, a deliberate
    # departure from the V_PR_UNREADABLE blocks-when-blind precedent, because
    # HEAD detaches during every interactive rebase and this operator
    # rebase-merges everything), and a missing DIRECTORY gets the bootstrap
    # wall exactly once per branch per session, latched on agent_boot_told.
    agent_note = ""
    if something_remains and astate in ("missing", "thin", "bloated", "aimless", "stale"):
        vadd('agent-state', False,
            M.V_AGENT_STATE
            % (
                agent_branch,
                astate,
                "" if aage is None else " (%d min old, limit %d)" % (aage, S.AGENT_STATE_STALE_MIN),
                S.AGENT_STATE_MIN_CHARS,
                S.AGENT_STATE_MAX_CHARS,
                me8,
            )
        )
    elif astate == "no-dir":
        if state_doc.get("agent_boot_told") != agent_branch:
            vadd('agent-bootstrap', True,M.V_AGENT_BOOTSTRAP % (agent_branch, agent_branch, agent_branch))
            state_doc["agent_boot_told"] = agent_branch
            S.save_state(worklist, session_id, state_doc)
        elif something_remains:
            vadd('agent-absent', False,M.V_AGENT_STILL_ABSENT % agent_branch)
    elif astate == "no-branch":
        agent_note = M.N_AGENT_BLIND % root
        # Class 2, volatile: recomputed from the branch state every stop.
        outq_add(worklist, session_id, state_doc, "agent-blind", agent_note, 2)
    # v18: unread sub-agent reports, on ORDINARY stops as well as at the two
    # boundaries wl_report already covers by hook. SessionStart and PostCompact
    # catch a fresh or compacted session; this catches the far commoner case of
    # a long-running session whose teammate finished twenty minutes ago and
    # whose SendMessage has since scrolled out of reach.
    #
    # REPORT-ONLY, never a violation. An unread report is information the
    # session may act on, not an obligation it owes anyone -- and there is no
    # honest evidence a stop could demand for "I read it".
    try:
        _unread = wl_report.unread(
            wl_report.store_root(root), agent_branch or wl_report.NO_BRANCH, session_id
        )
        if _unread:
            _rp = str(pathlib.Path(__file__).resolve().parent / "wl_report.py")
            _rows = "\n".join(
                "    %s%-12s %-22s %s"
                % (
                    "[SILENT] " if e.get("silent") else "",
                    e["id"],
                    str(e.get("agent"))[:22],
                    e.get("title") or "(stopped without reporting)",
                )
                for e in _unread[-10:]
            )
            if len(_unread) > 10:
                _rows = "    (%d older not shown)\n%s" % (len(_unread) - 10, _rows)
            outq_add(
                worklist, session_id, state_doc, "unread-reports",
                M.N_UNREAD_REPORTS % (
                    len(_unread), agent_branch or "?", _rows, _rp, _rp, me8
                ),
                2,
            )
    except Exception:  # noqa: BLE001 -- an advisory surface must never wedge a stop
        pass
    # v19 L2: identities that write to this store but have never stopped. The
    # CLI check refuses them at the door from now on; this is the backstop for
    # what it cannot reach -- history already written, and the deliberate hole
    # where the environment cannot name the caller.
    #
    # PRIORITY 1, not 2, and the reason is mechanical: OUTQ_PER_STOP defaults to
    # 1 and outq_drain is highest-priority-first, so a priority-2 note can queue
    # behind others for many stops. An identity split is not something to
    # ration. REPORT-ONLY: this runs on every session's Stop path and the repair
    # is not always this session's to make.
    try:
        _phantoms, _blind = phantom_identities(worklist, session_id, fold, all_reqs)
        _wp = str(pathlib.Path(hook_file).resolve())
        if _blind:
            outq_add(worklist, session_id, state_doc, "phantom-blind",
                     M.N_PHANTOM_BLIND % _blind, 1)
        elif _phantoms:
            _rows = "\n".join(
                "    %-12s %4d event(s), first seen %dm ago, owns %s"
                % (p, n, age, owns) for p, n, age, owns in _phantoms
            )
            outq_add(
                worklist, session_id, state_doc, "phantom-identity",
                M.N_PHANTOM_IDENTITY % (len(_phantoms), _rows, _wp, me8), 1,
            )
    except Exception:  # noqa: BLE001 -- a backstop must never wedge a stop
        pass
    dstate, ddrift, ddir = docs_drift(root)
    if dstate == "drifted":
        vadd('docs-drift', False,M.V_DOCS_DRIFT % (ddrift, " ".join(PROGRAM_SURFACE), ddir))
    # v9: the two-cron shape (operator directive). A looped session carries
    # exactly one 5-minute inbox poll beside at most one work loop.
    # v18: a CONFIRMED waiter satisfies this in place of a poll cron. The check
    # exists so that a looped session has SOME inbox delivery mechanism; the
    # waiter is a strictly better one (seconds of latency instead of up to the
    # cron period, and no turn spent on an empty inbox), so demanding a cron
    # beside it would be demanding the worse mechanism for its own sake.
    if live_crons and not live_poll_crons and not _waiters_confirmed:
        vadd('no-poll', False,M.V_NO_POLL_CRON % (me8, me8))
    # v18: REQUIRE a waiter -- but ONLY of a session that has been told and has
    # ignored it. The operator asked to "force contexts to run in background";
    # my first attempt keyed on "no confirmed waiter right now" and was WRONG in
    # both of its branches, measured rather than argued:
    #
    #   as a VIOLATION it broke 16 unrelated cases in this suite, because a
    #   looped session with a peer is the NORMAL state, and -- worse -- a waiter
    #   legitimately exits every time it fires, so the condition is true in
    #   exactly the window the session is supposed to be in. It punished the
    #   correct behaviour.
    #
    #   as a REPORT it was worse still: a sticky outq entry on every such stop
    #   permanently occupied a slot in a bounded queue and starved the real
    #   sections (cases 173/174 released nothing at all).
    #
    # So the trigger is the IGNORED COUNT the PostToolUse nudge maintains. The
    # nudge does the forcing -- every 10 minutes, with the exact command, at no
    # cost when satisfied -- and it resets the moment a waiter appears. This is
    # only the backstop for a session that has been asked WAITER_GRACE_NUDGES
    # times over half an hour and has not complied.
    if live_work_crons and not _waiters_confirmed:
        _dead_min = float(os.environ.get("WORKLIST_REQUEST_DEAD_MIN", "180"))
        _peers = [
            k for k in briefs
            if not C.same_session(k, session_id)
            and (S.brief_age_min(worklist, k, briefs) or _dead_min + 1) <= _dead_min
        ]
        if _peers and wl_wait.nudges_ignored(worklist, me8) >= WAITER_GRACE_NUDGES:
            vadd('no-waiter', False, M.V_NO_WAITER % (
                len(_peers),
                str(pathlib.Path(__file__).resolve().parent / "wl_wait.py"),
                me8))
    if len(live_work_crons) > 1:
        vadd('many-work-crons', False,
            M.V_MANY_WORK_CRONS
            % (
                len(live_work_crons),
                ", ".join(
                    "%s (%s)" % (c.get("id", "?"), c.get("schedule", "?"))
                    for c in live_work_crons
                ),
            )
        )
    if len(live_poll_crons) > 1:
        vadd('many-poll-crons', False,M.V_MANY_POLL_CRONS % len(live_poll_crons))
    # v18: the surviving half of the deleted NEXT WAKEUPS section. A schedule
    # this hook cannot parse is invisible to every check above -- it is neither
    # a poll cron nor a countable work cron -- so it must be said out loud
    # rather than left implicit in a list nobody prints any more.
    try:
        _broken_scheds = broken_schedules(event)
    except Exception:  # noqa: BLE001 -- a shape check must never wedge a stop
        _broken_scheds = []
    if _broken_scheds:
        vadd('broken-schedule', False,
             M.V_BROKEN_SCHEDULE % (len(_broken_scheds), "\n".join(_broken_scheds)))
    # A "blocked on you" claim the operator never confirmed is a guess about
    # someone else's intent, and it is how work parks itself indefinitely. The
    # confirmed form carries the operator's own words back.
    unconfirmed = [
        i
        for i, _, _ in tasks
        if re.search(r"#%s\b[^\n]*\bYou\b" % re.escape(i), last_msg or "")
        and not re.search(
            r"#%s\b[^\n]*You \(User Thinks So\)" % re.escape(i), last_msg or ""
        )
    ]
    if unconfirmed:
        vadd('unconfirmed', False,M.V_UNCONFIRMED % ", ".join("#" + i for i in unconfirmed))
    # THE TASK LIST IS THE OPERATOR'S VIEW. They see "23 tasks (17 done, 6 open)"
    # in the app, so a Remaining section that omits one of those six is out of
    # sync with what they are looking at. Every open task id must appear.
    missing_ids = [i for i, _, _ in tasks if not re.search(r"#%s\b" % re.escape(i), last_msg or "")]
    # EVERY REMAINING ITEM MUST DECLARE ITS STATE. "who it is blocked on" is not
    # the same question as "is anyone working it": a list where six items all look
    # alike cannot tell the operator what is moving and what is parked. The word
    # must also AGREE with the harness, which is the list they see in their app.
    state_re = re.compile(
        r"\b(ongoing|in progress|in-progress|in_progress|pending|blocked|parked|waiting-cross-session)\b",
        re.I,
    )
    ONGOING = {"ongoing", "in progress", "in-progress", "in_progress"}
    unstated, mislabelled, uncited, xw_bad, xw_ok = [], [], [], [], []
    if REMAINING_HEADING.search(last_msg or ""):
        section = (last_msg or "")[REMAINING_HEADING.search(last_msg).start():]
        for tid, _sub, status in tasks:
            line = next(
                (ln for ln in section.splitlines() if re.search(r"#%s\b" % re.escape(tid), ln)),
                "",
            )
            if not line:
                continue  # the missing-id check below already covers this
            found = state_re.search(line)
            if not found:
                unstated.append(tid)
                continue
            word = found.group(1).lower()
            # A BLOCKER IS A CLAIM ABOUT REALITY, SO IT NEEDS A SOURCE.
            # Scoped deliberately narrow. Exempt anything already backed by
            # machinery this hook can SEE: a running background task or a live
            # lease means there is a real, named object being waited on, and
            # "blocked on the operator" has its own check above. What survives
            # the filter is exactly the Wave C class: a prose blocker naming a
            # phase of this project, which is the one shape nobody can check.
            # v9: waiting-cross-session is exempt from the file citation
            # because its request id IS the citation, verified in xsession_ok
            # across the request's whole lifecycle.
            if word == "waiting-cross-session":
                ok, detail = xsession_ok(line, all_reqs, session_id)
                if ok:
                    xw_ok.append(tid)
                else:
                    xw_bad.append("#%s: %s" % (tid, detail))
            elif word in ("blocked", "parked") and not live_bg and not in_flight:
                if not re.search(r"\byou\b", line, re.I):
                    ok, detail = citation_state(root, line)
                    if not ok:
                        uncited.append("#%s %s" % (tid, detail))
            if status == "in_progress" and word not in ONGOING:
                mislabelled.append("#%s is in_progress but reads '%s'" % (tid, word))
            elif status == "pending" and word in ONGOING:
                mislabelled.append("#%s is pending but reads '%s'" % (tid, word))
    # ---- I6: static idle detection (v8; below the scan since v9) ------------
    # Disjoint from the stuck detector by geometry: stuck is active-but-futile
    # and needs three stops; this is inactive-with-nothing-inbound, whose
    # deadliest form produces NO further stops, so the counter never fires.
    # Scoped to tasks: open [ ] items and undefaulted [?] already block above,
    # and a worklist of defaulted [?] is time-boxed autonomy, which may stop.
    # v9: only WORK crons count as a wake-up (a poll fires but advances
    # nothing by itself), and a VERIFIED waiting-cross-session task is exempt,
    # because the enforced poll delivers the answer that unblocks it.
    idle_tasks = [
        i
        for i, _, _ in tasks
        if i not in xw_ok
        and not re.search(r"#%s\b[^\n]*You \(User Thinks So\)" % re.escape(i), last_msg or "")
    ]
    if idle_tasks and not in_flight and not live_bg and not live_work_crons and not open_items:
        vadd('idle', False,M.V_IDLE % ", ".join("#" + i for i in idle_tasks[:8]))
    if xw_bad:
        vadd('xsession', False,M.V_XSESSION_BAD % ("\n".join("    " + b for b in xw_bad), me8))
    # ---- v10: the blocking ladder rungs. Rung 1 (ping) NEVER blocks; it
    # rides the report below. Each blocking rung fired at most once per
    # (item, stamp) -- see wl_liveness.ladder.
    facts = "\n".join("    " + w for w in worker_rows) or "    (no background tasks running)"
    if ladder_inv:
        vadd('ladder-investigate', True,
            M.V_LADDER_INVESTIGATE
            % ("\n".join("    " + s for s in ladder_inv), facts, me8)
        )
    if ladder_res:
        vadd('ladder-resolve', True,
            M.V_LADDER_RESOLVE
            % ("\n".join("    " + s for s in ladder_res), facts, me8)
        )
    # ---- v12 CI-WAITING FORCE. The observed failure, three times in one
    # night: the only thing in flight is a CI watch, the run is healthy, and
    # the stop is a Remaining table while 30+ aged [?] sit untouched. When
    # watching CI is ALL the in-flight work, waiting is not a valid stop:
    # the aged backlog is demanded, oldest first, bounded per stop. Every
    # named item has a single-turn solo exit (do it and tick, execute its
    # DEFAULT early, or re-justify with --defer, which resets its age below
    # CI_FORCE_MIN_AGE), so pressure converts into action, never a deadlock.
    ci_watching, watch_desc = wl_ci.ci_watch_only(live_bg)
    if ci_watching:
        backlog = [
            r for r in deferred_recs
            if (C.stamp_age_min(r.get("upd", "")) or 0) >= CI_FORCE_MIN_AGE
        ]
        if backlog:
            backlog.sort(key=lambda r: -(C.stamp_age_min(r.get("upd", "")) or 0))
            rows = []
            for r in backlog[:CI_FORCE_PER_STOP]:
                if not C.DEFAULT_TOKEN.search(r["line"]):
                    verb = ("give it a DEFAULT and a WHY/HOW with --defer %s %s, "
                            "or just do it and --tick" % (me8, r["id"]))
                elif not deferral_is_justified(r):
                    verb = ("do it now and --tick %s %s '<evidence>', or justify "
                            "it with --defer (WHY/HOW)" % (me8, r["id"]))
                else:
                    verb = ("execute its DEFAULT now and --tick %s %s "
                            "'<evidence>'; the wait was the only reason to hold it"
                            % (me8, r["id"]))
                rows.append(
                    "    #%s (sat %dm) %s\n        NEXT: %s"
                    % (r["id"], C.stamp_age_min(r.get("upd", "")) or 0,
                       S.brief_text(r, 120), verb)
                )
            vadd('ci-waiting', False,
                M.V_CI_WAITING % (watch_desc, len(backlog), "\n".join(rows))
            )
    # CLAUDE.md rule 2 says discovery is always in scope and FIXING is the default;
    # the "found, not fixed" list is meant as a last resort, not a parking bay. A
    # session that ends every turn with one has converted a fixing rule into a
    # reporting habit, which is exactly what the operator objected to.
    # ANCHORED TO A LINE START, because the first version matched the phrase
    # ANYWHERE and promptly fired on a message that was DESCRIBING this very
    # check ("2. \"Found, not fixed\" is now a blocking phrase"). A gate that
    # cannot survive being written about is too broad. A real list leads a line,
    # optionally behind markdown emphasis or a heading marker; a mention sits
    # mid-sentence or inside quotes or backticks, none of which match here.
    if uncited:
        vadd('uncited', False,M.V_UNCITED % "\n".join("    " + u for u in uncited))
    if re.search(r"^[ \t>*_#-]{0,6}found,?[ \t]+not[ \t]+fixed\b", last_msg or "", re.I | re.M):
        vadd('found-not-fixed', False,M.V_FOUND_NOT_FIXED)
    if unstated:
        vadd('unstated', False,M.V_UNSTATED % ", ".join("#" + i for i in unstated))
    if mislabelled:
        vadd('mislabelled', False,M.V_MISLABELLED % "; ".join(mislabelled))
    # DELIBERATELY NOT CHECKED: "no task is in_progress". A queue where everything
    # is honestly parked is a legitimate state, and blocking on it would nag a
    # session that is correctly waiting. The case that actually matters -- driving
    # something while the operator's list still shows it pending -- is caught by
    # the agreement check above, which fires when the message says "ongoing" and
    # the harness disagrees.
    if tasks and REMAINING_HEADING.search(last_msg or "") and missing_ids:
        vadd('out-of-sync', False,
            M.V_OUT_OF_SYNC % (len(missing_ids), ", ".join("#" + i for i in missing_ids))
        )
    if something_remains and not msg_readable:
        vadd('hook-blind', True,
            M.V_HOOK_BLIND
            % (
                event.get("transcript_path", ""),
                worklist.with_suffix(".lastevent-%s.json" % me8),
                hook_file,
            )
        )
    elif (
        something_remains
        and not REMAINING_HEADING.search(last_msg or "")
        # v14 gap 6: an unchanged world accepts the banked report instead of
        # demanding a byte-identical restatement.
        and state_doc.get("last_report_sig") != st_sig
    ):
        vadd('no-remaining', False, M.V_NO_REMAINING % "\n".join("    " + r for r in remaining_lines[:12]))

    # ---- v17 THE NO-OP WAKE LADDER. Placed HERE, after the whole battery has
    # run and before anything is emitted, because "nothing changed" is only
    # provable once every check has had its say: the streak advances on a wake
    # where the ONLY thing the hook had to offer was the background check-in,
    # and the signature says even that had no new bytes behind it.
    #
    # WHAT IS NEVER SUPPRESSED: every other violation key. An open item, a
    # missing evidence tick, an expired deferral, a stuck-rounds block, a
    # hook-integrity failure -- any one of them makes the wake not quiet, so
    # this branch is not reached and the normal battery blocks as before. Only
    # the ADVISORY layer stands down: the worker roster, the guide, the judge
    # stamp and the queued report sections.
    quiet_note = ""
    if _in_pure_wait:
        _other = [v for v in violations if v[0] != "bg-report"]
        _qsig = quiet_wake_sig(st_sig, fold, session_id, live_bg, bg_facts, bg_verdicts)
        _streak = quiet_wake_bump(state_doc, _qsig, not _other)
        if not _other and _streak >= QUIET_WAKES_TO_RESCHEDULE:
            quiet_note = quiet_wake_note(live_crons, _streak)
    else:
        state_doc.pop("quietwake", None)
    # Saved EAGERLY. The counter is bookkeeping that must survive every exit
    # below, and one of them (the WORKLIST_FOCUS=off block) emits without
    # saving at all -- exactly the shape that made the output queue lose
    # latched sections before it was moved to compute-time persistence.
    S.save_state(worklist, session_id, state_doc)
    if quiet_note:
        # The only violation that can be outstanding here is the check-in, and
        # it is STOOD DOWN rather than delivered: this emit replaces the block
        # entirely. Its window is deliberately not marked as fired, so the
        # "last delivered" stamp the roster prints stays true and the next
        # genuinely eventful stop still owes it.
        bank_pollbase(worklist, session_id, cur_sig)
        counter.unlink(missing_ok=True)
        S.save_state(worklist, session_id, state_doc)
        C.emit({"systemMessage": quiet_note})
    if bgwait_due:
        # Delivered for real (this stop emits it either way below), so the
        # stamp the next check-in prints is banked here and saved eagerly:
        # the WORKLIST_FOCUS=off block path emits without saving.
        state_doc.setdefault("bgwait", {})["fired"] = C.stamp_now()
        S.save_state(worklist, session_id, state_doc)

    if violations:
        counter.write_text(str(int(counter.read_text()) + 1 if counter.exists() else 1))
        # Bank BEFORE emitting, because emit() exits the process and this is
        # the path a busy session actually takes. See bank_pollbase.
        bank_pollbase(worklist, session_id, cur_sig)
        # The reggate fail-safe promises ONE line, never silence, even on a
        # stop that blocks for other reasons. ci_report and queue_note ride
        # along rather than blocking: a downgraded CI failure or a saturated
        # queue must stay visible on a stop that blocks for something else.
        sysmsg_tail = (
            "" if not reg_forgot
            else " [reggate marker was corrupt; settled verdicts forgotten]"
        )
        extras = (
            ("\n\n" + ci_report if ci_report else "")
            + ("\n\n" + queue_note if queue_note else "")
            + ("\n\n" + email_note if email_note else "")
        )
        if os.environ.get("WORKLIST_FOCUS", "on").lower() in ("off", "0", "no"):
            C.emit(
                {
                    "systemMessage": "Stop hook: %d check(s) failed, continuing. %s%s"
                    % (
                        len(violations),
                        violations[0][2].split("\n")[0][:110],
                        sysmsg_tail,
                    ),
                    "decision": "block",
                    "reason": M.R_BLOCK
                    % (
                        len(violations),
                        "\n\n".join("  " + t for _k, _a, t in violations),
                        hook_file,
                    )
                    + extras
                    + guide_tail,
                }
            )
        # ---- v13 FOCUSED BLOCK (default). One rotating check per stop, the
        # ALWAYS tier in full when present, everything else a bare count. The
        # guide deliberately does NOT ride blocks any more (operator,
        # 2026-07-31, superseding the v11 every-full-stop mandate); the wakeup
        # section that used to ride beside it is gone entirely as of v18. The
        # guide still leads every allow stop, and the one check that needs store data
        # (no-remaining) carries its own slice inside its text. Rotation is
        # LRU over check KEYS: prune what is no longer outstanding, serve the
        # least-recently-served, break ties by the battery's own order (which
        # is already severity-shaped). Worst-case wait for any rotating check
        # is (distinct outstanding checks - 1) stops.
        focus = state_doc.setdefault("focus", {})
        seq = int(focus.get("seq") or 0) + 1
        focus["seq"] = seq
        served = focus.setdefault("served", {})
        rot = [v for v in violations if not v[1]]
        outstanding = {k for k, _a, _t in rot}
        for k in [k for k in served if k not in outstanding]:
            del served[k]
        pick = None
        if rot:
            order = {v[0]: i for i, v in enumerate(rot)}
            pick = min(rot, key=lambda v: (served.get(v[0], -1), order[v[0]]))
            served[pick[0]] = seq
        S.save_state(worklist, session_id, state_doc)
        shown = [t for _k, a, t in violations if a]
        if pick is not None:
            shown.append(pick[2])
        n_more = len(violations) - len(shown)
        C.emit(
            {
                "systemMessage": "Stop hook: %d check(s) outstanding, surfacing %d.%s"
                % (len(violations), len(shown), sysmsg_tail),
                "decision": "block",
                "reason": M.R_BLOCK_FOCUS
                % (
                    "\n\n".join(shown),
                    M.R_FOCUS_MORE % n_more if n_more else M.R_FOCUS_ONLY,
                    hook_file,
                )
                + extras,
            }
        )

    # ---- static checks clean. Ask a model whether stopping is honest. -------
    # v7: a fix-signal stop consults the judge even with an empty queue,
    # because "I fixed it, all done" is exactly the stop the regression
    # question exists for. v10: an identical world and message within the
    # cache TTL reuses the last clean "stop" verdict instead of re-paying the
    # call; fix signals always miss (they change the world signature).
    #
    # v12 DEFERRAL AUDIT (operator: "Haiku should ask 'Why' and 'How'
    # questions... there is no human rights with him"). Aged JUSTIFIED
    # deferrals ride the same judge call as an extra section, so a stop never
    # pays a second model invocation; unjustified ones were demanded
    # statically above and never reach here. Bounded batch, oldest first, and
    # a banked "valid" verdict is keyed to the item's upd stamp, so an
    # untouched item is interrogated exactly once per generation.
    audit_cache = state_doc.setdefault("defer_audit", {})
    for k in [k for k in audit_cache if k not in fold.by_id]:
        del audit_cache[k]  # its item is gone; a banked verdict for it is litter
    audit_batch = []
    if not wl_judge.JUDGE_DISABLED:
        for r in sorted(
            deferred_recs, key=lambda r: -(C.stamp_age_min(r.get("upd", "")) or 0)
        ):
            age = C.stamp_age_min(r.get("upd", "")) or 0
            if age < S.DEFER_AUDIT_MIN:
                break  # sorted oldest-first: everything after is younger
            if not C.DEFAULT_TOKEN.search(r["line"]) or not deferral_is_justified(r):
                continue
            banked = audit_cache.get(r["id"])
            if (
                isinstance(banked, dict)
                and banked.get("stamp") == r.get("upd")
                and banked.get("verdict") == "valid"
            ):
                continue
            audit_batch.append(r)
            if len(audit_batch) >= S.DEFER_AUDIT_BATCH:
                break
    audit_note = ""
    judge_cached = False
    if (something_remains or reg_signals) and not wl_judge.JUDGE_DISABLED:
        streak = int(counter.read_text()) if counter.exists() else 0
        reg_scripts = wl_reggate.package_scripts(root) if reg_signals else {}
        reg_extra = ""
        if reg_signals:
            reg_extra = M.REGGATE_PROMPT % {
                "fixset": "\n".join("  " + s for s in reg_signals[:12]),
                "keys": "\n".join(
                    "  " + k for k in sorted(k for k in reg_scripts if k.startswith("check:"))
                )
                or "  (none)",
            }
        audit_extra = ""
        if audit_batch:
            arows = []
            for r in audit_batch:
                j = S.deferral_justification(r)
                arows.append(
                    "  id=%s  sat %dm  %s\n    WHY: %s\n    HOW: %s%s"
                    % (
                        r["id"],
                        C.stamp_age_min(r.get("upd", "")) or 0,
                        r["text"][:160],
                        j.get("why", "(none)")[:200],
                        j.get("how", "(none)")[:200],
                        "".join(
                            "\n    %s: %s" % (k.upper(), j[k][:120])
                            for k in ("tried", "needs", "blocked_on")
                            if j.get(k)
                        ),
                    )
                )
            audit_extra = M.DEFER_AUDIT_PROMPT % {
                "n": len(audit_batch),
                "window": S.DEFER_WINDOW_MIN,
                "items": "\n".join(arows),
            }
        verdict = None
        if not reg_signals and not audit_batch:
            verdict = wl_judge.cached_stop_verdict(state_doc, cur_sig, last_msg)
            judge_cached = verdict is not None
        err = None
        if verdict is None:
            # The judge's loop line prefers the COMPUTED truth from the live
            # cron expansion; the declared .loop record is only the fallback
            # when no cron is visible, because its stamped next-fire goes
            # stale on write (operator, 2026-07-30: the hook was not giving
            # the correct message).
            if live_work_crons:
                _wc = live_work_crons[0]
                _wnext = C.cron_next(str(_wc.get("schedule", "")))
                _wlabel = (str(_wc.get("prompt", "")).strip().splitlines() or ["unlabelled"])[0][:70]
                loop_desc = "%s, next fire %s (%d cron%s, live schedule %s)" % (
                    _wlabel,
                    _wnext.strftime("%Y-%m-%dT%H:%M:%SZ") if _wnext else "unparseable",
                    len(live_work_crons), "" if len(live_work_crons) == 1 else "s",
                    _wc.get("schedule", "?"),
                )
            elif lstate == "none":
                loop_desc = "none declared"
            else:
                loop_desc = "%s, next fire %s (%d cron%s)" % (
                    llabel or "unlabelled", lnext.strftime("%Y-%m-%dT%H:%M:%SZ"), lcrons,
                    "" if lcrons == 1 else "s")
            queue_extra = (
                "\nNOTE: the CI queue on the publish ref is SATURATED and the "
                "session has been instructed to work locally and not push this "
                "turn; do not direct it to push.\n"
                if queue_note
                else ""
            )
            # v15: waiting on background workers with nothing else pending is
            # a recognized state; the judge must not manufacture work for it.
            if live_bg and not open_items and bg_facts:
                queue_extra += (
                    "\nNOTE: the session is in a recognized PURE BACKGROUND "
                    "WAIT (%d live worker(s); the hook checks their output "
                    "streams every %d min). Waiting is legitimate here; do "
                    "not direct the session to find unrelated work.\n"
                    % (len(live_bg), wl_liveness.BG_REPORT_MIN)
                )
            verdict, err = wl_judge.run_judge(
                remaining_lines, len(in_flight), last_msg, streak,
                loop_desc,
                cited_excerpts(root, last_msg),
                extra=reg_extra + audit_extra + queue_extra,
                # Headings only (operator decision 2026-07-30): titles of
                # hard-won facts let the judge tell a real constraint from an
                # excuse, without turning a file designed to grow forever into
                # a per-stop cost multiplier. ~145 tokens today.
                traps=S.trap_headings(root),
            )
        if err is not None:
            # FAIL CLOSED, by operator instruction. A judge that cannot answer
            # must not become the way out.
            counter.write_text(str(streak + 1))
            C.emit(
                {
                    "systemMessage": "Stop hook: judge unavailable (%s). Blocking, per "
                    "no-escape-hatch." % err[:110],
                    "decision": "block",
                    "reason": M.R_JUDGE_UNAVAILABLE % (err, hook_file, wl_judge.JUDGE_MODEL)
                    + guide_tail,
                }
            )
        # v7: the regression verdict is processed BEFORE the stop/continue
        # verdict, so a settle persists (and a regression block fires) even
        # when the judge would also say continue for other reasons.
        if reg_signals:
            kind, payload, detail = wl_reggate.apply_regression_verdict(
                verdict.get("regression_gate"), reg_scripts, root,
                reg_state, reg_sig, lines, me8,
            )
            wl_reggate.save_reggate(reg_marker, reg_state)  # persist gate_runs regardless
            if kind == "malformed":
                counter.write_text(str(streak + 1))
                C.emit(
                    {
                        "systemMessage": "Stop hook: fix landed but the judge "
                        "returned no usable regression_gate. Blocking, per "
                        "no-escape-hatch.",
                        "decision": "block",
                        "reason": M.R_REGGATE_MALFORMED % (payload, hook_file)
                        + guide_tail,
                    }
                )
            if kind == "settle":
                rg = verdict.get("regression_gate") or {}
                reg_state["fixsets"][reg_sig] = {
                    "verdict": payload,
                    "existing_gate": str(rg.get("existing_gate", ""))[:100],
                    "blind_spot": str(rg.get("blind_spot", ""))[:300],
                    "at": C.stamp_now(),
                }
                reg_state["head"] = reg_head or reg_state["head"]
                reg_state["seen_ticks"] = sorted(
                    set(reg_state["seen_ticks"]) | {t for t, _ln in reg_new_ticks}
                )
                wl_reggate.save_reggate(reg_marker, reg_state)
                reg_settled = (payload, detail)
                # STICKY: the fixset is persisted, so every later stop absorbs
                # this verdict silently and the text never returns.
                outq_add(
                    worklist, session_id, state_doc, "reg-settled",
                    "Regression gate: fix-set %s settled as %s (%s); it will not be asked again."
                    % (reg_sig[:8], reg_settled[0], (reg_settled[1] or "")[:160]),
                    1, sticky=True,
                )
            if kind == "block":
                counter.write_text(str(streak + 1))
                C.emit(
                    {
                        "systemMessage": "Stop hook: a fix landed with no "
                        "regression gate (fix-set %s). Blocking." % reg_sig[:8],
                        "decision": "block",
                        "reason": payload + guide_tail,
                    }
                )
        # v12: the audit verdicts are processed BEFORE stop/continue, same
        # precedence argument as the regression gate: a banked "valid" must
        # persist, and a do_now must fire, whatever the judge said about the
        # stop itself.
        if audit_batch:
            akind, avalids, aorders = wl_judge.apply_defer_audit(
                verdict.get("defer_audit"), audit_batch
            )
            if akind == "malformed":
                counter.write_text(str(streak + 1))
                C.emit(
                    {
                        "systemMessage": "Stop hook: a deferral audit was "
                        "requested but the judge returned no usable "
                        "defer_audit. Blocking, per no-escape-hatch.",
                        "decision": "block",
                        "reason": M.R_AUDIT_MALFORMED
                        % (repr(verdict.get("defer_audit"))[:200], hook_file)
                        + guide_tail,
                    }
                )
            for rid, stamp, reason in avalids:
                audit_cache[rid] = {
                    "stamp": stamp,
                    "verdict": "valid",
                    "reason": reason[:160],
                    "at": C.stamp_now(),
                }
            S.save_state(worklist, session_id, state_doc)
            if avalids:
                audit_note = M.N_DEFER_AUDIT_OK % (
                    len(avalids),
                    "\n".join(
                        "  #%s: %s" % (rid, reason[:160]) for rid, _st, reason in avalids
                    ),
                )
                # STICKY: the verdicts were banked into defer_audit above, and
                # a banked item is never interrogated again at that stamp, so
                # this note cannot be regenerated.
                outq_add(worklist, session_id, state_doc, "audit", audit_note, 1, sticky=True)
            if aorders:
                # The REOPEN is the enforcement: a rejected deferral becomes
                # an ordinary open [ ] item, so the existing open-items
                # machinery (and the tick evidence gate) owns it from here.
                # The exits are the open item's exits: do it and tick with
                # evidence, or re-defer with a justification that carries
                # the fact the judge missed -- which is itself re-audited.
                for rid, order in aorders:
                    S.set_state(
                        worklist, "judge", rid, " ",
                        "REOPENED by the stop-gate judge: %s" % order[:160],
                    )
                counter.write_text(str(streak + 1))
                C.emit(
                    {
                        "systemMessage": "Stop hook: the deferral audit "
                        "rejected %d justification(s); those items are open "
                        "work again." % len(aorders),
                        "decision": "block",
                        "reason": M.V_DEFER_AUDIT
                        % (
                            len(aorders),
                            "\n".join(
                                "  #%s  ORDER: %s" % (rid, order) for rid, order in aorders
                            ),
                            me8,
                        )
                        + guide_tail,
                    }
                )
        judged_ok = verdict["verdict"] == "stop"
        if verdict["verdict"] == "continue":
            counter.write_text(str(streak + 1))
            C.emit(
                {
                    "systemMessage": "Stop hook: judge says continue (%d in a row). %s"
                    % (streak + 1, verdict["reason"][:110]),
                    "decision": "block",
                    "reason": M.R_JUDGE_CONTINUE
                    % (
                        verdict["reason"],
                        verdict["next_action"],
                        "\n".join("  " + r for r in remaining_lines[:12]),
                    )
                    + guide_tail,
                }
            )
        if judged_ok and not judge_cached and not reg_signals:
            wl_judge.bank_stop_verdict(state_doc, cur_sig, last_msg, verdict.get("reason", ""))
            S.save_state(worklist, session_id, state_doc)

    counter.unlink(missing_ok=True)
    # An allowed stop banks the baseline too. A fast-path stop still must
    # not extend its own horizon: that bound is what stops the silent path
    # becoming a way to live on polls alone, and it survives this change
    # because poll_fast_path exits before reaching here.
    bank_pollbase(worklist, session_id, cur_sig)
    # The guide LEADS the allow report: it is the thing the session copies
    # into its Remaining section, so it comes before everything else. Absent
    # entirely when it had no rows (v18), which is what lets a clean stop with
    # nothing queued emit zero bytes.
    parts = [] if guide_empty else [guide]
    if judged_ok:
        # NEVER QUEUED, deliberately: this line exists so a paid model call can
        # never be invisible, and the operator requires a context-fresh session
        # to get the full statement unconditionally. Queuing it would make both
        # properties probabilistic. What is rationed is the VERBOSITY -- the
        # reason is reading material on the stop where the context was just
        # rebuilt or the reason actually changed, and a bare stamp otherwise.
        # The pop sits inside this branch so a blocked stop cannot consume the
        # marker and a WORKLIST_JUDGE=off session holds it until its first
        # judged stop.
        fresh = state_doc.pop("ctx_fresh", None)
        rsn = (verdict or {}).get("reason", "")
        rsig = hashlib.sha1(rsn.encode("utf-8", "replace")).hexdigest()[:12]
        stamp = "approved (cached)" if judge_cached else "approved"
        if fresh or (not judge_cached and rsig != state_doc.get("judge_reason_sig")):
            # Set ONLY when the full reason is shown, so the next genuinely
            # different reason still fires. bank_stop_verdict already truncates
            # at 200, so 400 is a ceiling that bites only a fresh uncached one.
            parts.append(M.N_JUDGE_STAMP_FULL % (wl_judge.JUDGE_MODEL, stamp, rsn[:400]))
            state_doc["judge_reason_sig"] = rsig
        else:
            parts.append(M.N_JUDGE_STAMP % (wl_judge.JUDGE_MODEL, stamp))
    # Every section with an earlier producer was queued at that producer's
    # call site, so it survives a stop that blocks. The four below have no
    # earlier producer: the allow path is the only place they exist, and they
    # are enqueued here in the order the report used to carry them.
    #
    # Advisory, and deliberately on the FULL-stop path only: a silent poll exits long before
    # here, so the tip lands on the ~hourly stop the session is already reading rather than
    # interrupting the quiet it is telling us to buy more of.
    # Quiet = age of the NEWEST request of any kind. An inbox that has never received
    # anything is the quietest case there is, so it escalates rather than being exempt.
    try:
        _req_ages = [C.stamp_age_min(r["at"]) for r in all_reqs.values() if r.get("at")]
        _quiet_min = min(_req_ages) if _req_ages else 10**6
    except Exception:  # noqa: BLE001 -- an advisory note must never wedge a stop
        _quiet_min = 0
    backoff_tip = poll_backoff_tip(live_crons, _quiet_min, bool(req_to_me))
    if backoff_tip:
        outq_add(worklist, session_id, state_doc, "backoff", backoff_tip, 2,
                 refresh_min=BACKOFF_NOTE_MIN, on_change=False)
    if others_briefs:
        outq_add(worklist, session_id, state_doc, "others",
                 "Other sessions in this worktree:\n" + others_briefs, 2)
    if orphaned:
        outq_add(
            worklist, session_id, state_doc, "orphans",
            "Worklist: %d ORPHANED item(s) (owner session dead; auto-archive after %sh):\n%s"
            % (
                len(orphaned),
                os.environ.get("WORKLIST_ARCHIVE_HOURS", "168"),
                "\n".join("  " + o for o in orphaned),
            ),
            2,
        )
    # The in-flight and deferred sections that used to sit here were pure
    # duplication (operator, 2026-07-31: "Why I see such a big output?"):
    # guided_slice already lists every owned [>] and [?] with its LATEST and
    # NEXT verb, and the guide LEADS this very report. One source, said once.
    if req_open_mine:
        rows = []
        for r in req_open_mine:
            if r["to"] == "*":
                who = "broadcast"
            else:
                seen = S.brief_age_min(worklist, r["to"], briefs)
                who = "to %s, %s" % (
                    r["to"],
                    "never briefed" if seen is None else "last seen %dm ago" % seen,
                )
            rows.append("  #%s (%s; asked %s) %s" % (r["id"], who, r["at"], r["body"][:120]))
        outq_add(
            worklist, session_id, state_doc, "req-open",
            "Requests you posted, still OPEN (they block their recipients, never you):\n"
            + "\n".join(rows),
            2,
        )
    if others:
        # Reported, never blocked on. Blocking one session on another's
        # items deadlocks it: it cannot do them without racing live work in
        # the same tree, and it must not tick or delete someone else's
        # tracking. Surfacing beats blocking.
        outq_add(
            worklist, session_id, state_doc, "others-items",
            "Worklist: nothing open for this session.\n" + other_sessions_note(), 2,
        )
    # ONE section per stop by default, highest priority first and FIFO inside
    # a priority class. The "+N more" tail is MANDATORY for the reason spelled
    # out at the guide's own truncation: a silent cap reads as "that is
    # everything", and a session that can see three are waiting can raise
    # WORKLIST_REPORT_PER_STOP for one turn.
    texts, remaining = outq_drain(worklist, session_id, state_doc, OUTQ_PER_STOP)
    parts.extend(texts)
    if remaining:
        parts.append(M.N_OUTQ_MORE % remaining)
    # outq_drain persisted the queue already; this save carries the judge-line
    # marker pop and any late state mutation, and one redundant atomic write is
    # cheaper than reasoning about which came last. It happens BEFORE the exit
    # below, because a silent allow must still bank everything a loud one does.
    S.save_state(worklist, session_id, state_doc)
    if not parts:
        # v18: nothing actionable, nothing queued, no judge line to show. This
        # used to be impossible (the guide was unconditional) and is now the
        # common shape of a clean stop, so it exits the way the poll fast path
        # does: zero bytes, exit 0. Everything above still ran and still
        # persisted -- the silence is the report, not a skipped battery.
        raise SystemExit(0)
    C.emit({"systemMessage": "\n\n".join(parts)})
