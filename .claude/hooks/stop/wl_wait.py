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

import os
import pathlib
import sys
import time

import wl_core as C
import wl_report as RPT
import wl_requests as R
import wl_store as S

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
    to_me, bcast, answered, _mine = R.classify_requests(R.read_requests(worklist), me)
    return {
        "sig": S.my_requests_sig(worklist, me),
        "requests": {r["id"] for r in to_me + bcast + answered},
        "reports": {e["id"] for e in RPT.unread(store, branch, me)},
    }


def _new_requests(worklist, me, base):
    """Requests in this session's slice that were not in the baseline."""
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
        RPT.scan(store, start)
    except Exception:  # noqa: BLE001
        pass


def wait(me, timeout_min, start):
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

    deadline = time.monotonic() + timeout_min * 60.0
    next_scan = time.monotonic() + SCAN_EVERY_S

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            # ONE BOUNDED LINE, exit 0. Printing nothing would be cheaper and
            # would match --poll's empty-inbox contract, but a check whose
            # running you cannot see is worthless, and this is the only evidence
            # that the waiter ran at all rather than dying silently at launch.
            print("INBOX-WAIT: %dm elapsed, nothing new for %s" % (timeout_min, me))
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
            woke_ix = [
                e for e in RPT.unread(store, branch, me) if e["id"] not in base["reports"]
            ]

        to_me, bcast, answered = woke_rq
        if not (to_me or bcast or answered or woke_ix):
            continue

        if to_me or bcast or answered:
            R.print_inbox(to_me, bcast, answered, me, hook_path)
        if woke_ix:
            print("NEW SUB-AGENT REPORT(S) on branch %s:" % branch)
            for e in woke_ix:
                print("  %s%-12s %-20s %s" % (
                    "[SILENT] " if e.get("silent") else "",
                    e["id"], str(e.get("agent"))[:20],
                    e.get("title") or "(stopped without reporting)"))
            print("    read one:  python3 %s --show <id>" % RPT.__file__)
            print("    mark read: python3 %s --read %s <id> [<id>...]" % (RPT.__file__, me))
        return 0


def main(argv):
    if not argv or argv[0].startswith("-"):
        print("usage: wl_wait.py <your-8-char-session-id-prefix> [--timeout <minutes>]",
              file=sys.stderr)
        return 2
    me = argv[0]
    if not C.PREFIX_RE.match(me) or len(me) < 8:
        # Refused rather than half-working: a short prefix does not identify one
        # session, so the baseline would be armed against the wrong slice and the
        # waiter would wake on other sessions' mail or miss its own.
        print("bad prefix %r: pass YOUR 8-char session-id prefix" % me, file=sys.stderr)
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
    start = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    try:
        return wait(me, timeout_min, start)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
