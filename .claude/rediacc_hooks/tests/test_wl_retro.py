"""The stop-hook retro's inputs (agent/plans/PLAN-stop-hook-retro-20260924.md, section 8).

R.10: `.blocklog-<me8>.jsonl` carries one row per BLOCKED stop, with the key the block led with, every other outstanding key it named, and the judge's flags when the judge blocked. The first retro had to grep a 222 MB transcript to count blocks per key; the next one reads this file.

The retro-order cases (R.11 to R.13) belong in this module as well.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import time

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
    wl.append_transcript(boundary(False))
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
    wl.append_transcript(boundary(False))
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
    plant_rows(
        wl,
        ordered("early", 0, 100),
        {"ev": "saved", "session": "deadbeef", "band": "early", "item": "aaaa0001"},
        ordered("late", 100, 250, at="2026-09-24T12:00:00Z"),
    )
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


# ---- R.16 and R.17: attribute the compaction, window from the last reviewed retro, `voided` ----------


def _now_stamp(ago: float = 0.0) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(time.time() - ago))


def boundary(sidechain: bool, agent: str = "", ago: float = 2.0) -> dict:
    """The `compact_boundary` record, in the shape measured in agent-a149262d8b6a1601f.jsonl line 7512."""
    rec = {
        "type": "system",
        "subtype": "compact_boundary",
        "isSidechain": sidechain,
        "timestamp": _now_stamp(ago),
        "sessionId": "deadbeef",
        "compactMetadata": {"trigger": "auto", "postTokens": 5941},
    }
    if agent:
        rec["agentId"] = agent
    return rec


def plant_subagent_boundary(fix, agent: str = "a149262d8b6a1601f") -> None:
    sub = fix.transcript.with_suffix("") / "subagents"
    sub.mkdir(parents=True, exist_ok=True)
    (sub / ("agent-%s.jsonl" % agent)).write_text(
        json.dumps({"type": "user", "isSidechain": True, "message": {"content": "go"}})
        + "\n"
        + json.dumps(boundary(True, agent))
        + "\n",
        encoding="utf-8",
    )


def ctx_fresh(fix):
    path = fix.stem(".state-deadbeef.json")
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8")).get("ctx_fresh")


def test_r16_a_subagent_compaction_in_the_measured_shape_orders_nothing(wl):  # noqa: F811
    """CONTROL, the payload measured at 19:01:44Z: the LEAD's session_id and transcript_path, NO agent_id, and the boundary only in a subagents/agent-X.jsonl. Before R.16 this wrote the lead's post-compact row, carried the order and stamped the lead's ctx_fresh."""
    wl.plant_state("## Next action\n\nkeep going")
    plant_subagent_boundary(wl)
    text = compact(wl)
    assert "STOP-HOOK RETRO" not in text, text[-600:]
    assert ledger_rows(wl) == [], ledger_rows(wl)
    assert ctx_fresh(wl) is None, ctx_fresh(wl)
    assert text.startswith("This compaction is sub-agent a149262d8b6a1601f's"), text[:300]


def test_r16_inverse_a_lead_boundary_orders_one_row(wl):  # noqa: F811
    wl.plant_state("## Next action\n\nkeep going")
    plant_subagent_boundary(wl)
    wl.append_transcript(boundary(False))
    text = compact(wl)
    assert "--retro-brief deadbeef post-compact" in text, text[-600:]
    assert [(r["ev"], r["band"]) for r in ledger_rows(wl)] == [("ordered", "post-compact")]
    assert (ctx_fresh(wl) or {}).get("why") == "post-compact", ctx_fresh(wl)
    assert "sub-agent" not in text[:200], text[:200]


def test_r16_an_old_lead_boundary_is_unknown_and_orders_nothing(wl):  # noqa: F811
    """The Decision: an owner that cannot be determined orders no retro and leaves ctx_fresh alone. The lead's own boundary 16:25Z was 2.5 hours old at 19:01Z."""
    wl.plant_state("## Next action\n\nkeep going")
    wl.append_transcript(boundary(False, ago=9000))
    text = compact(wl)
    assert "STOP-HOOK RETRO" not in text, text[-600:]
    assert ledger_rows(wl) == []
    assert ctx_fresh(wl) is None
    assert "sub-agent" not in text[:200], text[:200]


def test_r16_mutant_the_agent_id_only_guard_lets_the_control_write_a_row(wl, tmp_path):  # noqa: F811
    """MUTANT: revert handle_post_compact's attribution to R.12's `not event.get("agent_id")` guard in a copy of the stop directory; the measured-shape control then writes the lead's row again."""
    src = wl.hook.parent
    dst = tmp_path / "hooks" / "stop"
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(
        src.parent / "context", dst.parent / "context", ignore=shutil.ignore_patterns("__pycache__")
    )
    checks = dst / "wl_checks.py"
    body = checks.read_text(encoding="utf-8")
    real = "owner = _compaction_owner(event, sid)"
    assert real in body, "the attribution call moved; update the mutant"
    checks.write_text(
        body.replace(real, 'owner = "agent:x" if event.get("agent_id") else "lead"', 1),
        encoding="utf-8",
    )
    wl.hook = dst / wl.hook.name
    wl.plant_state("## Next action\n\nkeep going")
    plant_subagent_boundary(wl)
    text = compact(wl)
    assert "STOP-HOOK RETRO" in text, text[-600:]
    assert [(r["ev"], r["band"]) for r in ledger_rows(wl)] == [("ordered", "post-compact")]


def test_r17_the_brief_window_starts_at_the_last_saved_retro(wl):  # noqa: F811
    """CONTROL: before R.17 the window and `since` started at the newest `ordered` row, here the unreviewed post-compact at 12:00Z, which hid the 11:00Z block."""
    wl.stem(".blocklog-deadbeef.jsonl").write_text(
        json.dumps({"at": "2026-09-24T11:00:00Z", "key": "unreviewed", "named": [], "judge": {}})
        + "\n"
        + json.dumps({"at": "2026-09-24T09:00:00Z", "key": "reviewed", "named": [], "judge": {}})
        + "\n"
    )
    plant_rows(
        wl,
        ordered("late", 0, 100, at="2026-09-24T10:00:00Z"),
        {"ev": "saved", "session": "deadbeef", "band": "late", "item": "aaaa0001"},
        ordered("post-compact", 100, 300, at="2026-09-24T12:00:00Z"),
        ordered("early", 300, 400, at="2026-09-24T13:00:00Z"),
    )
    got = wl.cli("--retro-brief", "deadbeef", "early")
    assert got.rc == 0, got.err[:300]
    assert "bytes 100-400" in got.out, got.out[:800]
    assert "led by unreviewed: 1" in got.out, got.out
    assert "reviewed: 1" not in got.out.replace("unreviewed: 1", ""), got.out


def test_r17_a_voided_pair_gets_no_item_and_can_be_ordered_again(wl):  # noqa: F811
    """CONTROL: before R.17 there was no `voided` event, so sync tracked the misattributed row and the dedupe key stayed taken."""
    plant_rows(wl, ordered("post-compact", 0, 500))
    spec = importlib.util.spec_from_file_location(
        "_t_ctx_budget", wl.hook.parents[1] / "context" / "ctx_budget.py"
    )
    assert spec is not None
    assert spec.loader is not None
    cb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cb)
    cb.retro_void(wl.proj, "deadbeef", "post-compact", "sub-agent X compaction")
    assert ledger_rows(wl)[-1]["ev"] == "voided", ledger_rows(wl)
    assert cb.retro_ordered(cb.retro_rows(wl.proj), "deadbeef", "post-compact") is None
    wl.brief_now()
    wl.hand_now()
    wl.say("all done")
    got = wl.run()
    assert retro_items(wl) == [], got.out[:400]
    assert not [r for r in ledger_rows(wl) if r["ev"] == "tracked"], ledger_rows(wl)
    wl.plant_state("## Next action\n\nkeep going")
    wl.append_transcript(boundary(False))
    text = compact(wl)
    assert "--retro-brief deadbeef post-compact" in text, text[-600:]
    live = [r for r in ledger_rows(wl) if r["ev"] == "ordered"]
    assert len(live) == 2, live
    assert live[-1]["from_off"] == 0, live[-1]


# ---- SessionStart source=compact is attributed too (retro writer A's finding #d85ee, second retro) ----


def session_start(fix, source: str) -> None:
    """The SessionStart payload in the measured PostCompact shape: the LEAD's session_id and transcript_path, no agent_id."""
    payload = {
        "session_id": fix.sid,
        "cwd": str(fix.proj),
        "transcript_path": str(fix.transcript),
        "source": source,
    }
    env = dict(fix.env)
    env["CLAUDE_PROJECT_DIR"] = str(fix.proj)
    got = fix.python(["--session-start"], stdin=json.dumps(payload), env=env)
    assert got.rc == 0, got.err[:300]


def test_session_start_compact_of_a_subagent_leaves_ctx_fresh_alone(wl):  # noqa: F811
    """CONTROL: before the fix handle_session_start called mark_context_fresh for source=compact with no attribution, so a sub-agent's compaction stamped the lead's ctx_fresh here even after R.16 gated handle_post_compact."""
    plant_subagent_boundary(wl)
    session_start(wl, "compact")
    assert ctx_fresh(wl) is None, ctx_fresh(wl)


def test_session_start_compact_of_the_lead_marks_ctx_fresh(wl):  # noqa: F811
    plant_subagent_boundary(wl)
    wl.append_transcript(boundary(False))
    session_start(wl, "compact")
    assert (ctx_fresh(wl) or {}).get("why") == "session-start:compact", ctx_fresh(wl)


def test_session_start_of_a_new_session_still_marks_ctx_fresh(wl):  # noqa: F811
    """A startup or resume is always the lead's own: no attribution is asked for."""
    plant_subagent_boundary(wl)
    session_start(wl, "startup")
    assert (ctx_fresh(wl) or {}).get("why") == "session-start:startup", ctx_fresh(wl)
