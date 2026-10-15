"""The effort level through the real Stop hook (agent/plans/PLAN-stop-hook-effort.md boxes E3 and E4).

E3: one key of each family is driven through all five levels, and the FLOOR blocks at `quiet`. The table verdicts are read from .claude/config/effort.json through `wl_effort`; the stops run `worklist.py` with a Stop event, as the harness does, against a fixture project whose QUEUE.md names the level.

E4: `--focus` is gone (an unknown verb, exit 2), `--phase` replaces it, and a phase only parks work.
"""

from __future__ import annotations

import itertools
import json

import pytest

from rediacc_hooks.tests import wlfix

E = wlfix.import_wl("wl_effort")
FLOOR = wlfix.import_wl("wl_floor")
LEVELS = ("quiet", "low", "smart", "high", "ultra")


@pytest.fixture
def world(tmp_path):
    fixture = wlfix.Fixture(tmp_path / "hookfix")
    fixture.setup()
    return fixture


def blocked_keys(fx) -> set[str]:
    """Every key the newest blocked stop led with or named, from `.blocklog-<me8>.jsonl`; empty when the stop allowed. Each read clears the log, so the next stop starts from nothing."""
    keys: set[str] = set()
    for path in fx.base.rglob("*blocklog-*.jsonl"):
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        if rows:
            keys |= {rows[-1]["key"], *rows[-1].get("named", [])}
        path.unlink()
    return keys


# ---- the table, one key per family --------------------------------------------------------------
# The effort tuner rewrites rows of the real table in place and records each old entry under `tuned.<key>.from` (wl_effort_tune.apply_changes), so a family's levels are read from the untuned table: the real one with every tuned row put back to its `from`.


def untuned_table():
    table = json.loads(E.TABLE_PATH.read_text(encoding="utf-8"))
    for key, rec in (table.get("tuned") or {}).items():
        table["checks"][key] = {**table["checks"][key], **rec["from"]}
    return table


# (family, key, verdict at quiet, low, smart, high, ultra)
FAMILIES = [
    ("floor", "ci-red", ("block",) * 5),
    ("mission", "open-items", ("off", "block", "block", "block", "block")),
    ("owed", "bg-report", ("off", "advise", "block", "block", "block")),
    ("integrity", "completion", ("off", "advise", "block", "block", "block")),
    ("advise-at-smart", "no-remaining", ("off", "off", "advise", "block", "block")),
    ("hygiene", "plan-drift", ("off", "off", "advise", "block", "block")),
]


@pytest.mark.parametrize(("family", "key", "want"), FAMILIES, ids=[f[0] for f in FAMILIES])
def test_one_key_per_family_through_every_level(family, key, want):
    del family
    table = untuned_table()
    assert tuple(E.verdict(key, level, table) for level in LEVELS) == want
    # A `:<subject>` suffix is the same check class.
    assert E.verdict(key + ":x", "smart", table) == want[2]


def test_the_floor_blocks_at_quiet_whatever_the_table_says():
    planted = {"checks": {k: {"block": "ultra", "advise": "ultra"} for k in FLOOR.FLOOR}}
    for key in FLOOR.FLOOR:
        assert E.verdict(key, "quiet", planted) == "block", key
    # STATE.md joins the floor only while compaction is due.
    assert E.verdict("agent-state", "quiet") == "off"
    assert E.verdict("agent-state", "quiet", compaction_due=True) == "block"


def test_an_unreadable_table_or_an_unlisted_key_blocks():
    assert E.verdict("open-items", "quiet", {"checks": {}}) == "block"
    assert E.verdict("anything", "quiet", None) == "block"  # the real table: unlisted
    assert E.advises("anything-new", "quiet") is True


def test_advisory_keys_follow_their_advise_level():
    assert [E.advises("agent-hint", lv) for lv in LEVELS] == [False, False, True, True, True]
    assert [E.advises("ci-report:pr-review", lv) for lv in LEVELS] == [
        False,
        True,
        True,
        True,
        True,
    ]
    assert E.advises("unread-reports", "quiet") is True  # a FLOOR key advises at every level too
    assert E.advises("agent-hint", None) is True  # no stop in progress: everything passes


# ---- through the real Stop hook ------------------------------------------------------------------


# The two report checks this world trips besides `open-items`. The hook reads the real, tuned table, so which level blocks or only advises each one is read from that table, never written down here.
REPORT_KEYS = ("no-remaining", "agent-state")


def test_e3_one_world_through_all_five_levels(world):
    """An open item and a message with no `## Remaining`: `open-items` (mission), `no-remaining` and `agent-state` fire, and each level blocks on exactly its share as the real table gives it. A fresh world per level, so every level judges the same first stop."""
    seen = {}
    for level in LEVELS:
        world.setup()
        assert world.cli("--add", wlfix.ME, "(%s) do the thing" % wlfix.ME).rc == 0
        world.say("done for now")
        world.settings(effort=level)
        got = world.run()
        seen[level] = (got.decision, blocked_keys(world))
    # Every level's share is read from the real table, the mission check included, so a tuner promotion or demotion moves the expectation with it (review 31c4e5c3.1): no level's set is written down here.
    watched = ("open-items", *REPORT_KEYS)
    for level in LEVELS:
        want = {key for key in watched if E.verdict(key, level) == "block"}
        # The whole blocked set, not its watched slice (review 2e50ca28.2): this world trips nothing else, so a check that starts blocking here at any level, quiet included, fails the row.
        assert seen[level][1] == want, (level, want, seen[level])
        assert seen[level][0] == ("block" if want else "allow"), (level, seen[level])
    # NOT VACUOUS: the table blocks at least one watched check at some level and leaves at least one level unblocked, so the loop above judges both directions.
    assert any(seen[lv][1] for lv in LEVELS), seen
    assert any(not seen[lv][1] & set(watched) for lv in LEVELS), seen
    # The levels are supersets of one another, as the plan says.
    order = [seen[lv][1] for lv in LEVELS]
    assert all(a <= b for a, b in itertools.pairwise(order)), order


def queued_keys(fx) -> set[str]:
    """The advisory-queue keys of this session's state doc (wl_checks.outq_add)."""
    path = fx.wl.with_suffix(".state-%s.json" % wlfix.ME)
    doc = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    return {str(e.get("key")) for e in ((doc.get("outq") or {}).get("items") or [])}


def stop_at(world, level):
    """One fresh stop of this world (an open item, no `## Remaining`) at `level`: (blocked keys, queued keys)."""
    world.setup()
    assert world.cli("--add", wlfix.ME, "(%s) do the thing" % wlfix.ME).rc == 0
    world.say("done for now")
    world.settings(effort=level)
    world.run()
    return blocked_keys(world), queued_keys(world)


def test_e3_an_advise_level_turns_a_report_check_into_an_advisory(world):
    """At a level where the real table only advises a report check, the check does not block: it rides the advisory queue in the block's place. At its block level it blocks and is not queued; at low it is neither."""
    advised = [
        (key, level) for key in REPORT_KEYS for level in LEVELS if E.verdict(key, level) == "advise"
    ]
    assert advised, "the table advises none of %s at any level" % (REPORT_KEYS,)
    key, level = advised[0]
    blocked, queued = stop_at(world, level)
    assert key not in blocked, (key, level, blocked)
    assert key in queued, (key, level, queued)
    # CONTROL, the same world at the first level that blocks it: it blocks.
    above = next(lv for lv in LEVELS if E.verdict(key, lv) == "block")
    blocked, queued = stop_at(world, above)
    assert key in blocked, (key, above, blocked)
    assert key not in queued, (key, above, queued)
    # CONTROL, at low: neither blocked nor queued.
    assert E.verdict(key, "low") == "off"
    blocked, queued = stop_at(world, "low")
    assert key not in blocked | queued


@pytest.mark.parametrize(
    ("label", "kw"),
    [
        ("unparseable event", {"event": "not json at all"}),
        ("background wait with no wake-up timer", {}),
    ],
)
def test_e3_the_floor_blocks_at_quiet(world, label, kw):
    world.settings(effort="quiet")
    if not kw:
        world.bg = json.dumps(
            [{"id": "b1", "type": "shell", "status": "running", "description": "x"}]
        )
        world.waker = False
    got = world.run(event=kw.get("event"))
    assert got.decision == "block", (label, got.out[:300])
    assert blocked_keys(world) & FLOOR.FLOOR, label
    # CONTROL: the same world with the floor's cause removed allows at quiet.
    world.bg, world.waker = "[]", True
    assert world.run().decision == "allow"


def test_quiet_replaces_the_off_switch_and_stop_hook_is_refused(world):
    """`stop_hook: off` is an unknown key now: it never quiets the hook, and the settings problem rides the stop."""
    assert world.cli("--add", wlfix.ME, "(%s) do the thing" % wlfix.ME).rc == 0
    world.say("done")
    path = world.proj / "agent" / "plans" / "QUEUE.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("cadence: off", "cadence: off\nstop_hook: off"),
        encoding="utf-8",
    )
    got = world.run()
    assert got.decision == "block", got.out[:300]
    assert "open-items" in blocked_keys(world)


# ---- E4: the phase -----------------------------------------------------------------------------


def test_e4_focus_is_an_unknown_verb(world):
    got = world.cli("--focus", wlfix.ME, "babysit")
    assert got.rc == 2, (got.rc, got.out, got.err)
    assert "--focus" in got.err


def test_e4_phase_records_build_babysit_and_merge(world):
    status = world.cli("--phase", wlfix.ME)
    assert status.rc == 0
    assert "build" in status.out
    on = world.cli("--phase", wlfix.ME, "babysit", "--pr", "77", "--branch", "1014-1")
    assert on.rc == 0, on.err
    assert "phase babysit" in on.out
    events = [json.loads(line) for line in world.wl_events().splitlines() if line.strip()]
    phases = [e for e in events if e.get("ev") == "phase"]
    assert phases
    assert (phases[-1]["mode"], phases[-1]["pr"]) == ("babysit", 77)
    assert "babysit" in world.cli("--phase", wlfix.ME).out
    off = world.cli("--phase", wlfix.ME, "build")
    assert off.rc == 0
    events = [json.loads(line) for line in world.wl_events().splitlines() if line.strip()]
    assert [e for e in events if e.get("ev") == "phase"][-1]["mode"] == "build"
    assert world.cli("--phase", wlfix.ME, "sprint").rc == 2


def test_e4_a_phase_parks_and_never_adds_a_block(world):
    """At effort quiet nothing outside the FLOOR blocks, and a babysit phase adds nothing to that."""
    assert world.cli("--add", wlfix.ME, "(%s) unrelated work" % wlfix.ME).rc == 0
    world.say("done")
    world.settings(effort="quiet")
    assert world.run().decision == "allow"
    assert world.cli("--phase", wlfix.ME, "babysit", "--pr", "77", "--branch", "1014-1").rc == 0
    got = world.run()
    assert got.decision == "allow", got.out[:300]
    # At low the open item blocks in build; under the babysit phase it is parked (it carries no pr:77).
    world.settings(effort="low")
    assert world.cli("--phase", wlfix.ME, "build").rc == 0
    assert world.run().decision == "block"
    blocked_keys(world)
    assert world.cli("--phase", wlfix.ME, "babysit", "--pr", "77", "--branch", "1014-1").rc == 0
    parked = world.run()
    assert "open-items" not in blocked_keys(world), parked.out[:300]
