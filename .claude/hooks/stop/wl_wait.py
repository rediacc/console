#!/usr/bin/env python3
"""wl_wait: block until something NEW arrives for this session, then exit.

    python3 /abs/path/.claude/hooks/stop/wl_wait.py <session-8-prefix> --timeout 60

Launched as a BACKGROUND SHELL TASK. Its exit is the ping.

WHY THIS SHAPE AND NOT ANOTHER. Nothing outside a session can inject a turn into
it. The one push channel that exists is the harness notifying the session when a
background task finishes, so "wake me when there is mail" has exactly one
spelling: a process that blocks until there is mail and then exits. The `*/5`
poll cron it replaces costs a full session turn every five minutes and prints
nothing on almost every firing.

NO QUOTES ANYWHERE IN THE COMMAND LINE, and that is not cosmetic. `_needle`
(wl_liveness.py:175-187) takes the longest QUOTE-FREE segment of a background
task's command and requires >= 12 characters, and `verify_background`
(wl_liveness.py:235-263) only reaches `confirmed` for a shell task with a usable
needle. Wrap this path in quotes and a perfectly healthy waiter renders as
`unverifiable`, which is exactly how a working waiter comes to look stuck. The
absolute path alone is far over 12 characters, so the property holds by
construction as long as nobody adds quotes.

IT NEVER TAKES A LOCK, AND THAT IS THE SHARPEST HAZARD IN THE WHOLE DESIGN.
`_append_lines` (wl_store.py) takes a BLOCKING LOCK_EX, so an hour-long holder
would stall every --ask/--add/--tick in the repo. Worse, the two LOCK_EX|LOCK_NB
paths that give up SILENTLY on contention -- escalation (wl_requests.py:196-199)
and dead-session cleanup (wl_store.py) -- would become permanent no-ops with no
error printed anywhere, so the damage would be invisible. Readers take no lock by
design and this process only ever reads, stats, or appends a single sub-1024-byte
line through wl_report (which is itself lock-free). Test 3 in
test-report-inbox.sh asserts it, with a control that proves the assertion can
fail.

IT IS A CHANGE DETECTOR, NEVER A BACKLOG DETECTOR. A request that arrived BEFORE
the waiter launched will not wake it, by design (see `arm`). That is the one bug
a review caught in this design rather than a test, so read `arm` before changing
the wake condition.

Stdlib only. Waiting is os.stat() plus time.sleep(): epoll is linux-only, kqueue
is absent, inotify/watchdog are not installed, and `pip install` is refused under
PEP 668. time.monotonic() for the deadline, never the wall clock, so an NTP step
cannot cut a wait short or extend it forever.
"""

import contextlib
import json
import os
import pathlib
import sys
import time

import wl_core as C

# wl_store / wl_requests / wl_report are imported LAZILY inside wait(). The
# --nudge mode below runs on EVERY PostToolUse, and importing the whole worklist
# stack (wl_store alone is ~53 KB) on every tool call is a cost the nudge does
# not need: it reads two file stamps and a brief list, and nothing else.

TICK_S = float(os.environ.get("WORKLIST_WAIT_TICK_S", "2"))
# 60 minutes, matching the hourly work-loop cadence this repo already runs on and
# the ~70-minute horizon the surrounding liveness checks are calibrated against.
DEFAULT_TIMEOUT_MIN = float(os.environ.get("WORKLIST_WAIT_TIMEOUT_MIN", "60"))
# How often the waiter re-runs wl_report --scan while it is awake anyway. This is
# what makes a report captured by neither the hook nor the previous scan still
# reach the session, so it is a correctness path, not an optimisation.
SCAN_EVERY_S = float(os.environ.get("WORKLIST_WAIT_SCAN_S", "300"))


def _stat(path):
    """(size, mtime_ns), or None when absent. The ONLY watch primitive portable
    to linux, macOS and Windows. `.requests` is strictly append-only and never
    compacted, so size alone is a sound change detector there; the pair is used
    anyway so an index rewrite could not hide behind an equal size."""
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_size, st.st_mtime_ns)


def arm(worklist, store, branch, me):
    """Snapshot what this session has ALREADY SEEN, and wake only on what is new
    relative to it.

    ARMING AGAINST A BASELINE RATHER THAN AGAINST EMPTINESS IS THE WHOLE
    CORRECTNESS ARGUMENT. There is no recipient-side read marker anywhere in the
    request system: "unread" there is computed as "not resolved and not
    escalated", which conflates *I have not seen it* with *I have seen it and am
    deliberately still working on it*. So the classified slice is NOT an inbox of
    unseen things. A waiter armed on "wake when the slice is non-empty" would
    fire instantly on launch, be relaunched, fire instantly again, and spin --
    turning the push mechanism into a busy loop strictly worse than the cron it
    replaces.

    The baseline is process-local and deliberately NOT persisted. A waiter is one
    bounded wait; persisting its baseline would recreate that same read-marker
    problem in a file, with no owner.
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
    """--scan, but a failure here must never end the wait: an unwritable store
    costs a self-heal pass, while raising would cost the session its wake-up."""
    try:
        import wl_report as RPT  # noqa: PLC0415

        RPT.scan(store, start)
    except Exception:  # noqa: BLE001
        pass


def heartbeat_path(worklist, me):
    """The file a RUNNING waiter re-touches every tick.

    WHY A HEARTBEAT AND NOT `confirmed_waiters`. The Stop hook can ask the OS,
    because its event carries `background_tasks`. `PostToolUse` DOES NOT -- I
    checked a captured payload rather than assuming: its keys are tool_name,
    tool_input, tool_response, tool_use_id, agent_id, agent_type, cwd,
    duration_ms, effort, permission_mode, prompt_id, session_id,
    transcript_path, hook_event_name. No background_tasks, no session_crons.

    So the nudge cannot see the task table, and a marker written once at launch
    would be a LIE the moment the waiter died. A file that only a live process
    keeps refreshing is the same guarantee by a different route: it goes stale
    on its own, needs no pid semantics (so it stays portable), and costs the
    hook exactly one stat.
    """
    return worklist.with_suffix(".waiter-%s" % (me or "unknown")[:8])


def nudge_path(worklist, me):
    return worklist.with_suffix(".waiternudge-%s" % (me or "unknown")[:8])


def _touch(path):
    # A missing heartbeat costs an extra nudge, never a wedged waiter.
    with contextlib.suppress(OSError):
        path.write_text(C.stamp_now(), encoding="utf-8")


def wait(me, timeout_min, start):
    import wl_report as RPT  # noqa: PLC0415 -- see the import note at the top
    import wl_requests as R  # noqa: PLC0415
    import wl_store as S  # noqa: PLC0415

    worklist = C.worklist_for(start)
    store = RPT.store_root(start)
    branch = C.git_branch(C.project_root(start)) or RPT.NO_BRANCH
    hook_path = "python3 %s" % (pathlib.Path(__file__).resolve().parent / "worklist.py")

    # Scan BEFORE arming, never after. The first scan on a fresh store indexes
    # every already-finished agent in the lookback window; if the baseline were
    # taken first, all of them would read as NEW and the waiter would wake
    # immediately with a flood of history on its very first run.
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
            # ONE BOUNDED LINE, exit 0. Printing nothing would be cheaper and
            # would match --poll's empty-inbox contract, but a check whose
            # running you cannot see is worthless, and this is the only evidence
            # that the waiter ran at all rather than dying silently at launch.
            print(
                "INBOX-WAIT: %dm elapsed, nothing new for %s. RELAUNCH to keep "
                "listening: python3 %s %s --timeout %d"
                % (timeout_min, me, pathlib.Path(__file__).resolve(), me, timeout_min)
            )
            hb.unlink(missing_ok=True)
            return 0
        time.sleep(min(TICK_S, remaining))

        if time.monotonic() >= next_scan:
            next_scan = time.monotonic() + SCAN_EVERY_S
            _safe_scan(store, start)

        woke_rq = ([], [], [])
        now_rq = _stat(rq)
        if now_rq != seen["rq"]:
            seen["rq"] = now_rq
            # THE CHEAP GATE FIRST. Any session in this repo appending to the
            # shared log moves its size, and folding on every such change would
            # make foreign traffic a source of empty wake-ups -- the exact cost
            # being removed here. The signature covers only events touching THIS
            # session, so an unmoved signature ends the tick without a fold.
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
        # THE WAITER FIRES ONCE AND IS THEN GONE. Nothing relaunches it, and a
        # session that does not re-arm is DEAF -- worse than the cron, which at
        # least fires again. Measured live: a waiter fired at 16:13, a peer
        # answered at 16:16, and the answer was never seen. So the exit line
        # carries the relaunch command, and the PostToolUse nudge below is the
        # belt to this braces.
        print(
            "RELAUNCH THE WAITER NOW (background task), or you stop hearing "
            "anything: python3 %s %s --timeout %d"
            % (pathlib.Path(__file__).resolve(), me, timeout_min)
        )
        hb.unlink(missing_ok=True)
        return 0


HELP = """wl_wait.py -- block until something new arrives for you, then EXIT.

    python3 %s <your-8-char-session-id-prefix> --timeout 60

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

EXIT CODES / OUTPUT
    0 + INBOX/REPORT lines   something arrived; act on it, then RELAUNCH
    0 + one INBOX-WAIT line  the timeout elapsed with nothing new; relaunch
    2                        misuse (bad prefix, bad --timeout); nothing waited

    --timeout <minutes>   default %d

Related: `worklist.py --poll <me>` is the pull version (one shot, prints only
what is already there). `worklist.py --reports` lists captured sub-agent reports.
""" % (pathlib.Path(__file__).resolve(), int(DEFAULT_TIMEOUT_MIN))


# A heartbeat older than this means no waiter is listening. Six ticks of slack
# at the 2s default, so a briefly-descheduled process is never called dead.
HEARTBEAT_STALE_S = float(os.environ.get("WORKLIST_WAITER_STALE_S", "60"))
# How often the PostToolUse nudge may speak. PostToolUse fires on EVERY tool
# call, so an unthrottled nudge is pure noise and noise is how a mechanism gets
# switched off. Ten minutes is a few times an hour on a busy session -- and it
# sits under BG_REPORT_MIN (15), so a session that has lost its waiter is told
# before the pure-wait check-in would start asking about it.
NUDGE_EVERY_S = float(os.environ.get("WORKLIST_WAITER_NUDGE_S", "600"))


def _fresh(path, max_age_s):
    try:
        return (time.time() - path.stat().st_mtime) <= max_age_s
    except OSError:
        return False


def nudges_ignored(worklist, me):
    """How many times this session has been told to start a waiter and has not.

    The Stop-side backstop keys on THIS rather than on "no waiter right now",
    which is the difference between proportionate and intolerable: a waiter
    legitimately exits every time it fires, so "no waiter right now" is true in
    a window the session is supposed to be in, and blocking there punishes the
    correct behaviour. A count only grows when the session has been asked,
    repeatedly, over the throttle interval, and ignored it."""
    try:
        return int(nudge_path(worklist, me).read_text(encoding="utf-8").split()[0])
    except (OSError, ValueError, IndexError):
        return 0


def nudge(event):
    """PostToolUse: tell a session with no live waiter to start one.

    ORDERED BY COST, cheapest gate first, because this runs on every tool call:
    one stat for the throttle, one stat for the heartbeat, and only then a read
    of the briefs file.
    """
    me = str(event.get("session_id") or "")[:8]
    if not me:
        return
    start = C.project_start(event)
    worklist = C.worklist_for(start)

    if _fresh(nudge_path(worklist, me), NUDGE_EVERY_S):
        return  # already said recently
    if _fresh(heartbeat_path(worklist, me), HEARTBEAT_STALE_S):
        # A waiter is listening. RESET the ignored-count: the session complied,
        # and a counter that only ever grows would eventually block a session
        # that has been doing the right thing for hours.
        nudge_path(worklist, me).unlink(missing_ok=True)
        return

    # DO NOT NUDGE WHEN THERE IS NOTHING TO LISTEN FOR. With no other live
    # session there is nobody who could send anything, and a waiter would be
    # pure cost. Over-firing is how this gets routed around, so the check earns
    # its silence here rather than being tuned down later.
    import wl_store as S  # noqa: PLC0415 -- only reached past both throttles

    dead_min = float(os.environ.get("WORKLIST_REQUEST_DEAD_MIN", "180"))
    peers = [
        k
        for k in S.read_briefs(worklist)
        if not C.same_session(k, me) and (S.brief_age_min(worklist, k) or dead_min + 1) <= dead_min
    ]
    if not peers:
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
        # The bare-usage path prints the SAME text. A tool whose entire value
        # depends on how it is invoked, whose usage line does not say how to
        # invoke it, does not get used -- which is exactly what happened: it
        # shipped, and the session that built it kept polling instead.
        print(HELP, file=sys.stderr)
        return 2
    me = argv[0]
    if not C.PREFIX_RE.match(me) or len(me) < C.ME_MIN_LEN:
        # Refused rather than half-working: a short prefix does not identify one
        # session, so the baseline would be armed against the wrong slice and the
        # waiter would wake on other sessions' mail or miss its own.
        print("bad prefix %r: pass YOUR 8-char session-id prefix" % me, file=sys.stderr)
        return 2
    # And the same argument one step further: a full-length prefix that is not
    # THIS session arms the baseline against the wrong slice just as completely,
    # and silently. This waiter blocks for minutes on the wrong inbox otherwise.
    ok, why = C.check_me(me)
    if not ok:
        print(why, file=sys.stderr)
        return 2
    timeout_min = DEFAULT_TIMEOUT_MIN
    if "--timeout" in argv:
        i = argv.index("--timeout")
        try:
            timeout_min = float(argv[i + 1])
        except (IndexError, ValueError):
            print("--timeout takes a number of minutes", file=sys.stderr)
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
