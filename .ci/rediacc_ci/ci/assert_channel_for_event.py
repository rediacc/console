#!/usr/bin/env python3
"""Port of `.ci/scripts/ci/assert-channel-for-event.sh` (65 lines).

Asserts the resolved R2 staging CHANNEL matches the GitHub event type. The
twin's own header carries the contract and the history (finding G, the
dryrun-<sha> fallthrough, ~5 GB of orphan R2 bytes per schedule trigger); none
of it is restated here.

LIVE CALLER, not repointed: `.github/workflows/ci.yml:295`
`run: .ci/scripts/ci/assert-channel-for-event.sh "${{ github.event_name }}"
"${{ steps.staging.outputs.channel }}"`. The bash twin stays the registered
gate; this module is its verified-equivalent alternative, and the cutover is a
separate, later, driver-only step.

Ledger: `.ci/shadow/w7p6-assert-channel-for-event.observations.jsonl`
(`npx tsx scripts/lib/shadow-gate.ts --pair w7p6-assert-channel-for-event
--assert --k 5`).

-----------------------------------------------------------------------------
THE `*)` ARM FAILS OPEN, AND THAT IS REPRODUCED RATHER THAN REPAIRED
-----------------------------------------------------------------------------
An event name the `case` does not know -- a typo, or a genuinely new trigger
such as `pull_request_target` -- WARNS and returns 0 with any channel at all:

    $ .ci/scripts/ci/assert-channel-for-event.sh pull_request_target dryrun-abc
    (warn) Unknown event: pull_request_target (channel: 'dryrun-abc') ...
    exit 0

That is the twin's documented behaviour (its `workflow_dispatch` arm exists
precisely because `*)` accepts), and `docs/ci-overhaul/02-v1-economics.md:92`
already names it as a thing to harden. Changing it here would make the port
non-equivalent, so it is carried verbatim and reported instead.

-----------------------------------------------------------------------------
TWO SPELLING DIFFERENCES, BOTH PINNED BY THE DIFFERENTIAL
-----------------------------------------------------------------------------
1. `$0` in the usage line is the program's own name, so bash prints the `.sh`
   path and this prints the `.py` path. The differential normalises that one
   token and compares the rest byte-for-byte.
2. common.sh logs with `echo -e`, which interprets backslash escapes IN THE
   MESSAGE, so a channel containing a literal `\t` prints a TAB from bash and
   two characters from here. `rediacc_ci.log` formats the message as data on
   purpose (see `log.py`'s "A SECOND DIVERGENCE" note), and
   `test_ci_assert_channel_for_event.py` asserts the two disagree so nobody
   "fixes" the Python to match a bug.
"""

from __future__ import annotations

import re
import sys

from rediacc_ci import log

# `^pr-[0-9]+$` from the twin, as a fullmatch. `[0-9]` is ASCII-only in both
# engines (the twin runs under LC_ALL=C in CI), and fullmatch rather than
# `re.match(... + "$")` because Python's `$` also matches before a trailing newline while bash's does not -- `pr-1\n` must fail on both sides.
PR_CHANNEL = re.compile(r"pr-[0-9]+")

# The two events that must produce NO R2 bytes at all. `workflow_dispatch` is
# the nightly rehearsal (ci.yml, guarded to main); the twin spells out at
# :44-53 why it needs an explicit arm rather than falling into `*)`.
EMPTY_CHANNEL_EVENTS = {
    "schedule": "  schedule must not produce R2 uploads.",
    "workflow_dispatch": "  The nightly rehearsal must not produce R2 uploads.",
}


def main(argv: list[str]) -> int:
    event = argv[0] if len(argv) >= 1 else ""
    channel = argv[1] if len(argv) >= 2 else ""

    if not event:
        log.error("Usage: %s <event_name> <channel>" % sys.argv[0])
        return 2

    if event in EMPTY_CHANNEL_EVENTS:
        if channel:
            log.error("Channel must be empty for %s events (got: %s)." % (event, channel))
            log.error(EMPTY_CHANNEL_EVENTS[event])
            return 1
    elif event == "push":
        if channel != "edge":
            log.error("push events must resolve to edge channel (got: '%s')." % channel)
            return 1
    elif event == "pull_request":
        if not PR_CHANNEL.fullmatch(channel):
            log.error("pull_request events must resolve to pr-N channel (got: '%s')." % channel)
            return 1
    else:
        log.warn(
            "Unknown event: %s (channel: '%s'); accepting without assertion" % (event, channel)
        )

    log.info("Channel '%s' matches event '%s'" % (channel or "<empty>", event))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
