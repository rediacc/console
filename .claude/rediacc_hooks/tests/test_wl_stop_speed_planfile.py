"""`wl_planfile.match_item`'s item-side prefix prune (agent/plans/PLAN-tooling-speed.md SP8).

The old task-side bound capped the shared-token count at ceil(TASK_MATCH * MIN_MATCH_TOKENS), so every long task scanned nearly the whole store: 844 tasks against 5,764 items cost 4.5 s of a 20 s stop on 2026-11-24. The prefix index keeps a common word out of the postings; these tests hold the answer equal to a brute-force scan on a skewed vocabulary at several thresholds, and show the common word is not indexed.
"""

from __future__ import annotations

import random

import pytest

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.test_wl_planfile_match import brute

PF = wlfix.import_wl("wl_planfile")
P = wlfix.import_wl("wl_planfid")

COMMON = ["the", "and", "plan", "writer", "ci"]
RARE = ["w%02d" % n for n in range(40)]


def _text(rng, lo, hi):
    words = rng.sample(RARE, rng.randint(lo, hi))
    words += [w for w in COMMON if rng.random() < 0.8]
    return " ".join(words)


@pytest.mark.parametrize("threshold", [0.5, 0.7, 0.9, 1.0])
def test_the_prefix_prune_agrees_with_a_brute_force_scan(monkeypatch, threshold):
    monkeypatch.setattr(P, "TASK_MATCH", threshold)
    rng = random.Random(int(threshold * 100))
    for _ in range(150):
        rows = [
            ("i%d" % n, rng.choice([" ", "x"]), _text(rng, 0, 6)) for n in range(rng.randint(1, 40))
        ]
        task = _text(rng, 1, 25)
        prepared = PF.prepare(rows)
        assert PF.match_item(task, prepared) == brute(task, prepared), (rows, task)


def test_a_word_every_item_carries_is_not_in_the_prefix_index():
    """Each item's prefix holds its rarest tokens, so `the` (in every item) stays out while each item's own rare word is in (CONTROL)."""
    rows = [("i%d" % n, " ", "the and %s %s" % (RARE[n], RARE[n + 1])) for n in range(20)]
    prepared = PF.prepare(rows)
    pidx = PF._prefix_index(prepared, PF._token_index(prepared))
    assert "the" not in pidx
    assert pidx[RARE[0]] == [0]


def test_need_is_the_exact_float_threshold():
    for k in range(1, 40):
        for t in (0.1, 0.5, 0.7, 0.75, 0.9, 1.0):
            c = PF._need(k, t)
            assert c / k >= t
            assert c == 0 or (c - 1) / k < t
