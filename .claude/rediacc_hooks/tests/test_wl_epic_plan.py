"""Epics carry their plan, and `--reopen` returns a deferral to the open list (agent/plans/PLAN-stop-hook-one-plan-scope.md, SC3).

The Stop hook scopes a live PR's blocking items to the epics whose `plan` is the PR's plan (Design 2 and 3). So the plan link has to be a FIELD the CLI writes and validates, never a title to parse: a title naming a plan resolves nothing (clean break). Every case drives the real CLI through `wlfix` and reads the epic sidecar back through `wl_epic` itself, in a subprocess pointed at the fixture store.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.test_wl_roster import write_plan
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

PROBE = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import wl_epic as E
print(json.dumps({
    "covers": sorted(E.plan_epics(sys.argv[2])),
    "epics": E.load_epics(),
}))
"""

DEFER = (
    "which plan owns this DEFAULT: re-home it WHY: needs-an-operator-ruling HOW: operator-answers"
)


def probe(fix, rel: str) -> dict:
    proc = subprocess.run(
        [sys.executable, "-c", PROBE, str(wlfix.STOP_DIR), rel],
        capture_output=True,
        text=True,
        env=fix.stop_env(),
        check=False,
    )
    assert proc.returncode == 0, "the probe failed: %s" % proc.stderr[-1200:]
    return json.loads(proc.stdout)


def add(fix, text: str) -> str:
    got = fix.cli("--add", wlfix.ME, text)
    assert got.rc == 0, got.err[:300]
    found = re.search(r"added #([0-9a-f]+)", got.out)
    assert found, got.out[:200]
    return found.group(1)


def new_epic(fix, *argv: str) -> str:
    got = fix.cli("--epic", wlfix.ME, "new", *argv)
    assert got.rc == 0, got.err[:300]
    found = re.search(r"epic #([0-9a-f]+)", got.out)
    assert found, got.out[:200]
    return found.group(1)


def rel_of(plan: str) -> str:
    return "agent/plans/%s" % plan


def test_epic_with_plan_resolves_its_covers(wl):  # noqa: F811
    rel = rel_of(write_plan(wl, "scope-a"))
    item = add(wl, "(deadbeef) work under scope-a")
    eid = new_epic(wl, "--plan", rel, "scope-a work")
    assert wl.cli("--epic", wlfix.ME, "add", eid, item).rc == 0
    got = probe(wl, rel)
    assert got["covers"] == [item], got
    assert got["epics"][eid]["plan"] == rel
    # CONTROL: another plan resolves nothing.
    other = rel_of(write_plan(wl, "scope-b"))
    assert probe(wl, other)["covers"] == []


def test_epic_later_add_keeps_the_plan(wl):  # noqa: F811
    rel = rel_of(write_plan(wl, "scope-a"))
    first, second = add(wl, "(deadbeef) one"), add(wl, "(deadbeef) two")
    eid = new_epic(wl, "--plan", rel, "scope-a work")
    assert wl.cli("--epic", wlfix.ME, "add", eid, first).rc == 0
    assert wl.cli("--epic", wlfix.ME, "add", eid, second).rc == 0
    got = probe(wl, rel)
    assert got["covers"] == sorted([first, second]), got
    assert got["epics"][eid]["plan"] == rel


def test_epic_title_naming_a_plan_resolves_nothing(wl):  # noqa: F811
    plan = write_plan(wl, "scope-a")
    rel = rel_of(plan)
    item = add(wl, "(deadbeef) titled only")
    eid = new_epic(wl, "work (%s)" % plan)
    assert wl.cli("--epic", wlfix.ME, "add", eid, item).rc == 0
    assert probe(wl, rel)["covers"] == [], "a title must never be parsed as the plan"
    # CONTROL: the same epic given the field resolves.
    got = wl.cli("--epic", wlfix.ME, "plan", eid, rel)
    assert got.rc == 0, got.err[:300]
    assert probe(wl, rel)["covers"] == [item]


def test_epic_plan_verb_sets_later_wins_and_list_prints_it(wl):  # noqa: F811
    rel_a = rel_of(write_plan(wl, "scope-a"))
    rel_b = rel_of(write_plan(wl, "scope-b"))
    item = add(wl, "(deadbeef) moves plan")
    eid = new_epic(wl, "--plan", rel_a, "moving epic")
    assert wl.cli("--epic", wlfix.ME, "add", eid, item).rc == 0
    assert wl.cli("--epic", wlfix.ME, "plan", eid, rel_b).rc == 0
    assert probe(wl, rel_a)["covers"] == []
    assert probe(wl, rel_b)["covers"] == [item]
    listed = wl.cli("--epic", wlfix.ME, "list")
    assert listed.rc == 0, listed.err[:300]
    assert "#%s" % eid in listed.out, listed.out
    assert "plan: %s" % rel_b in listed.out, listed.out
    # An epic with no plan prints a placeholder, never an empty column.
    bare = new_epic(wl, "no plan yet")
    listed = wl.cli("--epic", wlfix.ME, "list").out
    line = next(x for x in listed.splitlines() if x.startswith("#%s" % bare))
    assert line.endswith("plan: -"), line


def test_epic_nonexistent_plan_is_refused_and_writes_nothing(wl):  # noqa: F811
    write_plan(wl, "scope-a")
    for bad in ("agent/plans/PLAN-missing.md", "docs/PLAN-scope-a.md", "agent/plans/../x.md"):
        got = wl.cli("--epic", wlfix.ME, "new", "--plan", bad, "refused epic")
        assert got.rc == 2, (bad, got.rc, got.err)
        assert "REFUSED" in got.err, (bad, got.rc, got.err)
    assert probe(wl, "agent/plans/PLAN-missing.md")["epics"] == {}, "a refused new wrote a record"
    eid = new_epic(wl, "real epic")
    got = wl.cli("--epic", wlfix.ME, "plan", eid, "agent/plans/PLAN-missing.md")
    assert got.rc == 2, got.err
    assert "REFUSED" in got.err, got.err
    assert "plan" not in probe(wl, "x")["epics"][eid]
    # CONTROL: an unknown epic is refused even with a real plan.
    got = wl.cli("--epic", wlfix.ME, "plan", "abcdef12", "agent/plans/PLAN-scope-a.md")
    assert got.rc == 2, got.err
    assert "no epic" in got.err, got.err


def state_of(fix, item: str) -> str:
    got = fix.cli("--list")
    assert got.rc == 0, got.err[:300]
    line = next(x for x in got.out.splitlines() if "#%s" % item in x)
    found = re.match(r"\s*- \[(.)\]", line)
    assert found, line
    return found.group(1)


def test_reopen_moves_a_deferral_back_to_open(wl):  # noqa: F811
    item = add(wl, "(deadbeef) parked item")
    assert wl.cli("--defer", wlfix.ME, item, *DEFER.split()).rc == 0
    assert state_of(wl, item) == "?"
    got = wl.cli("--reopen", wlfix.ME, item, "re-homed onto its plan's epic")
    assert got.rc == 0, got.err[:300]
    assert "reopened #%s" % item in got.out
    assert state_of(wl, item) == " "


def test_reopen_is_refused_from_every_other_state(wl):  # noqa: F811
    done = add(wl, "(deadbeef) finished item")
    assert wl.cli("--tick", wlfix.ME, done, "https://ci.invalid/run/1").rc == 0
    got = wl.cli("--reopen", wlfix.ME, done, "try to reopen")
    assert got.rc != 0, (got.rc, got.err)
    assert "only a [?]" in got.err, (got.rc, got.err)
    assert state_of(wl, done) == "x"
    still_open = add(wl, "(deadbeef) open item")
    got = wl.cli("--reopen", wlfix.ME, still_open, "already open")
    assert got.rc != 0, (got.rc, got.err)
    assert "only a [?]" in got.err, (got.rc, got.err)
    leased = add(wl, "(deadbeef) leased item")
    assert wl.cli("--lease", wlfix.ME, leased, "+30", "worker:lead").rc == 0
    got = wl.cli("--reopen", wlfix.ME, leased, "leased")
    assert got.rc != 0, (got.rc, got.err)
    assert "only a [?]" in got.err, (got.rc, got.err)
    assert state_of(wl, leased) == ">"
    # A note is mandatory, like every other state change's evidence.
    parked = add(wl, "(deadbeef) parked")
    assert wl.cli("--defer", wlfix.ME, parked, *DEFER.split()).rc == 0
    got = wl.cli("--reopen", wlfix.ME, parked)
    assert got.rc != 0, got.out
    assert state_of(wl, parked) == "?"
