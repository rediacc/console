"""The live PR's scope: `wl_ci.pr_link` (box SC1) and `wl_prscope.loop_state` / `next_queued` (box SC2) of agent/plans/PLAN-stop-hook-one-plan-scope.md.

Every case runs against a temp git checkout with a planted agent/plans tree and QUEUE.md, and a fake `gh` on PATH that answers the one GraphQL read from a file, logs every call, and fails when a `down` marker exists. Each fire case has a control that differs by one planted fact.
"""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

import pytest

from rediacc_hooks.tests import wlfix

if TYPE_CHECKING:
    import pathlib

ME = wlfix.ME

GH_SHIM = """#!/bin/bash
echo "$*" >> "%(base)s/gh-calls.log"
if [ -e "%(base)s/down" ]; then echo "gh: planted outage" >&2; exit 1; fi
case "$*" in
    *'api graphql'*) cat "%(base)s/prlink.json"; exit 0 ;;
    *'pr list --head'*) cat "%(base)s/head-states.txt" 2>/dev/null; exit 0 ;;
    *'pr list'*) cat "%(base)s/heads.txt" 2>/dev/null; exit 0 ;;
esac
echo '{}'
"""

GIT_ENV = {
    "PATH": "/usr/bin:/bin",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t",
}


def _plan(opened=1, done=0, depends="", status="approved"):
    dep = depends or "no-dep -- a standalone plan in the scope fixture"
    boxes = "".join("- [x] D%d a ticked box sits here\n" % i for i in range(done))
    boxes += "".join("- [ ] O%d an open box sits here\n" % i for i in range(opened))
    return "# PLAN\nStatus: %s\nDepends-On: %s\nPriority: P2 -- seed\n\n## Boxes\n%s" % (
        status,
        dep,
        boxes,
    )


class World:
    """A checkout under `root`, the fake gh's files under `base`, the worklist mirror path, and the PATH that puts the shim first."""

    def __init__(self, tmp: pathlib.Path, monkeypatch):
        self.base = tmp / "gh"
        self.root = tmp / "repo"
        (self.base / "bin").mkdir(parents=True)
        (self.root / "agent" / "plans").mkdir(parents=True)
        shim = self.base / "bin" / "gh"
        shim.write_text(GH_SHIM % {"base": self.base}, encoding="utf-8")
        shim.chmod(0o755)
        monkeypatch.setenv("PATH", "%s:/usr/bin:/bin" % (self.base / "bin"))
        self.worklist = tmp / "wl" / "repo.md"
        self.worklist.parent.mkdir()
        self.git("init", "-q", "-b", "main")
        self.git("remote", "add", "origin", wlfix.FAKE_ORIGIN)
        (self.root / "README").write_text("r\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-qm", "base")
        self.nodes([])

    def git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.root), *args],
            check=True,
            capture_output=True,
            text=True,
            env=GIT_ENV,
        ).stdout.strip()

    def plans(self, **plans):
        for name, text in plans.items():
            (self.root / "agent" / "plans" / ("PLAN-%s.md" % name)).write_text(text, "utf-8")

    def queue(self, *names, generated=()):
        text = "# Plan queue\n\n## Promoted\n\n"
        text += "".join("%d. agent/plans/PLAN-%s.md\n" % (i + 1, n) for i, n in enumerate(names))
        if generated:
            text += "\n## Generated\n\n<!-- queue:generated:begin -->\n"
            text += "".join(
                "%d. agent/plans/PLAN-%s.md\n" % (i + 1, n) for i, n in enumerate(generated)
            )
            text += "<!-- queue:generated:end -->\n"
        (self.root / "agent" / "plans" / "QUEUE.md").write_text(text, encoding="utf-8")

    def nodes(self, nodes):
        body = {"data": {"repository": {"pullRequests": {"nodes": nodes}}}}
        (self.base / "prlink.json").write_text(json.dumps(body) + "\n", encoding="utf-8")
        for p in self.worklist.parent.glob("*.prlink-*"):
            p.unlink()

    def calls(self):
        log = self.base / "gh-calls.log"
        return log.read_text(encoding="utf-8").splitlines() if log.exists() else []

    def down(self):
        (self.base / "down").write_text("", encoding="utf-8")

    def branch(self, name):
        self.git("switch", "-q", "-c", name)


@pytest.fixture
def world(tmp_path, monkeypatch):
    return World(tmp_path, monkeypatch)


def rel(name):
    return "agent/plans/PLAN-%s.md" % name


def node(number, state, body="", at="2026-10-03T10:00:00Z"):
    return {
        "number": number,
        "state": state,
        "body": body,
        "mergedAt": at if state == "MERGED" else None,
        "closedAt": at if state != "OPEN" else None,
    }


# ---- SC1: one PR read ------------------------------------------------------------------


def test_pr_link_returns_open_and_merged_nodes_with_bodies(world):
    wl_ci = wlfix.import_wl("wl_ci")
    world.nodes([node(7, "OPEN", "Plan: a"), node(6, "MERGED", "Plan: b")])
    nodes, err = wl_ci.pr_link(world.root, world.worklist, ME, "1003-1")
    assert err == ""
    assert [(n["number"], n["state"], n["body"]) for n in nodes] == [
        (7, "OPEN", "Plan: a"),
        (6, "MERGED", "Plan: b"),
    ]
    calls = world.calls()
    assert len(calls) == 1, calls
    assert "states:[OPEN,MERGED,CLOSED]" in calls[0], calls
    assert 'headRefName:\\"1003-1\\"' in calls[0] or 'headRefName:"1003-1"' in calls[0], calls


def test_pr_link_cache_hit_makes_no_second_gh_call(world):
    wl_ci = wlfix.import_wl("wl_ci")
    world.nodes([node(7, "OPEN")])
    first = wl_ci.pr_link(world.root, world.worklist, ME, "1003-1")
    second = wl_ci.pr_link(world.root, world.worklist, ME, "1003-1")
    assert first == second, world.calls()
    assert len(world.calls()) == 1, world.calls()
    # Control: another branch is a different cache entry, so it reads.
    wl_ci.pr_link(world.root, world.worklist, ME, "1003-2")
    assert len(world.calls()) == 2, world.calls()


def test_pr_link_gh_failure_returns_the_error_and_no_nodes(world):
    wl_ci = wlfix.import_wl("wl_ci")
    world.down()
    nodes, err = wl_ci.pr_link(world.root, world.worklist, ME, "1003-1")
    assert nodes == [], (nodes, err)
    assert "planted outage" in err, (nodes, err)
    # A failure is not cached: the next read asks again.
    wl_ci.pr_link(world.root, world.worklist, ME, "1003-1")
    assert len(world.calls()) == 2, world.calls()


# ---- SC2: loop_state -------------------------------------------------------------------


def state(world, epics=None, today="1003"):
    prscope = wlfix.import_wl("wl_prscope")
    return prscope.loop_state(
        world.root,
        world.worklist,
        ME,
        today=today,
        epics=epics if epics is not None else (lambda _rel: set()),
    )


def test_a_live_pr_with_a_plan_line_gives_that_plan_and_its_epic_items(world):
    world.plans(a=_plan(), b=_plan())
    world.queue("b")
    world.branch("1003-1")
    world.nodes([node(592, "OPEN", "Plan: agent/plans/PLAN-a.md\n\nBody.")])
    epics = {rel("a"): {"i1", "i2"}, rel("b"): {"i9"}}
    got = state(world, epics=lambda r: epics.get(r, set()))
    assert got.kind == "live"
    assert got.pr == 592
    assert got.branch == "1003-1"
    assert got.plans == (rel("a"),)
    assert got.prereqs == ()
    assert got.epic_items == frozenset({"i1", "i2"})
    assert got.next_plan == rel("b")


def test_a_live_pr_without_a_plan_line_gives_the_queue_head(world):
    world.plans(a=_plan(), b=_plan())
    world.queue("b", generated=("a",))
    world.branch("1003-1")
    world.nodes([node(592, "OPEN", "No plan line yet.")])
    got = state(world)
    assert got.kind == "live"
    assert got.plans == (rel("b"),)
    assert got.queue_head == rel("b")
    assert got.next_plan == rel("a")


def test_an_operational_reason_body_scopes_to_both_plans(world):
    world.plans(a=_plan(), b=_plan(), c=_plan())
    world.queue("c")
    world.branch("1003-1")
    body = "Plan: agent/plans/PLAN-a.md, agent/plans/PLAN-b.md\nOperational-Reason: one PR"
    world.nodes([node(592, "OPEN", body)])
    got = state(world)
    assert got.plans == (rel("a"), rel("b"))
    assert got.next_plan == rel("c")


def test_a_merged_pr_gives_merged_and_the_first_entry_with_an_open_box(world):
    world.plans(a=_plan(opened=0, done=2), b=_plan(opened=0, done=1), c=_plan())
    world.queue("b", generated=("c",))
    world.branch("1003-1")
    world.nodes([node(592, "MERGED", "Plan: agent/plans/PLAN-a.md")])
    got = state(world)
    assert got.kind == "merged"
    assert got.pr == 592
    assert got.plans == ()
    assert got.next_plan == rel("c")


def test_a_finished_promoted_head_is_stale_and_skipped(world):
    world.plans(b=_plan(opened=0, done=1), c=_plan())
    world.queue("b", generated=("c",))
    world.branch("1003-1")
    world.nodes([node(592, "MERGED", "Plan: agent/plans/PLAN-b.md")])
    got = state(world)
    assert got.stale_promoted == rel("b")
    assert got.next_plan == rel("c")
    # Control: with an open box the head is neither stale nor skipped.
    world.plans(b=_plan(opened=1, done=1))
    got = state(world)
    assert got.stale_promoted == ""
    assert got.next_plan == rel("b")


def test_on_main_with_no_branch_gives_on_main_and_the_frozen_clock_name(world):
    world.plans(a=_plan())
    world.queue("a")
    (world.base / "heads.txt").write_text("0915-2\n0915-3\n0101-9\n", encoding="utf-8")
    got = state(world, today="0915")
    assert got.kind == "on-main"
    assert got.branch == "main"
    assert got.next_branch == "0915-4"
    assert got.next_plan == rel("a")


def test_a_non_loop_branch_is_off_loop(world):
    world.plans(a=_plan())
    world.queue("a")
    world.branch("feature-x")
    got = state(world)
    assert got.kind == "off-loop"
    assert got.plans == ()
    assert world.calls() == []


def test_gh_down_is_unreadable_and_falls_back_to_the_queue_head(world):
    world.plans(a=_plan())
    world.queue("a")
    world.branch("1003-1")
    world.down()
    got = state(world)
    assert got.kind == "unreadable"
    assert "planted outage" in got.reason
    assert got.plans == (rel("a"),)


def test_control_an_empty_queue_has_no_next_plan(world):
    world.plans(a=_plan())
    world.queue()
    world.branch("1003-1")
    world.nodes([node(592, "MERGED", "Plan: agent/plans/PLAN-a.md")])
    got = state(world)
    assert got.kind == "merged"
    assert got.next_plan == ""
    assert got.queue_head == ""


def test_a_branch_with_no_pr_is_no_pr(world):
    world.plans(a=_plan())
    world.queue("a")
    world.branch("1003-1")
    got = state(world)
    assert got.kind == "no-pr"
    assert got.pr == 0
    assert got.plans == ()


# ---- SC2 with prerequisites (operator ruling 7), through plan_gate.pr_plan_set -----------


def live(world, body, **plans):
    world.plans(**plans)
    world.queue()
    world.branch("1003-1")
    world.nodes([node(592, "OPEN", body)])
    return state(world)


def test_an_unfinished_prerequisite_joins_the_set_first(world):
    got = live(world, "Plan: agent/plans/PLAN-a.md", a=_plan(depends="PLAN-p.md"), p=_plan())
    assert got.plans == (rel("p"), rel("a"))
    assert got.prereqs == (rel("p"),)
    assert got.reason == ""


def test_control_a_finished_prerequisite_is_excluded(world):
    got = live(
        world,
        "Plan: agent/plans/PLAN-a.md",
        a=_plan(depends="PLAN-p.md"),
        p=_plan(opened=0, done=2),
    )
    assert got.plans == (rel("a"),)
    assert got.prereqs == ()


def test_a_transitive_chain_gives_all_three_deepest_first(world):
    got = live(
        world,
        "Plan: agent/plans/PLAN-a.md",
        a=_plan(depends="PLAN-b.md"),
        b=_plan(depends="PLAN-c.md"),
        c=_plan(),
    )
    assert got.plans == (rel("c"), rel("b"), rel("a"))
    assert got.prereqs == (rel("c"), rel("b"))


def test_a_held_prerequisite_is_included(world):
    got = live(
        world,
        "Plan: agent/plans/PLAN-a.md",
        a=_plan(depends="PLAN-h.md"),
        h=_plan(status="held"),
    )
    assert got.plans == (rel("h"), rel("a"))


def test_a_cycle_is_reported_in_reason_with_both_paths(world):
    got = live(
        world,
        "Plan: agent/plans/PLAN-a.md",
        a=_plan(depends="PLAN-b.md"),
        b=_plan(depends="PLAN-a.md"),
    )
    assert "cycle" in got.reason
    assert rel("a") in got.reason
    assert rel("b") in got.reason
    assert set(got.plans) == {rel("a"), rel("b")}


def test_a_missing_dependency_is_reported_with_its_path(world):
    got = live(world, "Plan: agent/plans/PLAN-a.md", a=_plan(depends="PLAN-gone.md"))
    assert "PLAN-gone.md" in got.reason
    assert rel("a") in got.reason
    assert got.plans == (rel("a"),)


def test_prerequisite_epics_are_in_scope(world):
    world.plans(a=_plan(depends="PLAN-p.md"), p=_plan(), u=_plan())
    world.queue()
    world.branch("1003-1")
    world.nodes([node(592, "OPEN", "Plan: agent/plans/PLAN-a.md")])
    epics = {rel("a"): {"i1"}, rel("p"): {"i2"}, rel("u"): {"i3"}}
    got = state(world, epics=lambda r: epics.get(r, set()))
    assert got.epic_items == frozenset({"i1", "i2"})


def test_after_a_merge_a_plan_with_an_open_prerequisite_yields_the_prerequisite(world):
    world.plans(done=_plan(opened=0, done=1), x=_plan(depends="PLAN-p.md"), y=_plan(), p=_plan())
    world.queue("x", "y", "p")
    world.branch("1003-1")
    world.nodes([node(592, "MERGED", "Plan: agent/plans/PLAN-done.md")])
    got = state(world)
    assert got.kind == "merged"
    assert got.next_plan == rel("p")
    # Control: the prerequisite finished, so the queued plan itself is next.
    world.plans(p=_plan(opened=0, done=1))
    assert state(world).next_plan == rel("x")


def test_next_queued_skips_the_excluded_plans(world):
    prscope = wlfix.import_wl("wl_prscope")
    world.plans(a=_plan(), b=_plan())
    world.queue("a", "b")
    assert prscope.next_queued(world.root) == (rel("a"), "")
    assert prscope.next_queued(world.root, exclude=(rel("a"),)) == (rel("b"), "")
    assert prscope.next_queued(world.root, exclude=(rel("a"), rel("b"))) == ("", "")


def test_epic_reader_without_plan_epics_is_empty(monkeypatch):
    """SC3 lands `wl_epic.plan_epics` in parallel; until then the default reader returns no items rather than failing the stop."""
    prscope = wlfix.import_wl("wl_prscope")
    wl_epic = wlfix.import_wl("wl_epic")
    monkeypatch.delattr(wl_epic, "plan_epics", raising=False)
    assert prscope.epic_items((rel("a"),)) == frozenset()


# ---- T9 of agent/plans/PLAN-stop-hook-turbo.md: the turbo picks ------------------------------------

TURBO = "\n## Settings\n\n```stop-hook\nturbo: %s\nbatch_size: 2\nwriter_cap: 4\n```\n"


def _xplan(name, opened=1, done=0):
    """A plan with the X fields the picks check (`wl_planconc.spawn_verdict` fails closed without `Owns:`)."""
    return _plan(opened=opened, done=done).replace(
        "Priority: P2 -- seed\n",
        "Priority: P2 -- seed\nConcurrency: parallel\nOwns: docs/%s/**\n" % name,
    )


def turbo_live(world, turbo="on"):
    world.plans(a=_xplan("a"), b=_xplan("b"), c=_xplan("c"), d=_xplan("d"))
    world.queue("a", "b", "c", "d")
    queue = world.root / "agent" / "plans" / "QUEUE.md"
    queue.write_text(
        queue.read_text(encoding="utf-8").replace(
            "\n## Promoted", TURBO % turbo + "\n## Promoted", 1
        ),
        "utf-8",
    )
    world.branch("1003-1")
    world.nodes([node(592, "OPEN", "Plan: agent/plans/PLAN-a.md\n\nBody.")])


def turbo_state(world, live):
    prscope = wlfix.import_wl("wl_prscope")
    return prscope.loop_state(
        world.root, world.worklist, ME, today="1003", epics=lambda _rel: set(), live=live
    )


def test_turbo_on_a_live_pr_with_two_free_slots_names_two_plans(world):
    turbo_live(world)
    got = turbo_state(world, ((), 2))
    assert got.turbo is True
    assert got.batch_size == 2
    assert got.turbo_picks == (rel("b"), rel("c"))
    assert got.turbo_more is True


def test_turbo_with_no_free_slot_names_none(world):
    turbo_live(world)
    got = turbo_state(world, (("PLAN-d.md",), 4))
    assert got.turbo_picks == ()
    # Something is still eligible, so the batch is not declared exhausted.
    assert got.turbo_more is True


def test_turbo_picks_skip_the_pr_set_and_a_live_writers_plan_owner(world):
    turbo_live(world)
    got = turbo_state(world, (("PLAN-b.md",), 1))
    assert rel("a") not in got.turbo_picks
    assert got.turbo_picks == (rel("c"), rel("d"))


def test_turbo_off_equals_today(world):
    turbo_live(world, turbo="off")
    got = turbo_state(world, ((), 0))
    plain = state(world)
    assert got == plain
    assert got.turbo is False
    assert got.turbo_picks == ()
    assert got.batch_size == 1


def test_batch_ready_waits_for_the_batch_or_an_empty_queue(world):
    prscope = wlfix.import_wl("wl_prscope")
    turbo_live(world)
    got = turbo_state(world, ((), 2))
    assert not prscope.batch_ready(got, True), "1 finished of 2 with eligible plans left"
    import dataclasses  # noqa: PLC0415

    assert prscope.batch_ready(dataclasses.replace(got, finished=2), True)
    assert prscope.batch_ready(dataclasses.replace(got, turbo_more=False), True)
    assert not prscope.batch_ready(dataclasses.replace(got, finished=2), False)
    assert prscope.batch_ready(dataclasses.replace(got, turbo=False), False)
