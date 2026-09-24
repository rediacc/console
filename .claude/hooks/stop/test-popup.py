#!/usr/bin/env python3
"""wl_popup.should_pop() -- both directions, deterministically.

    python3 .claude/hooks/stop/test-popup.py

A feature whose only test asserts a rate over many real calls is a coin-flip pretending to be a proof. Both cases here are 1.0 or 0.0 for a fixed seed, so each runs once.
"""

import os
import random
import sys

import wl_popup


class Tally:
    fails = 0
    count = 0


def control(label, got, want):
    Tally.count += 1
    if got != want:
        Tally.fails += 1
        print("FAIL  %s: got %r, wanted %r" % (label, got, want), file=sys.stderr)


def truthy(label, got):
    Tally.count += 1
    if not got:
        Tally.fails += 1
        print("FAIL  %s: got %r, wanted something truthy" % (label, got), file=sys.stderr)


# Seed 1's first draw must be under the floor, and seed 0's must clear it, or these two cases prove nothing about should_pop's own boundary.
truthy("seed 1 rolls under the floor", random.Random(1).random() < wl_popup.POP_PROBABILITY)
truthy("seed 0 rolls at or over the floor", random.Random(0).random() >= wl_popup.POP_PROBABILITY)

control("should_pop fires under a seed that rolls low", wl_popup.should_pop(random.Random(1)), True)
control(
    "should_pop stays silent under a seed that rolls high",
    wl_popup.should_pop(random.Random(0)),
    False,
)

# CONTROL: an explicit rng and the default must agree on a seeded instance, so `rng=None` is really `random` and not a second, silently different generator.
random.seed(1)
control(
    "the default rng is the module-level random",
    wl_popup.should_pop(),
    wl_popup.should_pop(random.Random(1)),
)

# PIN, not a measurement: the operator asked for 20%. A silent change to this constant should be a visible diff, not a passing test.
control("the probability is pinned at one in five", wl_popup.POP_PROBABILITY, 0.2)

# WORKLIST_POPUP_PROBABILITY is the cross-process seam wlfix.py's subprocess-driven suite needs, since it cannot swap `rng=` on a `wl_checks.py` running in another process. Prove both overrides here rather than trusting the read.
os.environ["WORKLIST_POPUP_PROBABILITY"] = "0"
control(
    "an override of 0 never fires, regardless of roll", wl_popup.should_pop(random.Random(1)), False
)
os.environ["WORKLIST_POPUP_PROBABILITY"] = "1"
control(
    "an override of 1 always fires, regardless of roll", wl_popup.should_pop(random.Random(0)), True
)
del os.environ["WORKLIST_POPUP_PROBABILITY"]
control(
    "an unset override falls back to POP_PROBABILITY",
    wl_popup.should_pop(random.Random(1)),
    random.Random(1).random() < wl_popup.POP_PROBABILITY,
)
os.environ["WORKLIST_POPUP_PROBABILITY"] = "not-a-float"
control(
    "an unparseable override falls back to POP_PROBABILITY rather than raising",
    wl_popup.should_pop(random.Random(1)),
    random.Random(1).random() < wl_popup.POP_PROBABILITY,
)
del os.environ["WORKLIST_POPUP_PROBABILITY"]

if Tally.count < 5:
    Tally.fails += 1
    print(
        "FAIL  only %d control(s) ran; the file is not being executed as written" % Tally.count,
        file=sys.stderr,
    )

if Tally.fails:
    print("FAIL: %d of %d control(s) failed" % (Tally.fails, Tally.count), file=sys.stderr)
    sys.exit(1)
print("%d control(s) passed" % Tally.count)
