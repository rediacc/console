"""`plan_gate.writer_startable` reads writer work only (agent/plans/PLAN-idle-writer-capacity.md I1, D1-D2).

On 2026-11-09 the branch's in-set plans had only live, operator or post-merge boxes left while a Promoted plan had a box a writer could take. These cases pin the tag grammar `writer_startable` reads (wl_boxready's): a box tagged for a live run, an operator window, the fleet or the merge is no writer's, and an untagged or `[writer]` box is. The parallelism ceiling that first read it went with the batch loop (agent/plans/PLAN-simple-two-tree-loop.md B4); the predicate stays, since a plan whose open boxes are all of that kind starts no writer.
"""

from __future__ import annotations

import pytest

from rediacc_hooks import plan_gate
from rediacc_hooks.tests.test_plan_gate import _xplan


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


def test_a_plan_of_live_only_boxes_starts_no_writer():
    """The 2026-11-09 shape: ticked code boxes, every open one live, operator, fleet or post-merge. The control is the same plan with one untagged code box, which a writer can start."""
    live_only = _xplan(opened=0, done=3) + (
        "- [ ] V1 [live] deploy the bench signer and prove the binding\n"
        "- [ ] H1 [operator window] after release, converge one machine\n"
        "- [ ] L8 [ops, post-merge] telemetry acceptance\n"
        "- [ ] X2 [hostinger rollout] machine setup with the released renet\n"
        "- [ ] SC13b evidence from a real run. Depends on: SC13a and this PR's merge\n"
    )
    assert plan_gate.writer_startable(live_only) is False
    assert plan_gate.writer_startable(live_only + "- [ ] C9 a code box a writer can do\n") is True
