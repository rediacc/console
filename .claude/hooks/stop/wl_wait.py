#!/usr/bin/env python3
"""wl_wait: block until something NEW arrives for this session, then exit.

    python3 /abs/path/.claude/hooks/stop/wl_wait.py <session-8-prefix> --timeout 60m

Launched as a BACKGROUND SHELL TASK. Its exit is the ping.

WHY THIS SHAPE AND NOT ANOTHER. Nothing outside a session can inject a turn into it. The one push channel that exists is the harness notifying the session when a background task finishes, so "wake me when there is mail" has exactly one spelling: a process that blocks until there is mail and then exits. The `*/5` poll cron it replaces costs a full session turn every five minutes and
prints nothing on almost every firing.

NO QUOTES ANYWHERE IN THE COMMAND LINE, and that is not cosmetic. `_needle` (wl_liveness.py:175-187) takes the longest QUOTE-FREE segment of a background
task's command and requires >= 12 characters, and `verify_background`
(wl_liveness.py:235-263) only reaches `confirmed` for a shell task with a usable needle. Wrap this path in quotes and a perfectly healthy waiter renders as `unverifiable`, which is exactly how a working waiter comes to look stuck. The absolute path alone is far over 12 characters, so the property holds by construction as long as nobody adds quotes.

IT NEVER TAKES A LOCK ON THE WORKLIST STORE, AND THAT IS THE SHARPEST HAZARD IN THE WHOLE DESIGN.
`_append_lines` (wl_store.py) takes a BLOCKING LOCK_EX, so an hour-long holder would stall every --ask/--add/--tick in the repo. Worse, the two LOCK_EX|LOCK_NB paths that give up SILENTLY on contention -- escalation (wl_requests.py:196-199) and dead-session cleanup (wl_store.py) -- would become permanent no-ops with no error printed anywhere, so the damage would be invisible.
Readers take no lock by design and this process only ever reads, stats, or appends a single sub-1024-byte line through wl_report (which is itself lock-free). Test 3 in test-report-inbox.sh asserts it, with a control that proves the assertion can fail.

THE ONE LOCK IT DOES TAKE IS ITS OWN, and the distinction above is exactly what makes that safe. `claim_instance` holds a LOCK_EX|LOCK_NB flock on a
PRIVATE per-session sidecar (`.waiterlock-<me8>`) that nothing else in this repo opens, reads or writes, so no --add/--tick/--ask path can ever contend on it and the silent-give-up hazard described above cannot reach it. What it buys is the single-writer assumption the heartbeat and the tombstone were built on: thirteen simultaneous instances for one session were measured on
2026-09-23, and because every one of them re-touched the SAME heartbeat every two seconds, a tombstone written by an exiting instance was clobbered within a tick, so `waiter_lapsed` never fired while any duplicate survived. See agent/plans/_done/PLAN-wl-wait-duplicate-listener.md.

IT IS A CHANGE DETECTOR, NEVER A BACKLOG DETECTOR. A request that arrived BEFORE the waiter launched will not wake it, by design (see `arm`). That is the one bug a review caught in this design rather than a test, so read `arm` before changing the wake condition.

Stdlib only. Waiting is os.stat() plus time.sleep(): epoll is linux-only, kqueue is absent, inotify/watchdog are not installed, and `pip install` is refused under PEP 668. time.monotonic() for the deadline, never the wall clock, so an NTP step cannot cut a wait short or extend it forever.
"""

import contextlib
import json
import os
import pathlib
import sys
import time

import wl_core as C

# wl_store / wl_requests / wl_report are imported LAZILY inside wait(). The --nudge mode below runs on EVERY PostToolUse, and importing the whole worklist stack (wl_store alone is ~53 KB) on every tool call is a cost the nudge does not need: the COMMON path returns on two file stats and reaches no import at all. Only the tail -- at most once per throttle window, and only when
# nothing is listening -- reads the brief list, the harness task dir and the item fold (measured together at ~22 ms against the live 1.3 MB event log).

TICK_S = float(os.environ.get("WORKLIST_WAIT_TICK_S", "2"))
# 60 minutes, matching the hourly work-loop cadence this repo already runs on and the ~70-minute horizon the surrounding liveness checks are calibrated against.
DEFAULT_TIMEOUT_MIN = float(os.environ.get("WORKLIST_WAIT_TIMEOUT_MIN", "60"))
# How often the waiter re-runs wl_report --scan while it is awake anyway. This is what makes a report captured by neither the hook nor the previous scan still reach the session, so it is a correctness path, not an optimisation.
SCAN_EVERY_S = float(os.environ.get("WORKLIST_WAIT_SCAN_S", "300"))

# `--timeout` TAKES A UNIT SUFFIX AND A BARE NUMBER IS REFUSED. Minutes per suffixed minute.
TIMEOUT_UNITS = {"s": 1.0 / 60.0, "m": 1.0, "h": 60.0}
# The refusal, spelled out once because it is the whole repair for a misreading this repo has now paid for twice. 2026-09-04 (worklist_messages.py, the V_ASK_NOLISTEN_CMD comment): a message asked for `--timeout 900` meaning fifteen minutes and bought a fifteen-HOUR wait. 2026-09-23: thirteen overlapping instances, each relaunched in the belief that a `--timeout 60`
# process launched minutes earlier had already finished.
#
# The sibling instrument is what makes a bare number genuinely ambiguous rather than merely undocumented: `.ci/scripts/ci/ci-trace.py --timeout` is the same flag name on the other sanctioned long-lived background process in this repo, and its unit is SECONDS. A session that has read either one cannot infer the other. So neither takes a bare number any more.
TIMEOUT_UNIT_REFUSAL = (
    "--timeout needs an explicit unit: %r could mean %s minutes or %s seconds and this flag will "
    "not guess. Write 60m, 3600s or 1h.\n"
    "THE UNIT IS NOT THE SAME ON THE SIBLING TOOL, which is why a bare number is refused rather "
    "than defaulted: .ci/scripts/ci/ci-trace.py --timeout is SECONDS, this one is minutes, and "
    "both now require the suffix so neither can be read off the other."
)


def parse_timeout_min(token):
    """(minutes, "") for an explicitly suffixed --timeout token, or (None, why).

    NO BARE-NUMBER FALLBACK, deliberately. Accepting `60` "as minutes" would leave exactly the ambiguity that produced the 13-instance pile: the value is read by a session, not by a parser, and a session reading `--timeout 60` in a message has no way to tell which of the two long-lived instruments' conventions is in force. A clean break is cheap here -- every emitter in
    the tree is swept in the same change and there are no external callers.
    """
    text = str(token).strip()
    if not text or text[-1] not in TIMEOUT_UNITS:
        return None, TIMEOUT_UNIT_REFUSAL % (text, text or "?", text or "?")
    try:
        value = float(text[:-1])
    except ValueError:
        return None, "--timeout %r is not a number followed by s, m or h" % text
    return value * TIMEOUT_UNITS[text[-1]], ""


def fmt_timeout(minutes):
    """A --timeout token this script would accept back, unit included.

    Every relaunch line in this file and in worklist_messages.py renders through a suffixed form, so no message can teach the spelling `main()` refuses. `%g` rather than `%d`: the old `%d` rendered a sub-minute timeout (the test suite uses 0.15) as the literal `0`, which is a value this script rejects as non-positive -- a relaunch command that could not run.
    """
    return "%gm" % minutes


def _stat(path):
    """(size, mtime_ns), or None when absent. The ONLY watch primitive portable to linux, macOS and Windows. `.requests` is strictly append-only and never compacted, so size alone is a sound change detector there; the pair is used anyway so an index rewrite could not hide behind an equal size."""
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_size, st.st_mtime_ns)


def arm(worklist, store, branch, me):
    """Snapshot what this session has ALREADY SEEN, and wake only on what is new relative to it.

    ARMING AGAINST A BASELINE RATHER THAN AGAINST EMPTINESS IS THE WHOLE
    CORRECTNESS ARGUMENT. There is no recipient-side read marker anywhere in the request system: "unread" there is computed as "not resolved and not escalated", which conflates *I have not seen it* with *I have seen it and am deliberately still working on it*. So the classified slice is NOT an inbox of unseen things. A waiter armed on "wake when the slice is non-empty" would fire
    instantly on launch, be relaunched, fire instantly again, and spin -- turning the push mechanism into a busy loop strictly worse than the cron it replaces.

    The baseline is process-local and deliberately NOT persisted. A waiter is one bounded wait; persisting its baseline would recreate that same read-marker problem in a file, with no owner.
    """
    import wl_report as RPT  # noqa: PLC0415
    import wl_requests as R  # noqa: PLC0415
    import wl_store as S  # noqa: PLC0415

    to_me, bcast, answered, _mine = R.classify_requests(R.read_requests(worklist), me)
    return {
        "sig": S.my_requests_sig(worklist, me),
        "requests": {r["id"] for r in to_me + bcast + answered},
        "reports": {e["id"] for e in RPT.unread(store, branch, me)},
    }


def _new_requests(worklist, me, base):
    """Requests in this session's slice that were not in the baseline."""
    import wl_requests as R  # noqa: PLC0415

    to_me, bcast, answered, _mine = R.classify_requests(R.read_requests(worklist), me)
    return (
        [r for r in to_me if r["id"] not in base["requests"]],
        [r for r in bcast if r["id"] not in base["requests"]],
        [r for r in answered if r["id"] not in base["requests"]],
    )


def _safe_scan(store, start):
    """--scan, but a failure here must never end the wait: an unwritable store costs a self-heal pass, while raising would cost the session its wake-up."""
    try:
        import wl_report as RPT  # noqa: PLC0415

        RPT.scan(store, start)
    except Exception:  # noqa: BLE001
        pass


def heartbeat_path(worklist, me):
    """The file a RUNNING waiter re-touches every tick.

    WHY A HEARTBEAT AND NOT `confirmed_waiters`. The Stop hook can ask the OS, because its event carries `background_tasks`. `PostToolUse` DOES NOT -- I checked a captured payload rather than assuming: its keys are tool_name, tool_input, tool_response, tool_use_id, agent_id, agent_type, cwd, duration_ms, effort, permission_mode, prompt_id, session_id, transcript_path,
    hook_event_name. No background_tasks, no session_crons.

    So the nudge cannot see the task table, and a marker written once at launch would be a LIE the moment the waiter died. A file that only a live process keeps refreshing is the same guarantee by a different route: it goes stale on its own, needs no pid semantics (so it stays portable), and costs the hook exactly one stat.

    ONE PATH PER SESSION, SO IT ASSUMES A SINGLE WRITER, and until claim_instance() nothing enforced that. Measured 2026-09-23: thirteen instances for one session each `_touch`ed this one path every TICK_S, so a tombstone written by an exiting instance was overwritten by a survivor's live pulse within two seconds. waiter_lapsed() below reads the CONTENT of this file, so it could
    never return a lapse while any duplicate survived, and the Stop-side `waiter-lapsed` check built on it was switched off by the very pile it would have been the evidence for. claim_instance() is what makes the assumption TRUE BY CONSTRUCTION rather than by convention: a second instance refuses before it touches anything.
    """
    return worklist.with_suffix(".waiter-%s" % (me or "unknown")[:8])


def waiterlock_path(worklist, me):
    """The PRIVATE single-instance claim for this session. Nothing else in the repo opens it.

    A DEDICATED FILE AND NEVER THE WORKLIST STORE. The module docstring's prohibition is about the store, whose locks are taken blocking by `_append_lines` and non-blocking-and-silent by escalation and dead-session cleanup; an hour-long holder there would turn both of those into invisible no-ops. This path has exactly one client -- this script -- so contention on it means
    one thing only, which is the fact the guard needs.
    """
    return worklist.with_suffix(".waiterlock-%s" % (me or "unknown")[:8])


def claim_instance(worklist, me):
    """(handle, "") when this process is the session's only waiter, or (None, refusal) when one is already running.

    THE HANDLE IS THE LOCK AND MUST BE HELD FOR THE PROCESS LIFETIME. Closing it releases the flock, and the kernel drops it on exit however the process dies, which is why this needs no cleanup path and no stale-pidfile handling -- the two failure modes a pidfile would have added.

    A REFUSING DUPLICATE WRITES NOTHING, and that is load-bearing rather than tidy. The obvious refusal -- leave a tombstone saying the launch gave up -- would write the INCUMBENT'S heartbeat path (there is only one per session), marking a waiter that is alive and counting down as lapsed, which is the precise failure this whole guard exists to end. The file is opened for APPEND and
    never written, so a refuser does not even truncate its own sidecar.

    NO SELF-CLEANUP. Killing the incumbent is the wrong trade three ways: the incumbent may be 55 minutes into a deadline with a peer's answer moments away while the newcomer has nothing, the heartbeat carries no pid so a killer would need an argv scan (block_self_matching_pgrep.py documents why that traps), and a killed process leaves a phantom in the harness task table that
    rates `suspect` and nags the session into launching yet another one. Teardown of a real surplus is a `TaskStop`, surfaced by the Stop-side `many-waiters` check.
    """
    import wl_store as S  # noqa: PLC0415

    path = waiterlock_path(worklist, me)
    try:
        handle = path.open("a", encoding="utf-8")  # the handle IS the lock; see the docstring
    except OSError:
        # FAIL OPEN. A sidecar that cannot be created is a broken TMPDIR, not a duplicate, and refusing to listen on that evidence would cost the session its mail to protect it from a process it probably does not have.
        return None, ""
    try:
        S._flock(handle, S.LOCK_EX | S.LOCK_NB)
    except OSError:
        handle.close()
        return None, refusal_text(worklist, me)
    except RuntimeError:
        # NO fcntl ON THIS PLATFORM (S._flock raises a named refusal rather than an ImportError). Degrade to the heartbeat predicate alone -- the same one nudge() already trusts to decide whether anybody is listening.
        handle.close()
        hb = heartbeat_path(worklist, me)
        if _fresh(hb, HEARTBEAT_STALE_S) and not _is_tombstone(hb):
            return None, refusal_text(worklist, me)
        return None, ""
    return handle, ""


def refusal_text(worklist, me):
    """What the duplicate prints on its way out, exit 3.

    IT MUST SAY DO NOT RELAUNCH IN SO MANY WORDS. A fast exit is otherwise indistinguishable from a waiter that fired, and a session acting on that reading relaunches immediately -- turning a slow pile-up into a spin. It names the incumbent's heartbeat age for the same reason: an unfalsifiable "one is already running" invites a session to disbelieve it.
    """
    hb = heartbeat_path(worklist, me)
    try:
        age_s = time.time() - hb.stat().st_mtime
        age = "its heartbeat was refreshed %ds ago" % int(age_s)
    except OSError:
        age = "its heartbeat file is not readable from here"
    return (
        "ALREADY LISTENING (exit 3): a waiter for %s is already running and %s. This second "
        "instance refused before reading, scanning or touching anything, so nothing it did can "
        "have disturbed the one that is listening.\n"
        "DO NOT RELAUNCH IT. You are already listening; there is nothing to fix and nothing to "
        "start. A duplicate is pure cost -- every instance re-touches the same heartbeat, so a "
        "pile of them destroys the lapse detector that would tell you when the real waiter "
        "died.\n"
        "A relaunch attempt is always SAFE to make for exactly this reason: if one is running "
        "you get this line in milliseconds, and if none is you get a waiter. Exit 3 means "
        "refused-as-redundant; it is not an error and it is not a fired waiter (that is exit 0 "
        "with INBOX or REPORT lines)." % (me, age)
    )


def ask_nolisten_path(worklist, me):
    return worklist.with_suffix(".asknolisten-%s" % (me or "unknown")[:8])


def ask_nolisten_count(worklist, me):
    """Consecutive stops where this session held an open ask and was not listening.

    Drives which rung of V_ASK_NOLISTEN_LADDER fires. A plain integer in a sidecar rather than an event, for the same reason nudge_path is: compact() folds the event log to a known set of kinds and would destroy a novel one, and this counter is worth nothing after a fold anyway.

    Unreadable counts as zero. The failure direction is one extra gentle nudge, never a session pinned at the terminal rung by a corrupt file.
    """
    try:
        return int(ask_nolisten_path(worklist, me).read_text(encoding="utf-8").split()[0])
    except (OSError, ValueError, IndexError):
        return 0


def bump_ask_nolisten(worklist, me):
    n = ask_nolisten_count(worklist, me) + 1
    with contextlib.suppress(OSError):
        ask_nolisten_path(worklist, me).write_text(str(n), encoding="utf-8")
    return n


def reset_ask_nolisten(worklist, me):
    """Back to rung 1. Called whenever the session is listening again OR has no open ask left -- the ladder must describe what is true now, not what the session did an hour ago."""
    with contextlib.suppress(OSError):
        ask_nolisten_path(worklist, me).unlink(missing_ok=True)


def nudge_path(worklist, me):
    return worklist.with_suffix(".waiternudge-%s" % (me or "unknown")[:8])


def _touch(path):
    # A missing heartbeat costs an extra nudge, never a wedged waiter.
    with contextlib.suppress(OSError):
        path.write_text(C.stamp_now(), encoding="utf-8")


# The tombstone a waiter leaves BEHIND ITSELF on exit, in place of the unlink both exits used to do. See tombstone().
TOMBSTONE = "EXPIRED"

# Open handles whose flock must survive for the process lifetime. See the comment at the claim site in wait().
HELD_LOCKS = []


def tombstone(path, why):
    """Mark a waiter's heartbeat DEAD instead of deleting it.

    WHY THIS EXISTS. wait() used to `hb.unlink()` on both of its exits -- the timeout at the top of the loop and the fired-and-returning path at the bottom -- which made a LAPSED waiter byte-identical to one that was never armed: in both cases there is simply no file. Combined with nudge()'s counter reset (see decay_nudges), arming a single waiter therefore bought 30+ minutes of
    guaranteed silence AFTER it died. That is a perverse incentive, not a gap: the cheapest way to be left alone was to arm one 60-minute waiter every few hours and never relaunch it.

    THE CARRIER IS THE SAME PATH, deliberately, and that is what makes this the cheapest possible change. Every existing reader is `_fresh(hb,
    HEARTBEAT_STALE_S)` with HEARTBEAT_STALE_S = 60s, and a tombstone is a
    WRITE, so it ages out within a minute exactly as a real heartbeat would. No existing caller changes behaviour; the only new reader is waiter_lapsed() below, which looks at the CONTENT rather than the mtime.

    AND IT ASSUMES IT IS THE ONLY WRITER ON THAT PATH. With N live instances for one session a tombstone survives at most TICK_S seconds before a survivor's `_touch` overwrites it with a live pulse, which made waiter_lapsed() and the Stop-side `waiter-lapsed` check unreachable for exactly the sessions that had lost track of their waiters. claim_instance() enforces N == 1, so
    the only process that can write here is the one whose exit this marks -- and a REFUSING duplicate writes nothing at all, precisely so it cannot leave this marker on a waiter that is still alive.
    """
    with contextlib.suppress(OSError):
        path.write_text("%s %s %s\n" % (TOMBSTONE, C.stamp_now(), why), encoding="utf-8")


def waiter_lapsed(worklist, me):
    """("", None) when no waiter has ever been armed for this session, or (why, age_minutes) when the last one EXITED and was never relaunched.

    A live waiter answers ("", None) too -- a fresh heartbeat is not a lapse -- so the caller does not have to re-derive liveness. NO GRACE PERIOD is warranted on the answer: unlike "you have never armed one", a lapse means the session already accepted the contract and then stopped listening.
    """
    path = heartbeat_path(worklist, me)
    try:
        raw = path.read_text(encoding="utf-8")
        age_s = time.time() - path.stat().st_mtime
    except OSError:
        return "", None  # never armed, or armed and its marker was removed
    if not raw.startswith(TOMBSTONE):
        return "", None  # a real heartbeat, live or merely stale
    if age_s <= HEARTBEAT_STALE_S:
        return "", None  # it exited seconds ago; the relaunch is still in hand
    parts = raw.split()
    return (parts[2] if len(parts) > 2 else "exited"), age_s / 60.0


def wait(me, timeout_min, start):
    import wl_report as RPT  # noqa: PLC0415 -- see the import note at the top
    import wl_requests as R  # noqa: PLC0415
    import wl_store as S  # noqa: PLC0415

    worklist = C.worklist_for(start)
    store = RPT.store_root(start)
    branch = C.git_branch(C.project_root(start)) or RPT.NO_BRANCH
    hook_path = "python3 %s" % (pathlib.Path(__file__).resolve().parent / "worklist.py")

    # THE INSTANCE GUARD COMES FIRST, BEFORE THE SCAN AND BEFORE THE BASELINE, so a duplicate pays for nothing: no report scan against the shared store, no request fold, no heartbeat touch. Everything below this line is work that a second instance for the same session would only repeat.
    #
    # The handle is parked in a module-level list rather than a local, and that is not style: an flock lives on the OPEN FILE DESCRIPTION, so the moment the last reference is dropped the object is finalized, the fd closes and the claim is silently released while the process runs on. A name that outlives the call is the whole mechanism.
    lock_handle, refusal = claim_instance(worklist, me)
    if refusal:
        print(refusal, file=sys.stderr)
        return 3
    if lock_handle is not None:
        HELD_LOCKS.append(lock_handle)

    # Scan BEFORE arming, never after. The first scan on a fresh store indexes every already-finished agent in the lookback window; if the baseline were taken first, all of them would read as NEW and the waiter would wake immediately with a flood of history on its very first run.
    _safe_scan(store, start)
    base = arm(worklist, store, branch, me)

    rq = S.requests_path(worklist)
    ix = RPT.index_path(store)
    seen = {"rq": _stat(rq), "ix": _stat(ix)}

    hb = heartbeat_path(worklist, me)
    _touch(hb)

    deadline = time.monotonic() + timeout_min * 60.0
    next_scan = time.monotonic() + SCAN_EVERY_S

    while True:
        _touch(hb)  # only a LIVE waiter keeps this fresh; see heartbeat_path
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            # ONE BOUNDED LINE, exit 0. Printing nothing would be cheaper and would match --poll's empty-inbox contract, but a check whose running you cannot see is worthless, and this is the only evidence that the waiter ran at all rather than dying silently at launch.
            print(
                "INBOX-WAIT: %gm elapsed, nothing new for %s. RELAUNCH to keep "
                "listening: python3 %s %s --timeout %s"
                % (
                    timeout_min,
                    me,
                    pathlib.Path(__file__).resolve(),
                    me,
                    fmt_timeout(timeout_min),
                )
            )
            # A TOMBSTONE, NOT AN UNLINK. See tombstone(): deleting the file made "this waiter lapsed" indistinguishable from "no waiter was ever armed", which is the state the Stop hook is most lenient about.
            tombstone(hb, "timeout")
            return 0
        time.sleep(min(TICK_S, remaining))

        if time.monotonic() >= next_scan:
            next_scan = time.monotonic() + SCAN_EVERY_S
            _safe_scan(store, start)

        woke_rq = ([], [], [])
        now_rq = _stat(rq)
        if now_rq != seen["rq"]:
            seen["rq"] = now_rq
            # THE CHEAP GATE FIRST. Any session in this repo appending to the shared log moves its size, and folding on every such change would make foreign traffic a source of empty wake-ups -- the exact cost being removed here. The signature covers only events touching THIS session, so an unmoved signature ends the tick without a fold.
            sig = S.my_requests_sig(worklist, me)
            if sig != base["sig"]:
                base["sig"] = sig
                woke_rq = _new_requests(worklist, me, base)

        woke_ix = []
        now_ix = _stat(ix)
        if now_ix != seen["ix"]:
            seen["ix"] = now_ix
            woke_ix = [e for e in RPT.unread(store, branch, me) if e["id"] not in base["reports"]]

        to_me, bcast, answered = woke_rq
        if not (to_me or bcast or answered or woke_ix):
            continue

        if to_me or bcast or answered:
            R.print_inbox(to_me, bcast, answered, me, hook_path)
        if woke_ix:
            print("NEW SUB-AGENT REPORT(S) on branch %s:" % branch)
            for e in woke_ix:
                print(
                    "  %s%-12s %-20s %s"
                    % (
                        "[SILENT] " if e.get("silent") else "",
                        e["id"],
                        str(e.get("agent"))[:20],
                        e.get("title") or "(stopped without reporting)",
                    )
                )
            print("    read one:  python3 %s --show <id>" % RPT.__file__)
            print("    mark read: python3 %s --read %s <id> [<id>...]" % (RPT.__file__, me))
        # THE WAITER FIRES ONCE AND IS THEN GONE. Nothing relaunches it, and a session that does not re-arm is DEAF -- worse than the cron, which at least fires again. Measured live: a waiter fired at 16:13, a peer answered at 16:16, and the answer was never seen. So the exit line carries the relaunch command, and the PostToolUse nudge below is the belt to this braces.
        print(
            "RELAUNCH THE WAITER NOW (background task), or you stop hearing "
            "anything: python3 %s %s --timeout %s"
            % (pathlib.Path(__file__).resolve(), me, fmt_timeout(timeout_min))
        )
        tombstone(hb, "fired")  # see tombstone(); never an unlink
        return 0


HELP = """wl_wait.py -- block until something new arrives for you, then EXIT.

    python3 %s <your-8-char-session-id-prefix> --timeout 60m

LAUNCH IT AS A BACKGROUND TASK (run_in_background: true). That is not a
suggestion, it is the whole mechanism: nothing can inject a turn into a running
session, so the one push channel that exists is the harness telling you a
background task finished. THE EXIT IS THE NOTIFICATION. Run it in the foreground
and you have simply blocked yourself for an hour.

NO QUOTES ANYWHERE IN THE COMMAND LINE. The liveness checker takes the longest
quote-free segment of a background task's command as its needle; wrap the path
in quotes and a perfectly healthy waiter reports as `unverifiable`, which is how
a working waiter comes to look stuck -- and an unverifiable waiter does not
satisfy the no-poll check either.

WHAT WAKES IT: a request newly addressed to you or broadcast, a new answer or
decline on one of your own asks, or a new sub-agent report on your branch. It
prints those with the exact --answer / --decline / --ack / --show commands.

WHAT DOES NOT: anything that was already there when it launched. IT IS A CHANGE
DETECTOR AND NEVER A BACKLOG DETECTOR -- it arms against a snapshot taken at
launch, because the request slice is not an inbox of unseen things (it holds
everything unresolved, including what you have read and are still working on),
so waking on "not empty" would fire instantly and spin forever. Keep the hourly
poll cron: it is what still surfaces a backlog that predates the waiter.

IT ONLY FIRES ONCE. After it wakes it is gone, and nothing relaunches it for
you -- a session that does not re-arm goes deaf, which is worse than the cron.
Relaunch it in the same turn you act on what it told you.

AND A RELAUNCH IS ALWAYS SAFE TO ATTEMPT, so never skip one because you think
one may still be running. A second instance for the same session refuses in
milliseconds with exit 3 and writes nothing at all, so the worst case of an
unnecessary relaunch is one line of output. The worst case of a SKIPPED one is
that you stop hearing cross-session mail. Thirteen simultaneous instances were
measured on 2026-09-23, every one of them relaunched in the belief that a
`--timeout 60` process started minutes earlier had already finished -- the flag
was MINUTES. They cost more than the waste: all thirteen re-touched the one
per-session heartbeat every two seconds, so the exit marker a dying waiter
leaves was clobbered within a tick and the lapse detector could never fire.

AND STOP IT WHEN YOU ARE DONE. A waiter held by a session with nothing open,
nothing in flight and no pending task is an orphan process with an hour to run:
kill the background task (TaskStop <id>) rather than ending the session on top
of it. The PostToolUse nudge goes quiet for a drained session for the same
reason, so nothing will ask you to re-arm one you were right to stop.

EXIT CODES / OUTPUT
    0 + INBOX/REPORT lines   something arrived; act on it, then RELAUNCH
    0 + one INBOX-WAIT line  the timeout elapsed with nothing new; relaunch
    2                        misuse (bad prefix, bad --timeout); nothing waited
    3                        refused: one is ALREADY listening for you. Not an
                             error, and not a fired waiter. Nothing was written
                             and nothing needs relaunching.

    --timeout <n>{s|m|h}  REQUIRED SUFFIX, e.g. 60m. Default %dm. A bare number
                          is refused: ci-trace.py's --timeout is SECONDS and
                          this one is minutes, so neither can be read off the
                          other and neither guesses.

Related: `worklist.py --poll <me>` is the pull version (one shot, prints only
what is already there). `worklist.py --reports` lists captured sub-agent reports.
""" % (pathlib.Path(__file__).resolve(), int(DEFAULT_TIMEOUT_MIN))


# A heartbeat older than this means no waiter is listening. Six ticks of slack at the 2s default, so a briefly-descheduled process is never called dead.
HEARTBEAT_STALE_S = float(os.environ.get("WORKLIST_WAITER_STALE_S", "60"))
# How often the PostToolUse nudge may speak. PostToolUse fires on EVERY tool call, so an unthrottled nudge is pure noise and noise is how a mechanism gets switched off. Ten minutes is a few times an hour on a busy session -- and it sits under BG_REPORT_MIN (15), so a session that has lost its waiter is told before the pure-wait check-in would start asking about it.
NUDGE_EVERY_S = float(os.environ.get("WORKLIST_WAITER_NUDGE_S", "600"))


def _fresh(path, max_age_s):
    try:
        return (time.time() - path.stat().st_mtime) <= max_age_s
    except OSError:
        return False


def _is_tombstone(path):
    """Is this heartbeat file a waiter's EXIT marker rather than a live pulse? Unreadable counts as NOT a tombstone: the failure direction is one extra nudge, never a session accused of losing a waiter it still has."""
    try:
        return path.read_text(encoding="utf-8").startswith(TOMBSTONE)
    except OSError:
        return False


def decay_nudges(worklist, me):
    """Take ONE off the ignored-count, floor zero. Never a reset.

    THE UNLINK THIS REPLACES WAS RESETTABLE BY THE FAILURE ITSELF. nudge() saw a fresh heartbeat and deleted the counter outright, so arming a single waiter zeroed it; when that waiter lapsed the count had to climb from zero again, over another WAITER_GRACE_NUDGES * NUDGE_EVERY_S (half an hour) before the Stop-side `no-waiter` backstop could fire. A session that armed one 60-minute
    waiter every few hours therefore held the check permanently below threshold while being deaf most of the time -- and the absent `.waiternudge-<id>` file on the failing night is the evidence it happened.

    Decay keeps the counter a measure of RECENT behaviour (which is what the reset was rightly for) without letting one act of compliance erase a history of ignoring it. Complying repeatedly still walks it to zero, one nudge window at a time.
    """
    n = nudges_ignored(worklist, me) - 1
    np = nudge_path(worklist, me)
    with contextlib.suppress(OSError):
        if n <= 0:
            np.unlink(missing_ok=True)
        else:
            np.write_text("%d %s\n" % (n, C.stamp_now()), encoding="utf-8")
    return max(n, 0)


def nudges_ignored(worklist, me):
    """How many times this session has been told to start a waiter and has not.

    The Stop-side backstop keys on THIS rather than on "no waiter right now", which is the difference between proportionate and intolerable: a waiter legitimately exits every time it fires, so "no waiter right now" is true in a window the session is supposed to be in, and blocking there punishes the correct behaviour. A count only grows when the session has been asked,
    repeatedly, over the throttle interval, and ignored it."""
    try:
        return int(nudge_path(worklist, me).read_text(encoding="utf-8").split()[0])
    except (OSError, ValueError, IndexError):
        return 0


def outstanding_work(worklist, session_id, transcript_path=""):
    """Does this session still owe anything? OPEN items, IN-FLIGHT items, and pending harness tasks -- the same three slices the Stop hook already calls `actionable_remains` (wl_checks.py, beside remaining_lines), computed the same way so the two ends of this mechanism cannot drift apart.

    WHAT IS DELIBERATELY NOT COUNTED, and why:

      A `[?]` DEFERRAL is parked on the OPERATOR. Its answer arrives in this
      session's own turn, or executes as its DEFAULT on a timer the Stop path
      drives; no peer can deliver one, so there is nothing here for a waiter
      to hear.

      A BACKGROUND JOB counts only through its `[>]` lease, and that is forced
      before it is chosen: PostToolUse does not carry `background_tasks` at all
      (its keys are listed in heartbeat_path above, checked against a captured
      payload). It is also the right answer for this repo, where background
      work must carry a `worker:<bg-id>` lease -- the lease is what makes a
      running job outstanding work rather than a claim, and a fresh one lands
      in `in_flight` below. An unleased job is invisible from here, and no
      cheaper oracle for it exists on this event.

    ANY FAILURE ANSWERS TRUE. Silence has to be EARNED by evidence that there is nothing to hear; a store that will not read is not that evidence, and failing the other way would switch the nudge off in exactly the window the worklist is sick.
    """
    try:
        # Tasks first: a directory glob against a resolved path, and the transcript is consulted only on the cold path (bounded tail read, and it banks the resolution for every later process).
        if C.pending_tasks(session_id, transcript_path):
            return True
        import wl_store as S  # noqa: PLC0415

        # sync=False is load-bearing, not a default: the sync path takes a
        # BLOCKING LOCK_EX, and this process must never hold one (see the module docstring). live_worker_ids is unavailable for the reason above, so an expired lease fails closed into an open item -- the conservative direction, and the one that keeps nudging.
        fold = S.load(worklist, sync=False)
        open_items, _others, _deferred, in_flight = S.classify_items(fold, session_id)
    except Exception:  # noqa: BLE001
        return True
    return bool(open_items or in_flight)


def nudge(event):
    """PostToolUse: tell a session with no live waiter to start one -- unless it has nothing left to do, in which case it is told nothing at all.

    ORDERED BY COST, cheapest gate first, because this runs on every tool call: one stat for the throttle, one stat for the heartbeat, then a read of the briefs file, and only past all three the item fold behind outstanding_work.
    """
    me = str(event.get("session_id") or "")[:8]
    if not me:
        return
    start = C.project_start(event)
    worklist = C.worklist_for(start)

    if _fresh(nudge_path(worklist, me), NUDGE_EVERY_S):
        return  # already said recently
    hb = heartbeat_path(worklist, me)
    if _fresh(hb, HEARTBEAT_STALE_S) and not _is_tombstone(hb):
        # A waiter is listening. DECAY the ignored-count by one -- do NOT delete it. See decay_nudges: the unlink this replaces was resettable BY THE FAILURE, so one 60-minute waiter armed every few hours kept the Stop-side backstop permanently under threshold. `_is_tombstone` is part of the same repair: a waiter's exit marker is a WRITE, so for its first HEARTBEAT_STALE_S seconds
        # it is "fresh" while naming a process that is already gone.
        decay_nudges(worklist, me)
        return

    # DO NOT NUDGE WHEN THERE IS NOTHING TO LISTEN FOR. With no other live session there is nobody who could send anything, and a waiter would be pure cost. Over-firing is how this gets routed around, so the check earns its silence here rather than being tuned down later.
    import wl_store as S  # noqa: PLC0415 -- only reached past both throttles

    dead_min = float(os.environ.get("WORKLIST_REQUEST_DEAD_MIN", "180"))
    peers = [
        k
        for k in S.read_briefs(worklist)
        if not C.same_session(k, me) and (S.brief_age_min(worklist, k) or dead_min + 1) <= dead_min
    ]
    if not peers:
        return

    # AND DO NOT NUDGE A SESSION THAT IS FINISHED. The waiter is how a session HEARS a peer while it still has something to do with what it hears; a drained session paid for it twice over -- a process held for up to an hour, plus this line on every single tool call telling it to relaunch. Observed live 2026-08-19 on a session with no open items, no background jobs and its VMs
    # already torn down, still being told it was NOT LISTENING. Last of the three gates because it is the dearest of them.
    if not outstanding_work(
        worklist, str(event.get("session_id") or ""), event.get("transcript_path")
    ):
        return

    np = nudge_path(worklist, me)
    n = nudges_ignored(worklist, me) + 1
    with contextlib.suppress(OSError):
        np.write_text("%d %s\n" % (n, C.stamp_now()), encoding="utf-8")
    import worklist_messages as M  # noqa: PLC0415

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": M.N_WAITER_NUDGE
                    % (len(peers), pathlib.Path(__file__).resolve(), me, int(DEFAULT_TIMEOUT_MIN)),
                },
            }
        )
    )


def main(argv):
    if argv and argv[0] == "--nudge":
        try:
            raw = sys.stdin.read()
            nudge(json.loads(raw) if raw.strip() else {})
        except Exception:  # noqa: BLE001 -- a nudge must never break a tool call
            pass
        return 0
    if argv and argv[0] in ("--help", "-h", "help"):
        # stdout, not stderr: this one was ASKED for.
        print(HELP)
        return 0
    if not argv or argv[0].startswith("-"):
        # The bare-usage path prints the SAME text. A tool whose entire value depends on how it is invoked, whose usage line does not say how to invoke it, does not get used -- which is exactly what happened: it shipped, and the session that built it kept polling instead.
        print(HELP, file=sys.stderr)
        return 2
    me = argv[0]
    if not C.PREFIX_RE.match(me) or len(me) < C.ME_MIN_LEN:
        # Refused rather than half-working: a short prefix does not identify one session, so the baseline would be armed against the wrong slice and the waiter would wake on other sessions' mail or miss its own.
        print("bad prefix %r: pass YOUR 8-char session-id prefix" % me, file=sys.stderr)
        return 2
    # And the same argument one step further: a full-length prefix that is not THIS session arms the baseline against the wrong slice just as completely, and silently. This waiter blocks for minutes on the wrong inbox otherwise.
    ok, why = C.check_me(me)
    if not ok:
        print(why, file=sys.stderr)
        return 2
    timeout_min = DEFAULT_TIMEOUT_MIN
    if "--timeout" in argv:
        i = argv.index("--timeout")
        if i + 1 >= len(argv):
            print("--timeout takes a value with a unit suffix, e.g. 60m", file=sys.stderr)
            return 2
        timeout_min, why = parse_timeout_min(argv[i + 1])
        if why:
            print(why, file=sys.stderr)
            return 2
    if timeout_min <= 0:
        print("--timeout must be positive", file=sys.stderr)
        return 2
    start = C.project_start()
    try:
        return wait(me, timeout_min, start)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
