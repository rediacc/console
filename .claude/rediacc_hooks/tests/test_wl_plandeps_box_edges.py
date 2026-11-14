"""Per-box Depends-on in wl_plandeps (agent/plans/PLAN-idle-writer-capacity.md I4, D3; operator ruling R4 of 2026-11-09).

A box with its own `Depends on:` line is judged by that line, strictly; a box that states none is judged by its plan's `Depends-On:` edges, which a caller may clear with a predicate. `item_deps` lets a linked item through when its box states a line and every ref resolves, and keeps its plan-level verdict otherwise.
"""

from __future__ import annotations

import importlib

import pytest

from rediacc_hooks import plan_gate, syspath

syspath.on_sys_path(plan_gate.STOP_DIR)
D = importlib.import_module("wl_plandeps")
R = importlib.import_module("wl_planrec")

ALONE = "no-dep -- stands alone in this fixture"


def _plan(boxes, depends=ALONE, name="x"):
    return (
        "# PLAN-%s\nStatus: approved\nOwner: d778be9d\nDepends-On: %s\nPriority: P2 -- seed\n"
        "Concurrency: parallel\nOwns: docs/%s/**\n\n## Boxes\n%s" % (name, depends, name, boxes)
    )


TICKED = "    (ticked) 2026-11-09T08:00:00Z by d778be9d: commit:abc1234567 the evidence line\n"


def _graph(texts):
    return D.Graph.from_texts({"agent/plans/%s" % k: v for k, v in texts.items()})


def _block(text, box_id):
    """The block text of the box whose id is `box_id`, through the module's own reader."""
    for box in D.plan_boxes(text):
        if box.id == box_id:
            return D.box_block(text, box.line)
    raise AssertionError("no box %s" % box_id)


@pytest.mark.parametrize(
    ("block", "want"),
    [
        ("S3 the client. Depends on: S2.", ("S2",)),
        (
            "S3 the client.\n  Depends on: S2, PLAN-y.md#T3 and PLAN-z.md.",
            ("S2", "PLAN-y.md#T3", "PLAN-z.md"),
        ),
        ("SC10 the sweep. Depends on: SC5-SC8", ("SC5", "SC6", "SC7", "SC8")),
        ("PF9 lands. Depends on: PF3; lands after PF8", ("PF3",)),
        ("PF2 the map. Depends on: PF1 (JSON contract)", ("PF1",)),
        ("SC13b real run. Depends on: SC13a and this PR's merge", ("SC13a",)),
        ("T2 standalone. Depends on: none", ()),
        ("T2 standalone, no line at all", None),
        # The header field spelling is not a box line.
        ("Depends-On: PLAN-y.md", None),
    ],
)
def test_box_depends_reads_the_clause(block, want):
    assert D.box_depends(block) == want


def test_box_block_takes_the_continuation_lines_and_stops_at_the_next_box():
    text = _plan(
        "- [ ] S3 [writer] the client\n  Owns: a.py\n  Depends on: S2.\n- [ ] S4 [writer] next\n"
    )
    block = _block(text, "S3")
    assert "Owns: a.py" in block
    assert "Depends on: S2" in block
    assert "S4" not in block


def test_an_own_line_is_judged_alone_and_strictly():
    """S3 states `Depends on: S2`; the plan-level edge to PLAN-y (open) does not hold it once S2 is ticked with evidence."""
    x_open = _plan(
        "- [ ] S2 [writer] the signer\n- [ ] S3 [writer] the client. Depends on: S2.\n",
        depends="PLAN-y.md",
    )
    x_done = _plan(
        "- [x] S2 [writer] the signer\n"
        + TICKED
        + "- [ ] S3 [writer] the client. Depends on: S2.\n",
        depends="PLAN-y.md",
    )
    y = _plan("- [ ] Y1 [writer] still open\n", name="y")
    g = _graph({"PLAN-x.md": x_open, "PLAN-y.md": y})
    assert [t for t, _d in g.box_blockers("agent/plans/PLAN-x.md", _block(x_open, "S3"))] == ["S2"]
    g2 = _graph({"PLAN-x.md": x_done, "PLAN-y.md": y})
    assert g2.box_blockers("agent/plans/PLAN-x.md", _block(x_done, "S3")) == []
    # CONTROL: a box with no own line is held by the open plan-level edge.
    assert [t for t, _d in g2.box_blockers("agent/plans/PLAN-x.md", "S9 [writer] no line")] == [
        "PLAN-y.md"
    ]


def test_a_box_ticked_without_evidence_still_holds_and_an_unknown_id_holds():
    x = _plan("- [x] S2 the signer\n- [ ] S3 the client. Depends on: S2, Q7.\n")
    g = _graph({"PLAN-x.md": x})
    got = dict(g.box_blockers("agent/plans/PLAN-x.md", _block(x, "S3")))
    assert set(got) == {"S2", "Q7"}


def test_own_line_tokens_to_other_plans():
    y = _plan("- [x] T3 done\n" + TICKED + "- [ ] T4 open\n", name="y")
    x = _plan(
        "- [ ] A1 a. Depends on: PLAN-y.md#T3.\n- [ ] A2 b. Depends on: PLAN-y.md#T4.\n- [ ] A3 c. Depends on: PLAN-y.md.\n"
    )
    g = _graph({"PLAN-x.md": x, "PLAN-y.md": y})
    rel = "agent/plans/PLAN-x.md"
    assert g.box_blockers(rel, _block(x, "A1")) == []
    assert [t for t, _d in g.box_blockers(rel, _block(x, "A2"))] == ["PLAN-y.md#T4"]
    # A plan token on an own line is strict: the predicate never clears it.
    assert [t for t, _d in g.box_blockers(rel, _block(x, "A3"), clear=lambda *_a: True)] == [
        "PLAN-y.md"
    ]


def test_the_clear_predicate_applies_to_plan_level_edges_only():
    y = _plan("- [ ] Y1 [live] deploy\n", name="y")
    x = _plan("- [ ] S2 [writer] the signer\n", depends="PLAN-y.md, PLAN-z.md")
    z = _plan("- [x] Z1 done\n" + TICKED, name="z").replace("Status: approved", "Status: done")
    g = _graph({"PLAN-x.md": x, "PLAN-y.md": y, "PLAN-z.md": z})
    rel = "agent/plans/PLAN-x.md"
    seen = []

    def clear(_target, edge):
        seen.append(str(edge))
        return True

    assert [t for t, _d in g.box_blockers(rel, _block(x, "S2"))] == ["PLAN-y.md"]
    assert g.box_blockers(rel, _block(x, "S2"), clear=clear) == []
    # The finished plan is never offered to the predicate.
    assert seen == ["PLAN-y.md"]


def test_item_deps_honours_a_resolved_own_line(tmp_path):
    """A linked item whose box states a resolved line is free although its plan-level edge is open; one whose box states none keeps the plan-level verdict."""
    folder = tmp_path / "agent" / "plans"
    folder.mkdir(parents=True)
    x = _plan(
        "- [x] S2 the signer\n"
        + TICKED
        + "- [ ] S3 the client. Depends on: S2.\n- [ ] S4 no line here\n",
        depends="PLAN-y.md",
    )
    (folder / "PLAN-x.md").write_text(x, encoding="utf-8")
    (folder / "PLAN-y.md").write_text(_plan("- [ ] Y1 open\n", name="y"), encoding="utf-8")
    g = D.Graph.load(tmp_path)
    sig3 = next(b.sig for b in D.plan_boxes(x) if b.id == "S3")
    sig4 = next(b.sig for b in D.plan_boxes(x) if b.id == "S4")
    assert D.item_deps(g, "do PLAN-x.md [%s] now" % sig3, []) is None
    held = D.item_deps(g, "do PLAN-x.md [%s] now" % sig4, [])
    assert held is not None
    assert held.roots == ("PLAN-y.md",)
    # CONTROL: an own line with an open ref keeps the plan-level verdict, unchanged.
    x2 = x.replace("- [x] S2 the signer\n" + TICKED, "- [ ] S2 the signer\n")
    (folder / "PLAN-x.md").write_text(x2, encoding="utf-8")
    g2 = D.Graph.load(tmp_path)
    sig3b = next(b.sig for b in D.plan_boxes(x2) if b.id == "S3")
    held2 = D.item_deps(g2, "do PLAN-x.md [%s] now" % sig3b, [])
    assert held2 is not None
    assert held2.roots == ("PLAN-y.md",)


def test_item_deps_frees_a_writer_box_whose_prerequisite_holds_only_live_work(tmp_path):
    """Ruling KEEP: a `[writer]` box of a plan whose prerequisite has only live boxes left is free for --lease and --plan-tick, the verdict IDLE CAPACITY reads; an untagged box of the same plan, and a writer box whose prerequisite still holds writer work, stay held."""
    folder = tmp_path / "agent" / "plans"
    folder.mkdir(parents=True)
    x = _plan("- [ ] S3 [writer] the client\n- [ ] S5 untagged\n", depends="PLAN-y.md")
    (folder / "PLAN-x.md").write_text(x, encoding="utf-8")
    (folder / "PLAN-y.md").write_text(_plan("- [ ] Y1 [live] deploy\n", name="y"), encoding="utf-8")
    g = D.Graph.load(tmp_path)
    sig3 = next(b.sig for b in D.plan_boxes(x) if b.id == "S3")
    sig5 = next(b.sig for b in D.plan_boxes(x) if b.id == "S5")
    assert g.writer_box_free("agent/plans/PLAN-x.md", sig3) is True
    assert D.item_deps(g, "do PLAN-x.md [%s] now" % sig3, []) is None
    # CONTROL: an untagged box keeps the plan-level verdict.
    held = D.item_deps(g, "do PLAN-x.md [%s] now" % sig5, [])
    assert held is not None
    assert held.roots == ("PLAN-y.md",)
    # CONTROL: a prerequisite that still holds writer work holds the writer box.
    (folder / "PLAN-y.md").write_text(
        _plan("- [ ] Y1 [live] deploy\n- [ ] Y2 [writer] code\n", name="y"), encoding="utf-8"
    )
    g2 = D.Graph.load(tmp_path)
    assert g2.writer_box_free("agent/plans/PLAN-x.md", sig3) is False
    assert D.item_deps(g2, "do PLAN-x.md [%s] now" % sig3, []) is not None


def test_writer_box_free_is_false_without_a_root():
    x = _plan("- [ ] S3 [writer] the client\n", depends="PLAN-y.md")
    g = _graph({"PLAN-x.md": x, "PLAN-y.md": _plan("- [ ] Y1 [live] deploy\n", name="y")})
    sig3 = next(b.sig for b in D.plan_boxes(x) if b.id == "S3")
    assert g.writer_box_free("agent/plans/PLAN-x.md", sig3) is False
