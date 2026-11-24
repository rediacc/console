"""The Stop battery's registry and clock (agent/plans/PLAN-tooling-speed.md D4, box SP3).

WHY. run_stop is one function of about 3,800 lines and nothing measured where its 15-40 s per stop went (plan Context 1 and 7). This module names every segment of that battery once, in order, with its tier, and times each one with `time.monotonic`; a blocked stop's blocklog row carries the durations (`wl_checks.blocklog`), so the retro and the profiler read which segment is slow from data instead of guessing.

A SEGMENT, NOT A FUNCTION. Each entry is one `R.begin("<key>")` mark in run_stop: the segment runs from its mark to the next one. The sections stay inline because they share run_stop's locals (the fold, the roster, `vadd`, the CI state) and because the suite's mutation fixtures match wl_checks.py text at its current indentation; lifting them into functions is a separate change. What this module guarantees is the inventory: test_wl_stop_speed_registry.py asserts that the marks in run_stop and REGISTRY name the same keys in the same order, that each tier agrees with the `vadd` calls inside its segment, and that every segment a fixture stop reaches writes a duration.

TIERS:
    setup     bookkeeping before any check speaks (the fold, the ladder, the store status, the guide)
    always    a segment holding at least one ALWAYS-tier `vadd` (never rotated away by the cadence)
    rotating  a segment whose `vadd` calls are all rotating
    advisory  a segment that only queues advisories (`outq_add`), never a violation
    verdict   the effort level, parks, stand-downs, the cadence gate and the judge, after every check has had its say

The floor set is wl_floor's and is not restated here; the effort table's one-row-per-key rule (`check_plan_record --effort-table`) reads violation keys, which are a different namespace from these segment keys.
"""

import time
from typing import NamedTuple

TIERS = ("setup", "always", "rotating", "advisory", "verdict")


class Segment(NamedTuple):
    key: str
    tier: str


# In run_stop order. `setup` is opened by R.start at the top of run_stop; every other key by its R.begin mark.
REGISTRY = (
    Segment("setup", "setup"),
    Segment("reggate-detect", "setup"),
    Segment("gather", "setup"),
    Segment("bg-wait", "setup"),
    Segment("ladder-bookkeeping", "setup"),
    Segment("store-status", "setup"),
    Segment("guide", "setup"),
    Segment("roster", "always"),
    Segment("wake-timer", "always"),
    Segment("idle-stall", "always"),
    Segment("pending-ask", "always"),
    Segment("sweep-moment", "rotating"),
    Segment("defer-expired", "rotating"),
    Segment("defer-justify", "rotating"),
    Segment("completion", "rotating"),
    Segment("work-gate", "rotating"),
    Segment("plan-drift", "rotating"),
    Segment("plan-file", "rotating"),
    Segment("next-plan", "advisory"),
    Segment("plan-set", "rotating"),
    Segment("landed-work", "rotating"),
    Segment("ci-queue", "always"),
    Segment("loop-speed", "advisory"),
    Segment("sched-red", "always"),
    Segment("sched-fresh", "advisory"),
    Segment("handover", "rotating"),
    Segment("ops-health", "rotating"),
    Segment("pr-review", "rotating"),
    Segment("pr-finish", "always"),
    Segment("landing-stack", "rotating"),
    Segment("loop-next", "always"),
    Segment("idle-capacity", "always"),
    Segment("big-pieces", "always"),
    Segment("checklist", "always"),
    Segment("idle-detect", "rotating"),
    Segment("ladder-rungs", "always"),
    Segment("store-freshness", "rotating"),
    Segment("store-fold", "advisory"),
    Segment("ci-waiting", "rotating"),
    Segment("plan-fidelity", "advisory"),
    Segment("trapguard", "always"),
    Segment("admit", "always"),
    Segment("effort", "verdict"),
    Segment("verdict", "verdict"),
    Segment("judge", "verdict"),
)
KEYS = frozenset(s.key for s in REGISTRY)

# One stop per process: the open segment, when it opened, and the milliseconds each closed segment took.
_CLOCK: dict = {"open": None, "since": 0.0, "ms": {}}


def _close(now):
    key = _CLOCK["open"]
    if key is not None:
        ms = _CLOCK["ms"]
        ms[key] = ms.get(key, 0.0) + (now - _CLOCK["since"]) * 1000.0


def start(key, clock=time.monotonic):
    """Reset the clock for a new stop and open `key`. An unregistered key raises KeyError: a mark the registry does not name is a wiring bug the suite must see, never a silent untimed segment."""
    if key not in KEYS:
        raise KeyError("stop segment %r is not in wl_stopregistry.REGISTRY" % key)
    _CLOCK["ms"] = {}
    _CLOCK["open"] = key
    _CLOCK["since"] = clock()


def begin(key, clock=time.monotonic):
    """Close the open segment and open `key`. Raises KeyError on an unregistered key, like start."""
    if key not in KEYS:
        raise KeyError("stop segment %r is not in wl_stopregistry.REGISTRY" % key)
    now = clock()
    _close(now)
    _CLOCK["open"] = key
    _CLOCK["since"] = now


def durations(clock=time.monotonic):
    """{segment key: whole milliseconds} for this stop so far, the open segment counted up to now, in REGISTRY order. Empty before start."""
    if _CLOCK["open"] is None:
        return {}
    now = clock()
    ms = dict(_CLOCK["ms"])
    open_key = _CLOCK["open"]
    ms[open_key] = ms.get(open_key, 0.0) + (now - _CLOCK["since"]) * 1000.0
    return {s.key: round(ms[s.key]) for s in REGISTRY if s.key in ms}


def exports(local_names, names):
    """{name: value} for each of `names` that is bound in `local_names` (a segment function's `locals()`). A name a segment binds only on some paths is simply absent, so the next segment's load of it stays unbound, exactly as it was when the segments shared one function's locals."""
    return {n: local_names[n] for n in names if n in local_names}
