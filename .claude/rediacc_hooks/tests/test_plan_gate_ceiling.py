"""The turbo ceiling counts writer work only (agent/plans/PLAN-idle-writer-capacity.md I1, D1-D2).

On 2026-11-09 the branch's five in-set plans had only live, operator or post-merge boxes left, `plan_concurrency` was 5, and `next_turbo` returned [] for hours while a Promoted plan had a box a writer could take. These cases pin the tag grammar `writer_startable` reads and the ceiling that counts a plan only when a writer can start one of its open boxes before the merge.
"""

from __future__ import annotations

import pytest

from rediacc_hooks import plan_gate
from rediacc_hooks.tests.test_plan_gate import _t, _turbo_root, _xplan

FIVE = "```stop-hook\neffort: high\nturbo: on\nbatch_size: 3\nplan_concurrency: 5\n```\n"


def _live_only():
    """An in-set plan of the 2026-11-09 shape: ticked code boxes, and the open ones all live, operator or post-merge."""
    return _xplan(opened=0, done=3) + (
        "- [ ] V1 [live] deploy the bench signer and prove the binding\n"
        "- [ ] H1 [operator window] after release, converge one machine\n"
        "- [ ] L8 [ops, post-merge] telemetry acceptance\n"
        "- [ ] X2 [hostinger rollout] machine setup with the released renet\n"
        "- [ ] SC13b evidence from a real run. Depends on: SC13a and this PR's merge\n"
    )


@pytest.mark.parametrize(
    ("line", "want"),
    [
        ("- [ ] V1 [live] deploy the signer\n", False),
        ("- [ ] V1 [live, post-merge] after the merge, release\n", False),
        ("- [ ] H1 [operator window] after release\n", False),
        ("- [ ] H1 [hostinger rollout] machine setup\n", False),
        ("- [ ] K2 [fleet] the K2 rows on the KVM fleet\n", False),
        ("- [ ] T1 [drill] L1 complete\n", False),
        ("- [ ] W1 [local GPU] on the WSL host\n", False),
        ("- [ ] L9 [account, post-merge] retire the path\n", False),
        ("- [ ] L1 [lead] runbook check\n", False),
        ("- [ ] SC13b the run. Depends on: SC13a and this PR's merge\n", False),
        # writer work: tagged, untagged, or tagged with a word that names no non-writer kind
        ("- [ ] S2 [writer] signer service\n", True),
        ("- [ ] S2 [writer, opus] signer service\n", True),
        ("- [ ] R2 [opus] hole punching\n", True),
        ("- [ ] N1 [ci] fix the red nightly\n", True),
        ("- [ ] B4 [P2] e2e against a VM\n", True),
        ("- [ ] T5 a box a writer can do\n", True),
        # a word merely containing a tag word is no marker
        ("- [ ] T6 live-reload the dev server config\n", True),
    ],
)
def test_writer_startable_reads_the_bracket_tags(line, want):
    assert plan_gate.writer_startable(_xplan(opened=0) + line) is want


def test_the_2026_11_09_shape_leaves_a_slot_for_a_writer_box(tmp_path):
    """Five in-set plans with live-only boxes, plan_concurrency 5, and a Promoted plan with a box a writer can do: the pick is that plan."""
    plans = {n: _live_only() for n in ("p1", "p2", "p3", "p4", "p5")}
    plans["ent"] = _xplan(opened=0) + "- [ ] S2 [writer] signer service and Worker\n"
    root = _turbo_root(tmp_path, plans, ["p1", "p2", "p3", "p4", "p5", "ent"], FIVE)
    in_set = tuple(_t(n) for n in ("p1", "p2", "p3", "p4", "p5"))
    assert plan_gate.next_turbo(root, (), 20, in_set=in_set) == [_t("ent")]


def test_an_in_set_plan_with_writer_work_still_counts(tmp_path):
    """CONTROL: the same five plans each with one untagged open code box fill the ceiling, so the tags and nothing else freed the slot above."""
    plans = {n: _live_only() + "- [ ] C9 a code box a writer can do\n" for n in "abcde"}
    plans["ent"] = _xplan(opened=0) + "- [ ] S2 [writer] signer service and Worker\n"
    root = _turbo_root(tmp_path, plans, ["a", "b", "c", "d", "e", "ent"], FIVE)
    in_set = tuple(_t(n) for n in "abcde")
    assert plan_gate.next_turbo(root, (), 20, in_set=in_set) == []


def test_live_writers_still_count_against_the_ceiling(tmp_path):
    """The plans live writers serve count whatever their boxes say: a live writer is a slot taken."""
    plans = {n: _live_only() for n in ("p1", "p2", "p3", "p4", "p5")}
    plans["ent"] = _xplan(opened=0) + "- [ ] S2 [writer] signer service and Worker\n"
    root = _turbo_root(tmp_path, plans, ["p1", "p2", "p3", "p4", "p5", "ent"], FIVE)
    live = ("PLAN-w1.md", "PLAN-w2.md", "PLAN-w3.md", "PLAN-w4.md", "PLAN-w5.md")
    assert plan_gate.next_turbo(root, live, 20) == []


def test_a_live_only_plan_is_no_pick(tmp_path):
    """A pick is a writer slot, so a Promoted plan whose open boxes are all live is skipped for the one behind it."""
    plans = {"l": _live_only(), "b": _xplan()}
    root = _turbo_root(tmp_path, plans, ["l", "b"], FIVE)
    assert plan_gate.next_turbo(root, (), 4) == [_t("b")]
