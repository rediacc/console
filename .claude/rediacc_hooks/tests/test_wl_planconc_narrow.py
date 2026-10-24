"""`wl_planconc.live_plans` records each live plan's declared writer Owns (#f412fdb8), so `spawn_verdict` can judge a live plan on the subset its writers declared.

The roster read and the transcript read are stubbed: the subject is how the prompts' `Owns:` lines fold into `LivePlans.owns`, and the narrowing decision itself is covered in .claude/hooks/stop/test-plandeps.py.
"""

from __future__ import annotations

import datetime
import types

from rediacc_hooks.tests import wlfix

X = wlfix.import_wl("wl_planconc")
ROSTER = wlfix.import_wl("wl_roster")
LH = wlfix.import_wl("wl_leasehelp")


def live(monkeypatch, prompts: dict[str, str]):
    rows = [{"id": wid, "writer": True, "desc": "", "type": "general-purpose"} for wid in prompts]
    metas = {wid: {"jsonl": wid} for wid in prompts}
    monkeypatch.setattr(ROSTER, "live_estimate", lambda *_a, **_k: (rows, metas))
    monkeypatch.setattr(LH, "first_prompt", lambda jsonl: prompts[jsonl])
    return X.live_plans("/nonexistent", "d778be9d-0000", types.SimpleNamespace(items=[]))


def test_every_holder_declaring_owns_narrows_the_plan_to_their_union(monkeypatch):
    got = live(
        monkeypatch,
        {
            "w1": "Plan: PLAN-t.md\nOwns: src/t/a.py",
            "w2": "Plan: PLAN-t.md\nOwns: src/t/b/**",
        },
    )
    assert dict(got) == {
        "PLAN-t.md": ["writer w1 (general-purpose)", "writer w2 (general-purpose)"]
    }
    assert got.owns == {"PLAN-t.md": ("src/t/a.py", "src/t/b/**")}


def test_one_holder_without_owns_keeps_the_whole_plan(monkeypatch):
    """CONTROL: the second writer declares nothing, so the plan is not narrowed."""
    got = live(
        monkeypatch,
        {"w1": "Plan: PLAN-t.md\nOwns: src/t/a.py", "w2": "Plan: PLAN-t.md"},
    )
    assert "PLAN-t.md" in got
    assert got.owns == {}


def test_a_plain_dict_live_map_narrows_nothing():
    """`spawn_verdict` reads `owns` with getattr, so every caller passing a plain dict keeps the whole-plan comparison."""
    xi = {
        "PLAN-p.md": X.PlanX("PLAN-p.md", owns=("src/proxy/**",)),
        "PLAN-t.md": X.PlanX("PLAN-t.md", owns=("src/t/**", "src/proxy/**")),
    }
    plain = {"PLAN-t.md": ["writer w1"]}
    assert X.spawn_verdict({"PLAN-p.md"}, plain, xi.__getitem__).kind == "overlap"
    narrowed = X.LivePlans(plain)
    narrowed.owns["PLAN-t.md"] = ("src/t/**",)
    assert X.spawn_verdict({"PLAN-p.md"}, narrowed, xi.__getitem__).allow


PO = wlfix.import_wl("wl_planorder")


def _roster_world():
    xi = {
        "PLAN-b.md": X.PlanX("PLAN-b.md", owns=("private/renet/**", ".ci/**")),
        "PLAN-d.md": X.PlanX("PLAN-d.md", owns=("private/renet/pkg/compose/validate.go",)),
    }
    serving = {"wb": {"PLAN-b.md"}, "wd": {"PLAN-d.md"}}
    live = {
        "PLAN-b.md": ["writer wb (backup-storage)"],
        "PLAN-d.md": ["writer wd (general-purpose)"],
    }
    return xi, serving, live


def test_the_roster_backstop_judges_writers_on_their_declared_owns():
    """The Stop-side backstop (`roster-concurrency`) must agree with the spawn guard: two writers whose declared Owns are disjoint are not a conflict even when their plans' whole Owns overlap. Before the fix it passed declared=None and a plain dict, and accused both writers."""
    xi, serving, live = _roster_world()
    declared = {
        "wb": ("private/renet/pkg/chunkstore/**",),
        "wd": ("private/renet/pkg/compose/validate.go",),
    }
    assert PO.conflicts(serving, live, xi.__getitem__, declared) == []


def test_the_roster_backstop_still_flags_overlapping_declared_owns():
    """CONTROL: declared subsets that share a file are still a conflict."""
    xi, serving, live = _roster_world()
    declared = {
        "wb": ("private/renet/pkg/compose/**",),
        "wd": ("private/renet/pkg/compose/validate.go",),
    }
    assert {aid for aid, _v in PO.conflicts(serving, live, xi.__getitem__, declared)} == {
        "wb",
        "wd",
    }


def test_the_roster_backstop_without_declarations_compares_whole_plans():
    """CONTROL: a writer that declared nothing keeps the whole-plan comparison."""
    xi, serving, live = _roster_world()
    assert {aid for aid, _v in PO.conflicts(serving, live, xi.__getitem__)} == {"wb", "wd"}


def test_a_lease_held_by_this_session_keeps_the_whole_plan(monkeypatch):
    """A fresh lease of this session on a plan-linked item is a holder with no readable prompt, so it must stop the narrowing exactly like a peer's lease. Before the fix only a peer's lease recorded `None`, and the writer's subset narrowed the plan under a live holder that declared nothing."""
    until = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=30)).strftime(
        "%Y-%m-%dT%H:%MZ"
    )
    rec = {
        "id": "abcd1234",
        "state": ">",
        "worker": "w1",
        "owner": None,
        "text": "fix it PLAN-t.md [abcd1234]",
        "line": "- [>] fix it PLAN-t.md [abcd1234] until:%s worker:w1" % until,
    }
    prompts = {"w1": "Plan: PLAN-t.md\nOwns: src/t/a.py"}
    rows = [{"id": "w1", "writer": True, "desc": "", "type": "general-purpose"}]
    monkeypatch.setattr(ROSTER, "live_estimate", lambda *_a, **_k: (rows, {"w1": {"jsonl": "w1"}}))
    monkeypatch.setattr(LH, "first_prompt", lambda jsonl: prompts[jsonl])
    got = X.live_plans("/nonexistent", "d778be9d-0000", types.SimpleNamespace(items=[rec]))
    assert any("lease #abcd1234" in h for h in got["PLAN-t.md"])
    assert got.owns == {}


def test_the_roster_backstop_keeps_the_whole_plan_when_one_holder_declares_nothing():
    """MIXED HOLDERS (483392a8.3): one writer of plan B declares Owns, another does not, so `all(owns)` is false and B keeps its whole-plan Owns, which overlaps D's file. CONTROL: with the undeclared holder gone, B narrows and there is no conflict."""
    xi, serving, live = _roster_world()
    serving = {**serving, "wx": {"PLAN-b.md"}}
    live = {**live, "PLAN-b.md": [*live["PLAN-b.md"], "writer wx (general-purpose)"]}
    declared = {
        "wb": ("private/renet/pkg/chunkstore/**",),
        "wd": ("private/renet/pkg/compose/validate.go",),
        "wx": None,
    }
    assert "wd" in {aid for aid, _v in PO.conflicts(serving, live, xi.__getitem__, declared)}
    del serving["wx"]
    live["PLAN-b.md"] = ["writer wb (backup-storage)"]
    assert PO.conflicts(serving, live, xi.__getitem__, declared) == []
