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
(wl_checks); the compact-recovery document is .agent/<branch>/STATE.md with world-keyed
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
    wl_email      the operator email channel (SES digests of open questions)
    wl_judge      the stop-legitimacy judge and its verdict cache
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

import fcntl
import json
import os
import pathlib
import re
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
    "wl_core", "wl_store", "wl_requests", "wl_liveness", "wl_ci",
    "wl_reggate", "wl_judge", "wl_email", "wl_checks", "worklist_messages",
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

# Re-exported for direct importers (the suite drives these two as library
# functions; keeping them on this module is part of the compatibility
# surface). Absent when their module is broken, which is correct: a caller
# gets an AttributeError naming this module instead of a silent stub.
if "wl_checks" not in _BROKEN:
    cited_excerpts = _MODS["wl_checks"].cited_excerpts
    citation_state = _MODS["wl_checks"].citation_state
if "wl_ci" not in _BROKEN:
    submodule_pointer_moves = _MODS["wl_ci"].submodule_pointer_moves


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


def _read_event():
    try:
        ev = json.load(sys.stdin)
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
    root = C.project_root(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    if item_id:
        fold = S.load(worklist, sync=True)
        rec = fold.by_id.get(item_id)
        if rec is None:
            die("no item #%s (worklist.py --list shows ids)" % item_id)
        if rec["owner"] is not None and not C.same_session(rec["owner"], me):
            die("#%s is owned by %s; never tick or edit another session's tracking"
                % (item_id, rec["owner"]))
    else:
        # Every triaged finding is TRACKED, before any verdict exists. A
        # finding that reaches this verb and leaves no item behind is exactly
        # the loss the worklist exists to prevent.
        item_id = S.add_item(worklist, me, text)
    print("triaging #%s: %s" % (item_id, text[:120]))
    branch = C.git_branch(root)
    context = CK.triage_context(root, worklist, me)
    degraded = ""
    verdict = None
    if not J.JUDGE_DISABLED:
        verdict, err = J.run_triage(text, context)
        if err:
            degraded = "\n  THE TRIAGE JUDGE COULD NOT ANSWER: %s" % err
    if verdict is None:
        print(M.CLI_TRIAGE_SELF % {
            "id": item_id, "me": me, "why": degraded, "context": context,
            "branch": branch or "<branch>",
        })
        return
    kind = verdict.get("verdict", "")
    reason = str(verdict.get("reason", "")).strip() or "(the judge gave no reason)"
    if kind == "plan-subagent":
        slug = PLAN_SLUG_RE.sub("-", str(verdict.get("plan_slug", "")).lower()).strip("-")
        slug = slug[:60] or item_id
        plan = "docs/agent/%s/PLAN-%s.md" % (branch or "<branch>", slug)
        S.triage_item(worklist, me, item_id, kind, reason, plan)
        print(M.CLI_TRIAGE_PLAN % {
            "id": item_id, "me": me, "reason": reason, "plan": plan,
            "finding": text,
        })
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
            root = C.project_root(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
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
    if rec["owner"] is not None and not C.same_session(rec["owner"], me):
        die("#%s is owned by %s; never tick or edit another session's tracking"
            % (item_id, rec["owner"]))
    rest = " ".join(argv[3:]).replace("\n", " ").strip()
    root = C.project_root(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
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
            die("a [?] without a DEFAULT: is a note, not a decision; append "
                "'DEFAULT: <what you will do if unanswered>'")
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
        print("deferred #%s with its justification on record; it is reported "
              "every stop, its WHY faces the judge's audit after %d min, and "
              "its DEFAULT executes after %d min"
              % (item_id, S.DEFER_AUDIT_MIN, S.DEFER_WINDOW_MIN))
        return
    if mode == "--update":
        if not rest:
            die("an empty update updates nothing: one line of what moved")
        S.update_item(worklist, me, item_id, rest)
        print("updated #%s" % item_id)
        return
    if mode == "--lease":
        if len(argv) < 4:
            die(M.CLI_ITEM_USAGE)
        until_arg = argv[3]
        if until_arg.startswith("+") and until_arg[1:].isdigit():
            import datetime
            minutes = min(int(until_arg[1:]), C.MAX_LEASE_MIN)
            until = (C.utcnow() + datetime.timedelta(minutes=minutes)).strftime(
                "%Y-%m-%dT%H:%MZ"
            )
        else:
            until = until_arg.replace("until:", "")
        wm = next((a for a in argv[4:] if a.startswith("worker:")), "")
        if not wm:
            die("a [>] lease must name its worker (worker:<background-task-id>); "
                "an in-flight claim with no worker to trace is the gap this "
                "program exists to catch")
        note = " ".join(a for a in argv[4:] if not a.startswith("worker:")).strip()
        if C.lease_state("until:%s" % until) != "fresh":
            die("until:%s is not a valid fresh lease (ISO8601Z, at most %d min ahead)"
                % (until, C.MAX_LEASE_MIN))
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
        if _running is not None:
            if wid in _running:
                verified = " (worker verified against the harness's running tasks)"
            else:
                print(
                    "WARNING: worker:%s is not among the harness's running background "
                    "task ids (%s). If you named an Agent, lease its TASK id instead; "
                    "the hook verifies against these ids and anything else reads as "
                    "unverifiable." % (wid, ", ".join(_running[:10]) or "none")
                )
        S.lease_item(worklist, me, item_id, until, wid, note)
        print("leased #%s until %s on %s%s" % (item_id, until, wm, verified))
        return
    die("unknown item mode %s" % mode)


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
    worklist = C.worklist_for(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    if worklist.with_suffix(".lastevent-%s.json" % phantom[:8]).exists():
        _die2(M.CLI_REASSIGN_ALIVE % (phantom, phantom))
    fold = S.load(worklist, sync=True)
    stamp = C.stamp_now()
    moved_items = [
        rec["id"] for rec in fold.items
        if rec["state"] in (" ", "?", ">") and rec["owner"] is not None
        and C.same_session(rec["owner"], phantom)
    ]
    if moved_items:
        S.append_events(worklist, [
            {"ev": "reassign", "id": rid, "at": stamp, "by": me, "o": me,
             "from_o": phantom}
            for rid in moved_items
        ])
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
    print(M.CLI_REASSIGN_DONE % (
        phantom, me,
        ", ".join("#" + i for i in moved_items) or "(none)",
        ", ".join("#" + i for i in moved_reqs) or "(none)",
        me, me,
    ))


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
        print(_local_worklist_path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()))
        return
    if len(sys.argv) > 1 and sys.argv[1] == "--compact":
        S.compact(C.worklist_for(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()))
        return
    if sys.argv[1:2] == ["--state"] and len(sys.argv) < 3:
        # BEFORE the real handler and matched on argv[1] ALONE, which is the
        # whole point: the old guard required argv[2] to enter this branch at
        # all, so a bare `--state` fell through to the hook path below and hung
        # forever reading the event from stdin (report #7c1c2629).
        sys.stderr.write(M.CLI_STATE_USAGE)
        sys.exit(2)
    if len(sys.argv) > 2 and sys.argv[1] == "--state":
        # `... --state <prefix>` with the STATE.md body on stdin. The document
        # is PER BRANCH now, not per session, so the old "no other writer to
        # race" assumption is dead: two live sessions share one branch today.
        # flock + tempfile + os.replace makes the write atomic (a reader never
        # sees half a file); last-write-wins is deliberate, because a document
        # whose contract is "rewrite every time" has no merge semantics. The
        # success line names what was replaced, which is the only cheap
        # defence against session B silently deleting session A's next action.
        wl = _local_worklist_path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
        prefix = sys.argv[2]
        _identity_or_die(prefix, _die2)
        root = C.project_root(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
        branch = C.git_branch(root)
        if not branch:
            sys.stderr.write(M.CLI_STATE_NO_BRANCH % root)
            sys.exit(2)
        if not S.agent_branch_dir(root, branch).is_dir():
            # NEVER auto-created (operator decision 2026-07-30): the RULES.md
            # copy-forward is a judgement call a tool must not make.
            sys.stderr.write(M.CLI_STATE_NO_DIR % (branch, branch, branch))
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
        # Refuse a document the Stop check would reject, with the SAME rule.
        # Accept-then-reject leaves the one artifact designed to survive
        # compaction broken while the session believes it is fine; refusing
        # leaves the previous good document untouched.
        verdict, detail = S.agent_state_shape(body)
        if verdict != "ok":
            sys.stderr.write(
                M.CLI_STATE_REFUSED
                % (verdict, detail, S.AGENT_STATE_MIN_CHARS, S.agent_state_max_chars(body))
            )
            sys.exit(2)
        target = S.agent_state_path(root, branch)
        # Branch-scoped since the review round of 2026-07-31 (findings
        # 3688784930/3688787780): a shared slot let a write on ANOTHER branch
        # destroy this branch's only backup.
        backup = S.agent_state_backup_path(wl, branch)
        replaced = ""
        try:
            prev_age = int((time.time() - target.stat().st_mtime) / 60.0)
            prev_first = target.read_text(encoding="utf-8", errors="replace").strip().splitlines()[0][:100]
            replaced = ", replacing a %d-minute-old document (first line: %r)" % (prev_age, prev_first)
        except (OSError, IndexError):
            pass
        backed_up = False
        lock = S.agent_state_lock_path(wl)
        with open(lock, "w", encoding="utf-8") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            # Keep the outgoing document before overwriting it. Inside the lock
            # and before os.replace, so the copy is of the body we are actually
            # about to destroy and not of one a racing writer slipped in.
            try:
                backup.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
                backed_up = True
            except OSError:
                pass  # first write on this branch, or an unreadable target
            fd, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(body)
            os.replace(tmp, target)
        if replaced:
            # Name the backup ONLY when something was replaced AND the copy
            # actually landed (findings 3688770247/3688779150/3688787850: the
            # old line advertised a recovery path that a failed write had
            # never created, which is worse than no promise at all).
            if backed_up:
                replaced += "; previous body saved to %s" % backup
            else:
                replaced += "; WARNING: the backup copy FAILED, the replaced body is gone"
        try:
            S.load(wl, sync=True)  # sync first, so the signature covers the synced world
            doc = S.load_state(wl, prefix)
            doc["state_sig"] = S.state_world_sig(root, wl, prefix)
            S.save_state(wl, prefix, doc)
        except Exception:  # noqa: BLE001 -- the sig is an optimisation, never a gate on writing
            pass
        print("STATE.md written for branch %s (%d chars)%s" % (branch, len(body), replaced))
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
        wl = _local_worklist_path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
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
    if sys.argv[1:2] == ["--brief"]:
        # Same class as --loop above, same fix.
        if len(sys.argv) <= 2:
            sys.stderr.write(M.CLI_BRIEF_USAGE)
            sys.exit(2)
        # `worklist.py --brief <session-prefix> <text...>` -- append, never
        # rewrite, for the same lost-update reason the store appends.
        # Self-contained so a broken sibling cannot take the brief channel down.
        import datetime
        wl = _local_worklist_path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
        prefix = sys.argv[2]
        # THE ROSTER. `.sessions` is the registry of who exists here -- it is
        # what --ask's recipient check reads and what the liveness ladder counts
        # -- and until now an unvalidated command-line string populated it. A
        # phantom identity that briefs itself looks exactly like a real session.
        _identity_or_die(prefix, _die2)
        text = " ".join(sys.argv[3:]).replace("\n", " ").strip()[:200]
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(wl.with_suffix(".sessions"), "a", encoding="utf-8") as fh:
            fh.write("%s %s %s\n" % (prefix, stamp, text))
        print("brief recorded for %s (%d chars)" % (prefix, len(text)))
        return
    if sys.argv[1:2] and sys.argv[1] in ("--ask", "--answer", "--decline", "--ack", "--requests"):
        R.request_cli(
            sys.argv[1:], C.worklist_for(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
        )
        return
    if sys.argv[1:2] == ["--poll"]:
        R.poll_cli(
            C.worklist_for(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()),
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
        wl = _local_worklist_path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
        known = {}
        try:
            ev = json.loads(wl.with_suffix(".lastevent-%s.json" % me[:8]).read_text())
            known = {str(b.get("id")): b for b in (ev.get("background_tasks") or [])
                     if isinstance(b, dict)}
        except (OSError, ValueError):
            known = {}
        if known:
            unknown = [i for i in ids if i not in known]
            if unknown:
                sys.stderr.write(M.CLI_REAP_UNKNOWN % (", ".join(unknown),
                                                       ", ".join(sorted(known)) or "(none)"))
                sys.exit(2)
        path = wl.with_suffix(".reaped-%s" % me[:8])
        with open(path, "a", encoding="utf-8") as fh:
            for i in ids:
                fh.write(i + "\n")
        print("reaped %d task(s): %s\nThey no longer count as running for this "
              "session. Nothing was killed -- if one is in fact alive it will "
              "still run; only this session's supervision of it stops."
              % (len(ids), " ".join(ids)))
        return
    if sys.argv[1:2] == ["--reassign"]:
        _reassign_cli(sys.argv[1:])
        return
    if sys.argv[1:2] == ["--reports"]:
        import wl_report
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
            rest = ["--list"] + rest
        sys.exit(wl_report.main(rest))
    if sys.argv[1:2] == ["--wait"]:
        import wl_wait
        sys.exit(wl_wait.main(sys.argv[2:]))
    if sys.argv[1:2] and sys.argv[1] in ("--add", "--triage", "--tick", "--defer", "--lease", "--update", "--list"):
        _item_cli(
            sys.argv[1:], C.worklist_for(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
        )
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
    worklist = _local_worklist_path(
        os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or os.getcwd()
    )
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
