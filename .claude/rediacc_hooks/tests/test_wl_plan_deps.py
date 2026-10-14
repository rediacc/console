"""Plan dependencies at start time, driven through the real CLI and the real Stop hook (agent/plans/PLAN-plan-dependencies.md sections 2c, 3 and 5c, T6-T9).

The library controls (classify_items, guided_slice, blocker_error, auto-lease, planenforce) live in `.claude/hooks/stop/test-depgate.py`; this file holds what only a process boundary shows: the exit codes and stderr of `--lease`, `--tick`, `--plan-tick`, `--add` and `--migrate --plan`, the waiver, and the UNBLOCKED line the stop writes when a plan root finishes.

Every refusal has a passing twin from the same fixture with one fact changed: the dependency finished, the item unlinked, or a real waiver given.
"""

from __future__ import annotations

import json
import re

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.test_wl_roster import linked, write_plan

# The sandbox fixture under a local name: pytest registers a fixture by the attribute it is found under, so the test arguments below say `fix`.
fix = wlfix.wl

EVIDENCE = "ran the fixture check, exit code 0 nocommit:research"
WAIVER = "DEPS-WAIVED: the root plan is replaced by a rewrite"


def add(box, text: str) -> str:
    got = box.cli("--add", wlfix.ME, text)
    assert got.rc == 0, got.err[:300]
    found = re.search(r"added #([0-9a-f]+)", got.out)
    assert found, got.out[:200]
    return found.group(1)


def chain(box, root_status: str = "in-progress") -> str:
    """Plans x -> z on disk (z the root); returns an open item linked to x."""
    write_plan(box, "z", status=root_status)
    write_plan(box, "x", dep="PLAN-z.md")
    return add(box, linked("PLAN-x.md", "port the x box"))


def test_d1_lease_is_refused_on_an_item_whose_plan_waits(fix):
    item = chain(fix)
    got = fix.cli("--lease", wlfix.ME, item, "+30", "worker:abc123")
    assert got.rc == 2, (got.rc, got.err[:400])
    assert "REFUSED" in got.err, got.err[:600]
    assert "PLAN-z.md" in got.err, got.err[:600]
    assert "DEPS-WAIVED" in got.err, got.err[:800]
    assert "check_plan_deps.py --set" in got.err, got.err[:800]


def test_d1b_twins_finished_dependency_and_unlinked_item_pass(fix):
    done = chain(fix, root_status="done")
    assert fix.cli("--lease", wlfix.ME, done, "+30", "worker:abc123").rc == 0
    other = add(fix, "(deadbeef) an unlinked item, mentions PLAN-x.md in passing")
    assert fix.cli("--lease", wlfix.ME, other, "+30", "worker:abc124").rc == 0


def test_d1c_release_is_never_refused(fix):
    item = chain(fix)
    assert fix.cli("--lease", wlfix.ME, item, "+30", "worker:abc123", WAIVER).rc == 0
    assert fix.cli("--lease", wlfix.ME, item, "release").rc == 0


def test_d2_tick_is_refused_and_a_waiver_licenses_it(fix):
    item = chain(fix)
    got = fix.cli("--tick", wlfix.ME, item, EVIDENCE)
    assert got.rc == 2, (got.rc, got.err[:400])
    assert "REFUSED" in got.err, got.err[:600]
    assert "PLAN-z.md" in got.err, got.err[:600]
    ok = fix.cli("--tick", wlfix.ME, item, EVIDENCE, WAIVER)
    assert ok.rc == 0, ok.err[:400]
    assert WAIVER in fix.cli("--list").out, "the waiver is stored verbatim"


def test_d2b_a_short_waiver_is_refused(fix):
    item = chain(fix)
    got = fix.cli("--tick", wlfix.ME, item, EVIDENCE, "DEPS-WAIVED: skip")
    assert got.rc == 2, (got.rc, got.err[:400])
    assert "DEPS-WAIVED token was refused" in got.err, got.err[:600]


def test_d2c_a_waiver_given_at_lease_time_stands_at_tick_time(fix):
    item = chain(fix)
    assert fix.cli("--lease", wlfix.ME, item, "+30", "worker:abc123", WAIVER).rc == 0
    assert fix.cli("--tick", wlfix.ME, item, EVIDENCE).rc == 0


def test_d2d_tick_with_the_dependency_finished_is_not_refused(fix):
    item = chain(fix, root_status="done")
    assert fix.cli("--tick", wlfix.ME, item, EVIDENCE).rc == 0


def test_d3_plan_tick_is_refused_without_a_present_row(fix):
    chain(fix)
    got = fix.cli("--plan-tick", wlfix.ME, "agent/plans/PLAN-x.md", "T1", EVIDENCE, "--write")
    assert got.rc == 2, (got.rc, got.err[:400])
    assert "REFUSED" in got.err, got.err[:600]
    assert "PLAN-z.md" in got.err, got.err[:600]
    assert "--plan-tick" in got.err, got.err[:600]


def test_d3b_plan_tick_twin_with_the_dependency_finished_passes_the_dependency_gate(fix):
    chain(fix, root_status="done")
    got = fix.cli("--plan-tick", wlfix.ME, "agent/plans/PLAN-x.md", "T1", EVIDENCE, "--write")
    # The verb may still refuse for its own reasons (no investigation row); it must not refuse for the dependency.
    assert "which cannot start yet" not in got.err, got.err[:600]


def test_d4_add_prints_a_note_naming_the_chain_and_still_adds(fix):
    write_plan(fix, "z")
    write_plan(fix, "x", dep="PLAN-z.md")
    got = fix.cli("--add", wlfix.ME, linked("PLAN-x.md", "port the x box"))
    assert got.rc == 0, (got.rc, got.out, got.err)
    assert "added #" in got.out, (got.rc, got.out, got.err)
    assert "NOTE" in got.err, got.err[:600]
    assert "PLAN-z.md" in got.err, got.err[:600]
    free = fix.cli("--add", wlfix.ME, linked("PLAN-z.md", "the root box"))
    assert free.rc == 0, free.err[:400]
    assert "NOTE" not in free.err, free.err[:400]


def test_d5_list_open_leads_with_the_first_row_and_the_waiting_row(fix):
    write_plan(fix, "z")
    write_plan(fix, "x", dep="PLAN-z.md")
    waiter = add(fix, linked("PLAN-x.md", "port the x box"))
    out = fix.cli("--list", "--open", wlfix.ME).out
    assert "FIRST PLAN-z.md" in out, out[:800]
    assert "chain: PLAN-x.md -> PLAN-z.md" in out, out[:800]
    assert "nothing yet" in out, out[:1000]
    assert "--add %s" % wlfix.ME in out, out[:1000]
    root = add(fix, linked("PLAN-z.md", "the root box"))
    out = fix.cli("--list", "--open", wlfix.ME).out
    assert "tracked by: #%s" % root in out, out[:1000]
    assert waiter in out, out[:1200]
    assert "waiting (PLAN-z.md)" in out, out[:1200]


def unblocked_texts(box) -> list[str]:
    doc = json.loads(box.stem(".state-deadbeef.json").read_text(encoding="utf-8"))
    return [e.get("text", "") for e in doc.get("outq", {}).get("items", [])]


def test_d6_the_stop_says_unblocked_when_the_root_finishes(fix):
    write_plan(fix, "z")
    write_plan(fix, "x", dep="PLAN-z.md")
    fix.brief_now()
    fix.hand_now()
    root = add(fix, linked("PLAN-z.md", "the root box"))
    waiter = add(fix, linked("PLAN-x.md", "port the x box"))
    fix.say("working\n\n## Remaining\n- #%s and #%s" % (root, waiter))
    fix.run()
    # The waiting row is the guide's, which a block no longer carries: read it where the guide lives.
    first = fix.cli("--list", "--open", wlfix.ME).out
    assert waiter in first, first[-900:]
    assert "waiting (PLAN-z.md)" in first, first[-900:]
    write_plan(fix, "z", status="done")
    assert fix.cli("--tick", wlfix.ME, root, EVIDENCE).rc == 0
    fix.newturn()
    fix.say("working\n\n## Remaining\n- #%s" % waiter)
    second = fix.run().out
    line = "UNBLOCKED #%s: PLAN-z.md is finished" % waiter
    texts = unblocked_texts(fix)
    assert any(t.startswith(line) for t in texts) or line in second, (texts, second[-700:])


def test_d6b_inverse_a_root_nobody_tracks_does_not_claim_to_be_finished(fix):
    write_plan(fix, "z")
    write_plan(fix, "x", dep="PLAN-z.md")
    fix.brief_now()
    fix.hand_now()
    root = add(fix, linked("PLAN-z.md", "the root box"))
    waiter = add(fix, linked("PLAN-x.md", "port the x box"))
    fix.say("working\n\n## Remaining\n- #%s and #%s" % (root, waiter))
    fix.run()
    assert fix.cli("--tick", wlfix.ME, root, EVIDENCE).rc == 0
    fix.newturn()
    fix.say("working\n\n## Remaining\n- #%s" % waiter)
    out = fix.run().out
    assert not any("is finished, so it is open work again" in t for t in unblocked_texts(fix))
    assert "is finished, so it is open work again" not in out, out[-700:]
    assert "nothing tracks it; start there" in out, out[-900:]
