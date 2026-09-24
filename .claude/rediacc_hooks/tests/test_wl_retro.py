"""The stop-hook retro's inputs (agent/plans/PLAN-stop-hook-retro-20260924.md, section 8).

R.10: `.blocklog-<me8>.jsonl` carries one row per BLOCKED stop, with the key the block led with, every other outstanding key it named, and the judge's flags when the judge blocked. The first retro had to grep a 222 MB transcript to count blocks per key; the next one reads this file.

The retro-order cases (R.11 to R.13) belong in this module as well.
"""

from __future__ import annotations

import json

from rediacc_hooks.tests.test_wl_judge_fixset_scope import timeout_fix_world
from rediacc_hooks.tests.wlfix import wl  # noqa: F401


def blocklog_rows(fix) -> list[dict]:
    path = fix.stem(".blocklog-deadbeef.jsonl")
    if not path.is_file():
        return []
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def test_r10_a_battery_block_writes_one_row_naming_its_keys(wl):  # noqa: F811
    """CONTROL: before R.10 no block left a row."""
    wl.brief_now()
    wl.hand_now()
    wl.add_item("- [ ] (deadbeef) open thing")
    wl.say("answer with no report section")
    got = wl.run()
    assert got.decision == "block", got.out[:300]
    rows = blocklog_rows(wl)
    assert len(rows) == 1, rows
    keys = {rows[0]["key"], *rows[0]["named"]}
    assert "open-items" in keys, rows[0]
    assert "no-remaining" in keys, rows[0]


def test_r10_inverse_an_allowed_stop_writes_no_row(wl):  # noqa: F811
    wl.brief_now()
    wl.hand_now()
    wl.say("all done")
    got = wl.run()
    assert got.decision == "allow", got.out[:300]
    assert blocklog_rows(wl) == []


def test_r10_a_judge_block_carries_the_judge_flags(wl):  # noqa: F811
    timeout_fix_world(wl, "grep -rn '\"timeout\"' .claude/settings.json")
    got = wl.runj()
    assert got.decision == "block", got.out[:300]
    rows = blocklog_rows(wl)
    judged = [r for r in rows if r["judge"]]
    assert judged, rows
    assert judged[-1]["judge"]["sweep"] is True, judged[-1]
    assert judged[-1]["judge"]["verdict"] == "continue", judged[-1]


# ---- R.12 and R.13: the retro order at PostCompact, the tracking item, and the brief ----------

RETRO_PLAN = "agent/plans/PLAN-stop-hook-retro-20260924.md"


def ledger(fix):
    return fix.proj / "agent" / "ledgers" / "stop-hook-retros.jsonl"


def ledger_rows(fix) -> list[dict]:
    path = ledger(fix)
    if not path.is_file():
        return []
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def plant_rows(fix, *rows: dict) -> None:
    path = ledger(fix)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def ordered(band: str, from_off: int, to_off: int, at: str = "2026-09-24T10:00:00Z") -> dict:
    return {
        "ev": "ordered",
        "at": at,
        "session": "deadbeef",
        "band": band,
        "transcript": "/t/lead.jsonl",
        "from_off": from_off,
        "to_off": to_off,
    }


def compact(fix, **extra):
    payload = {"session_id": fix.sid, "cwd": str(fix.proj), "transcript_path": str(fix.transcript)}
    payload.update(extra)
    env = dict(fix.env)
    env["CLAUDE_PROJECT_DIR"] = str(fix.proj)
    got = fix.python(["--post-compact"], stdin=json.dumps(payload), env=env)
    assert got.rc == 0, got.err[:300]
    return json.loads(got.out)["hookSpecificOutput"]["additionalContext"]


def retro_items(fix) -> list[str]:
    return [ln for ln in fix.wl_events().splitlines() if "stop-hook retro" in ln and '"add"' in ln]


def test_r12_post_compact_orders_the_retro_once(wl):  # noqa: F811
    """CONTROL: before R.12 the PostCompact briefing carried no retro order and wrote no row."""
    wl.plant_state("## Next action\n\nkeep going")
    first = compact(wl)
    assert "STOP-HOOK RETRO" in first, first[-600:]
    assert "--retro-brief deadbeef post-compact" in first, first[-600:]
    assert "After reading the briefing above" in first, first[-600:]
    rows = ledger_rows(wl)
    assert [(r["ev"], r["band"], r["session"]) for r in rows] == [
        ("ordered", "post-compact", "deadbeef")
    ], rows
    assert rows[0]["to_off"] == wl.transcript.stat().st_size, rows
    assert "bytes 0-%d" % rows[0]["to_off"] in first, first[-600:]
    second = compact(wl)
    assert "STOP-HOOK RETRO" not in second, second[-600:]
    assert len(ledger_rows(wl)) == 1


def test_r12_the_missing_state_arm_orders_after_the_write(wl):  # noqa: F811
    text = compact(wl)
    assert "After you write STATE.md" in text, text[-600:]


def test_r12_a_subagent_event_orders_nothing(wl):  # noqa: F811
    """CONTROL: the agent_id guard. Without it this event writes a row and carries the order."""
    wl.plant_state("## Next action\n\nkeep going")
    text = compact(wl, agent_id="agent_01xyz", agent_type="Explore")
    assert "STOP-HOOK RETRO" not in text, text[-600:]
    assert ledger_rows(wl) == []


def test_r13_one_ordered_row_is_one_owned_item_across_two_stops(wl):  # noqa: F811
    """CONTROL: before R.13 an ordered row produced no item at all."""
    wl.brief_now()
    wl.hand_now()
    plant_rows(wl, ordered("early", 0, 500))
    wl.say("all done")
    got = wl.run()
    assert got.decision == "block", got.out[:300]
    assert "stop-hook retro early 20260924" in got.out, got.out[:600]
    wl.run()
    items = retro_items(wl)
    assert len(items) == 1, items
    assert json.loads(items[0])["o"] == "deadbeef", items[0]
    tracked = [r for r in ledger_rows(wl) if r["ev"] == "tracked"]
    assert len(tracked) == 1, tracked
    assert tracked[0]["band"] == "early", tracked


def test_r13_an_allowed_world_without_a_ledger_adds_nothing(wl):  # noqa: F811
    """INVERSE: no ordered row, no item, no ledger file."""
    wl.brief_now()
    wl.hand_now()
    wl.say("all done")
    assert wl.run().decision == "allow"
    assert retro_items(wl) == []
    assert not ledger(wl).exists()


def test_r13_retro_brief_prints_the_id_and_the_previous_range_end(wl):  # noqa: F811
    """CONTROL: before R.13 the verb did not exist."""
    plan = wl.proj / "agent" / "plans" / "PLAN-stop-hook-demo.md"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text("# demo\n\n- [x] **D1** a landed box\n- [ ] **D2** an open box\n")
    wl.stem(".blocklog-deadbeef.jsonl").write_text(
        json.dumps(
            {
                "at": "2026-09-24T11:00:00Z",
                "key": "no-remaining",
                "named": ["open-items"],
                "judge": {},
            }
        )
        + "\n"
        + json.dumps(
            {"at": "2026-09-24T09:00:00Z", "key": "before-the-range", "named": [], "judge": {}}
        )
        + "\n"
    )
    plant_rows(wl, ordered("early", 0, 100), ordered("late", 100, 250, at="2026-09-24T12:00:00Z"))
    got = wl.cli("--retro-brief", "deadbeef", "late")
    assert got.rc == 0, got.err[:300]
    tracked = [r for r in ledger_rows(wl) if r["ev"] == "tracked"]
    assert len(tracked) == 1, tracked
    assert tracked[0]["band"] == "late", tracked
    assert "#%s" % tracked[0]["item"] in got.out, got.out[:400]
    assert "bytes 100-250" in got.out, got.out[:800]
    assert "PLAN-stop-hook-demo.md [ ] D2" in got.out, got.out
    assert "[x] D1" in got.out, got.out
    assert "led by no-remaining: 1" in got.out, got.out
    assert "before-the-range" not in got.out, got.out
    again = wl.cli("--retro-brief", "deadbeef", "late")
    assert len([r for r in ledger_rows(wl) if r["ev"] == "tracked"]) == 1, again.out[:200]
    assert len(retro_items(wl)) == 1


def test_r13_retro_brief_refuses_an_unknown_band(wl):  # noqa: F811
    got = wl.cli("--retro-brief", "deadbeef", "sometime")
    assert got.rc == 2, got.err
    assert "early, late, post-compact" in got.err, got.err
    assert not ledger(wl).exists()


def test_r13_a_tick_with_the_plan_path_writes_the_saved_row(wl):  # noqa: F811
    """CONTROL: before R.13 a ticked retro item left no saved row."""
    plan = wl.proj / RETRO_PLAN
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text(
        "# retro\n\n- [ ] **R20260924.1** one\n- [ ] **R20260924.2** two\n- [x] **R20260924.3** three\n"
    )
    plant_rows(wl, ordered("early", 0, 500))
    wl.cli("--retro-brief", "deadbeef", "early")
    item = next(r["item"] for r in ledger_rows(wl) if r["ev"] == "tracked")
    ticked = wl.cli("--tick", "deadbeef", item, "%s:1" % RETRO_PLAN)
    assert ticked.rc == 0, ticked.err[:300]
    wl.brief_now()
    wl.hand_now()
    wl.say("all done")
    wl.run()
    saved = [r for r in ledger_rows(wl) if r["ev"] == "saved"]
    assert len(saved) == 1, ledger_rows(wl)
    assert (saved[0]["plan"], saved[0]["tasks_open"], saved[0]["tasks_total"]) == (RETRO_PLAN, 2, 3)
    wl.run()
    assert len([r for r in ledger_rows(wl) if r["ev"] == "saved"]) == 1


def test_r13_a_leased_item_writes_the_dispatched_row_once(wl):  # noqa: F811
    """CONTROL: before R.13 a lease on the retro item left no dispatched row."""
    plant_rows(wl, ordered("early", 0, 500))
    wl.cli("--retro-brief", "deadbeef", "early")
    item = next(r["item"] for r in ledger_rows(wl) if r["ev"] == "tracked")
    leased = wl.cli("--lease", "deadbeef", item, "+60", "worker:bw9", "the retro Plan agent")
    assert leased.rc == 0, leased.err[:300]
    wl.say("waiting on the retro agent")
    wl.run()
    wl.run()
    dispatched = [r for r in ledger_rows(wl) if r["ev"] == "dispatched"]
    assert [(r["item"], r["agent"]) for r in dispatched] == [(item, "bw9")], ledger_rows(wl)
