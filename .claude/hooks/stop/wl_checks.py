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
import wl_judge
import wl_liveness
import wl_reggate
import wl_requests
import wl_store as S
import worklist_messages as M

# Heading, any level, so "## Remaining" and "### Remaining work" both count.
REMAINING_HEADING = re.compile(r"^[ \t]{0,3}#{1,4}[ \t]*Remaining\b", re.M | re.I)

# Consecutive stops that may move nothing before the hook demands a planning or
# investigation agent. Three is the operator's number, not a guess.
STUCK_ROUNDS = int(os.environ.get("WORKLIST_STUCK_ROUNDS", "3"))

DESIGN_DOCS = os.environ.get("WORKLIST_DESIGN_DOCS", "docs/ci-overhaul")
DOCS_DRIFT_MAX = int(os.environ.get("WORKLIST_DOCS_DRIFT_MAX", "10"))
# What counts as "the program surface": changing these is changing the thing the
# design docs describe.
PROGRAM_SURFACE = os.environ.get("WORKLIST_PROGRAM_SURFACE", ".ci .github .claude").split()

# ---- v9 poll constants ------------------------------------------------------
# The poll cron is recognised by SCHEDULE SHAPE, not by id or prompt text:
# schedules are structural, survive restarts, and a work cron cannot claim the
# shape without also BECOMING a 5-minute loop.
POLL_SCHEDULE_RE = re.compile(r"^\*/5( \*){4}$")
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

def stuck_rounds(worklist, session_id, tasks, head, exempt):
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
    """
    # tasks are (id, subject, status); the STATUS is what has to move.
    base = "|".join(sorted("%s:%s" % (i, st) for i, _, st in tasks))

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


# ---- cron memory and docs drift --------------------------------------------

def cron_memory(worklist, session_id, live_count):
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
    if S.world_sig(root, worklist, session_id) != base_sig:
        return False  # tracked work happened since the last full stop
    crons = event.get("session_crons") or []
    if len([c for c in crons if is_poll_cron(c)]) != 1:
        return False
    if len([c for c in crons if not is_poll_cron(c)]) > 1:
        return False
    fold = S.load(worklist, sync=False)
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
        if state == ">":
            if C.lease_state(rec["line"]) != "fresh":
                return False  # an expiring lease is a wake-up; the battery says so
            age = C.stamp_age_min(rec.get("upd", ""))
            if age is not None and age >= wl_liveness.LADDER_INVESTIGATE_MIN:
                return False  # a blocking rung may be due
    for tid, seen in (S.load_state(worklist, session_id).get("tasks_seen") or {}).items():
        if seen.get("status") == "in_progress":
            age = C.stamp_age_min(seen.get("since", ""))
            if age is not None and age >= wl_liveness.LADDER_INVESTIGATE_MIN:
                return False
    to_me, bcast, answered, _mine = wl_requests.classify_requests(
        wl_requests.read_requests(worklist), session_id
    )
    if to_me or bcast or answered:
        return False  # the inbox is the poll's whole subject; deliver it loudly
    if wl_requests.escalate_requests(worklist, session_id, dry_run=True):
        return False  # due escalations happen on a full stop that reports them
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

GUIDE_MAX = int(os.environ.get("WORKLIST_GUIDE_MAX", "12"))
GUIDE_TEXT_CHARS = 90


def guided_slice(fold, session_id, verdicts=None, me=None):
    """The bounded, guided, store-derived instruction block.

    One line per actionable item: state, #id, age from the store's own
    stamps, the capped text, and the EXACT verb that moves it -- an open
    item gets --tick, a live lease gets --update, an undefaulted [?] gets
    --defer, an expired-window [?] gets its default-execution order. Sorted
    by priority (obligations first) so truncation drops the least urgent.
    `verdicts` (from wl_liveness.verify_background) annotates lease workers
    when the caller has an event to verify against; the CLI does not.
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
        txt = rec["text"][:GUIDE_TEXT_CHARS]
        upd = C.stamp_age_min(rec.get("upd", ""))
        age = "?" if upd is None else "%dm" % upd
        rid = rec["id"]
        if st == " ":
            rows.append((0, "  - [ ] #%s (upd %s) %s\n        NEXT: do it, then --tick %s %s '<evidence>'"
                         % (rid, age, txt, me_arg, rid)))
        elif st == ">":
            wm = C.WORKER.search(rec["line"])
            wid = rec.get("worker") or (wm.group(1) if wm else "")
            if C.lease_state(rec["line"]) == "fresh":
                osw = verdicts.get(wid, "")
                wtag = "worker:%s%s" % (wid or "?", " [%s]" % osw if osw else "")
                rows.append((3, "  - [>] #%s (quiet %s, %s) %s\n        NEXT: --update %s %s '<one line of what moved>'"
                             % (rid, age, wtag, txt, me_arg, rid)))
            else:
                rows.append((0, "  - [>] #%s LEASE DEAD (quiet %s) %s\n        NEXT: finish it and --tick %s %s '<evidence>', or re-lease: --lease %s %s +60 worker:<bg-id>"
                             % (rid, age, txt, me_arg, rid, me_arg, rid)))
        elif st == "?":
            if not C.DEFAULT_TOKEN.search(rec["line"]):
                rows.append((2, "  - [?] #%s (age %s, NO DEFAULT) %s\n        NEXT: --defer %s %s '<question> DEFAULT: <action>'"
                             % (rid, age, txt, me_arg, rid)))
            elif upd is not None and upd >= S.DEFER_WINDOW_MIN:
                rows.append((1, "  - [?] #%s WINDOW CLOSED (waited %s) %s\n        NEXT: execute its DEFAULT now, then --tick %s %s '<evidence>'"
                             % (rid, age, txt, me_arg, rid)))
            else:
                left = "?" if upd is None else "%dm" % max(0, S.DEFER_WINDOW_MIN - upd)
                rows.append((4, "  - [?] #%s (age %s) %s\n        operator may answer; its DEFAULT executes in %s"
                             % (rid, age, txt, left)))
    if not rows:
        return M.GUIDE_EMPTY
    rows.sort(key=lambda r: r[0])
    shown = rows[:GUIDE_MAX]
    out = [M.GUIDE_HEADER] + [line for _p, line in shown]
    if len(rows) > len(shown):
        out.append(M.GUIDE_TRUNCATED % (len(rows) - len(shown), GUIDE_MAX))
    return "\n".join(out)


# ---- SessionStart / PostCompact ---------------------------------------------

def handle_session_start(event):
    root = C.project_root(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or os.getcwd())
    docs = pathlib.Path(root) / DESIGN_DOCS
    if not docs.is_dir():
        return
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
    C.emit(
        {
            "systemMessage": "SessionStart: %d design doc(s) in %s%s"
            % (
                len(files),
                DESIGN_DOCS,
                "" if state != "drifted" else " (DRIFTED by %d commits)" % drift,
            ),
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": M.CTX_SESSION_START % (DESIGN_DOCS, listing, stale),
            },
        }
    )


def handle_post_compact(event):
    # PostCompact hook: the model has just lost its context. Hand the
    # document straight back as additionalContext so continuity does not
    # depend on it remembering to go looking.
    wl = C.worklist_for(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or os.getcwd())
    sid = event.get("session_id", "")
    state, _age, text = S.handover_state(wl, sid)
    if state == "missing":
        msg = M.CTX_POSTCOMPACT_MISSING % (S.handover_path(wl, sid), (sid or "unknown")[:8])
    else:
        msg = M.CTX_POSTCOMPACT_BRIEFING % (DESIGN_DOCS, text.strip())
    C.emit(
        {
            "systemMessage": "PostCompact: handover %s (%s)" % (state, S.handover_path(wl, sid).name),
            "hookSpecificOutput": {
                "hookEventName": "PostCompact",
                "additionalContext": msg,
            },
        }
    )


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
    all_reqs = {}
    try:
        all_reqs = wl_requests.read_requests(worklist)
        req_to_me, req_bcast, req_answered, req_open_mine = wl_requests.classify_requests(
            all_reqs, session_id
        )
    except Exception:  # noqa: BLE001 -- a corrupt log must not wedge every stop
        all_reqs = {}
        req_to_me, req_bcast, req_answered, req_open_mine = [], [], [], []

    lines = fold.lines()
    open_items, others, deferred_recs, in_flight_recs = S.classify_items(fold, session_id)
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
    live_bg = [b for b in (event.get("background_tasks") or []) if b.get("status") == "running"]
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
    # this stop (sync, cleanup, escalation), and reused by the handover check,
    # the poll baseline and the judge cache, so all three describe one world.
    cur_sig = S.world_sig(root, worklist, session_id)
    hstate, hage, _htext = S.handover_state(
        worklist, session_id, cur_sig=cur_sig, saved_sig=state_doc.get("handover_sig")
    )

    remaining_lines = (
        ["[ ] " + i for i in open_items]
        + ["task #%s [%s] %s" % (i, st, sub) for i, sub, st in tasks]
        + ["[?] " + d for d in deferred]
        + ["[>] " + f for f in in_flight]
    )
    something_remains = bool(remaining_lines)

    # STUCK DETECTION. Runs before the others so the count advances on every
    # stop, including the ones where something else already fired: a session
    # blocked three times running on the same check has also moved nothing.
    stuck_n, stuck_fired, stuck_why = stuck_rounds(
        worklist, session_id, tasks, C._git(root, "rev-parse", "HEAD"), bool(live_bg)
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
    S.save_state(worklist, session_id, state_doc)

    # ---- v11: the store-derived guide, present on EVERY full stop (allow
    # and block alike), so the session reports from the store, not memory.
    # Never breaks gating, and a broken guide SAYS SO rather than vanishing.
    try:
        guide = guided_slice(fold, session_id, worker_verdicts, me8)
    except Exception as exc:  # noqa: BLE001
        guide = "WORKLIST GUIDE unavailable (hook bug, fix wl_checks.guided_slice): %s" % (
            str(exc)[:160]
        )

    violations = []
    if stuck_fired and something_remains:
        # TIER-ACCURATE HEADLINE. This used to assert "not one task changed
        # status AND HEAD did not advance" for every tier, which is FALSE for
        # the tasks-only tier: that one fires precisely BECAUSE commits do not
        # count, so it fires while HEAD is moving. A blocker that overstates
        # its own evidence teaches the session to distrust it.
        violations.append(
            M.V_STUCK
            % (
                M.STUCK_HEADLINES.get(stuck_why, "NOTHING HAS MOVED"),
                stuck_n,
                M.STUCK_DETAILS.get(stuck_why, ""),
            )
        )
    if not event_ok:
        violations.append(M.V_EVENT_UNPARSEABLE % hook_file)
    if open_items:
        violations.append(
            M.V_OPEN_ITEMS % (len(open_items), "\n".join("    " + i for i in open_items))
        )
    undefaulted = [d for d in deferred if not C.DEFAULT_TOKEN.search(d)]
    if undefaulted:
        violations.append(
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
        violations.append(
            M.V_DEFER_EXPIRED
            % (
                len(expired),
                S.DEFER_WINDOW_MIN,
                "\n".join(
                    "    #%s %s" % (r["id"], r["line"][:150]) for r in shown
                ),
                "" if len(expired) <= len(shown) else
                "    (and %d more, held back so this drains %d per stop)\n"
                % (len(expired) - len(shown), S.DEFER_EXEC_PER_STOP),
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
        violations.append(
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
        violations.append(M.V_ANSWERS_UNACKED % ("\n".join(rows), me8))
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
        violations.append(
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
        violations.append(
            M.V_BRIEF
            % (
                bstate,
                "" if bage is None else " (%d min old, limit %d)" % (bage, S.SESSION_BRIEF_STALE_MIN),
                me8,
            )
        )
    pstate, pahead, pref = wl_ci.publish_divergence(root)
    if pstate == "stale-local":
        violations.append(M.V_STALE_LOCAL % (pref, pahead))
    if pstate == "diverged":
        violations.append(M.V_DIVERGED % (pref, pahead, pref))
    # Before the PR checks, because a moved pointer changes what the PR IS.
    moves = wl_ci.submodule_pointer_moves(root)
    if moves:
        violations.append(
            M.V_SUBMODULE_POINTER
            % (
                len(moves),
                "; ".join("%s %s -> %s, %s" % (p, a, b, w) for p, a, b, w in moves),
            )
        )
    fstate, fdetail = wl_ci.pr_body_freshness(root)
    if fstate == "stale":
        violations.append(M.V_PR_STALE % fdetail)
    elif fstate == "unreadable":
        violations.append(M.V_PR_UNREADABLE % fdetail)
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
        violations.append(M.V_CI_UNREADABLE % cidetail)
    elif cistate in ("trouble", "downgraded", "soft"):
        _rows = cidetail["hard"] or cidetail["soft"]
        _txt = wl_ci.ci_rows_text(_rows, cidetail["info"])
        _pr = cidetail["info"].get("pr", "?")
        if cistate == "trouble":
            violations.append(
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
    # v9: count WORK crons only. With two crons, a dead work loop behind a
    # surviving 5-minute poll was invisible to a total-count high-water mark,
    # and the work loop dying quietly is the exact failure the operator named.
    loop_died, had_crons = cron_memory(worklist, session_id, len(live_work_crons))
    if loop_died:
        violations.append(M.V_LOOP_DIED % had_crons)
    if something_remains and hstate != "ok":
        violations.append(
            M.V_HANDOVER
            % (
                hstate,
                "" if hage is None else " (%d min old, limit %d)" % (hage, S.HANDOVER_STALE_MIN),
                S.HANDOVER_MIN_CHARS,
                S.HANDOVER_MAX_CHARS,
                me8,
            )
        )
    dstate, ddrift, ddir = docs_drift(root)
    if dstate == "drifted":
        violations.append(M.V_DOCS_DRIFT % (ddrift, " ".join(PROGRAM_SURFACE), ddir))
    # v9: the two-cron shape (operator directive). A looped session carries
    # exactly one 5-minute inbox poll beside at most one work loop.
    if live_crons and not live_poll_crons:
        violations.append(M.V_NO_POLL_CRON % me8)
    if len(live_work_crons) > 1:
        violations.append(
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
        violations.append(M.V_MANY_POLL_CRONS % len(live_poll_crons))
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
        violations.append(M.V_UNCONFIRMED % ", ".join("#" + i for i in unconfirmed))
    # THE TASK LIST IS THE OPERATOR'S VIEW. They see "23 tasks (17 done, 6 open)"
    # in the app, so a Remaining section that omits one of those six is out of
    # sync with what they are looking at. Every open task id must appear.
    missing_ids = [i for i, _, _ in tasks if not re.search(r"#%s\b" % re.escape(i), last_msg or "")]
    # EVERY REMAINING ITEM MUST DECLARE ITS STATE. "who it is blocked on" is not
    # the same question as "is anyone working it": a list where six items all look
    # alike cannot tell the operator what is moving and what is parked. The word
    # must also AGREE with the harness, which is the list they see in their app.
    state_re = re.compile(
        r"\b(ongoing|in progress|in-progress|pending|blocked|parked|waiting-cross-session)\b",
        re.I,
    )
    ONGOING = {"ongoing", "in progress", "in-progress"}
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
        violations.append(M.V_IDLE % ", ".join("#" + i for i in idle_tasks[:8]))
    if xw_bad:
        violations.append(M.V_XSESSION_BAD % ("\n".join("    " + b for b in xw_bad), me8))
    # ---- v10: the blocking ladder rungs. Rung 1 (ping) NEVER blocks; it
    # rides the report below. Each blocking rung fired at most once per
    # (item, stamp) -- see wl_liveness.ladder.
    facts = "\n".join("    " + w for w in worker_rows) or "    (no background tasks running)"
    if ladder_inv:
        violations.append(
            M.V_LADDER_INVESTIGATE
            % ("\n".join("    " + s for s in ladder_inv), facts, me8)
        )
    if ladder_res:
        violations.append(
            M.V_LADDER_RESOLVE
            % ("\n".join("    " + s for s in ladder_res), facts, me8)
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
        violations.append(M.V_UNCITED % "\n".join("    " + u for u in uncited))
    if re.search(r"^[ \t>*_#-]{0,6}found,?[ \t]+not[ \t]+fixed\b", last_msg or "", re.I | re.M):
        violations.append(M.V_FOUND_NOT_FIXED)
    if unstated:
        violations.append(M.V_UNSTATED % ", ".join("#" + i for i in unstated))
    if mislabelled:
        violations.append(M.V_MISLABELLED % "; ".join(mislabelled))
    # DELIBERATELY NOT CHECKED: "no task is in_progress". A queue where everything
    # is honestly parked is a legitimate state, and blocking on it would nag a
    # session that is correctly waiting. The case that actually matters -- driving
    # something while the operator's list still shows it pending -- is caught by
    # the agreement check above, which fires when the message says "ongoing" and
    # the harness disagrees.
    if tasks and REMAINING_HEADING.search(last_msg or "") and missing_ids:
        violations.append(
            M.V_OUT_OF_SYNC % (len(missing_ids), ", ".join("#" + i for i in missing_ids))
        )
    if something_remains and not msg_readable:
        violations.append(
            M.V_HOOK_BLIND
            % (
                event.get("transcript_path", ""),
                worklist.with_suffix(".lastevent-%s.json" % me8),
                hook_file,
            )
        )
    elif something_remains and not REMAINING_HEADING.search(last_msg or ""):
        violations.append(M.V_NO_REMAINING % "\n".join("    " + r for r in remaining_lines[:12]))

    if violations:
        counter.write_text(str(int(counter.read_text()) + 1 if counter.exists() else 1))
        # Bank BEFORE emitting, because emit() exits the process and this is
        # the path a busy session actually takes. See bank_pollbase.
        bank_pollbase(worklist, session_id, cur_sig)
        C.emit(
            {
                "systemMessage": "Stop hook: %d check(s) failed, continuing. %s%s"
                % (
                    len(violations),
                    violations[0].split("\n")[0][:110],
                    # The reggate fail-safe promises ONE line, never silence,
                    # even on a stop that blocks for other reasons.
                    ""
                    if not reg_forgot
                    else " [reggate marker was corrupt; settled verdicts forgotten]",
                ),
                "decision": "block",
                # ci_report rides along rather than blocking: a CI failure that
                # has spent its block budget must still be visible on a stop
                # that blocks for some unrelated reason.
                "reason": M.R_BLOCK
                % (len(violations), "\n\n".join("  " + v for v in violations), hook_file)
                + ("\n\n" + ci_report if ci_report else "")
                + "\n\n" + guide,
            }
        )

    # ---- static checks clean. Ask a model whether stopping is honest. -------
    # v7: a fix-signal stop consults the judge even with an empty queue,
    # because "I fixed it, all done" is exactly the stop the regression
    # question exists for. v10: an identical world and message within the
    # cache TTL reuses the last clean "stop" verdict instead of re-paying the
    # call; fix signals always miss (they change the world signature).
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
        verdict = None
        if not reg_signals:
            verdict = wl_judge.cached_stop_verdict(state_doc, cur_sig, last_msg)
            judge_cached = verdict is not None
        err = None
        if verdict is None:
            verdict, err = wl_judge.run_judge(
                remaining_lines, len(in_flight), last_msg, streak,
                "none declared" if lstate == "none"
                else "%s, next fire %s (%d cron%s)"
                % (llabel or "unlabelled", lnext.strftime("%Y-%m-%dT%H:%M:%SZ"), lcrons,
                   "" if lcrons == 1 else "s"),
                cited_excerpts(root, last_msg),
                extra=reg_extra,
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
                    + "\n\n" + guide,
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
                        + "\n\n" + guide,
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
            if kind == "block":
                counter.write_text(str(streak + 1))
                C.emit(
                    {
                        "systemMessage": "Stop hook: a fix landed with no "
                        "regression gate (fix-set %s). Blocking." % reg_sig[:8],
                        "decision": "block",
                        "reason": payload + "\n\n" + guide,
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
                    + "\n\n" + guide,
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
    # into its Remaining section, so it comes before everything else.
    parts = [guide]
    if judged_ok:
        # Never let a paid model call be invisible. A gate that spends money
        # without saying so is indistinguishable from one that is not running.
        parts.append(
            "Stop-gate judge (%s) %s this stop: %s"
            % (
                wl_judge.JUDGE_MODEL,
                "approved (cached verdict, same world and message)" if judge_cached else "approved",
                (verdict or {}).get("reason", "")[:200],
            )
        )
    if ci_report:
        parts.append(ci_report)
    if ladder_pings:
        parts.append(
            M.N_LADDER_PING
            % ("\n".join("  " + p for p in ladder_pings), me8)
        )
    if others_briefs:
        parts.append("Other sessions in this worktree:\n" + others_briefs)
    if archived:
        parts.append(
            "Worklist: archived %d dead-session item(s) (state -> [~]):\n%s"
            % (len(archived), "\n".join("  " + a for a in archived))
        )
    if orphaned:
        parts.append(
            "Worklist: %d ORPHANED item(s) (owner session dead; auto-archive after %sh):\n%s"
            % (len(orphaned), os.environ.get("WORKLIST_ARCHIVE_HOURS", "168"), "\n".join("  " + o for o in orphaned))
        )
    if in_flight:
        # Allowed to stop, but never silently: the operator sees what is
        # still riding on background work every single time.
        parts.append(
            "Worklist: %d item(s) in flight on background work (lease-fresh):\n%s"
            % (len(in_flight), "\n".join("  " + d for d in in_flight))
        )
    if deferred:
        # The operator sees these even if my summary buries them. Bounded
        # display (v10): the two or three real decisions were drowning in a
        # thirty-item wall, and everything past the window is already being
        # drained by the autonomy check above.
        shown = deferred[:8]
        parts.append(
            "Worklist: %d item(s) deferred rather than done:\n%s%s"
            % (
                len(deferred),
                "\n".join("  " + d for d in shown),
                "" if len(deferred) <= 8 else "\n  ... and %d more (worklist.py --list shows all)" % (len(deferred) - 8),
            )
        )
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
        parts.append(
            "Requests you posted, still OPEN (they block their recipients, never you):\n"
            + "\n".join(rows)
        )
    if req_escalated:
        parts.append(
            "Requests ESCALATED to operator-visible [?] items (nobody left to block):\n"
            + "\n".join("  " + e for e in req_escalated)
        )
    if reg_settled:
        parts.append(
            "Regression gate: fix-set %s settled as %s (%s); it will not be asked again."
            % (reg_sig[:8], reg_settled[0], (reg_settled[1] or "")[:160])
        )
    if reg_flood:
        parts.append(
            "Regression gate: %d historical ticks were absorbed as bookkeeping "
            "(store-format change), not asked about." % reg_flood
        )
    if reg_forgot:
        parts.append(
            "Regression marker was corrupt and has been re-initialised; previously "
            "settled verdicts were forgotten, so an old fix-set may be asked once more."
        )
    if others:
        # Reported, never blocked on. Blocking one session on another's
        # items deadlocks it: it cannot do them without racing live work in
        # the same tree, and it must not tick or delete someone else's
        # tracking. Surfacing beats blocking.
        parts.append("Worklist: nothing open for this session.\n" + other_sessions_note())
    if parts:
        C.emit({"systemMessage": "\n\n".join(parts)})
