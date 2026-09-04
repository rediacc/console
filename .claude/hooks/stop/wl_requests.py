"""wl_requests: the v6 cross-session request log and its CLI.

The log at <worklist>.requests is append-only JSONL (ask / answer / decline /
ack / escalate events; state is a fold, never an edit) -- NOT a worklist
state, because a request is a conversation (a body, an answer with its own
body, an acknowledgement) and the item protocol has no room for that. No
operation deletes or rewrites shared state, so there is no delete-then-
recreate window where it is absent (the cron lesson): a missing log simply
reads as empty, and every transition is an appended event that supersedes,
never replaces, what came before.

Delivery rides INSIDE the block, untruncated. The motivating failure was a
finding written into a commit message: correct, passive, and read by nobody
until the operator relayed it BY HAND. So the request body and the answer
text are carried whole in the block reason -- the one channel a session
cannot end a turn around -- and never behind a pointer to --requests, which
would make reading them a choice again.

Blocking preserves the ownership rule (block only on YOUR obligations):
  - a direct request blocks its RECIPIENT until answered or declined;
  - a broadcast blocks EACH live session only until THAT session answers or
    declines ("not my area") -- never session A on session B's silence;
  - an unacked answer blocks the ASKER, with the answer text in the block
    reason, because the reason is the only channel the asking MODEL actually
    reads (systemMessage goes to the operator); --ack ends it, permanently.
Dead recipients cannot black-hole a request: liveness comes from the
.sessions briefs, and an unanswerable request is ESCALATED exactly once,
under a flock, into an operator-visible `- [?]` item owned by the asker.
"""

import contextlib
import hashlib
import json
import os
import sys
import time

import wl_core as C
import wl_store as S

REQUEST_BODY_MAX = 1000


def append_request_event(worklist, obj):
    """One event = one full line = ONE write() on an O_APPEND handle, taken
    under a blocking flock on <requests>.lock (its own lock file, so it never
    contends with the worklist cleaner's lock). The flock makes concurrent
    writers a settled question rather than an unlikely one: they serialize
    absolutely, and the lock is held for microseconds. Readers take no lock;
    a torn trailing line is only possible on a crash mid-write, fails
    json.loads, and is skipped by every reader. The shared appender also
    heals a torn tail before writing (v10 hardening)."""
    S._append_lines(S.requests_path(worklist), str(S.requests_path(worklist)) + ".lock", [obj])


def read_requests(worklist):
    """{id: request} folded from the append-only event log. State is DERIVED,
    never edited: an answer, decline, ack or escalation is an appended event,
    so no writer ever rewrites another's line."""
    p = S.requests_path(worklist)
    reqs = {}
    if not p.exists():
        return reqs
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return reqs
    for line in lines:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if not isinstance(ev, dict):
            continue
        rid, kind = ev.get("id"), ev.get("ev")
        if kind == "ask" and rid and rid not in reqs:
            reqs[rid] = {
                "id": rid,
                "from": str(ev.get("from", "")),
                "to": str(ev.get("to", "*")),
                "at": str(ev.get("at", "")),
                "body": str(ev.get("body", "")),
                "answers": [],
                "declines": [],
                "acked": False,
                "escalated": "",
            }
        elif rid in reqs:
            r = reqs[rid]
            if kind == "answer":
                r["answers"].append(ev)
            elif kind == "decline":
                r["declines"].append(ev)
            elif kind == "ack":
                r["acked"] = True
            elif kind == "escalate" and not r["escalated"]:
                r["escalated"] = str(ev.get("why", "escalated"))
            elif kind == "reassign":
                # v19: rebind a phantom identity's side of the request onto a
                # session that actually reads its inbox. APPENDED like every
                # other state change here, so the `ask` event still records who
                # really sent it -- the log stays truthful about history and
                # only the routing moves.
                if ev.get("from"):
                    r["from"] = str(ev["from"])
                if ev.get("to"):
                    r["to"] = str(ev["to"])
    return reqs


def request_resolved(r):
    """A direct request is resolved by an answer OR a decline: a refusal with
    a reason IS an answer. A broadcast is resolved only by an answer -- a
    decline there just releases the decliner ("not my area")."""
    if r["answers"]:
        return True
    return r["to"] != "*" and bool(r["declines"])


def escalate_requests(worklist, session_id, dry_run=False):
    """Promote unanswerable requests to operator-visible `- [?]` items.

    `dry_run` (v9): report what WOULD escalate without appending anything.
    The poll fast path uses it to forfeit the silent exit when an escalation
    is due, so escalation always happens on a FULL stop that reports it --
    an escalation performed silently would be an operator-visible event that
    nobody surfaced.

    THE DEAD-RECIPIENT PROBLEM. A request nobody will ever be blocked on is a
    silent black hole, and blocking the SENDER instead would punish the one
    session that did the right thing. So ANY session's stop escalates when:
      - a direct request's recipient has no fresh brief (older than
        WORKLIST_REQUEST_DEAD_MIN, default 180 min, or none at all) and the
        request is past WORKLIST_REQUEST_GRACE_MIN (default 30 -- grace for a
        recipient that has not briefed YET);
      - a broadcast has no other live session to answer it, or every live
        session has declined it;
      - anything is unanswered past WORKLIST_REQUEST_STALE_MIN (default 240),
        live recipient or not: a recipient that never stops never runs this
        hook, and four hours of silence is the operator's business.
    Escalation appends an `escalate` event plus a `- [?]` item (a CLI-origin
    store event since v10, no longer a markdown append) owned by the ASKER,
    carrying the ask's own DEFAULT: (or a generic proceed-without-it one), so
    the existing deferral machinery reports it to the operator every stop
    without wrongly blocking anyone. Check-then-append is not idempotent, so
    it runs under an exclusive NON-BLOCKING flock with a re-read inside the
    lock: the losing racer skips and retries next stop, and a request is
    escalated exactly once."""
    stale_min = float(os.environ.get("WORKLIST_REQUEST_STALE_MIN", "240"))
    dead_min = float(os.environ.get("WORKLIST_REQUEST_DEAD_MIN", "180"))
    grace_min = float(os.environ.get("WORKLIST_REQUEST_GRACE_MIN", "30"))
    reqs = read_requests(worklist)
    if not reqs:
        return []
    now = C.utcnow()
    briefs = S.read_briefs(worklist)
    live = {
        k
        for k, (when, _t) in briefs.items()
        if when is not None and (now - when).total_seconds() / 60.0 <= dead_min
    }

    def unanswerable(r):
        if r["escalated"] or r["acked"] or request_resolved(r):
            return ""
        if r["to"] == "operator":
            # THE REPORT IS THE ESCALATION. An operator request is already in
            # front of the one party who can settle it, so cloning it into a
            # `- [?]` would report the same question twice: once as a live
            # request and once as a deferral carrying its text, each with its
            # own DEFAULT window. Escalation exists for a question with nobody
            # left to answer it; this one is addressed to the one party who
            # always can. (It used to leave the machine over SES as well; that
            # channel is gone, and the reasoning never depended on it.)
            return ""
        age = C.stamp_age_min(r["at"])
        if age is None:
            return ""
        if age >= stale_min:
            return "unanswered for %dmin" % age
        if r["to"] != "*":
            seen = S.brief_age_min(worklist, r["to"], briefs)
            if (seen is None or seen > dead_min) and age >= grace_min:
                return "recipient %s %s" % (
                    r["to"],
                    "never briefed" if seen is None else "silent for %dmin" % seen,
                )
            return ""
        others = {k for k in live if not C.same_session(k, r["from"])}
        if not others:
            return "no other live session to answer"
        if all(any(C.same_session(str(d.get("by", "")), k) for d in r["declines"]) for k in others):
            return "every live session declined"
        return ""

    candidates = [(r, unanswerable(r)) for r in reqs.values()]
    candidates = [(r, why) for r, why in candidates if why]
    if not candidates:
        return []
    if dry_run:
        return ["#%s to %s: %s" % (r["id"], r["to"], why) for r, why in candidates]
    escalated = []
    with open(str(S.requests_path(worklist)) + ".lock", "w") as lock:
        try:
            # S._flock, not a direct fcntl import: this module is imported by the
            # read-only inbox surfaces (the report index and the waiter), which
            # take no lock at all, so a module-scope `import fcntl` here would
            # kill them on Windows over a call they never make.
            S._flock(lock, S.LOCK_EX | S.LOCK_NB)
        except OSError:
            return []  # another stop is escalating; it wins, next stop retries
        current = read_requests(worklist)  # re-read under the lock
        stamp = C.stamp_now()
        for r, why in candidates:
            fresh = current.get(r["id"])
            if fresh is None or fresh["escalated"] or fresh["acked"] or request_resolved(fresh):
                continue
            with open(S.requests_path(worklist), "a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "ev": "escalate",
                            "id": r["id"],
                            "by": (session_id or "unknown")[:8],
                            "at": stamp,
                            "why": why,
                        },
                        separators=(",", ":"),
                    )
                    + "\n"
                )
            body = r["body"]
            if not C.DEFAULT_TOKEN.search(body):
                body += " DEFAULT: the asker proceeds without an answer and says so in its summary"
            # The WHY/HOW are intrinsic here (v12): an escalated request IS a
            # question no session could answer, so it earns its [?] seat at
            # creation instead of being nagged for a justification at 30 min.
            S.add_item(
                worklist,
                (session_id or "unknown")[:8],
                "request #%s to %s went unanswered (%s): %s"
                "  WHY: %s, so no session can settle it and only the operator can"
                "  HOW: the operator answers it, or its DEFAULT executes when the window closes"
                % (r["id"], r["to"], why, body, why),
                state="?",
                owner=r["from"] or "unknown",
            )
            escalated.append("#%s to %s: %s" % (r["id"], r["to"], why))
    return escalated


def classify_requests(reqs, session_id):
    """(to_me, broadcasts_awaiting_me, answered_unacked_mine, open_mine).

    The ownership rule, applied to requests: a session is only ever blocked
    on its OWN obligations -- answering what is addressed to it (a broadcast
    is addressed to everyone, but only until THIS session responds) and
    acting on answers to what it asked. Never on another session's silence."""
    to_me, bcast, answered_mine, open_mine = [], [], [], []
    for r in sorted(reqs.values(), key=lambda x: (x["at"], x.get("id", ""))):
        mine = bool(session_id) and C.same_session(r["from"], session_id)
        resolved = request_resolved(r)
        if mine:
            if resolved and not r["acked"]:
                answered_mine.append(r)
            elif not resolved and not r["escalated"]:
                open_mine.append(r)
            continue
        if resolved or r["escalated"] or not session_id:
            continue
        if r["to"] == "*":
            if not any(C.same_session(str(d.get("by", "")), session_id) for d in r["declines"]):
                bcast.append(r)
        elif C.same_session(r["to"], session_id):
            to_me.append(r)
    return to_me, bcast, answered_mine, open_mine


def _briefed(worklist, to):
    """Has `to` ever briefed in this store? None when the ROSTER ITSELF is empty.

    Three values, not two, because the blind case is not the negative case. An
    empty `.sessions` means the check has no data at all (a fresh worktree, a
    wiped TMPDIR), and refusing every ask there would break the mechanism in
    exactly the situation where nothing is wrong. A check that cannot answer
    must say so rather than answer no.

    same_session, not ==: a brief is filed under a short prefix and an asker may
    hold the full uuid, and either side of that comparison can be either.
    """
    briefs = S.read_briefs(worklist)
    if not briefs:
        return None
    return any(C.same_session(k, to) for k in briefs)


def request_cli(argv, worklist):
    """--ask / --answer / --decline / --ack / --requests. Exits non-zero on
    misuse, so a session cannot mistake a rejected post for a delivered one.

    The catalogue import is LAZY so an inbox poll on an empty inbox (and the
    read-only --requests listing) keep working when worklist_messages.py is
    broken; the two die() sites that need it fail into the crash handler,
    naming the catalogue, which is the fail-closed direction."""
    import worklist_messages as M  # noqa: PLC0415 -- lazy on purpose: a broken catalogue must fail into the crash handler, not at import time

    def die(msg):
        print(msg, file=sys.stderr)
        sys.exit(1)

    def request_body(what):
        """Join, flatten, and LENGTH-CHECK the free-text argument. Over-length
        is REFUSED, never silently clipped: a write-time truncation would be
        the commit-message defect one layer down, losing the tail (often the
        crucial part) while telling the sender it was delivered."""
        body = " ".join(argv[3:]).replace("\n", " ").strip()
        if len(body) > REQUEST_BODY_MAX:
            die(M.CLI_BODY_REFUSED % (what, len(body), REQUEST_BODY_MAX))
        return body

    mode = argv[0]
    stamp = C.stamp_now()
    if mode == "--requests":
        reqs = read_requests(worklist)
        if not reqs:
            print("no requests recorded (%s)" % S.requests_path(worklist))
            return
        for r in sorted(reqs.values(), key=lambda x: (x["at"], x.get("id", ""))):
            state = (
                "acked"
                if r["acked"]
                else "answered"
                if request_resolved(r)
                else "escalated"
                if r["escalated"]
                else "open"
            )
            print(
                "#%s %s %s -> %s [%s] %s" % (r["id"], r["at"], r["from"], r["to"], state, r["body"])
            )
            for a in r["answers"]:
                print(
                    "    answer by %s at %s: %s"
                    % (a.get("by", "?"), a.get("at", "?"), a.get("body", ""))
                )
            for d in r["declines"]:
                print(
                    "    decline by %s at %s: %s"
                    % (d.get("by", "?"), d.get("at", "?"), d.get("reason", ""))
                )
            if r["escalated"]:
                print("    escalated: %s" % r["escalated"])
        return
    if len(argv) < 3:
        die(M.CLI_REQUEST_USAGE)
    me = argv[1]
    if not C.PREFIX_RE.match(me):
        die("bad prefix %r: pass YOUR session-id prefix first" % me)
    _ok, _why = C.check_me(me)
    if not _ok:
        die(_why)
    if mode == "--ask":
        to = argv[2]
        if to != "*" and not C.PREFIX_RE.match(to):
            die(
                "bad recipient %r: a session prefix from the .sessions briefs, or * to broadcast"
                % to
            )
        if to != "*" and C.same_session(me, to):
            die("that request is addressed to yourself; use the worklist for your own items")
        # THE SAME DEFECT FROM THE SENDER'S SIDE. The recipient was validated by
        # SHAPE only, so a prefix no session has ever briefed accepted the post
        # and nobody ever read it. That is not hypothetical: peers asked
        # `4c3e095a` -- an identity that never existed -- and the request sat
        # until it auto-escalated with "recipient silent for 2062min", 34 hours
        # late. A NEVER-EXISTED check, not a staleness check: an idle peer still
        # has a brief, so this cannot fire on one that is merely quiet.
        if to not in ("*", "operator") and _briefed(worklist, to) is False:
            die(M.CLI_ASK_UNKNOWN_RECIPIENT % (to, ", ".join(sorted(S.read_briefs(worklist)))))
        body = request_body("request body")
        if not body:
            die(
                "an empty request asks nothing: say what you need, why, and a DEFAULT: if unanswered"
            )
        if to == "operator" and not C.DEFAULT_TOKEN.search(body):
            # Same rule the escalation retrofit applies below, enforced at the
            # door instead. An operator request is answered by a human who may
            # be asleep, so a question with no stated fallback is a session
            # volunteering to stall for hours; a DEFAULT: makes the wait
            # time-boxed rather than open-ended.
            die(M.CLI_ASK_OPERATOR_NO_DEFAULT)
        rid = hashlib.sha1(
            ("%d|%d|%s|%s" % (time.time_ns(), os.getpid(), me, body)).encode("utf-8")
        ).hexdigest()[:8]
        append_request_event(
            worklist, {"ev": "ask", "id": rid, "from": me, "to": to, "at": stamp, "body": body}
        )
        if to == "*":
            dead_min = float(os.environ.get("WORKLIST_REQUEST_DEAD_MIN", "180"))
            others = [
                k
                for k in S.read_briefs(worklist)
                if not C.same_session(k, me)
                and (S.brief_age_min(worklist, k) or dead_min + 1) <= dead_min
            ]
            print(
                "request #%s broadcast: %d other live session(s) will each be blocked "
                "until they answer or decline%s"
                % (
                    rid,
                    len(others),
                    "" if others else "; NONE are live, so it will escalate to the operator",
                )
            )
        elif to == "operator":
            # The operator has no brief and never will, so the liveness line
            # below would be a lie. Say what actually happens instead.
            print(
                "request #%s posted to the operator; your next full stop emails it "
                "and it is mailed only once. It does not block you: keep working, "
                "and its DEFAULT stands until an answer arrives." % rid
            )
        else:
            seen = S.brief_age_min(worklist, to)
            print(
                "request #%s posted to %s (%s)"
                % (
                    rid,
                    to,
                    "never briefed here; if it stays silent this escalates to the operator"
                    if seen is None
                    else "last seen %dm ago" % seen,
                )
            )
        return
    rid = argv[2]
    r = read_requests(worklist).get(rid)
    if r is None:
        die("no request #%s here (list them with --requests)" % rid)
    if mode == "--ack":
        if not C.same_session(me, r["from"]):
            die("only the asker (%s) can ack #%s" % (r["from"], rid))
        if not request_resolved(r):
            die("#%s has no answer yet; acking now would silence it unanswered" % rid)
        if r["acked"]:
            print("#%s already acked" % rid)
            return
        append_request_event(worklist, {"ev": "ack", "id": rid, "by": me, "at": stamp})
        print("acked #%s; it will not block you again" % rid)
        return
    body = request_body("answer/decline text")
    if C.same_session(me, r["from"]):
        die("#%s is your own request; answering yourself defeats the mechanism" % rid)
    if mode == "--answer":
        if not body:
            die("an empty answer answers nothing")
        append_request_event(
            worklist, {"ev": "answer", "id": rid, "by": me, "at": stamp, "body": body}
        )
        print("answered #%s; %s is blocked on acting on it at their next stop" % (rid, r["from"]))
        return
    if mode == "--decline":
        if not body:
            die("a decline without a reason is a stall, not an answer: say why not")
        append_request_event(
            worklist, {"ev": "decline", "id": rid, "by": me, "at": stamp, "reason": body}
        )
        print(
            "declined #%s%s"
            % (
                rid,
                " (broadcast: this releases only you)"
                if r["to"] == "*"
                else "; the asker gets your reason",
            )
        )
        return
    die("unknown request mode %s" % mode)


def poll_cli(worklist, me, hook_path):
    """`--poll <8-char-prefix>`: the 5-minute inbox poll (v9). EMPTY inbox:
    print NOTHING, exit 0, so the poll turn costs the session almost no
    context. Non-empty: the full payloads plus the exact commands. Either way
    it drops the single-use poll marker that lets the Stop hook recognise
    this turn structurally."""
    if not C.PREFIX_RE.match(me or "") or len(me or "") < C.ME_MIN_LEN:
        # A short prefix would name a DIFFERENT marker than the Stop hook
        # derives from the full session id, silently disabling the fast
        # path, so misuse is refused rather than half-working. This floor is
        # where C.ME_MIN_LEN comes from; check_me now applies it -- and the
        # identity check this verb never had -- to every verb taking a <me>.
        print(
            "usage: --poll <your-8-char-session-id-prefix> (got %r)" % me,
            file=sys.stderr,
        )
        sys.exit(1)
    ok, why = C.check_me(me)
    if not ok:
        print(why, file=sys.stderr)
        sys.exit(1)
    # No marker means no fast path: the safe direction.
    with contextlib.suppress(OSError):
        worklist.with_suffix(".pollmark-%s" % me[:8]).write_text(C.stamp_now(), encoding="utf-8")
    to_me, bcast, answered, _mine = classify_requests(read_requests(worklist), me)
    if not (to_me or bcast or answered):
        sys.exit(0)  # print NOTHING: the operator's contract for this mode
    print_inbox(to_me, bcast, answered, me, hook_path)
    sys.exit(0)


def print_inbox(to_me, bcast, answered, me, hook_path):
    """The inbox rendering, shared by `--poll` and by the blocking waiter.

    Factored out rather than copied because the payload and the exact
    --answer/--decline/--ack command lines are the whole product of both modes:
    a second copy would drift, and the copy that drifts is the one a session
    reads at 3am when it cannot remember the verb."""
    for r in to_me + bcast:
        print(
            "INBOX #%s from %s (%s, asked %s): %s"
            % (
                r["id"],
                r["from"],
                "to you" if r["to"] != "*" else "broadcast",
                r["at"],
                r["body"],
            )
        )
        print("    answer:  %s --answer %s %s '<what you did or know>'" % (hook_path, me, r["id"]))
        print("    decline: %s --decline %s %s '<why not>'" % (hook_path, me, r["id"]))
    for r in answered:
        print("ANSWERED #%s (you asked: %s)" % (r["id"], r["body"][:120]))
        for a in r["answers"]:
            print(
                "    answer by %s at %s: %s"
                % (a.get("by", "?"), a.get("at", "?"), a.get("body", ""))
            )
        for d in r["declines"]:
            print(
                "    decline by %s at %s: %s"
                % (d.get("by", "?"), d.get("at", "?"), d.get("reason", ""))
            )
        print("    ack when acted on: %s --ack %s %s" % (hook_path, me, r["id"]))
