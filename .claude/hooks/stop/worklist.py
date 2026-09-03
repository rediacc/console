#!/usr/bin/env python3
"""Stop hook: refuse to end a turn while tracked work remains unhandled.

WHY: the failure this prevents is stopping to REPORT a discovery instead of
acting on it. The full design history (v1-v9: the [ ]/[x]/[?]/[>] state
machine, the harness task queue, cross-session requests, the regression
gate, the poll fast path) lives in the sibling modules beside each piece of
logic; this file is only the ENTRY POINT: the recursion guard, the CLI
dispatch, and the fail-closed wrapper.

v10 (2026-07-30, operator request): the item store moved from the markdown
file to an append-only JSONL event log (wl_store: the markdown stays as a
synced INBOX, so nothing written there is ever silently ignored); every item
carries start and last-update stamps; in-flight claims are verified against
the OS and walked up a 45/90/120-minute ladder (wl_liveness); deferrals
execute their DEFAULT after an autonomy window instead of nagging forever
(wl_checks); the compact-recovery document is agent/<me>/STATE.md with world-keyed
staleness; and the judge caches identical verdicts (wl_judge). The one
3600-line file became nine modules; worklist_messages.py remains the
catalogue of user-facing prose.

v12 (2026-07-30, operator request: "Too many '[?]'. This is an escape
hatch."): a deferral must EARN its seat. --defer validates WHY:/HOW: (plus
optional TRIED:/NEEDS:/BLOCKED_ON:) at creation and stores them as real
fields; an aged [?] without them is demanded, bounded per stop (wl_checks);
a justified one faces the judge's audit riding the existing judge call, and
a rejected justification REOPENS the item as [ ] (wl_judge.apply_defer_audit
fails closed); and a session whose only in-flight work is a CI watch is
FORCED onto the aged backlog by id and verb (wl_ci.ci_watch_only). Every
demand's exit is completable alone in one turn: do it and tick with
evidence, execute the DEFAULT, or answer the WHY/HOW honestly.

v17 (2026-08-04, operator report: "normally there is exponential backoff for
the stop hook. It seems it's running every 5 mins."): it WAS, and the cause
was scope, not cadence. wl_store.world_sig hashed the BYTES of the shared
markdown, event log and requests file, so any teammate's --add or --tick broke
every other session's poll baseline and invalidated its judge cache; measured
on the live store, 32 of 32 events in a three-hour window were foreign and
polluted half the five-minute windows. The signature is this session's own
world now (wl_store.world_sig, wl_store.my_requests_sig). Two smaller fixes
ride with it: the background check-in's clock is cleared when the wait ENDS
(it used to freeze, so re-entering a wait fired the roster demand on arrival),
and it prints its last-fired and next-earliest stamps so the latch it claims
is checkable from the message. New: the NO-OP WAKE LADDER (wl_checks
.quiet_wake_sig / quiet_wake_bump / quiet_wake_note) counts wakes on which
nothing measurably moved and, after three, collapses the whole stop to one
line asking for the next rung of the 5/10/20/40/60 poll ladder. It suppresses
ADVISORY output only: every violation that can block still blocks.

v18 (2026-08-04, operator: "we don't need to print next wakeup times. We
should just track the hook moments and notify/warn when needed. let's go for
efficient ai context usage"): two standing sections that printed on every full
stop are DELETED rather than shortened. The NEXT WAKEUPS list (every scheduled
task's next firing plus its prompt label) is gone; the schedules are still
tracked by the cron-shape checks, the backoff ladder, the loop-death detector
and the judge's loop line, and the one actionable thing the list carried is
now its own silent-until-broken warning (wl_checks.broken_schedules,
V_BROKEN_SCHEDULE). The empty WORKLIST GUIDE line ("no actionable items in the
store") is gone too, which lets a clean stop with nothing queued exit with
zero bytes the way the poll fast path does. Both supersede earlier deliberate
choices ("a short honest line, never ambiguous silence"): silence is no longer
ambiguous now that the fast path is silent many times an hour. The rule going
forward is silent when there is nothing to act on, one focused message when
there is.

MODULE MAP:
    wl_core       shared primitives (paths, git, regexes, tasks, transcript)
    wl_store      event log, markdown sync, sidecars, session state doc
    wl_requests   cross-session requests (.requests) and their CLI
    wl_liveness   worker verification against /proc|ps, the 45/90/120 ladder
    wl_ci         publish divergence, PR freshness, submodule pointers, CI
    wl_reggate    v7/v8 regression-gate machinery
    wl_judge      the stop-legitimacy judge and its verdict cache
    wl_checklist  the /handoff checklist gate over agent/programs/<slug>/CHECKLIST.md
    wl_checks     the static battery and the Stop orchestration (run_stop)
    worklist_messages  every user-facing string (arity-pinned by the suite)

INVARIANTS THAT MUST NOT MOVE:
  * STOPHOOK_CHILD is the FIRST statement of main(): `claude -p` re-fires
    this hook (proven with a marker hook; `--settings '{"hooks":{}}'` does
    NOT suppress it). Remove the guard and the hook recurses until the
    machine dies.
  * emit() exits the process, so ordering inside run_stop is load-bearing.
  * A crashing hook must BLOCK, never read as allow: an unhandled exception
    prints to stderr and NOTHING to stdout, which the harness reads as
    ALLOW, so one bug anywhere would silently disable every check. The
    __main__ wrapper below closes that hole for every mode.
  * A check that cannot read must say it is blind (the V_PR_UNREADABLE
    pattern) rather than pass quietly.
  * The store is shared: append under the lock, never rewrite wholesale.
  * NO ESCAPE HATCH (operator, explicit): judge failure, timeout, or
    malformed output BLOCKS. A block you can fix is a bug report with
    teeth, not a deadlock.

SIBLING IMPORTS ARE PROBED, NOT ASSUMED. A top-level ImportError would
crash before the fail-closed wrapper exists, print nothing to stdout, and
read as ALLOW. So every sibling is imported inside a probe; a broken one is
replaced by a shim whose every attribute access raises, naming EVERY broken
module. Query modes that need no sibling (--path, --help) keep working, and
the Stop path blocks loudly instead of failing open.

What still allows a stop:
  1. An empty world: no open items, no pending tasks, no obligations.
  2. Removing the hook from .claude/settings.json.
  3. A VERIFIED no-op inbox-poll stop (wl_checks.poll_fast_path), silent by
     design and bounded by POLL_FULL_MAX_MIN.
"""

import contextlib
import datetime
import fcntl
import json
import os
import pathlib
import re
import select
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_BROKEN = {}  # module name -> error string
_MODS = {}


class _BrokenModule:
    """Every attribute access raises, naming every unusable sibling, so the
    first USE fails into the crash handler with the full picture. The
    message lists all broken modules because the first attribute touched is
    rarely the interesting one."""

    def __init__(self, name):
        self._name = name

    def __getattr__(self, attr):
        raise RuntimeError(
            "sibling module %s is unusable (wanted %s.%s); broken: %s"
            % (
                self._name,
                self._name,
                attr,
                "; ".join("%s: %s" % (k, v) for k, v in sorted(_BROKEN.items())),
            )
        )


for _name in (
    "wl_core",
    "wl_store",
    "wl_requests",
    "wl_liveness",
    "wl_ci",
    "wl_reggate",
    "wl_judge",
    "wl_checks",
    "wl_roundlog",
    "worklist_messages",
):
    try:
        _MODS[_name] = __import__(_name)
    except Exception as _exc:  # noqa: BLE001 -- a broken sibling must not crash the probe
        _BROKEN[_name] = "%s: %s" % (type(_exc).__name__, _exc)
        _MODS[_name] = _BrokenModule(_name)

C = _MODS["wl_core"]
S = _MODS["wl_store"]
R = _MODS["wl_requests"]
CK = _MODS["wl_checks"]
J = _MODS["wl_judge"]
M = _MODS["worklist_messages"]
RL = _MODS["wl_roundlog"]

# Re-exported for direct importers (the suite drives these two as library
# functions; keeping them on this module is part of the compatibility
# surface). Absent when their module is broken, which is correct: a caller
# gets an AttributeError naming this module instead of a silent stub.
if "wl_checks" not in _BROKEN:
    cited_excerpts = _MODS["wl_checks"].cited_excerpts
    citation_state = _MODS["wl_checks"].citation_state
if "wl_ci" not in _BROKEN:
    submodule_pointer_moves = _MODS["wl_ci"].submodule_pointer_moves


def _local_project_start(event=None):
    """Self-contained twin of wl_core.project_start, for the same reason
    _local_worklist_path exists: --path and the self-contained append modes
    must answer even when every sibling module is broken, and reaching for
    C.project_start() there would raise out of _BrokenModule instead. Keep in
    lockstep with wl_core.project_start -- including the ladder ORDER, since a
    divergence here would silently point --path at a different store than the
    hook writes to."""
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return env
    cand = pathlib.Path(__file__).resolve().parents[3]
    if (cand / ".git").exists() and (cand / ".claude" / "hooks" / "stop").is_dir():
        return str(cand)
    if event:
        cwd = event.get("cwd")
        if cwd:
            return cwd
    return os.getcwd()


def _local_worklist_path(start):
    """Self-contained twin of wl_core.worklist_for, used ONLY by --path, the
    self-contained append modes and the broken-sibling block, so the queries
    every script depends on work even when every sibling is missing. Keep in
    lockstep with wl_core.worklist_for."""
    p = pathlib.Path(start).resolve()
    root = p
    for candidate in [p, *p.parents]:
        if (candidate / ".git").exists():
            root = candidate
            break
    d = pathlib.Path(os.environ.get("TMPDIR", "/tmp")) / "claude-worklist"
    d.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^A-Za-z0-9._-]", "_", str(root)).strip("_")
    return d / (slug + ".md")


def _emit(obj):
    print(json.dumps(obj))
    sys.exit(0)


def _die2(msg):
    """The `sys.exit(2)` misuse exit the top-level verbs use, as a callable, so
    _identity_or_die reports the same way whichever verb called it."""
    sys.stderr.write(msg.rstrip("\n") + "\n")
    sys.exit(2)


def _identity_or_die(me, die):
    """Refuse a `<me>` that this process cannot be. See wl_core.check_me for the
    incident that bought this.

    Applied at EVERY `<me>` parse site, and the completeness is the point: the
    defect's shape is "a rule applied to some call sites and not others", so a
    partial rollout reproduces the bug in whichever verbs were missed. The
    suite's anti-vacuity case derives the verb list from this source and fails
    when a verb it finds has no coverage, so verb 14 cannot silently reopen it.

    A BROKEN wl_core DEGRADES TO PASS rather than crashing. --brief and --loop
    are deliberately self-contained (a broken sibling must not take the roster
    or the loop channel down), and an unresolvable identity is already the
    documented "cannot verify, so say nothing" case. The Stop path still fails
    closed on the same broken module a few lines below.
    """
    if "wl_core" in _BROKEN:
        return
    ok, msg = C.check_me(me)
    if not ok:
        die(msg)


# Bounded wait for the Stop payload. Long enough for a slow writer, short
# enough that a missing payload fails the hook instead of stalling the session.
STDIN_WAIT_SECONDS = 10.0


def _read_event():
    """Read the Stop payload from stdin, bounded, without hanging or crashing.

    Two failure modes, both observed, and the naive fix for one causes the other:

    1. EAGAIN. Observed 2026-08-07: the hook died with "Failed with non-blocking
       status code: EAGAIN: resource temporarily unavailable, read". The pipe is
       sometimes handed over in NON-BLOCKING mode with the payload not yet
       written, and json.load() only caught JSONDecodeError/ValueError while
       EAGAIN surfaces as BlockingIOError, an OSError. The hook crashed, so
       EVERY stop check silently did not run.

    2. HANG. The obvious fix -- os.set_blocking(fd, True) -- makes read() wait
       forever when the writer holds the pipe open and sends nothing. Measured:
       that version had to be SIGKILLed. A hook that hangs is worse than one
       that crashes, because it stalls the session instead of failing it.

    So: wait for readability with a DEADLINE, then read what is there. Late
    payload → we wait for it. No payload → we give up, loudly, in bounded time.
    """
    deadline = time.monotonic() + STDIN_WAIT_SECONDS
    try:
        fd = sys.stdin.fileno()
    except (OSError, ValueError, AttributeError):
        fd = None

    raw = ""
    if fd is None:
        # No real fd (pytest capture, a StringIO harness): a plain read cannot
        # block on a pipe that does not exist.
        try:
            raw = sys.stdin.read()
        except Exception:  # noqa: BLE001 - any read failure here means no event
            return {}, False
    else:
        with contextlib.suppress(OSError, ValueError):
            os.set_blocking(fd, False)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                print(
                    "worklist.py: no Stop payload on stdin after %ss. This is a HOOK "
                    "failure, not a clean stop -- no check ran." % STDIN_WAIT_SECONDS,
                    file=sys.stderr,
                )
                return {}, False
            try:
                ready, _, _ = select.select([fd], [], [], min(remaining, 0.25))
            except (OSError, ValueError):
                break
            if not ready:
                continue
            try:
                chunk = os.read(fd, 65536)
            except BlockingIOError:
                continue
            except OSError as exc:
                print("worklist.py: could not read the Stop payload: %s" % exc, file=sys.stderr)
                return {}, False
            if not chunk:
                break  # EOF: the writer closed, so we have everything
            raw += chunk.decode("utf-8", "replace")

    try:
        ev = json.loads(raw) if raw.strip() else None
        return (ev, True) if isinstance(ev, dict) else ({}, False)
    except (json.JSONDecodeError, ValueError):
        # A malformed event used to degrade to {} silently, which quietly turns
        # EVERY check into "session_id is empty, nothing is configured" and
        # produces confusing advice. Fail loudly instead: a Stop payload this
        # hook cannot parse is a bug.
        return {}, False


USAGE_FALLBACK = "worklist.py: see --help (message catalogue unavailable: %s)"


PLAN_SLUG_RE = re.compile(r"[^a-z0-9-]+")


def _triage_cli(argv, worklist, me, die):
    """--triage <me> [--id <id>] <finding...>: how does this finding get fixed?

    WHY (operator, 2026-07-31): the fix-in-session rule says a finding is
    fixed by the session that finds it, and the only excuse that ever beat
    that rule was "it is too big for right now". So the machinery answers the
    size question itself and hands back the exact next command: fix it
    inline, or write a plan file and implement it this session, or the one
    door that genuinely makes it someone else's.

    DELIBERATELY ASYMMETRIC with the stop judge, which fails CLOSED because
    it gates an exit. This is a decision aid on a CLI path, so a judge error
    DEGRADES to the self-assessment printout with the error named, exit 0,
    and WORKLIST_JUDGE=off degrades the same way silently. Degraded mode
    records NO triage event: the machinery must not claim a verdict it did
    not produce. The `add` event still lands either way, so the finding is
    tracked regardless of whether the judge could answer.
    """
    args = argv[2:]
    item_id = ""
    if args[:1] == ["--id"]:
        if len(args) < 2:
            die(M.CLI_ITEM_USAGE)
        item_id = args[1].lstrip("#")
        args = args[2:]
    text = " ".join(args).replace("\n", " ").strip()
    if not text:
        die("an empty finding triages nothing: state what you found, in a line")
    root = C.project_root(C.project_start())
    if item_id:
        fold = S.load(worklist, sync=True)
        rec = fold.by_id.get(item_id)
        if rec is None:
            die("no item #%s (worklist.py --list shows ids)" % item_id)
        # owned_by_me, NOT same_session: the latter is a PEER comparison and has no
        # notion of lineage, so a compaction that renamed this session would make it
        # refuse its own items -- which is the bug this branch exists to stop. The
        # resolved id is passed rather than `me` because owned_by_me tests
        # `session_id.startswith(owner)` (a tag is a short prefix of a full id), and
        # `me` has already been identity-checked against the environment.
        if rec["owner"] is not None and not C.owned_by_me(
            rec["owner"], C.resolve_session_id() or me
        ):
            die(
                "#%s is owned by %s; never tick or edit another session's tracking"
                % (item_id, rec["owner"])
            )
    else:
        # Every triaged finding is TRACKED, before any verdict exists. A
        # finding that reaches this verb and leaves no item behind is exactly
        # the loss the worklist exists to prevent.
        item_id = S.add_item(worklist, me, text)
    print("triaging #%s: %s" % (item_id, text[:120]))
    context = CK.triage_context(root, worklist, me)
    degraded = ""
    verdict = None
    if not J.JUDGE_DISABLED:
        verdict, err = J.run_triage(text, context)
        if err:
            degraded = "\n  THE TRIAGE JUDGE COULD NOT ANSWER: %s" % err
    if verdict is None:
        print(
            M.CLI_TRIAGE_SELF
            % {
                "id": item_id,
                "me": me,
                "why": degraded,
                "context": context,
            }
        )
        return
    kind = verdict.get("verdict", "")
    reason = str(verdict.get("reason", "")).strip() or "(the judge gave no reason)"
    if kind == "plan-subagent":
        slug = PLAN_SLUG_RE.sub("-", str(verdict.get("plan_slug", "")).lower()).strip("-")
        slug = slug[:60] or item_id
        plan = "agent/PLAN-%s.md" % slug
        S.triage_item(worklist, me, item_id, kind, reason, plan)
        print(
            M.CLI_TRIAGE_PLAN
            % {
                "id": item_id,
                "me": me,
                "reason": reason,
                "plan": plan,
                "finding": text,
            }
        )
        return
    S.triage_item(worklist, me, item_id, kind, reason)
    if kind == "inline":
        print(M.CLI_TRIAGE_INLINE % {"id": item_id, "me": me, "reason": reason})
    else:
        print(M.CLI_TRIAGE_OPERATOR % {"id": item_id, "me": me, "reason": reason})


def _item_cli(argv, worklist):
    """--add / --triage / --tick / --defer / --lease / --update / --list: the
    v10 item verbs. Exits non-zero on misuse, so a rejected write cannot be
    mistaken for a delivered one."""

    def die(msg):
        print(msg, file=sys.stderr)
        sys.exit(1)

    mode = argv[0]
    if mode == "--list":
        fold = S.load(worklist, sync=True)
        if argv[1:2] == ["--open"]:
            # The same actionable slice the Stop hook emits (v11), so a human
            # and the hook are never looking at different views. An optional
            # prefix scopes ownership and binds the printed verbs.
            #
            # full=True: the hook's GUIDE_MAX cap bounds a payload nobody
            # asked for; this command IS the ask, and it is the command
            # GUIDE_TRUNCATED sends people to "for the full slice". Inheriting
            # the cap here made that advice a loop.
            me = argv[2] if len(argv) > 2 else ""
            # Checked even though it is OPTIONAL and read-only. The incident's
            # writes were wrong and its reads were right; the next one could be
            # the other way round, and a session reading the wrong half's slice
            # sees an empty, reassuring, false picture.
            if me:
                _identity_or_die(me, die)
            root = C.project_root(C.project_start())
            print(CK.guided_slice(fold, me or None, None, me or None, root, full=True))
            return
        for rec in fold.items:
            age = C.stamp_age_min(rec.get("first", ""))
            upd = C.stamp_age_min(rec.get("upd", ""))
            print(
                "%s   [#%s %s age:%s upd:%s]"
                % (
                    rec["line"],
                    rec["id"],
                    rec["origin"],
                    "?" if age is None else "%dm" % age,
                    "?" if upd is None else "%dm" % upd,
                )
            )
        return
    if len(argv) < 3:
        die(M.CLI_ITEM_USAGE)
    me = argv[1]
    if not C.PREFIX_RE.match(me):
        die("bad prefix %r: pass YOUR session-id prefix first" % me)
    _identity_or_die(me, die)
    if mode == "--add":
        text = " ".join(argv[2:]).replace("\n", " ").strip()
        if not text:
            die("an empty item tracks nothing")
        rid = S.add_item(worklist, me, text)
        print("added #%s: %s" % (rid, text))
        return
    if mode == "--triage":
        # BEFORE the item_id parse below, because like --add this verb takes
        # free text: `--triage <me> <finding...>`, with an optional
        # `--id <item>` to triage a finding that is already tracked.
        _triage_cli(argv, worklist, me, die)
        return
    item_id = argv[2].lstrip("#")
    fold = S.load(worklist, sync=True)
    rec = fold.by_id.get(item_id)
    if rec is None:
        die("no item #%s (worklist.py --list shows ids)" % item_id)
    # See the note at the sibling refusal above: owned_by_me is lineage-aware,
    # same_session is deliberately not.
    if rec["owner"] is not None and not C.owned_by_me(rec["owner"], C.resolve_session_id() or me):
        die(
            "#%s is owned by %s; never tick or edit another session's tracking"
            % (item_id, rec["owner"])
        )
    rest = " ".join(argv[3:]).replace("\n", " ").strip()
    root = C.project_root(C.project_start())
    if mode == "--tick":
        if not rest or not CK.completion_evidence(root, rest):
            die(M.CLI_TICK_NO_EVIDENCE % item_id)
        # v16 THE DOOR GATE. completion_evidence passes on ANY URL by shape,
        # so a bare issue link closed a finding: filing WAS a resolution, in
        # code, whatever the prose said. An issue now settles an item only
        # when the tick names the last-resort door that made filing the right
        # answer. Shape-only; whether the door is TRUE is the judge's
        # question, and every tick already flows into that path.
        if CK.issue_only_evidence(root, rest):
            die(M.CLI_TICK_ISSUE_DOOR % item_id)
        S.set_state(worklist, me, item_id, "x", rest)
        print("ticked #%s (%s)" % (item_id, rest[:80]))
        return
    if mode == "--defer":
        if not C.DEFAULT_TOKEN.search(rest):
            die(
                "a [?] without a DEFAULT: is a note, not a decision; append "
                "'DEFAULT: <what you will do if unanswered>'"
            )
        # v12: a deferral must EARN its seat at creation time, the same way
        # --tick refuses evidence-free completion. The cheap shape gate lives
        # here; whether the WHY is TRUE is the judge audit's question later.
        just = C.parse_justification(rest)
        why, how = just.get("why", ""), just.get("how", "")
        if not why or not how:
            die(M.CLI_DEFER_NO_JUSTIFICATION)
        vague = C.VAGUE_WHY_RE.search(why)
        if vague or len(why) < 12:
            die(M.CLI_DEFER_VAGUE_WHY % (vague.group(0) if vague else why))
        S.set_state(worklist, me, item_id, "?", rest, extra={"j": just})
        print(
            "deferred #%s with its justification on record; it is reported "
            "every stop, its WHY faces the judge's audit after %d min, and "
            "its DEFAULT executes after %d min" % (item_id, S.DEFER_AUDIT_MIN, S.DEFER_WINDOW_MIN)
        )
        return
    if mode == "--update":
        if not rest:
            die("an empty update updates nothing: one line of what moved")
        # v17 THE VANISHING DEFAULT. An --update on a `- [?]` silently dropped
        # its DEFAULT:, because the rendered line carries only the MOST RECENT
        # update (CK scans rec["line"]). So the deferral's default stopped
        # being visible the instant any progress landed, and the next stop
        # blocked on a [?] that demonstrably HAD a default when it was written.
        # Hit live, by the session that wrote this.
        #
        # REFUSING was the first fix and it was WRONG, caught by case 141: a
        # refresh is documented as "the exit is always available", and the
        # aged-deferral rung tells a session to refresh. Blocking it removes
        # the only exit the rung offers -- the same shape as the --lease
        # release comment below. So the default is carried forward VERBATIM and
        # the carry is announced. Silence was the defect; the exit is not.
        _cur = next((r for r in fold.items if r["id"] == item_id), None)
        if _cur is not None and _cur["state"] == "?" and not C.DEFAULT_TOKEN.search(rest):
            _src = _cur.get("text") or ""
            _m = C.DEFAULT_TOKEN.search(_src)
            if _m:
                _tail = C.JUST_TOKEN.search(_src, _m.end())
                _carried = _src[_m.start() : _tail.start() if _tail else len(_src)].strip()
                rest = "%s  %s" % (rest, _carried)
                print(
                    "NOTE: #%s is deferred and this update carried no DEFAULT:, so the "
                    "existing one was carried forward verbatim:\n    %s\n"
                    "Restate it yourself if the design moved -- a default that outlives "
                    "the change it was written under still EXECUTES." % (item_id, _carried),
                    file=sys.stderr,
                )
        S.update_item(worklist, me, item_id, rest)
        print("updated #%s" % item_id)
        return
    if mode == "--lease":
        if len(argv) < 4:
            die(M.CLI_ITEM_USAGE)
        # RELEASE, the missing third exit. The quiet-worker rung tells a session
        # to "finish the item, re-delegate with a new worker id, or RECLASSIFY
        # it" -- and until this existed the third option had no verb. --lease
        # could only ever set [>]; nothing moved an item back to open. So a
        # session whose worker had legitimately finished, with the item NOT done
        # and no honest successor to lease, had exactly two false choices: tick
        # work that was not finished, or lease a worker that was not measuring
        # it. Both are the stale claim the rung exists to prevent, arrived at by
        # following the rung's own instructions.
        if argv[3] in ("release", "none", "-"):
            # `item_id`, NOT a second read of argv[2]. Review finding on PR #551:
            # this branch used the raw argument while every other verb in this
            # function goes through the `.lstrip("#")` at the top, so
            # `--lease #abc123 release` -- copied straight from this tool's OWN
            # output, which prints ids as `#abc123` -- appended an unlease event
            # for an id matching nothing, printed "released ##abc123", and left
            # the item [>]. A verb that reports success while changing nothing is
            # the defect this whole file exists to catch, and it shipped inside
            # the fix for a different silent no-op.
            _rid = item_id
            S.append_events(
                worklist,
                [
                    {
                        "ev": "unlease",
                        "id": _rid,
                        "at": C.stamp_now(),
                        "by": me,
                        "t": " ".join(argv[4:]).strip()
                        or "worker finished; no successor rides this",
                    }
                ],
            )
            print(
                "released #%s back to open; it is ordinary open work again, "
                "claimed by no worker" % _rid
            )
            return
        until_arg = argv[3]
        if until_arg.startswith("+") and until_arg[1:].isdigit():
            minutes = min(int(until_arg[1:]), C.MAX_LEASE_MIN)
            until = (C.utcnow() + datetime.timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%MZ")
        else:
            until = until_arg.replace("until:", "")
        wm = next((a for a in argv[4:] if a.startswith("worker:")), "")
        if not wm:
            die(
                "a [>] lease must name its worker (worker:<background-task-id>); "
                "an in-flight claim with no worker to trace is the gap this "
                "program exists to catch"
            )
        note = " ".join(a for a in argv[4:] if not a.startswith("worker:")).strip()
        if C.lease_state("until:%s" % until) != "fresh":
            die(
                "until:%s is not a valid fresh lease (ISO8601Z, at most %d min ahead)"
                % (until, C.MAX_LEASE_MIN)
            )
        wid = wm.split(":", 1)[1]
        # v14 gap 3: validate the worker id against the harness's last event
        # AT LEASE TIME. The hook verifies leases against OS-visible task ids,
        # and an Agent's NAME is not its task id: a lease on the name reads as
        # unverifiable forever, which cost a false "worker is gone" round. A
        # warning, not a refusal, because the sidecar can lag a just-started
        # task; a genuinely wrong id still gets caught by the hook's verifier.
        verified = ""
        try:
            _ev = json.loads(
                worklist.with_suffix(".lastevent-%s.json" % me[:8]).read_text(encoding="utf-8")
            )
            _running = sorted(
                str(b.get("id") or "")
                for b in (_ev.get("background_tasks") or [])
                if b.get("status") == "running"
            )
        except (OSError, ValueError):
            _running = None
        was_verified = False
        if _running is not None:
            if wid in _running:
                was_verified = True
                verified = " (worker verified against the harness's running tasks)"
            else:
                # Name BOTH causes, and annotate the ids. The message used to
                # offer only "you named an Agent", which sends a caller hunting
                # for a task id that does not exist when the real cause is the
                # second one: the sidecar event is a SNAPSHOT, so a task started
                # moments ago is legitimately absent from it.
                #
                # The ids are annotated with their output-file age because the
                # bare list reads as "these are alive" and it is not: this list
                # is the harness's last word, and a task whose process has died
                # stays in it. A caller trusted that literally this session and
                # nearly pointed a second writer at a dead worker's files.
                print(
                    "WARNING: worker:%s is not among the harness's running background "
                    "task ids. Two causes: you leased an Agent's NAME instead of its "
                    "task id, OR the task started after the last sidecar snapshot, "
                    "which is expected and harmless. Last known running (age = minutes "
                    "since its output last grew; a stale age means the entry may "
                    "already be dead): %s" % (wid, _annotated_running(_running, me) or "none")
                )
        # The verification bit is PERSISTED, not just printed. Liveness needs it
        # to tell a worker that died from one that was never confirmable, and
        # until now it was computed here and dropped on the floor.
        S.lease_item(worklist, me, item_id, until, wid, note, worker_verified=was_verified)
        print("leased #%s until %s on %s%s" % (item_id, until, wm, verified))
        return
    die("unknown item mode %s" % mode)


def _annotated_running(ids, me):
    """Render harness-reported running task ids with their output-file age.

    The bare id list reads as a roster of LIVE workers, and it is not: it is
    the harness's last word, and an entry stays in it after its process dies.
    A caller in this session read that list literally, concluded a worker was
    alive, and came within one command of pointing a second writer at the files
    a dead worker had been given. The age is the cheapest available correction:
    it comes from the output stream's mtime, which no self-report can fake.

    Silent about what it cannot measure. A task with no output file yet (an
    agent that reports only at completion) is printed bare rather than accused,
    for the same reason the ladder reports an unverifiable worker instead of
    declaring it dead.
    """
    facts = {}
    try:
        # Resolve the task directory by SESSION PREFIX. The liveness module
        # derives it from a full session id supplied by the harness event, and
        # there is no event on this path -- a --lease is a plain CLI call. The
        # first cut passed an empty id, found no files, and annotated nothing
        # while still printing a confident list: a check that silently could not
        # fire, which is worse than no check because the caller reads the bare
        # ids as verified.
        munged = re.sub(r"[^A-Za-z0-9]", "-", os.getcwd())
        root = os.path.join(tempfile.gettempdir(), "claude-%d" % os.getuid(), munged)
        base = ""
        with contextlib.suppress(OSError):
            for d in sorted(os.listdir(root)):
                if d.startswith(me) and os.path.isdir(os.path.join(root, d, "tasks")):
                    base = os.path.join(root, d, "tasks")
                    break
        if not base:
            return ", ".join(ids[:10])
        for i in ids:
            with contextlib.suppress(OSError):
                st = os.stat(os.path.join(base, i + ".output"))
                facts[i] = int((time.time() - st.st_mtime) / 60.0)
    except Exception:  # noqa: BLE001 -- an annotation must never break the lease
        facts = {}

    out = []
    for i in ids[:10]:
        age = facts.get(i)
        out.append("%s (%dm)" % (i, age) if age is not None else i)

    return ", ".join(out)


def _adopt_cli(argv):
    """`--adopt <me> <prev>`: record that a compaction split one conversation.

    THE SIBLING OF --reassign, AND ITS OPPOSITE. --reassign repairs a FICTION and
    is proven by ABSENCE: an identity that wrote events and never stopped. --adopt
    joins two REAL identities and is proven by PRESENCE: harness-written evidence
    that both transcripts belong to one conversation. Merging them would mean one
    verb whose evidence test flips depending on its argument, so they stay apart.

    There is deliberately NO --force. The whole value of the edge is that it was
    proven; an unprovable one recorded anyway would let any session claim any
    other's items, which is precisely what the ownership rule exists to prevent.
    When the evidence is genuinely absent the operator's WORKLIST_SESSION_ID
    override remains, and that is recorded as a human's declaration rather than as
    a derived fact.
    """
    if len(argv) < 3:
        sys.stderr.write(M.CLI_ADOPT_USAGE)
        sys.exit(2)
    me, prev = argv[1], argv[2]
    if not C.PREFIX_RE.match(me) or not C.PREFIX_RE.match(prev):
        sys.stderr.write(M.CLI_ADOPT_USAGE)
        sys.exit(2)
    _identity_or_die(me, _die2)
    if C.same_session(me, prev):
        sys.stderr.write(M.CLI_ADOPT_SELF % prev)
        sys.exit(2)

    # Imported HERE, not at module scope, and deliberately: wl_lineage opens and
    # mmaps transcripts, and every other verb in this CLI -- run ~880 times by
    # the case suite alone -- has no use for it. One verb pays for it.
    import wl_lineage  # noqa: PLC0415

    sid = C.resolve_session_id() or me
    projects = C.projects_dir(C.project_root(os.getcwd()))
    transcript = os.environ.get("CLAUDE_TRANSCRIPT_PATH") or wl_lineage.transcript_for(
        sid, projects
    )
    resolved, ev = wl_lineage.resolve(sid, transcript, projects, claimed_prev=prev)
    if resolved is None:
        sys.stderr.write(M.CLI_ADOPT_REFUSED % (me, prev, ev))
        sys.exit(2)

    worklist = C.worklist_for(C.project_start())
    stamp = C.stamp_now()
    S.append_events(
        worklist,
        [
            {
                "ev": "lineage",
                "at": stamp,
                "by": me,
                "prev": resolved,
                "next": sid,
                "via": ev["via"],
                "ev_id": ev["ev_id"],
                "shared": ev["shared"],
                "prev_tx": ev["prev_tx"],
                "next_tx": ev["next_tx"],
            }
        ],
    )
    fold = S.load(worklist, sync=True)
    mine = [
        r for r in fold.items if r["state"] in (" ", "?", ">") and C.owned_by_me(r["owner"], sid)
    ]
    sys.stdout.write(
        M.CLI_ADOPT_DONE
        % (me, prev, ev["via"], ev["basis"], (ev["ev_id"] or "n/a")[:8], len(mine), me)
    )


def _reassign_cli(argv):
    """`--reassign <me> <phantom-prefix>`: take over a dead identity's work.

    THE REPAIR VERB for what the identity check cannot heal by refusing: items
    and requests already written under a `<me>` that was never a session. The
    Stop hook's phantom backstop points here, and a backstop with no fix verb is
    a nag.

    THREE RULES, each one guarding a way this could become a weapon:

    * `<me>` faces the same identity check as every other verb, so you cannot
      reassign work TO a fiction and make the problem worse.
    * `<phantom>` must have no `.lastevent-<prefix>.json` -- it must never have
      stopped. This is what stops --reassign becoming a way to steal a LIVE
      peer's items, which CLAUDE.md forbids in as many words ("never tick or
      remove an item that is not yours").
    * OPEN items and OPEN requests only. History is left exactly as it was:
      the phantom really did write those events, and a log that lies about that
      is worse than one that is untidy.

    Appends `reassign` events; nothing is ever rewritten. Both logs are
    append-only and fold-derived, which is what makes the lock-free design
    sound, and the fold arms that read these events live beside the events they
    interpret (wl_store._fold_events, wl_requests.read_requests).
    """
    if len(argv) < 3:
        sys.stderr.write(M.CLI_REASSIGN_USAGE)
        sys.exit(2)
    me, phantom = argv[1], argv[2]
    if not C.PREFIX_RE.match(me) or not C.PREFIX_RE.match(phantom):
        sys.stderr.write(M.CLI_REASSIGN_USAGE)
        sys.exit(2)
    _identity_or_die(me, _die2)
    if C.same_session(me, phantom):
        _die2("%s is you; there is nothing to take over" % phantom)
    worklist = C.worklist_for(C.project_start())
    if worklist.with_suffix(".lastevent-%s.json" % phantom[:8]).exists():
        _die2(M.CLI_REASSIGN_ALIVE % (phantom, phantom))
    fold = S.load(worklist, sync=True)
    # AGE GATE, and without it the guarantee above is not delivered. The
    # `.lastevent-` file is written exactly once, when the Stop hook first runs
    # for a session. A session that is mid-turn -- it has added items but has
    # not yet reached its first stop -- has no such file either, so the check
    # above cannot tell it from a genuine phantom. Any session can read a peer's
    # prefix out of `--list --open` output, and concurrent sessions in one tree
    # are routine here, so without this a peer's OPEN items and request routing
    # could be moved onto the caller WHILE that peer was actively working on
    # them. The docstring and the refusal message both promise this cannot
    # happen; this is the code that makes the promise true.
    #
    # Same threshold and same derivation as the advisory backstop
    # (wl_checks.phantom_identities), deliberately: two different answers to
    # "is this identity a phantom" is how the two drift apart.
    _first = ""
    for _ev in S._read_events(worklist):
        _by, _at = str(_ev.get("by") or ""), str(_ev.get("at") or "")
        if _by and _at and C.same_session(_by, phantom) and (not _first or _at < _first):
            _first = _at
    _age = C.stamp_age_min(_first)
    if _age is None:
        # No events at all under that prefix: there is nothing to move, and
        # saying "too young" would misdescribe it as a live peer.
        _die2(M.CLI_REASSIGN_EMPTY % (phantom, phantom))
    if _age < CK.PHANTOM_MIN:
        _die2(M.CLI_REASSIGN_YOUNG % (phantom, _age, CK.PHANTOM_MIN, phantom))
    stamp = C.stamp_now()
    moved_items = [
        rec["id"]
        for rec in fold.items
        if rec["state"] in (" ", "?", ">")
        and rec["owner"] is not None
        and C.same_session(rec["owner"], phantom)
    ]
    if moved_items:
        S.append_events(
            worklist,
            [
                {"ev": "reassign", "id": rid, "at": stamp, "by": me, "o": me, "from_o": phantom}
                for rid in moved_items
            ],
        )
    reqs = R.read_requests(worklist)
    moved_reqs = []
    for r in sorted(reqs.values(), key=lambda x: x["at"]):
        if r["acked"] or R.request_resolved(r):
            continue
        ev = {"ev": "reassign", "id": r["id"], "at": stamp, "by": me}
        if C.same_session(r["from"], phantom):
            ev["from"] = me
        if C.same_session(r["to"], phantom):
            ev["to"] = me
        if "from" in ev or "to" in ev:
            R.append_request_event(worklist, ev)
            moved_reqs.append(r["id"])
    if not moved_items and not moved_reqs:
        print("nothing open under %s; the history stays as it is" % phantom)
        return
    print(
        M.CLI_REASSIGN_DONE
        % (
            phantom,
            me,
            ", ".join("#" + i for i in moved_items) or "(none)",
            ", ".join("#" + i for i in moved_reqs) or "(none)",
            me,
            me,
        )
    )


def _teammate_idle_cli():
    """Journal one TeammateIdle edge. Best effort, by design.

    The payload carries the COMMON hook fields (session_id, transcript_path,
    cwd, hook_event_name) plus agent_id/agent_type in subagent context. It does
    NOT carry the teammate's name, so the name is recovered from the sibling
    meta.json the harness wrote next to the transcript -- the same file
    `wl_liveness._teammate_meta` joins on, read from the other end.

    A record with NO name is still written, keyed by agent id. It costs one line
    and it is the only evidence available that this hook fires here AT ALL,
    which as of 2026-08-23 is unobserved for Agent-tool subagents. A feature
    that silently writes nothing when the event does not fire is
    indistinguishable from one that is working, which is the whole class of
    error this item exists to remove.
    """
    import wl_store as S  # noqa: PLC0415 -- sibling, probed not assumed

    raw = "" if sys.stdin.isatty() else sys.stdin.read()
    try:
        event = json.loads(raw) if raw.strip() else {}
    except ValueError:
        event = {}
    if not isinstance(event, dict):
        event = {}
    cwd = event.get("cwd") or os.getcwd()
    transcript = event.get("transcript_path") or ""
    # `teammate_name` FIRST, because that is what the event actually carries.
    # Measured on a live probe 2026-08-23 rather than read off a doc page: the
    # published hook reference documents no input schema for TeammateIdle at
    # all, and the payload turned out to be
    #   cwd, hook_event_name, permission_mode, prompt_id, session_id,
    #   team_name, teammate_name, transcript_path
    # -- no `agent_id`, and no `name`. The first cut of this function looked for
    # `agent_id` and fell back to the transcript's sibling meta.json, so every
    # record landed with name=null and `idle_edge`, which joins on name, could
    # never match one. The journal fired correctly and was unusable, which is
    # the failure mode that looks exactly like a hook that never fires.
    name = event.get("teammate_name") or None
    if name is None and transcript.endswith(".jsonl"):
        meta = pathlib.Path(transcript)
        meta = meta.with_name(meta.name[: -len(".jsonl")] + ".meta.json")
        try:
            info = json.loads(meta.read_text(encoding="utf-8", errors="replace"))
            name = info.get("name") if isinstance(info, dict) else None
        except (OSError, ValueError):
            name = None
    rec = {
        "at": time.time(),
        "name": name,
        "agent_id": event.get("agent_id"),
        "agent_type": event.get("agent_type"),
        "session": event.get("session_id"),
    }
    if name is None:
        # DIAGNOSTIC, and it earns its place. Measured 2026-08-23 on a live
        # probe: TeammateIdle fires, but the payload arrived with no agent_id
        # and no usable transcript_path, so the name could not be recovered and
        # `idle_edge` -- which joins on name -- can never match the record. A
        # record that cannot be joined is indistinguishable from a hook that
        # never fired, which is the exact ambiguity this whole item exists to
        # remove. Recording the payload's KEYS (never its values) makes the next
        # occurrence self-diagnosing instead of another round of probing.
        rec["unjoinable_payload_keys"] = sorted(event)
    path = S.teammate_idle_path(C.worklist_for(C.project_start({"cwd": cwd})))
    path.parent.mkdir(parents=True, exist_ok=True)
    # One line, one write, O_APPEND. Atomic against concurrent teammates at this
    # size, which is why this needs no lock -- unlike the event log, nothing
    # here is read-modify-write.
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")


def main():
    # FIRST STATEMENT, DELIBERATELY. `claude -p` runs this hook again; the guard
    # is the only thing that works (--settings with empty hooks does not).
    if os.environ.get("STOPHOOK_CHILD"):
        sys.exit(0)

    # BEFORE every other arm. Asking a tool how to use it must never reach the
    # Stop-hook path, which reads stdin as JSON and, finding none, emits a block
    # telling the caller they have a hook bug. That happened, and the answer to
    # "how do I use this" was a wall of unrelated advice.
    if sys.argv[1:2] and sys.argv[1] in ("--help", "-h", "help"):
        try:
            print(M.USAGE)
        except Exception:  # noqa: BLE001 -- help must not crash on a broken catalogue
            print(USAGE_FALLBACK % "; ".join(sorted(_BROKEN)))
        return

    if len(sys.argv) > 1 and sys.argv[1] == "--path":
        # Self-contained: works with every sibling broken (see case 118).
        print(_local_worklist_path(_local_project_start()))
        return
    if len(sys.argv) > 1 and sys.argv[1] == "--compact":
        S.compact(C.worklist_for(C.project_start()))
        return
    if sys.argv[1:2] == ["--state"] and len(sys.argv) < 3:
        # BEFORE the real handler and matched on argv[1] ALONE, which is the
        # whole point: the old guard required argv[2] to enter this branch at
        # all, so a bare `--state` fell through to the hook path below and hung
        # forever reading the event from stdin (report #7c1c2629).
        sys.stderr.write(M.CLI_STATE_USAGE)
        sys.exit(2)
    if len(sys.argv) > 2 and sys.argv[1] == "--state":
        # `... --state <prefix>` with THIS SESSION'S SECTION BODY on stdin.
        #
        # It used to be the whole document, and last-write-wins was called
        # deliberate: "a document whose contract is rewrite-every-time has no
        # merge semantics". On 2026-08-09 that contract met three live sessions
        # in one checkout. The staleness gate nagged 99ccf057 about a document
        # 2fd369e0 owned, 99ccf057 obeyed, and a peer's entire state document
        # (a live canary campaign, attempt 6 in flight) was destroyed. It came
        # back only because the single-slot .prev backup was read before the
        # next write overwrote it.
        #
        # So the document has merge semantics now: one OWNED SECTION per
        # session, replaced or appended in place under the existing flock,
        # every other section byte-identical afterwards. flock + tempfile +
        # os.replace still makes the write atomic. The success line names what
        # was kept and what was reaped, because a session that cannot see the
        # peers cannot be expected to respect them.
        wl = _local_worklist_path(_local_project_start())
        prefix = sys.argv[2]
        _identity_or_die(prefix, _die2)
        root = C.project_root(C.project_start())
        # NO BRANCH GUARD any more (2026-08-18): the document is keyed on the
        # session alone, so a detached HEAD -- which this operator gets on every
        # interactive rebase -- no longer makes the one artifact designed to
        # survive compaction unwritable.
        if not S.agent_session_dir(root, prefix).is_dir():
            # NEVER auto-created (operator decision 2026-07-30): bootstrapping
            # is a judgement call a tool must not make. MY OWN directory since
            # the split: a session joining a checkout a peer bootstrapped still
            # has nowhere of its own to write, and creating it for them would
            # make that decision on their behalf.
            sys.stderr.write(M.CLI_STATE_NO_DIR % (prefix, prefix))
            sys.exit(2)
        # isatty FIRST: reading an interactive terminal is the hang this verb
        # was reported for, and refusing beats blocking even now that a bare
        # `--state` no longer reaches the hook path.
        if sys.stdin.isatty():
            sys.stderr.write(M.CLI_STATE_NO_BODY % (" (stdin is a terminal)", prefix))
            sys.exit(2)
        body = sys.stdin.read()
        # An EMPTY stdin is its own diagnosis, not a short document. The shape
        # check would call it `thin: 0 chars`, which reads as "too short" when
        # the truth is "never arrived" -- and the commonest cause is passing
        # the body as argv, so say so when extra arguments are present.
        if not body.strip():
            extra = ""
            if len(sys.argv) > 3:
                extra = " (%d extra argument(s) were passed; the body does not go in argv)" % (
                    len(sys.argv) - 3
                )
            sys.stderr.write(M.CLI_STATE_NO_BODY % (extra, prefix))
            sys.exit(2)
        # A body carrying a '## SESSION' heading is a session pasting the WHOLE
        # document, which is the pre-2026-08-09 habit. Refusing it is how the
        # contract gets taught, and the refusal costs nothing: the previous
        # document is untouched, so the worst case is one wasted command.
        if S.AGENT_STATE_HEAD_RE.search(body):
            sys.stderr.write(M.CLI_STATE_WHOLE_DOC % prefix)
            sys.exit(2)
        # Refuse a section the Stop check would reject, with the SAME rule.
        # Accept-then-reject leaves the one artifact designed to survive
        # compaction broken while the session believes it is fine; refusing
        # leaves the previous good document untouched.
        verdict, detail = S.agent_state_shape(body)
        if verdict == "waitled":
            # Its own message: the generic one talks about char limits, which
            # says nothing about why leading with a watch is refused, and a
            # refusal a session cannot act on is a refusal it routes around.
            _m = S.AGENT_NEXT_RE.search(body)
            _lead = S.agent_next_lead(body, _m.end())[1] if _m else ""
            sys.stderr.write(M.CLI_STATE_WAIT_LED % _lead[:120])
            sys.exit(2)
        if verdict != "ok":
            sys.stderr.write(
                M.CLI_STATE_REFUSED
                % (verdict, detail, S.AGENT_STATE_MIN_CHARS, S.AGENT_STATE_MAX_CHARS)
            )
            sys.exit(2)
        target = S.agent_state_path(root, prefix)
        # Session-scoped since the tree split: with one STATE.md per session a
        # shared slot lets a PEER's write destroy the only copy of my replaced
        # body. It used to carry the branch as well (findings
        # 3688784930/3688787780, when the document itself was per branch); the
        # branch left the document's path, so it left the slot's name with it.
        backup = S.agent_state_backup_path(wl, prefix)
        reaped_path = S.agent_state_reaped_path(wl, prefix)
        pdir = C.projects_dir(root)
        backed_up = had_prev = False
        replaced = ""
        kept_rows, reaped_rows = [], []
        lock = S.agent_state_lock_path(wl)
        with open(lock, "w", encoding="utf-8") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            # EVERYTHING between here and os.replace reads and writes under the
            # lock. The old code read the outgoing document before taking it,
            # which was harmless when the write was a whole-file replace and is
            # not harmless now: a merge that parsed a pre-lock snapshot would
            # drop a section a racing writer added in between.
            try:
                current = target.read_text(encoding="utf-8", errors="replace")
                mtime = target.stat().st_mtime
            except OSError:
                current, mtime = "", time.time()
            had_prev = bool(current.strip())
            if had_prev:
                try:
                    backup.write_text(current, encoding="utf-8")
                    backed_up = True
                except OSError:
                    pass  # unwritable backup slot; confessed in the line below
            sections = S.agent_state_parse(current, mtime)
            kept, reaped = S.agent_state_dead(sections, prefix, pdir)
            if reaped:
                # ARCHIVE BEFORE DROP, append-only. Reaping is the one path that
                # deletes content nobody chose to delete, so it is the one path
                # that gets a guarantee stronger than the single .prev slot. A
                # failed archive ABORTS the reap: keeping a dead section forever
                # is a tidiness problem, losing it is the failure this file
                # exists to prevent.
                try:
                    with open(reaped_path, "a", encoding="utf-8") as af:
                        af.write(
                            "\n".join(
                                "# reaped %s by %s\n%s\n"
                                % (
                                    S.agent_state_stamp(time.time()),
                                    prefix,
                                    S.agent_state_render([s]),
                                )
                                for s in reaped
                            )
                        )
                    reaped_rows = [
                        "%s (%d min old)" % (s["owner"], int((time.time() - s["ts"]) / 60.0))
                        for s in reaped
                    ]
                except OSError as exc:
                    sys.stderr.write(
                        "WARNING: could not archive %d dead section(s) to %s (%s), so they "
                        "were KEPT rather than dropped.\n" % (len(reaped), reaped_path, exc)
                    )
                    kept, reaped = sections, []
            mine = S.agent_state_mine(kept, prefix)
            stamp = S.agent_state_stamp(time.time())
            if mine is not None:
                replaced = ", replacing your %d-minute-old section" % int(
                    max(0.0, (time.time() - mine["ts"]) / 60.0)
                )
                mine["tail"] = stamp
                # AFTER `replaced` above, which deliberately reports the age of
                # the section being replaced. Without this line the kept_rows
                # confirmation below re-uses the OLD ts and tells the writer its
                # freshly-written section is minutes old, which is exactly the
                # kind of thing this whole change exists to stop a session
                # believing. The on-disk document was always right; only the
                # confirmation lied. Caught in review of PR #565.
                mine["ts"] = time.time()
                mine["body"] = body.strip()
            else:
                kept.append(
                    {
                        "owner": prefix,
                        "tail": stamp,
                        "ts": time.time(),
                        "stamped": True,
                        "body": body.strip(),
                    }
                )
            merged = S.agent_state_render(kept)
            kept_rows = [
                "%s%s (%d min old)"
                % (
                    s["owner"],
                    " <- you" if s["owner"] == prefix else "",
                    int(max(0.0, (time.time() - s["ts"]) / 60.0)),
                )
                for s in kept
            ]
            fd, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(merged)
            os.replace(tmp, target)
        # Name the backup ONLY when a previous document existed AND the copy
        # actually landed (findings 3688770247/3688779150/3688787850: the old
        # line advertised a recovery path that a failed write had never
        # created, which is worse than no promise at all). The condition is
        # "there was a document", not "I replaced my own section": since the
        # merge, a write that only APPENDS a section still rewrites the file,
        # so the backup is real and worth naming either way.
        if had_prev:
            if backed_up:
                replaced += "; previous document saved to %s" % backup
            else:
                replaced += "; WARNING: the backup copy FAILED, the replaced body is gone"
        try:
            S.load(wl, sync=True)  # sync first, so the signature covers the synced world
            doc = S.load_state(wl, prefix)
            doc["state_sig"] = S.state_world_sig(root, wl, prefix)
            S.save_state(wl, prefix, doc)
        except Exception:  # noqa: BLE001 -- the sig is an optimisation, never a gate on writing
            pass
        print(
            "STATE.md section written for %s (%d chars)%s\n"
            "  sections kept: %s" % (prefix, len(body), replaced, ", ".join(kept_rows))
        )
        if reaped_rows:
            print(
                "  sections REAPED as dead: %s; archived to %s"
                % (", ".join(reaped_rows), reaped_path)
            )
        return
    if sys.argv[1:2] == ["--publish"] and len(sys.argv) < 4:
        # Bare-verb arity guard, same shape and same reason as --epic below.
        sys.stderr.write(M.CLI_PUBLISH_USAGE)
        sys.exit(2)
    if len(sys.argv) > 3 and sys.argv[1] == "--publish":
        import wl_epic as E  # noqa: PLC0415 -- sibling, probed not assumed

        me = sys.argv[2]
        _identity_or_die(me, _die2)
        branch = sys.argv[3]
        wl = C.worklist_for(os.getcwd())
        fold = S.load(wl, sync=False)
        body = E.render(wl, fold)
        # WORKLIST_PUBLISH_ROOT lets a test point the snapshot somewhere
        # harmless. Without it the L1 harness ran --publish with the real repo as
        # cwd and left agent/pr/l1probe.md in a TRACKED directory: a suite that
        # dirties a shared working tree, which is the one thing this repo's
        # sessions cannot tolerate from each other.
        root = pathlib.Path(
            os.environ.get("WORKLIST_PUBLISH_ROOT") or C.project_root(os.getcwd()) or os.getcwd()
        )
        out = root / "agent" / "pr" / ("%s.md" % branch.replace("/", "-"))
        out.parent.mkdir(parents=True, exist_ok=True)
        header = (
            "<!-- generated by worklist.py --publish; edit the worklist, not this file -->\n"
            "# Work in %s\n\n" % branch
        )
        out.write_text(header + body, encoding="utf-8")
        sys.stdout.write(
            M.CLI_PUBLISH_WROTE
            % (out.relative_to(root), len(header) + len(body), len(E.load_epics(wl)))
        )
        sys.exit(0)
    if sys.argv[1:2] == ["--epic"] and len(sys.argv) < 4:
        # Bare verb matched on argv[1] ALONE, the shape --state and --roundlog
        # document three times over: a bare verb that falls through to the hook
        # path hangs forever reading an event off stdin.
        sys.stderr.write(M.CLI_EPIC_USAGE)
        sys.exit(2)
    if len(sys.argv) > 3 and sys.argv[1] == "--epic":
        # Epics live in a SIDECAR, never the event log, because compact() folds
        # the log to md/add/lease and would destroy a novel event kind.
        import wl_epic as E  # noqa: PLC0415 -- sibling, probed not assumed

        me = sys.argv[2]
        _identity_or_die(me, _die2)
        wl = C.worklist_for(os.getcwd())
        sub = sys.argv[3]
        rest = sys.argv[4:]
        if sub == "new":
            if not rest:
                sys.stderr.write(M.CLI_EPIC_REFUSED % "an epic needs a title")
                sys.exit(2)
            title = " ".join(rest)
            eid = E.new_epic(wl, me, title)
            sys.stdout.write(M.CLI_EPIC_MADE % (eid, title))
            sys.exit(0)
        if sub == "add":
            if len(rest) < 2:
                sys.stderr.write(
                    M.CLI_EPIC_REFUSED % "usage: --epic <me> add <epic-id> <item-id>..."
                )
                sys.exit(2)
            got = E.add_to_epic(wl, me, rest[0], rest[1:])
            if not got:
                sys.stderr.write(
                    M.CLI_EPIC_REFUSED % ("no epic %r; run --epic <me> list" % rest[0])
                )
                sys.exit(2)
            total = len(E.load_epics(wl)[got].get("covers") or [])
            sys.stdout.write(M.CLI_EPIC_ATTACHED % (got, total))
            sys.exit(0)
        if sub == "list":
            for eid, rec in E.load_epics(wl).items():
                sys.stdout.write(
                    "#%s  %s  (%d item(s))\n"
                    % (eid, rec.get("title") or "(untitled)", len(rec.get("covers") or []))
                )
            sys.exit(0)
        sys.stderr.write(M.CLI_EPIC_REFUSED % ("unknown subcommand %r" % sub))
        sys.exit(2)
    if sys.argv[1:2] == ["--git"] and len(sys.argv) < 3:
        # Bare verb matched on argv[1] ALONE, the same shape as --state and
        # --roundlog below and for the same measured reason: a bare verb that
        # falls through to the hook path hangs forever reading stdin.
        from wl_git import USAGE as GIT_USAGE  # noqa: PLC0415 -- sibling, probed not assumed

        sys.stderr.write(GIT_USAGE)
        sys.exit(2)
    if len(sys.argv) > 2 and sys.argv[1] == "--git":
        # The mediated submodule / force-push capability, delegated whole the way
        # --wait is, because it is far too large to inline here.
        #
        # It drives git through subprocess, which the pre-bash guards never see,
        # so a raw leased force push typed on a command line stays blocked while
        # this path works. That is deliberate: the guard stays strict and the
        # safety lives in the module's own checks, not in permission.
        import wl_git  # noqa: PLC0415 -- sibling, probed not assumed

        sys.exit(wl_git.main(sys.argv[2:]))
    if sys.argv[1:2] == ["--roundlog"] and len(sys.argv) < 3:
        # Matched on argv[1] ALONE, the same shape as the `--state` guard above
        # and for the same reason: a bare verb that falls through to the hook
        # path hangs forever reading an event off stdin.
        sys.stderr.write(M.CLI_ROUNDLOG_USAGE)
        sys.exit(2)
    if len(sys.argv) > 2 and sys.argv[1] == "--roundlog":
        # `... --roundlog <branch> [round]` with the STATUS BODY on stdin.
        #
        # The round log is wave header, then STATUS overwritten in place, then
        # the history appendix. On 2026-08-19 a heartbeat tick refreshed STATUS
        # with `text[:i] + new` and deleted the appendix, because that splice
        # replaces from the heading to END OF FILE. There was no backup of that
        # file anywhere. This verb cannot express that: it replaces the middle
        # part only, and REPORTS the bytes it kept on either side, so a
        # truncation could never again look like a routine success.
        branch = sys.argv[2]
        explicit_round = None
        if len(sys.argv) > 3:
            try:
                explicit_round = int(sys.argv[3])
            except ValueError:
                sys.stderr.write(M.CLI_ROUNDLOG_REFUSED % ("bad-round", sys.argv[3]))
                sys.exit(2)
        body = "" if sys.stdin.isatty() else sys.stdin.read()
        verdict, detail = RL.shape(body)
        if verdict != "ok":
            sys.stderr.write(M.CLI_ROUNDLOG_REFUSED % (verdict, detail))
            sys.exit(2)
        root = C.project_root(C.project_start())
        target = RL.roundlog_path(C.projects_dir(root), branch)
        try:
            current = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            current = ""
        if not RL.WAVE_HEADER_RE.search(current):
            sys.stderr.write(M.CLI_ROUNDLOG_NO_LOG % target)
            sys.exit(2)
        # Same write discipline as --state: flock, a .prev slot, tempfile and
        # os.replace. A delegated babysitter and its lead can both hold this
        # path, so the lock is not ceremony.
        backup = target.with_suffix(".md.prev")
        lock_path = str(target) + ".lock"
        with open(lock_path, "w", encoding="utf-8") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            # Re-read UNDER the lock: a pre-lock snapshot would splice into a
            # document a racing writer has already moved on from.
            try:
                current = target.read_text(encoding="utf-8", errors="replace")
            except OSError:
                current = ""
            backed_up = False
            try:
                backup.write_text(current, encoding="utf-8")
                backed_up = True
            except OSError:
                pass  # unwritable slot; confessed in the line below
            new, rep = RL.splice(current, body, round_no=explicit_round)
            fd, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(new)
            os.replace(tmp, target)
        print(
            "round log %s: STATUS is now round %d (%s)\n"
            "  wave header kept: %d bytes\n"
            "  STATUS replaced:  %d bytes -> %d bytes\n"
            "  appendix kept:    %d bytes%s"
            % (
                target.name,
                rep["round"],
                RL.stamp(),
                rep["head_bytes"],
                rep["replaced_bytes"],
                len(new) - rep["head_bytes"] - rep["tail_bytes"],
                rep["tail_bytes"],
                "" if rep["tail_bytes"] else "  <- nothing below STATUS yet",
            )
        )
        if not backed_up:
            print("  WARNING: the .prev backup copy FAILED")
        return
    if sys.argv[1:2] == ["--session-start"]:
        ev, _ok = _read_event()
        CK.handle_session_start(ev)
        return
    if sys.argv[1:2] == ["--post-compact"]:
        ev, _ok = _read_event()
        CK.handle_post_compact(ev)
        return
    if sys.argv[1:2] == ["--loop"]:
        # ARITY VALIDATED INSIDE, matched on argv[1] ALONE. The old guard was
        # `len(sys.argv) > 3 and sys.argv[1] == "--loop"`, so `--loop x` did not
        # merely fail: it fell through to the Stop battery below, which ran every
        # check against an empty event, returned a real "decision": "block" at
        # exit 0, and wrote six `*-unknown` sidecars. Same shape and same fix as
        # the `--state` guard above; verified by running it.
        if len(sys.argv) <= 3:
            sys.stderr.write(M.CLI_LOOP_USAGE)
            sys.exit(2)
        # `worklist.py --loop <prefix> <next-ISO8601Z> <count> <label...>`
        # Self-contained append (works without siblings, like --brief).
        _identity_or_die(sys.argv[2], _die2)
        wl = _local_worklist_path(_local_project_start())
        with open(wl.with_suffix(".loop"), "a", encoding="utf-8") as fh:
            fh.write(
                "%s %s %s %s\n"
                % (
                    sys.argv[2],
                    sys.argv[3],
                    sys.argv[4] if len(sys.argv) > 4 else "1",
                    " ".join(sys.argv[5:]).replace("\n", " ")[:120],
                )
            )
        print("loop declared for %s, next fire %s" % (sys.argv[2], sys.argv[3]))
        return
    if sys.argv[1:2] == ["--intent"]:
        # `worklist.py --intent <me> '<=240 chars>' [--covers <key|#id> ...] [--for <min>]`
        #
        # A statement of PLAN. It is NOT evidence of work, and the gating below
        # is deliberately tiny because of that: it reprioritises the rotation and
        # answers the two checks whose entire content is a status question. It
        # can never satisfy tick evidence, and it never touches the integrity,
        # judge or deferral tiers.
        argv = sys.argv[2:]
        me = argv[0] if argv else ""
        if not C.PREFIX_RE.match(me or ""):
            sys.stderr.write(M.CLI_INTENT_USAGE)
            sys.exit(2)
        _identity_or_die(me, _die2)
        covers, minutes, words = [], S.INTENT_DEFAULT_MIN, []
        i = 1
        while i < len(argv):
            if argv[i] == "--covers" and i + 1 < len(argv):
                covers.append(argv[i + 1].lstrip("#"))
                i += 2
            elif argv[i] == "--for" and i + 1 < len(argv):
                try:
                    minutes = int(argv[i + 1])
                except ValueError:
                    sys.stderr.write(M.CLI_INTENT_USAGE)
                    sys.exit(2)
                i += 2
            else:
                words.append(argv[i])
                i += 1
        text = " ".join(words).replace("\n", " ").strip()
        if not text:
            sys.stderr.write(M.CLI_INTENT_USAGE)
            sys.exit(2)
        wl = C.worklist_for(C.project_start())
        S.record_intent(wl, me, text, covers, minutes)
        print(
            "intent recorded for %s (%d chars, %d min horizon%s).\n"
            "  It reprioritises the rotation and answers `brief`/`agent-state`. It is NOT "
            "evidence: ticks still need it, and the integrity, judge and deferral tiers are "
            "untouched. If it expires while what it covers is still outstanding, that "
            "becomes its own violation."
            % (
                me,
                len(text),
                max(1, min(minutes, S.INTENT_MAX_MIN)),
                ", covering " + ", ".join(covers) if covers else "",
            )
        )
        return
    if sys.argv[1:2] == ["--brief"]:
        # Same class as --loop above, same fix.
        if len(sys.argv) <= 2:
            sys.stderr.write(M.CLI_BRIEF_USAGE)
            sys.exit(2)
        # `worklist.py --brief <session-prefix> <text...>` -- append, never
        # rewrite, for the same lost-update reason the store appends.
        # Self-contained so a broken sibling cannot take the brief channel down.
        wl = _local_worklist_path(_local_project_start())
        prefix = sys.argv[2]
        # THE ROSTER. `.sessions` is the registry of who exists here -- it is
        # what --ask's recipient check reads and what the liveness ladder counts
        # -- and until now an unvalidated command-line string populated it. A
        # phantom identity that briefs itself looks exactly like a real session.
        _identity_or_die(prefix, _die2)
        text = " ".join(sys.argv[3:]).replace("\n", " ").strip()[:200]
        # A lone id is a MISREAD of this verb, not a short brief. The word reads
        # both ways (publish a brief / brief me on X) and the argument shape is
        # `--tick <me> <id> <evidence>` minus the evidence, so the id lands where
        # the sentence goes and the roster then advertises it as live activity.
        # Shape only, no store read: this branch stays self-contained on purpose
        # (see above), and a bare hex token is never a real brief either way.
        if (
            len(sys.argv) == 4
            and 6 <= len(text) <= 16
            and all(ch in "0123456789abcdefABCDEF" for ch in text)
        ):
            sys.stderr.write(M.CLI_BRIEF_LOOKS_LIKE_ID % text)
            sys.exit(2)
        stamp = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(wl.with_suffix(".sessions"), "a", encoding="utf-8") as fh:
            fh.write("%s %s %s\n" % (prefix, stamp, text))
        # Stamp the WORLD alongside the brief, so the staleness check can ask
        # whether reality moved rather than only whether the clock did. A brief
        # describing an unchanged world is still accurate at 91 minutes, and
        # nagging for a rewrite of an accurate sentence is the pure-wall-clock
        # failure this closes. The check falls back to wall-clock when the key
        # is absent, so an older brief -- or one written while wl_store was
        # broken -- behaves exactly as before.
        #
        # Best-effort and last, deliberately: this branch is self-contained so a
        # broken sibling cannot take the brief channel down, and that guarantee
        # outranks the optimisation. The brief is already on disk by this point.
        try:
            _root = C.project_start()
            _doc = S.load_state(wl, prefix)
            _doc["brief_sig"] = S.state_world_sig(_root, wl, prefix)
            S.save_state(wl, prefix, _doc)
        except Exception:  # noqa: BLE001 -- never let the sig block the brief
            pass
        print("brief recorded for %s (%d chars)" % (prefix, len(text)))
        return
    if sys.argv[1:2] and sys.argv[1] in ("--ask", "--answer", "--decline", "--ack", "--requests"):
        R.request_cli(sys.argv[1:], C.worklist_for(C.project_start()))
        return
    if sys.argv[1:2] == ["--poll"]:
        R.poll_cli(
            C.worklist_for(C.project_start()),
            sys.argv[2] if len(sys.argv) > 2 else "",
            __file__,
        )
        return
    # ONE CLI DOOR. Everything a session is told to run goes through this file,
    # so the report inbox and the waiter are reachable here too rather than by
    # remembering two more script names. Both delegate; neither reimplements.
    if sys.argv[1:2] == ["--reap"]:
        # `worklist.py --reap <me> <task-id>...` -- retire roster entries this
        # session knows are finished. Validated against the LAST EVENT the hook
        # saw, so a typo cannot silently suppress a live worker, and a compacted
        # session (which remembers nothing) can still see the id list.
        me = sys.argv[2] if len(sys.argv) > 2 else ""
        ids = sys.argv[3:]
        if not C.PREFIX_RE.match(me or "") or not ids:
            sys.stderr.write(M.CLI_REAP_USAGE)
            sys.exit(2)
        _identity_or_die(me, _die2)
        wl = _local_worklist_path(_local_project_start())
        known = {}
        try:
            ev = json.loads(wl.with_suffix(".lastevent-%s.json" % me[:8]).read_text())
            known = {
                str(b.get("id")): b
                for b in (ev.get("background_tasks") or [])
                if isinstance(b, dict)
            }
        except (OSError, ValueError):
            known = {}
        if known:
            unknown = [i for i in ids if i not in known]
            if unknown:
                sys.stderr.write(
                    M.CLI_REAP_UNKNOWN % (", ".join(unknown), ", ".join(sorted(known)) or "(none)")
                )
                sys.exit(2)
        path = wl.with_suffix(".reaped-%s" % me[:8])
        with open(path, "a", encoding="utf-8") as fh:
            fh.writelines(i + "\n" for i in ids)
        print(
            "reaped %d task(s): %s\nThey no longer count as running for this "
            "session. Nothing was killed -- if one is in fact alive it will "
            "still run; only this session's supervision of it stops." % (len(ids), " ".join(ids))
        )
        return
    if sys.argv[1:2] == ["--teammate-idle"]:
        # Fired by the `TeammateIdle` hook with the harness payload on stdin.
        #
        # ALWAYS EXITS 0, and never blocks. `TeammateIdle` supports blocking --
        # exit 2 prevents the teammate going idle and it keeps working -- and
        # that power is deliberately unused here. Pinning a teammate the lead
        # did not ask to keep working is a worse failure than the one this
        # closes, and a crash in a journal writer must never become one.
        try:
            _teammate_idle_cli()
        except Exception as exc:  # noqa: BLE001 -- see above: never block a teammate
            sys.stderr.write("teammate-idle journal skipped: %s\n" % exc)
        return
    if sys.argv[1:2] == ["--adopt"]:
        _adopt_cli(sys.argv[1:])
        return
    if sys.argv[1:2] == ["--reassign"]:
        _reassign_cli(sys.argv[1:])
        return
    if sys.argv[1:2] == ["--reports"]:
        import wl_report  # noqa: PLC0415 -- sibling, probed not assumed (see SIBLING IMPORTS above)

        rest = sys.argv[2:]
        # `--reports --all` MUST work, and it did not: the dispatcher forwarded
        # `--all` as if it were a MODE, and wl_report answered "unknown mode
        # --all" (exit 2). It matters more than a papercut because that exact
        # flag was in the announcement broadcast to other sessions, so the first
        # thing a peer tried, on our instructions, failed. Anything that is not
        # a mode is a modifier, and modifiers belong to --list.
        if not rest:
            rest = ["--list", "--unread"]
        elif rest[0] not in wl_report.MODES:
            rest = ["--list", *rest]
        sys.exit(wl_report.main(rest))
    if sys.argv[1:2] == ["--wait"]:
        import wl_wait  # noqa: PLC0415 -- sibling, probed not assumed (see SIBLING IMPORTS above)

        sys.exit(wl_wait.main(sys.argv[2:]))
    if sys.argv[1:2] and sys.argv[1] in (
        "--add",
        "--triage",
        "--tick",
        "--defer",
        "--lease",
        "--update",
        "--list",
    ):
        _item_cli(sys.argv[1:], C.worklist_for(C.project_start()))
        return

    # THE CLASS FIX. Per-verb arity guards close the three verbs anyone has
    # noticed; this closes the shape. ANY unrecognised flag reaching this point
    # used to be handed to the Stop battery, which reads its event from stdin --
    # so `worklist.py --tpyo` emitted a genuine block verdict at exit 0 with
    # stdin closed, and hung forever with stdin open. Both measured, not
    # theorised. A bare invocation (no argv) is the real hook and passes through
    # untouched, which is why this tests for a LEADING DASH and not for
    # "unmatched".
    if sys.argv[1:2] and str(sys.argv[1]).startswith("-"):
        sys.stderr.write(M.CLI_UNKNOWN_VERB % sys.argv[1])
        sys.exit(2)

    # CI NO-OP, and it is placed HERE rather than beside the STOPHOOK_CHILD guard
    # on purpose. Everything above this line is a query or write mode that a
    # runner may legitimately want (`--path`, `--state`); exiting at the top of
    # main() would break those silently. The thing that must not happen on a
    # runner is the BLOCK below: CLAUDE.md tells a session to track items and
    # this hook refuses to end a turn while any remain, so an unattended model
    # in Actions burns its turn budget against a gate no human will ever answer.
    # Required by the autopilot design (docs/ci-overhaul/03-v2-autonomy.md).
    if os.environ.get("GITHUB_ACTIONS") == "true":
        sys.exit(0)

    event, event_ok = _read_event()
    # _local_project_start, NOT C.project_start: this line runs BEFORE the
    # _BROKEN fail-closed emit below, so touching a sibling here would raise
    # out of _BrokenModule and crash the hook with nothing on stdout -- which
    # the harness reads as ALLOW. Same reason _local_worklist_path exists.
    worklist = _local_worklist_path(_local_project_start(event))
    if _BROKEN:
        # Fail CLOSED with the full list: a hook that cannot run its checks
        # must not wave the stop through, and the session that hits this is
        # the one positioned to fix it.
        _emit(
            {
                "systemMessage": "Stop hook: %d sibling module(s) unusable; blocking."
                % len(_BROKEN),
                "decision": "block",
                "reason": "THIS IS A HOOK BUG: worklist.py could not import its sibling "
                "modules, so none of its checks can run. Broken:\n%s\n\nRestore or fix "
                "the modules beside %s (worklist_messages.py and the wl_*.py siblings), "
                "then stop again."
                % (
                    "\n".join("  %s: %s" % (k, v) for k, v in sorted(_BROKEN.items())),
                    __file__,
                ),
            }
        )
    CK.run_stop(event, event_ok, worklist, __file__)


# GUARDED, so the module can be imported and its re-exported helpers tested
# directly: a bare main() call once meant `import worklist` ran the whole Stop
# path against whatever happened to be on stdin.
if __name__ == "__main__":
    # FAIL CLOSED ON CRASH. This was the hook's global escape hatch and nobody
    # put it there on purpose: an unhandled exception prints a traceback to
    # stderr and NOTHING to stdout, the harness sees no decision, and the stop is
    # ALLOWED. So any bug anywhere in this file silently disabled EVERY check at
    # once, which is the exact opposite of the no-escape-hatch rule the rest of
    # it is built on. It is not hypothetical: a v8 cut crashed on a tuple unpack
    # and the stop sailed through; only a suite needle assertion caught it.
    #
    # A crash is now a BLOCK carrying the traceback, because a hook that cannot
    # decide must not be the way out, and the session that hits it is the one
    # positioned to fix it. Deliberately outside main() so it covers every mode.
    try:
        main()
    except SystemExit:
        raise
    except BaseException:  # noqa: BLE001 - a bare crash must not become an allow
        import traceback

        _emit(
            {
                "systemMessage": "Stop hook CRASHED; blocking rather than waving the stop "
                "through. Fix %s." % __file__,
                "decision": "block",
                "reason": "THIS IS A HOOK BUG: %s crashed, so none of its checks ran.\n\n%s\n"
                "A crash used to print to stderr and nothing to stdout, which the harness "
                "reads as ALLOW, so one bug disabled every check silently. It now blocks. "
                "Fix the traceback above, then stop again."
                % (__file__, traceback.format_exc()[-1800:]),
            }
        )
