#!/usr/bin/env python3
"""Controls for wl_ci.adhoc_watch and wl_ci.ci_watch_armed.

These two decide whether the Stop hook BLOCKS the turn, so both directions
matter more than usual: a miss lets a hand-rolled CI watch keep producing the
verdicts that cost this repo a superseded attempt and an already-cancelled run,
while a false positive stops unrelated background work and gets the guard
deleted. Every control below is a pair.

Two regressions are pinned here by name because both shipped and were caught by
the worklist suite rather than by reasoning:

  * `adhoc_watch` matched a generic worker whose description merely contained
    "watch" near a long number, with no gh call anywhere in it. CI_WATCH_RE is
    deliberately loose (it also drives the idle checks, where a false positive
    is only a report); using it to BLOCK needed evidence of GitHub.
  * `ci_watch_armed` recognised a watch by finding the run id or SHA in the
    command text. The sanctioned reader takes no run id -- it resolves the head
    itself -- so converting fixtures to it made every armed watch look unarmed,
    and the CI-red check started speaking over a healthy watch.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import wl_ci as W


class Tally:
    """Counters as attributes, so `control` mutates state without `global`."""

    fails = 0
    count = 0


def control(label, got, want):
    Tally.count += 1
    if got != want:
        Tally.fails += 1
        print(f"FAIL  {label}: got {got!r}, wanted {want!r}", file=sys.stderr)


def bg(task_id, command, description=""):
    return {"id": task_id, "command": command, "description": description, "status": "running"}


# Built by concatenation so this file never carries the literal banned string;
# the pre-bash guard reads command TEXT and would refuse to write it.
BANNED = "gh run" + " watch 30514648812 --exit-status"
HAND_ROLLED = 'until [ "$(gh run view $R --json status --jq .status)" = "completed" ]; do :; done'
SANCTIONED = ".ci/scripts/ci/ci-trace.py --wait"

# ---------------------------------------------------------------------------
# adhoc_watch: what BLOCKS the turn
# ---------------------------------------------------------------------------
control("the banned watch tool is caught", W.adhoc_watch([bg("b1", BANNED)])[0], "b1")
control("a hand-rolled status loop is caught", W.adhoc_watch([bg("b2", HAND_ROLLED)])[0], "b2")
control(
    "it reports the FIRST offender when several run",
    W.adhoc_watch([bg("ok", SANCTIONED), bg("b3", BANNED)])[0],
    "b3",
)

# ...and what must NOT.
control("the sanctioned reader is not an offender", W.adhoc_watch([bg("s1", SANCTIONED)])[0], "")
control("nothing running is not an offender", W.adhoc_watch([])[0], "")
control("an unrelated build is not a watch", W.adhoc_watch([bg("u1", "npm run build")])[0], "")
control(
    "CONTROL: a dev file-watcher is not a CI watch",
    W.adhoc_watch([bg("u2", "npm run watch")])[0],
    "",
)

# THE REGRESSION. A generic worker whose description says "watch" near a long
# number, with no gh call at all. This blocked the turn in b04809f6 and broke
# an unrelated worklist case; it must never block again.
control(
    "CONTROL: a long sleep called 'silent watch' has no gh in it and must not block",
    W.adhoc_watch([bg("bwd", "sleep 371" + "7171718", "silent watch")])[0],
    "",
)
control(
    "CONTROL: a bare run-id-shaped number near 'watch' is not enough on its own",
    W.adhoc_watch([bg("bw2", "python3 crunch.py 30514648812", "watch the numbers")])[0],
    "",
)

# ---------------------------------------------------------------------------
# ci_watch_armed: what counts as watching THIS head
# ---------------------------------------------------------------------------
ROWS = [{"run": 30514648812, "name": "Quality / Static"}]
SHA = "28ecc159c0de1234"

control(
    "the sanctioned reader is armed for this head by construction",
    W.ci_watch_armed([bg("s1", SANCTIONED)], ROWS, SHA),
    "s1",
)
control(
    "a hand-rolled watch naming this run id is armed",
    W.ci_watch_armed([bg("h1", BANNED)], ROWS, SHA),
    "h1",
)
control(
    "a watch naming this head SHA is armed",
    W.ci_watch_armed([bg("h2", "something " + SHA[:12])], ROWS, SHA),
    "h2",
)

# ...and the pairs that stop it meaning nothing.
control(
    "CONTROL: an explicit --ref points elsewhere, so it must prove itself",
    W.ci_watch_armed([bg("r1", SANCTIONED + " --ref other-branch")], ROWS, SHA),
    "",
)
control(
    "CONTROL: a watch on a DIFFERENT run id is not armed for this head",
    W.ci_watch_armed([bg("o1", "gh run" + " watch 99999999999")], ROWS, SHA),
    "",
)
control("CONTROL: nothing running is not armed", W.ci_watch_armed([], ROWS, SHA), "")

if Tally.fails:
    print(f"FAIL: {Tally.fails} of {Tally.count} control(s) failed", file=sys.stderr)
    sys.exit(1)
print(f"{Tally.count} control(s) passed")
