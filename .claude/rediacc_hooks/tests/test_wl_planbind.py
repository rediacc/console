"""Red-first controls for `wl_planbind.bindings` (agent/plans/PLAN-plan-compaction-bindings.md, box CB1).

Every refusal has a passing twin built from the same fixture with one fact changed, so a function that binds everything cannot pass the refusals and one that binds nothing cannot pass the controls.
"""

from __future__ import annotations

import importlib
import json
import pathlib
import subprocess
import sys

import pytest

STOP = pathlib.Path(__file__).resolve().parents[2] / "hooks" / "stop"
if str(STOP) not in sys.path:
    sys.path.insert(0, str(STOP))

B = importlib.import_module("wl_planbind")
R = importlib.import_module("wl_planrec")

TARGET = "agent/plans/PLAN-x.md"
OTHER = "agent/plans/PLAN-y.md"
ALONE = "no-dep -- stands alone in this fixture"


def plan(
    status="approved", boxes=("[x] T1 finished work",), depends=ALONE, extra="", name="PLAN-x"
):
    lines = [
        "# %s: fixture" % name,
        "",
        "Status: %s" % status,
        "Owner: abc12345",
        "Depends-On: %s" % depends,
        "",
        extra,
        "## Tasks",
        "",
    ]
    lines += ["- %s" % b for b in boxes]
    return "\n".join(lines) + "\n"


def other_plan(**kw):
    return plan(name="PLAN-y", **kw)


def sig_of(text, n=0):
    return R.open_boxes(text)[n][3]


def item(iid, state, text):
    return {"id": iid, "state": state, "text": text}


def kinds(found):
    return sorted(b.kind for b in found)


def run(texts, items=(), tmp=None):
    return B.bindings(
        tmp or "/nonexistent-root", TARGET, texts=texts, items=list(items), index_text=""
    )


def test_clean_plan_has_no_binding():
    assert run({TARGET: plan()}) == []


def test_missing_plan_has_no_binding():
    gone = "agent/plans/PLAN-gone.md"
    assert B.bindings("/nonexistent-root", gone, texts={}, items=[], index_text="") == []


@pytest.mark.parametrize("state", [" ", ">", "?"])
def test_open_item_citing_plan_binds(state):
    found = run({TARGET: plan()}, [item("aa11bb22", state, "finish PLAN-x.md first")])
    assert kinds(found) == ["item"]
    assert found[0].where == "#aa11bb22"


@pytest.mark.parametrize("state", ["x", "~"])
def test_closed_item_does_not_bind(state):
    assert run({TARGET: plan()}, [item("aa11bb22", state, "finish PLAN-x.md first")]) == []


def test_item_naming_a_longer_plan_name_does_not_bind():
    assert run({TARGET: plan()}, [item("aa11bb22", " ", "see PLAN-x.mdx and PLAN-xy.md")]) == []


def test_item_citing_box_sig_binds():
    text = plan(boxes=("[ ] T1 open work here",))
    found = run({TARGET: text}, [item("aa11bb22", " ", "worklist twin of box %s" % sig_of(text))])
    assert "item" in kinds(found)


def test_item_citing_a_shared_sig_under_another_plan_does_not_bind():
    """Identical box lines in two plans share a signature (every `LP-bench [live]` box); an item that names the other plan beside the signature is that plan's, not this one's (CB7 real run, PLAN-snapshot-read-io-cap.md)."""
    text = plan(boxes=("[ ] T1 open work here",))
    sig = sig_of(text)
    other_item = item("aa11bb22", " ", "PLAN-y.md proof: box %s" % sig)
    found = [b for b in run({TARGET: text}, [other_item]) if b.kind == "item"]
    assert found == []
    bare = item("ee55ff66", " ", "PLAN-y proof: box %s" % sig)
    assert [b for b in run({TARGET: text}, [bare]) if b.kind == "item"] == []
    # CONTROL: the same signature beside this plan's own name binds.
    own_item = item("cc33dd44", " ", "PLAN-x.md proof: box %s" % sig)
    assert "item" in kinds(run({TARGET: text}, [own_item]))


def test_item_citing_other_sig_does_not_bind():
    text = plan(boxes=("[x] T1 finished work",))
    assert run({TARGET: text}, [item("aa11bb22", " ", "unrelated deadbeef")]) == []


def test_unfinished_dependent_binds_finished_does_not():
    dep = other_plan(depends="PLAN-x.md")
    found = run({TARGET: plan(), OTHER: dep})
    assert kinds(found) == ["dependent"]
    assert found[0].where == OTHER
    done = other_plan(status="done", depends="PLAN-x.md")
    assert run({TARGET: plan(), OTHER: done}) == []


def test_open_box_elsewhere_citing_a_box_binds():
    text = plan(boxes=("[ ] T1 open work here",))
    sig = sig_of(text)
    for cite in (
        "after PLAN-x.md#T1 lands",
        "after PLAN-x.md [%s] lands" % sig,
        "after box %s lands" % sig,
    ):
        found = run({TARGET: text, OTHER: other_plan(boxes=("[ ] Q1 %s" % cite,))})
        assert "citing-box" in kinds(found), cite


def test_citing_box_controls():
    text = plan(boxes=("[x] T1 finished work",))
    # naming the plan with no box reference is not a citation of a box
    background = other_plan(boxes=("[ ] Q1 read PLAN-x.md for background",))
    assert run({TARGET: text, OTHER: background}) == []
    # a ticked citing box does not bind
    ticked = other_plan(boxes=("[x] Q1 after PLAN-x.md#T1 lands",))
    assert run({TARGET: text, OTHER: ticked}) == []
    # an open citing box in a finished plan does not bind
    finished = other_plan(status="done", boxes=("[ ] Q1 after PLAN-x.md#T1 lands",))
    assert run({TARGET: text, OTHER: finished}) == []


def test_own_open_box_binds_without_ruling():
    found = run({TARGET: plan(boxes=("[ ] T1 open work here",))})
    assert kinds(found) == ["box"]
    assert found[0].where.startswith(TARGET + ":")


def ruled(tmp_path):
    quote = "operator said fold it into the other plan"
    (tmp_path / "ruling.txt").write_text(quote + "\n", encoding="utf-8")
    return 'Ruling: "%s" in ruling.txt' % quote


def test_own_open_box_released_by_ruling_and_home_plan(tmp_path):
    base = plan(status="done", boxes=("[ ] T1 open work here",), extra=ruled(tmp_path))
    # control: the ruling resolves, but the box names no home
    found = run({TARGET: base, OTHER: other_plan()}, tmp=tmp_path)
    assert kinds(found) == ["box"]
    assert "no live home" in found[0].detail
    # re-homed to a live plan on the line beneath the box
    homed = base + "  moved to PLAN-y.md box Q1\n"
    assert run({TARGET: homed, OTHER: other_plan()}, tmp=tmp_path) == []
    # a home plan that is itself finished is no home
    assert kinds(run({TARGET: homed, OTHER: other_plan(status="done")}, tmp=tmp_path)) == ["box"]


def test_ruling_that_does_not_resolve_keeps_the_box_bound(tmp_path):
    (tmp_path / "ruling.txt").write_text("something else\n", encoding="utf-8")
    bad = 'Ruling: "quote that is in no file" in ruling.txt'
    homed = (
        plan(status="done", boxes=("[ ] T1 open work here",), extra=bad) + "  moved to PLAN-y.md\n"
    )
    assert kinds(run({TARGET: homed, OTHER: other_plan()}, tmp=tmp_path)) == ["box"]


def test_box_rehomed_to_open_item_bound_to_live_plan(tmp_path):
    texts = {
        TARGET: plan(
            status="done", boxes=("[ ] T1 open work here #cc33dd44",), extra=ruled(tmp_path)
        ),
        OTHER: other_plan(),
    }
    assert run(texts, [item("cc33dd44", " ", "carry the work under PLAN-y.md")], tmp_path) == []
    assert kinds(run(texts, [item("cc33dd44", " ", "carry it somewhere vague")], tmp_path)) == [
        "box"
    ]
    assert kinds(
        run(texts, [item("cc33dd44", "x", "carry the work under PLAN-y.md")], tmp_path)
    ) == ["box"]


def test_box_dropped_by_a_closed_ruling_item_is_released(tmp_path):
    """A box the operator dropped names the closed ruling item on a line under it (CB5)."""
    base = plan(status="done", boxes=("[ ] T1 open work here",), extra=ruled(tmp_path))
    dropped = base + "  dropped by ruling #aa11bb22: the operator took neither option\n"
    texts = {TARGET: dropped}
    assert run(texts, [item("aa11bb22", "x", "operator ruling: drop T1")], tmp_path) == []


def test_dropped_line_controls_keep_the_box_bound(tmp_path):
    base = plan(status="done", boxes=("[ ] T1 open work here",), extra=ruled(tmp_path))
    dropped = base + "  dropped by ruling #aa11bb22\n"
    # the ruling item is still open: a question, not a decision
    assert kinds(run({TARGET: dropped}, [item("aa11bb22", " ", "drop T1?")], tmp_path)) == ["box"]
    # the ruling item is deferred
    assert kinds(run({TARGET: dropped}, [item("aa11bb22", "?", "drop T1?")], tmp_path)) == ["box"]
    # the ruling item was tombstoned, not closed
    assert kinds(run({TARGET: dropped}, [item("aa11bb22", "~", "drop T1")], tmp_path)) == ["box"]
    # the ruling item does not exist
    assert kinds(run({TARGET: dropped}, [], tmp_path)) == ["box"]
    # the line names an item but not as a drop
    noted = base + "  see #aa11bb22\n"
    assert kinds(run({TARGET: noted}, [item("aa11bb22", "x", "drop T1")], tmp_path)) == ["box"]
    # the drop sits on the box line itself, not under it
    inline = plan(
        status="done",
        boxes=("[ ] T1 open work here, dropped by ruling #aa11bb22",),
        extra=ruled(tmp_path),
    )
    assert kinds(run({TARGET: inline}, [item("aa11bb22", "x", "drop T1")], tmp_path)) == ["box"]


def test_dropped_line_without_a_resolving_ruling_keeps_the_box_bound(tmp_path):
    dropped = (
        plan(status="done", boxes=("[ ] T1 open work here",)) + "  dropped by ruling #aa11bb22\n"
    )
    assert kinds(run({TARGET: dropped}, [item("aa11bb22", "x", "drop T1")], tmp_path)) == ["box"]


def test_render_lists_every_binding_and_the_next_commands():
    text = plan(boxes=("[ ] T1 open work here",))
    found = run({TARGET: text}, [item("aa11bb22", " ", "finish PLAN-x.md")])
    out = B.render(TARGET, found)
    for needle in ("#aa11bb22", "open box", "--tick", "--plan-revive"):
        assert needle in out
    assert B.render(TARGET, []) == ""


def test_store_items_reads_the_fold_and_drops_tombstones(tmp_path):
    store = tmp_path / "agent" / "worklist"
    store.mkdir(parents=True)
    rows = [
        {
            "ev": "add",
            "id": "aa11bb22",
            "at": "2026-11-01T00:00:00Z",
            "by": "s1",
            "text": "hold PLAN-x.md",
            "ns": 1,
        },
        {
            "ev": "add",
            "id": "bb22cc33",
            "at": "2026-11-01T00:00:01Z",
            "by": "s2",
            "text": "hold PLAN-x.md",
            "ns": 2,
        },
        {
            "ev": "tomb",
            "id": "bb22cc33",
            "at": "2026-11-01T00:00:02Z",
            "by": "s2",
            "why": "gone",
            "ns": 3,
        },
    ]
    (store / "s1.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    ids = {r["id"] for r in B.store_items(tmp_path)}
    assert "aa11bb22" in ids
    assert "bb22cc33" not in ids


# --------------------------------------------------------------------------- CB2: wl_planrec.compact asks bindings first.


def _sh(root, *args):
    subprocess.run(args, cwd=root, check=True, capture_output=True)


def _compact_tree(tmp_path, item_state):
    """A committed repo holding one plan with a finished box and one worklist item citing it in `item_state`."""
    plans = tmp_path / "agent" / "plans"
    plans.mkdir(parents=True)
    # Padded past the record-size floor (`BLOB_RATIO`), so the control can actually compact.
    body = plan(status="done", extra="Why this plan exists. " * 400)
    (plans / "PLAN-x.md").write_text(body, encoding="utf-8")
    store = tmp_path / "agent" / "worklist"
    store.mkdir()
    row = {"id": "aa11bb22", "by": "s1", "ev": "add", "at": "2026-11-01T00:00:00Z", "ns": 1}
    rows = [dict(row, s=item_state, o="s1", t="finish PLAN-x.md")]
    (store / "s1.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    ident = ("-c", "user.name=t", "-c", "user.email=t@t")
    _sh(tmp_path, "git", "init", "-q")
    _sh(tmp_path, "git", "add", "-A")
    _sh(tmp_path, "git", *ident, "commit", "-qm", "fixture")
    return tmp_path


@pytest.mark.parametrize("park", [False, True])
def test_compact_refuses_while_an_open_item_cites_the_plan(tmp_path, park):
    root = _compact_tree(tmp_path, " ")
    with pytest.raises(R.BoundError) as exc:
        R.compact(root, TARGET, "deadbeef", why="auto", park=park)
    assert "#aa11bb22" in str(exc.value)
    assert "--plan-revive" in str(exc.value)


def test_compact_proceeds_once_the_item_is_ticked(tmp_path):
    root = _compact_tree(tmp_path, "x")
    assert B.bindings(root, TARGET) == []
    text, _notes = R.compact(root, TARGET, "deadbeef", why="auto")
    assert R.parse(text) is not None


def test_bound_refusal_message_is_catalogued():
    msgs = importlib.import_module("worklist_messages")
    out = msgs.CLI_PLANREC_BOUND % ("bound text", "abc12345", TARGET)
    assert "bound text" in out
    assert "--plan-compact abc12345 " + TARGET in out


def test_a_reused_graph_gives_the_same_verdict_and_a_stale_one_is_refused():
    """Review 7aa999c1.1/.2: the gate builds one graph for every plan; the verdict equals the per-call build, and a graph over another plan set is refused rather than silently used."""
    texts = {TARGET: plan(boxes=("[ ] T1 open work here",)), OTHER: other_plan(depends="PLAN-x.md")}
    items = [item("aa11bb22", " ", "finish PLAN-x.md")]
    deps = importlib.import_module("wl_plandeps")
    graph = deps.Graph(texts, "", None)
    alone = B.bindings("/nonexistent", TARGET, texts=texts, items=items, index_text="")
    shared = B.bindings(
        "/nonexistent", TARGET, texts=texts, items=items, index_text="", graph=graph
    )
    assert alone == shared
    assert alone
    stale = deps.Graph({TARGET: texts[TARGET]}, "", None)
    with pytest.raises(ValueError, match="different plan set"):
        B.bindings("/nonexistent", TARGET, texts=texts, items=items, index_text="", graph=stale)


def test_the_open_box_memo_returns_the_parser_result():
    text = plan(boxes=("[ ] T1 open work here", "[x] T2 done"))
    assert list(B._open_boxes(text)) == list(R.open_boxes(text))


def test_a_signature_shared_with_another_plan_does_not_bind_an_item_naming_no_plan():
    """CB5: #658c04e3 cited 7692f2db, the LP-hostinger signature 12 plans share, named no plan, and bound one of them at random."""
    box = "[ ] T1 open work here"
    texts = {TARGET: plan(boxes=(box,)), OTHER: other_plan(boxes=(box,))}
    sig = sig_of(texts[TARGET])
    found = [
        b for b in run(texts, [item("aa11bb22", " ", "proof: box %s" % sig)]) if b.kind == "item"
    ]
    assert found == []
    # CONTROL: a signature this plan alone carries still binds an item naming no plan.
    alone = {TARGET: plan(boxes=(box,))}
    assert "item" in kinds(run(alone, [item("cc33dd44", " ", "proof: box %s" % sig)]))


def test_a_plan_named_without_its_md_binds():
    """CB5: "PLAN-ci-prebaked-vm-images B5" named the plan and was not seen."""
    found = run({TARGET: plan()}, [item("aa11bb22", " ", "finish PLAN-x B5 next")])
    assert "item" in kinds(found)
    assert run({TARGET: plan()}, [item("bb22cc33", " ", "see PLAN-xy B5")]) == []
