"""The probabilistic "out of the blue" reminder gate.

wl_hints.py's rotating one-line reminder is deliberately gated on `parts` already being non-empty (wl_checks.py: "gated on parts already being non-empty... must never be the reason one exists"), so a clean stop with nothing else to say stays silent, always.

That is correct for the common case, and this module exists for the one the operator asked for: an occasional reminder that fires with nothing else queued, not tied to any other finding.

should_pop() is the whole gate -- a single boolean roll, isolated in its own module rather than folded into wl_checks.py's own body, for the reason PLAN-popup-reminder.md names: wl_checks.py is a currently-contested file (a concurrent session's uncommitted rewrite), and the only change it needs to take this feature is one call site swapping `if parts:` for `if parts or wl_popup.should_pop():`.

Everything else -- the probability, the seam, the test -- lives here where it cannot collide.

THE SEAM MATCHES outq_drain's AND hint_pick's, on purpose: `rng=None` resolves to the module-level `random`, and a test drives the identical code path with `random.Random(seed)` instead of asserting over many real calls.

A feature whose only proof is "run it 1000 times and check the rate is near 20%" is a flaky test wearing a real one's clothes; this one is instead provably 1.0 or 0.0 for a given seed, checked once each way.

`WORKLIST_POPUP_PROBABILITY` IS THE CROSS-PROCESS SEAM, matching `WORKLIST_HINTS_FILE`'s precedent: `wl_checks.py` runs as a subprocess in the wlfix.py harness, so an in-process `rng=` swap cannot reach it from a test driving the real Stop event end to end. A genuinely-silent-stop control sets this to `"0"` rather than hunting for a seed whose first roll happens to clear the floor.

CONTROLS live in test-popup.py beside this file, the same convention test-planfile.py uses next to wl_planfile.py.
"""

import os
import random

POP_PROBABILITY = 0.2


def _probability():
    try:
        return float(os.environ.get("WORKLIST_POPUP_PROBABILITY", str(POP_PROBABILITY)))
    except ValueError:
        return POP_PROBABILITY


def should_pop(rng=None):
    """True with probability `_probability()`, False otherwise. Never raises."""
    r = rng if rng is not None else random
    return r.random() < _probability()
