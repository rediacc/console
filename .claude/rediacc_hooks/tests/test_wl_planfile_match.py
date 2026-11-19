"""`wl_planfile.match_item` caches (`_prepared`, `_token_index`) and its pigeonhole pruning (0f739755.1-.3).

The pruned, indexed lookup must give the same answer as a brute-force scan over every prepared row, and a changed `MIN_MATCH_TOKENS` must not be served from a cache built under the old value.
"""

from __future__ import annotations

import math
import random

from rediacc_hooks.tests import wlfix

PF = wlfix.import_wl("wl_planfile")
P = wlfix.import_wl("wl_planfid")

WORDS = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india", "juliet", "kilo", "lima"]


def brute(task, prepared):
    """The full scan the index replaces: every prepared row, same score and tie rules."""
    tt = PF._toks(task)
    if len(tt) < P.MIN_MATCH_TOKENS:
        return None
    best = None
    for iid, state, it, _ids in prepared:
        if not it:
            continue
        inter = len(tt & it)
        if inter / len(tt) >= P.TASK_MATCH or inter / len(it) >= P.TASK_MATCH:
            score = inter / float(min(len(tt), len(it)))
            better = best is None or score > best[0]
            tie = (
                best is not None
                and score == best[0]
                and state not in PF.CLOSED_STATES
                and best[2] in PF.CLOSED_STATES
            )
            if better or tie:
                best = (score, iid, state)
    return None if best is None else (best[1], best[2])


def test_the_pruned_lookup_agrees_with_a_brute_force_scan():
    rng = random.Random(7)
    for _ in range(300):
        rows = [
            ("i%d" % n, rng.choice([" ", "x"]), " ".join(rng.sample(WORDS, rng.randint(3, 9))))
            for n in range(rng.randint(1, 12))
        ]
        task = " ".join(rng.sample(WORDS, rng.randint(3, 10)))
        prepared = PF.prepare(rows)
        # tokens shorter than the floor are dropped by _toks; rows with no box id and too few tokens are not prepared.
        assert PF.match_item(task, prepared) == brute(task, prepared), (rows, task)


def test_the_pruning_bound_is_the_ceiling_of_the_match_ratio():
    """The pigeonhole count m is ceil(TASK_MATCH * len) capped at ceil(TASK_MATCH * MIN): an item sharing exactly m tokens with the task is found (CONTROL: one fewer shared token is not a match)."""
    task = " ".join(WORDS[:10])
    need = math.ceil(P.TASK_MATCH * 10 - 1e-9)
    shared = " ".join(WORDS[:need])
    rows = [("hit", " ", shared + " " + " ".join(["zulu%d" % k for k in range(0)]))]
    assert PF.match_item(task, PF.prepare(rows)) == ("hit", " ")
    below = [("miss", " ", " ".join(WORDS[: need - 1]) + " yankee xray whiskey victor uniform tango")]
    assert PF.match_item(task, PF.prepare(below)) is None


def test_a_changed_min_match_tokens_is_not_served_from_the_caches(monkeypatch):
    rows = [("a", " ", "alpha bravo")]
    task = "alpha bravo"
    monkeypatch.setattr(P, "MIN_MATCH_TOKENS", 2)
    prepared = PF._prepared(rows)
    assert PF.match_item(task, prepared) == ("a", " ")
    monkeypatch.setattr(P, "MIN_MATCH_TOKENS", 3)
    # Same rows list, new constant: the row is now too short to fingerprint and must drop out.
    assert PF._prepared(rows) == []
    assert PF._token_index(prepared) == {}


def test_control_the_same_constant_reuses_the_caches():
    rows = [("a", " ", "alpha bravo charlie")]
    assert PF._prepared(rows) is PF._prepared(rows)
    prepared = PF._prepared(rows)
    assert PF._token_index(prepared) is PF._token_index(prepared)
