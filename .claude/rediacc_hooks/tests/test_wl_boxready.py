"""The ready `[writer]` boxes and the IDLE CAPACITY block (agent/plans/PLAN-idle-writer-capacity.md I2, I3; operator rulings R1-R4 of 2026-11-09).

On 2026-11-09 17 of 25 writer slots sat free for hours while PLAN-enterprise-isolation.md had `[writer]` boxes a writer could take, and no check said so. `wl_boxready.ready_boxes` lists those boxes, and `idle_capacity_text` is the block the Stop hook raises when free slots and ready boxes meet.
"""

from __future__ import annotations

import ast
import importlib
import json
import pathlib

import pytest

from rediacc_hooks import plan_gate, syspath
from rediacc_hooks.tests.test_plan_gate import _t, _turbo_root

syspath.on_sys_path(plan_gate.STOP_DIR)
B = importlib.import_module("wl_boxready")
D = importlib.import_module("wl_plandeps")
E = importlib.import_module("wl_effort")

FIVE = "```stop-hook\neffort: high\nturbo: on\nbatch_size: 3\nplan_concurrency: 5\n```\n"
TICKED = "    (ticked) 2026-11-09T08:00:00Z by d778be9d: commit:abc1234567 the evidence line\n"


def _plan(boxes, depends="no-dep -- stands alone in this fixture", owns="docs/{name}/**", extra=""):
    return (
        "# PLAN\nStatus: approved\nOwner: d778be9d\nDepends-On: %s\nPriority: P2 -- seed\n"
        "Concurrency: parallel\nOwns: %s\n%s\n## Boxes\n%s" % (depends, owns, extra, boxes)
    )


LIVE_ONLY = _plan(
    "- [x] C1 [writer] the code landed\n" + TICKED + "- [ ] V1 [live] deploy and prove it\n"
    "- [ ] H1 [operator window] after release\n- [ ] L8 [ops, post-merge] acceptance\n"
)

ENT = _plan(
    "- [ ] S2 [writer] signer service and Worker\n"
    "  Owns: docs/ent/signer/**, docs/ent/signer_test.py (new).\n"
    "- [ ] S3 [writer] the signer client\n  Owns: docs/ent/client.py\n  Depends on: S2.\n"
    "- [ ] C9 an untagged code box\n"
    "- [ ] G9 [writer, post-merge] after the merge\n"
    "- [ ] V1 [live] bench proof\n"
    "- [ ] K2 [writer] ring runner\n  Owns: docs/ent/rings.py\n"
)


def _root(tmp_path, plans, promoted):
    return _turbo_root(tmp_path, plans, promoted, FIVE)


def _ids(ready):
    return [(pathlib.Path(b.rel).name, b.id) for b in ready]


def _sig(text, box_id):
    return next(b.sig for b in D.plan_boxes(text) if b.id == box_id)


def test_tag_grammar():
    assert B.writer_tagged("S2 [writer] signer") is True
    assert B.writer_tagged("S2 [writer, opus] signer") is True
    assert B.writer_tagged("C9 an untagged code box") is False
    assert B.writer_tagged("V1 [live] proof") is False
    assert B.non_writer("V1 [live] proof") is True
    assert B.non_writer("H1 [hostinger rollout] setup") is True
    assert B.non_writer("S2 [writer] x") is False
    assert B.non_writer("C9 an untagged code box") is False
    assert B.post_merge("G9 [writer, post-merge] x") is True
    assert B.post_merge("SC13b run. Depends on: SC13a and this PR's merge") is True
    assert B.post_merge("S2 [writer] x") is False


def test_the_2026_11_09_shape_names_the_ready_writer_boxes(tmp_path):
    """Five in-set plans with live-only boxes and a Promoted plan with ready `[writer]` boxes: S2 and K2 are named; S3 waits on S2, C9 is untagged (R3), G9 is post-merge and V1 is live."""
    plans = dict.fromkeys(("p1", "p2", "p3", "p4", "p5"), LIVE_ONLY)
    plans["ent"] = ENT
    root = _root(tmp_path, plans, ["p1", "p2", "p3", "p4", "p5", "ent"])
    ready, skipped = B.ready_boxes(root)
    assert _ids(ready) == [("PLAN-ent.md", "S2"), ("PLAN-ent.md", "K2")]
    why = {s.id: s.why for s in skipped}
    assert "S2" in why["S3"]
    assert "post-merge" in why["G9"]
    assert ready[0].sig == _sig(ENT.replace("{name}", "ent"), "S2")
    assert ready[0].owns == ("docs/ent/signer/**", "docs/ent/signer_test.py")


def test_a_ticked_prerequisite_box_frees_its_dependent(tmp_path):
    done = ENT.replace(
        "- [ ] S2 [writer] signer service and Worker\n",
        "- [x] S2 [writer] signer service and Worker\n" + TICKED,
    )
    root = _root(tmp_path, {"ent": done}, ["ent"])
    assert _ids(B.ready_boxes(root)[0]) == [("PLAN-ent.md", "S3"), ("PLAN-ent.md", "K2")]


def test_held_plans_and_writers_none_are_skipped(tmp_path):
    held = ENT.replace("Status: approved", "Status: held")
    none = ENT.replace("Owner: d778be9d\n", "Owner: d778be9d\nWriters: none -- sibling repos\n")
    root = _root(tmp_path, {"h": held, "n": none, "ent": ENT}, ["h", "n", "ent"])
    assert {pathlib.Path(b.rel).name for b in B.ready_boxes(root)[0]} == {"PLAN-ent.md"}


def test_a_box_a_worklist_item_tracks_is_not_named(tmp_path):
    root = _root(tmp_path, {"ent": ENT}, ["ent"])
    text = ENT.replace("{name}", "ent")
    items = [
        {
            "id": "aa11bb22",
            "state": ">",
            "worker": "a1",
            "owner": "d778be9d",
            "text": "PLAN-ent S2 %s writer (lease); land, rerun accept" % _sig(text, "S2"),
        },
    ]
    ready, skipped = B.ready_boxes(root, items=items)
    assert _ids(ready) == [("PLAN-ent.md", "K2")]
    assert any(s.id == "S2" and "#aa11bb22" in s.why for s in skipped)
    # A box id with the plan name tracks it too, and a ticked item tracks nothing.
    by_id = [{"id": "cc", "state": " ", "owner": "x", "text": "PLAN-ent K2 ring runner"}]
    assert _ids(B.ready_boxes(root, items=by_id)[0]) == [("PLAN-ent.md", "S2")]
    closed = [{"id": "cc", "state": "x", "owner": "x", "text": "PLAN-ent K2 ring runner"}]
    assert len(B.ready_boxes(root, items=closed)[0]) == 2


def test_owns_overlap_with_work_in_flight_and_between_picks(tmp_path):
    clash = _plan(
        "- [ ] A1 [writer] first\n  Owns: docs/shared/x.py\n"
        "- [ ] A2 [writer] second\n  Owns: docs/shared/**\n"
        "- [ ] A3 [writer] third\n  Owns: docs/other.py\n"
    )
    root = _root(
        tmp_path, {"c": clash, "w": _plan("- [ ] W1 [writer] x\n", owns="docs/other.py")}, ["c"]
    )
    # Two ready boxes never claim one file: A2 overlaps A1, which came first.
    ready, skipped = B.ready_boxes(root)
    assert _ids(ready) == [("PLAN-c.md", "A1"), ("PLAN-c.md", "A3")]
    assert any(s.id == "A2" and "overlap" in s.why for s in skipped)
    # A live writer serving PLAN-w holds its header Owns, so A3 waits.
    assert _ids(B.ready_boxes(root, live_plans=("PLAN-w.md",))[0]) == [("PLAN-c.md", "A1")]
    # A leased box of the same plan holds its own Owns: A1 in flight holds A2 as well.
    items = [
        {
            "id": "dd",
            "state": ">",
            "worker": "a2",
            "owner": "x",
            "text": "PLAN-c A1 %s writer" % _sig(clash, "A1"),
        }
    ]
    assert _ids(B.ready_boxes(root, items=items)[0]) == [("PLAN-c.md", "A3")]


def test_a_live_only_prerequisite_does_not_hold_writer_boxes(tmp_path):
    """The enterprise case: its header waits on a plan whose open boxes are all `[live]` and on a task edge to a `[live]` box. A writer box builds on the prerequisite's code, which has landed."""
    dep = _plan(
        "- [x] R1 [writer] the rename code\n"
        + TICKED
        + "- [ ] L6 [live] deploy us\n- [ ] M1 [live, post-merge] merge\n"
    )
    web = _plan(
        "- [x] W1 [writer] lookup\n"
        + TICKED
        + "- [ ] M3 [live] one real mail\n- [ ] W9 still code\n"
    )
    ent = ENT.replace(
        "Depends-On: no-dep -- stands alone in this fixture",
        "Depends-On: PLAN-dep.md, PLAN-web.md#M3",
    )
    root = _root(tmp_path, {"dep": dep, "web": web, "ent": ent}, ["ent"])
    assert _ids(B.ready_boxes(root)[0]) == [("PLAN-ent.md", "S2"), ("PLAN-ent.md", "K2")]
    # CONTROL: an untagged open box in the prerequisite holds every writer box that states no line.
    dep2 = dep + "- [ ] R2 more rename code\n"
    root2 = _root(tmp_path / "two", {"dep": dep2, "web": web, "ent": ent}, ["ent"])
    ready2, skipped2 = B.ready_boxes(root2)
    assert ready2 == []
    assert any(s.id == "S2" and "PLAN-dep.md" in s.why for s in skipped2)
    # CONTROL: a task edge to an open code box holds too.
    ent3 = ent.replace("PLAN-web.md#M3", "PLAN-web.md#W9")
    root3 = _root(tmp_path / "three", {"dep": dep, "web": web, "ent": ent3}, ["ent"])
    assert B.ready_boxes(root3)[0] == []


def test_turbo_off_reads_the_given_plan_set_only(tmp_path):
    root = _root(tmp_path, {"ent": ENT, "b": _plan("- [ ] B1 [writer] b\n")}, ["ent", "b"])
    got = B.ready_boxes(root, plans=(_t("b"),))[0]
    assert _ids(got) == [("PLAN-b.md", "B1")]


# ---------------------------------------------------------------- the block


def _text(root, **kw):
    args = {
        "free": 3,
        "cap": 25,
        "phase": False,
        "turbo_picks": (),
        "plans": None,
        "live_plans": (),
        "items": (),
        "me8": "d778be9d",
    }
    args.update(kw)
    return B.idle_capacity_text(root, **args)


def test_the_block_names_boxes_and_the_spawn_command(tmp_path):
    root = _root(tmp_path, {"ent": ENT}, ["ent"])
    text = _text(root)
    sig = _sig(ENT.replace("{name}", "ent"), "S2")
    assert text.startswith("IDLE CAPACITY")
    assert "PLAN-ent.md#%s" % sig in text
    assert "/writers-now PLAN-ent.md" in text
    assert "3 free writer slot(s) of 25" in text
    assert "2 ready" in text


@pytest.mark.parametrize(
    "kw",
    [{"free": 0}, {"free": -2}, {"phase": True}, {"free": 1, "turbo_picks": ("PLAN-x.md",)}],
)
def test_the_block_stands_down(tmp_path, kw):
    root = _root(tmp_path, {"ent": ENT}, ["ent"])
    assert _text(root, **kw) == ""


def test_the_block_is_silent_with_no_ready_box(tmp_path):
    root = _root(tmp_path, {"l": LIVE_ONLY}, ["l"])
    assert _text(root) == ""


def test_a_turbo_pick_takes_its_slot_and_its_boxes_but_never_silences_the_rest(tmp_path):
    """The real run of 2026-11-09 after the ceiling fix: TURBO NEXT named one plan while 21 slots were free. The picked plan's boxes leave the list and its slot is spent; the other ready boxes are still named."""
    other = _plan("- [ ] B1 [writer] b_one with an underscore\n")
    root = _root(tmp_path, {"ent": ENT, "b": other}, ["ent", "b"])
    text = _text(root, free=21, turbo_picks=(_t("ent"),))
    assert "20 free writer slot(s)" in text
    assert "PLAN-ent.md#" not in text
    assert "/writers-now PLAN-b.md" in text
    # The row is the raw box line: an underscore survives (the parsed body strips it).
    assert "B1 [writer] b_one with an underscore" in text


def test_the_effort_table_owns_the_key_and_the_hook_produces_it():
    blocking, _advisory = E.produced_keys()
    assert "idle-capacity" in blocking
    table = json.loads(pathlib.Path(E.TABLE_PATH).read_text(encoding="utf-8"))
    assert table["checks"]["idle-capacity"] == {"block": "smart", "advise": "low"}
    assert E.table_problems(table, *E.produced_keys()) == []


def test_the_pr_loop_profile_keeps_the_key():
    tree = ast.parse((plan_gate.STOP_DIR / "wl_checks.py").read_text(encoding="utf-8"))
    keeps = next(
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Assign)
        and any(getattr(t, "id", "") == "TURBO_KEEPS" for t in n.targets)
    )
    assert "idle-capacity" in ast.unparse(keeps)
