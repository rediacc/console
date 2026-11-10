"""wl_hints: corpus parsing, round-robin selection, and the stop-report wiring.

Ported from PLAN-stop-hook-behavioral-hints.md's own task list: the in-process unit tests drive `hint_pick` directly with `random.Random(seed)` (the same determinism seam `outq_drain`'s own tests already use), and the subprocess tests prove the wiring fires on a loud stop, stays silent on a clean one, and stays silent on a blocked or empty-corpus stop -- the vacuity and liveness controls the plan's Section 6.3 demands.
"""

from __future__ import annotations

import json
import pathlib
import random
from typing import Any

from rediacc_hooks.tests import wlfix

REAL_ROOT = pathlib.Path(__file__).resolve().parents[3]
REAL_HINTS = str(REAL_ROOT / "docs" / "agent-reference" / "HINTS.md")


def _hints():
    return wlfix.import_wl("wl_hints")


# ---- load_corpus ------------------------------------------------------------


def test_load_corpus_reads_the_real_thirteen_entries_clean():
    """13 total since D-M1 retired `haiku-for-derived-work` and added `haiku-read-only-only`
    in its place (agent/DECISIONS.md D-M1); 12 of the 13 are `active`, the retired one kept
    with its history intact per HINTS.md's own precedent."""
    h = _hints()
    entries, errors = h.load_corpus(REAL_HINTS)
    assert errors == [], errors
    assert len(entries) == 13, [e["id"] for e in entries]
    ids = [e["id"] for e in entries]
    assert len(set(ids)) == 13, "duplicate Hint-Id in the real corpus"
    statuses = {e["id"]: e["status"] for e in entries}
    assert statuses["haiku-for-derived-work"] == "retired", statuses
    active = [e for e in entries if e["id"] != "haiku-for-derived-work"]
    assert len(active) == 12, [e["id"] for e in active]
    for e in entries:
        assert e["heading"], e
        assert e["source"], e["id"]
        assert e["status"] in ("active", "retired"), e["id"]
    for e in active:
        assert e["status"] == "active", e["id"]


def test_load_corpus_missing_file_is_silent_not_an_error():
    """A missing corpus reads as NOT CONFIGURED, matching `wl_agents.load_corpus`'s own precedent for a missing agents directory: every test fixture that has never pointed WORKLIST_HINTS_FILE at a real file must not spuriously report a broken corpus."""
    h = _hints()
    entries, errors = h.load_corpus("/no/such/path/HINTS.md")
    assert entries == []
    assert errors == []


def test_load_corpus_an_unreadable_file_is_still_a_real_error(tmp_path):
    """The other half: a corpus that EXISTS but cannot be read (not merely absent) is a genuine, loud error."""
    h = _hints()
    path = tmp_path / "hints.md"
    path.write_text(
        "## x\nHint-Id: x\nSource: file:CLAUDE.md:1\nStatus: active\n", encoding="utf-8"
    )
    path.chmod(0o000)
    try:
        entries, errors = h.load_corpus(str(path))
        assert entries == []
        assert len(errors) == 1
        assert "cannot read" in errors[0]
    finally:
        path.chmod(0o644)


def test_load_corpus_entry_with_no_hint_id_is_an_error_not_a_silent_skip(tmp_path):
    h = _hints()
    path = tmp_path / "hints.md"
    path.write_text("## A heading with no trailer at all\n\nbody only\n", encoding="utf-8")
    _entries, errors = h.load_corpus(str(path))
    assert len(errors) == 1
    assert "no Hint-Id" in errors[0]


def test_load_corpus_entry_with_no_source_is_an_error(tmp_path):
    h = _hints()
    path = tmp_path / "hints.md"
    path.write_text(
        "## A heading\nHint-Id: x\nStatus: active\n\nbody\n",
        encoding="utf-8",
    )
    _entries, errors = h.load_corpus(str(path))
    assert len(errors) == 1
    assert "no Source" in errors[0]


def test_load_corpus_duplicate_hint_id_is_an_error(tmp_path):
    h = _hints()
    path = tmp_path / "hints.md"
    path.write_text(
        "## First\nHint-Id: dup\nSource: file:CLAUDE.md:1\nStatus: active\n\n"
        "## Second\nHint-Id: dup\nSource: file:CLAUDE.md:2\nStatus: active\n",
        encoding="utf-8",
    )
    _entries, errors = h.load_corpus(str(path))
    assert any("duplicate Hint-Id" in e for e in errors), errors


def test_load_corpus_a_retired_entry_still_parses_but_is_excluded_from_pick(tmp_path):
    h = _hints()
    path = tmp_path / "hints.md"
    path.write_text(
        "## Live one\nHint-Id: live\nSource: file:CLAUDE.md:1\nStatus: active\n\n"
        "## Dead one\nHint-Id: dead\nSource: file:CLAUDE.md:2\nStatus: retired\n",
        encoding="utf-8",
    )
    entries, errors = h.load_corpus(str(path))
    assert errors == []
    assert {e["id"] for e in entries} == {"live", "dead"}
    ledger: dict[Any, Any] = {}
    for _ in range(10):
        picked = h.hint_pick(entries, ledger, rng=random.Random(1))
        assert picked[0]["id"] == "live", "a retired entry was ever picked"


def test_load_corpus_a_heading_inside_a_fenced_block_is_not_a_phantom_entry(tmp_path):
    h = _hints()
    path = tmp_path / "hints.md"
    path.write_text(
        "## Real one\nHint-Id: real\nSource: file:CLAUDE.md:1\nStatus: active\n\n"
        "body with an example:\n\n```\n## This looks like a heading but is not\n```\n",
        encoding="utf-8",
    )
    entries, errors = h.load_corpus(str(path))
    assert errors == []
    assert [e["id"] for e in entries] == ["real"]


def test_load_corpus_strips_a_trailing_style_ok_marker_from_the_source_value(tmp_path):
    h = _hints()
    path = tmp_path / "hints.md"
    path.write_text(
        "## Heading\nHint-Id: x\nSource: trap:some-id-with-you-in-it <!-- style-ok -->\nStatus: active\n",
        encoding="utf-8",
    )
    entries, _errors = h.load_corpus(str(path))
    assert entries[0]["source"] == "trap:some-id-with-you-in-it"


# ---- hint_pick: round-robin, randomized, cycle-bounded -----------------------


def test_hint_pick_full_cycle_coverage_across_fifty_seeds():
    h = _hints()
    entries, _errors = h.load_corpus(REAL_HINTS)
    for seed in range(50):
        ledger: dict[Any, Any] = {}
        seen = set()
        for _ in range(12):
            picked = h.hint_pick(entries, ledger, rng=random.Random(seed))
            seen.add(picked[0]["id"])
        assert len(seen) == 12, "seed %d: did not cover the full corpus in one cycle" % seed


def test_hint_pick_never_repeats_inside_a_single_cycle():
    h = _hints()
    entries, _errors = h.load_corpus(REAL_HINTS)
    ledger: dict[Any, Any] = {}
    seen = []
    for i in range(12):
        picked = h.hint_pick(entries, ledger, rng=random.Random(7 + i))
        seen.append(picked[0]["id"])
    assert len(set(seen)) == 12, seen


def test_hint_pick_never_repeats_across_a_cycle_boundary():
    h = _hints()
    entries, _errors = h.load_corpus(REAL_HINTS)
    ledger: dict[Any, Any] = {}
    last_of_cycle_one = None
    for i in range(12):
        picked = h.hint_pick(entries, ledger, rng=random.Random(100 + i))
        last_of_cycle_one = picked[0]["id"]
    first_of_cycle_two = h.hint_pick(entries, ledger, rng=random.Random(200))[0]["id"]
    assert first_of_cycle_two != last_of_cycle_one


def test_hint_pick_entropy_control_different_seeds_pick_different_first_hints():
    """CONTROL: proves the selection is genuinely randomized, not a fixed order that happens to look shuffled."""
    h = _hints()
    entries, _errors = h.load_corpus(REAL_HINTS)
    firsts = set()
    for seed in range(30):
        picked = h.hint_pick(entries, {}, rng=random.Random(seed))
        firsts.add(picked[0]["id"])
    assert len(firsts) > 1, "30 different seeds all picked the same first hint"


def test_hint_pick_returns_none_when_the_corpus_has_nothing_active():
    h = _hints()
    assert h.hint_pick([], {}, rng=random.Random(0)) is None
    retired_only = [{"id": "x", "heading": "h", "source": "s", "status": "retired"}]
    assert h.hint_pick(retired_only, {}, rng=random.Random(0)) is None


def test_hint_pick_index_and_total_match_the_active_corpus_size():
    h = _hints()
    entries, _errors = h.load_corpus(REAL_HINTS)
    picked = h.hint_pick(entries, {}, rng=random.Random(0))
    _entry, index, total = picked
    assert total == 12
    assert 1 <= index <= 12


def test_render_names_heading_id_and_source_all_refutable_in_one_look():
    h = _hints()
    entry = {"heading": "Do the thing", "id": "do-the-thing", "source": "file:CLAUDE.md:1"}
    text = h.render(entry, 3, 12)
    assert "3 of 12" in text
    assert "Do the thing" in text
    assert "do-the-thing" in text
    assert "file:CLAUDE.md:1" in text


# ---- the wiring: fires on a loud stop, silent on a clean or blocked one -----


def test_hint_fires_on_a_loud_allow_stop(wl):
    wl.env["WORKLIST_HINTS_FILE"] = REAL_HINTS
    wl.brief_now()
    wl.hand_now()
    # A deferred item of this session's own makes the allow LOUD (its guide leads the report); a peer's brief did until the peer listing was deleted 2026-09-24.
    wl.add_item("- [?] (deadbeef) keep the flag? DEFAULT: keep it")
    wl.say("answer\n\n## Remaining\n- the flag decision, deferred with a default")
    got = wl.run()
    assert "TIP (hint" in got.out, got.out[-600:]


def test_hint_absent_on_a_genuinely_silent_clean_stop(wl):
    wl.env["WORKLIST_HINTS_FILE"] = REAL_HINTS
    # The popup reminder (wl_popup.py) is a separate, deliberate exception to this same silence, on a ~20% independent roll -- pinned off here because this control is about the rotating hint's own gate, not about that roll.
    wl.env["WORKLIST_POPUP_PROBABILITY"] = "0"
    wl.brief_now()
    wl.hand_now()
    wl.run()
    got2 = wl.run()
    assert got2.out == "", repr(got2.out)


def test_hint_rides_a_blocked_stop_at_most_once_per_30_min(wl):
    """Since 2026-09-24 (agent/plans/PLAN-stop-hook-continuity.md P0.5) a block is an output the hint may ride, because a busy session otherwise never sees the corpus. INVERSE in the same case: a second block inside BLOCK_HINT_MIN carries none, so the tip cannot become an every-stop line."""
    wl.env["WORKLIST_HINTS_FILE"] = REAL_HINTS
    wl.add_item("- [ ] (deadbeef) open thing")
    got = wl.run()
    assert '"decision": "block"' in got.out, got.out[:400]
    assert "TIP (hint" in got.out, got.out[-600:]
    wl.newturn()
    wl.say("still working")
    again = wl.run()
    assert '"decision": "block"' in again.out, again.out[:400]
    assert "TIP (hint" not in again.out, again.out[-600:]


def test_hint_absent_with_an_empty_corpus_proves_the_corpus_drives_the_line(wl):
    """NEGATIVE CONTROL, per Section 6.3's H5: point the seam at a corpus with no active entries and confirm the tip disappears with everything else unchanged, proving the corpus -- not some other condition -- is what produces the line."""
    empty = wl.base / "empty-hints.md"
    empty.write_text("# empty corpus\n", encoding="utf-8")
    wl.env["WORKLIST_HINTS_FILE"] = str(empty)
    wl.brief_now()
    wl.hand_now()
    wl.add_item("- [?] (deadbeef) keep the flag? DEFAULT: keep it")
    wl.say("answer\n\n## Remaining\n- the flag decision, deferred with a default")
    got = wl.run()
    assert "TIP (hint" not in got.out, got.out[-600:]
    assert "WORKLIST GUIDE" in got.out, "the rest of the stop still ran"


def test_hint_missing_corpus_never_blocks_and_reports_nothing(wl):
    missing = str(wl.base / "no-such-hints.md")
    wl.env["WORKLIST_HINTS_FILE"] = missing
    wl.brief_now()
    wl.hand_now()
    wl.add_item("- [?] (deadbeef) keep the flag? DEFAULT: keep it")
    wl.say("answer\n\n## Remaining\n- the flag decision, deferred with a default")
    got = wl.run()
    assert got.rc == 0, got.out
    assert '"decision": "block"' not in got.out, got.out
    assert "Hint corpus problem" not in got.out, got.out


def test_hint_corpus_error_is_reported_and_never_blocks(wl):
    """A corpus that EXISTS but cannot be parsed cleanly -- as opposed to one that is simply absent -- is the real error this advisory exists to surface."""
    broken = wl.base / "broken-hints.md"
    broken.write_text("## a heading with no trailer at all\n\nbody\n", encoding="utf-8")
    wl.env["WORKLIST_HINTS_FILE"] = str(broken)
    wl.brief_now()
    wl.hand_now()
    wl.add_item("- [?] (deadbeef) keep the flag? DEFAULT: keep it")
    wl.say("answer\n\n## Remaining\n- the flag decision, deferred with a default")
    got = wl.run()
    assert got.rc == 0, got.out
    assert '"decision": "block"' not in got.out, got.out
    assert "Hint corpus problem" in got.out, got.out


# ---- the session-contribution channel ---------------------------------------


def test_propose_writes_only_the_ledger_and_never_touches_hints_md(tmp_path):
    h = _hints()
    (tmp_path / "docs" / "agent-reference").mkdir(parents=True)
    hints_file = tmp_path / "docs" / "agent-reference" / "HINTS.md"
    hints_file.write_text("# corpus\n", encoding="utf-8")
    before = hints_file.read_text(encoding="utf-8")
    row = h.propose(str(tmp_path), "d778be9d", "a lesson worth keeping", "incident-1")
    after = hints_file.read_text(encoding="utf-8")
    assert after == before, "propose() touched HINTS.md"
    ledger = tmp_path / "agent" / "ledgers" / "hint-proposals.jsonl"
    assert ledger.is_file()
    assert row["text"] == "a lesson worth keeping"
    assert row["source"] == "incident-1"


def _corpus(tmp_path, body):
    (tmp_path / "docs" / "agent-reference").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "agent-reference" / "HINTS.md").write_text(body, encoding="utf-8")


def _resolution(tmp_path, pid, pointer):
    ledger = tmp_path / "agent" / "ledgers" / "hint-resolutions.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"by": "d778be9d", "at": "x", "id": pid, "pointer": pointer}) + "\n")


def test_pending_control_reworded_or_copied_text_with_no_cite_stays_pending(tmp_path, monkeypatch):
    """CONTROL (PLAN-experience-feedback.md C2b): text is never matched. Before C2b an exact copy left the count by substring; a reworded promotion never did. Both now stay until an entry cites the id."""
    monkeypatch.delenv("WORKLIST_HINTS_FILE", raising=False)
    h = _hints()
    _corpus(
        tmp_path,
        "## already promoted\nHint-Id: x\nSource: file:CLAUDE.md:1\nStatus: active\n\n"
        "## Promoted, in other words\nHint-Id: y\nSource: file:CLAUDE.md:1\nStatus: active\n",
    )
    h.propose(str(tmp_path), "d778be9d", "already promoted", "")
    h.propose(str(tmp_path), "d778be9d", "promoted with different words", "")
    pending = h.pending_proposals(str(tmp_path))
    assert [p["text"] for p in pending] == ["already promoted", "promoted with different words"]


def test_pending_a_proposal_line_citing_the_id_takes_it(tmp_path, monkeypatch):
    monkeypatch.delenv("WORKLIST_HINTS_FILE", raising=False)
    h = _hints()
    first = h.propose(str(tmp_path), "d778be9d", "lesson one", "")
    h.propose(str(tmp_path), "d778be9d", "lesson two", "")
    _corpus(
        tmp_path,
        "## Lesson one, reworded\nHint-Id: one\nSource: file:CLAUDE.md:1\nStatus: active\n"
        "Proposal: %s, 00000000\n" % first["id"],
    )
    assert [p["text"] for p in h.pending_proposals(str(tmp_path))] == ["lesson two"]


def _plant_guard(guards, stem):
    """A guard the shared resolver (trap_registry.pointer_problem) accepts: loaded by the package's stems() and tested by a sibling suite that names it."""
    (guards / "__init__.py").write_text(
        "import pathlib\n\n\ndef stems():\n"
        "    return sorted(p.stem for p in pathlib.Path(__file__).parent.glob('block_*.py'))\n",
        encoding="utf-8",
    )
    (guards / ("%s.py" % stem)).write_text("RULE = 1\n", encoding="utf-8")
    (guards / ("test-%s.py" % stem)).write_text(
        "# tests %s\ndef test_it():\n    pass\n" % stem, encoding="utf-8"
    )


def test_pending_control_a_resolution_with_a_dead_pointer_stays_pending(tmp_path, monkeypatch):
    """CONTROL: a resolution row counts only while its pointer resolves; a guard that does not exist (or was deleted) puts the proposal back."""
    monkeypatch.delenv("WORKLIST_HINTS_FILE", raising=False)
    h = _hints()
    row = h.propose(str(tmp_path), "d778be9d", "a lesson a guard carries", "")
    _resolution(tmp_path, row["id"], "guard:block_no_such_guard")
    assert [p["id"] for p in h.pending_proposals(str(tmp_path))] == [row["id"]]
    guards = tmp_path / ".claude" / "rediacc_hooks" / "guards"
    guards.mkdir(parents=True)
    _plant_guard(guards, "block_no_such_guard")
    assert h.pending_proposals(str(tmp_path)) == []
    (guards / "block_no_such_guard.py").unlink()
    assert [p["id"] for p in h.pending_proposals(str(tmp_path))] == [row["id"]]


def test_proposal_id_is_derived_for_old_rows_and_written_for_new_ones(tmp_path):
    h = _hints()
    old = {"by": "d778be9d", "at": "2026-10-24T04:27:51Z", "text": "an old lesson"}
    assert h.proposal_id(old) == h.proposal_id(dict(old)), "a derived id must be stable"
    assert len(h.proposal_id(old)) == 8
    assert h.proposal_id(dict(old, text="another")) != h.proposal_id(old)
    row = h.propose(str(tmp_path), "d778be9d", "a new lesson", "")
    assert row["id"] == h.proposal_id({k: v for k, v in row.items() if k != "id"})
    assert [r["id"] for r in h.proposals(str(tmp_path))] == [row["id"]]


def test_pending_note_names_the_curator_and_its_run_directory():
    h = _hints()
    note = h.pending_note("d778be9d-aaaa", 3)
    assert note.startswith("3 hint proposal(s)"), note
    assert "lesson-curator" in note, note
    assert "agent/d778be9d/lessons/e" in note, note
    assert "--hint-resolve d778be9d <id> <kind>:<token>" in note, note


def test_hint_resolve_cli_refuses_an_unknown_id_and_a_dead_pointer_then_records_a_live_one(wl):
    wl.env["WORKLIST_HINTS_FILE"] = str(wl.proj / "no-hints.md")
    proposed = wl.cli("--hint-propose", "deadbeef", "a lesson a guard now carries")
    assert proposed.rc == 0, proposed.err
    pid = proposed.out.rsplit("(id ", 1)[1].split(")")[0]
    ledger = wl.proj / "agent" / "ledgers" / "hint-resolutions.jsonl"
    unknown = wl.cli("--hint-resolve", "deadbeef", "0000beef", "guard:block_planted")
    assert unknown.rc == 2, unknown.err
    assert "no hint proposal has id 0000beef" in unknown.err, unknown.err
    dead = wl.cli("--hint-resolve", "deadbeef", pid, "guard:block_planted")
    assert dead.rc == 2, dead.err
    assert "not a live enforcer" in dead.err, dead.err
    assert not ledger.exists()
    guards = wl.proj / ".claude" / "rediacc_hooks" / "guards"
    guards.mkdir(parents=True, exist_ok=True)
    _plant_guard(guards, "block_planted")
    live = wl.cli("--hint-resolve", "deadbeef", pid, "guard:block_planted")
    assert live.rc == 0, live.err
    rows = [json.loads(ln) for ln in ledger.read_text(encoding="utf-8").splitlines()]
    assert [(r["id"], r["pointer"]) for r in rows] == [(pid, "guard:block_planted")]
    assert _hints().pending_proposals(str(wl.proj)) == []


def test_hint_propose_cli_round_trip_via_worklist(wl):
    wl.env["WORKLIST_HINTS_FILE"] = REAL_HINTS
    wl.brief_now()
    wl.hand_now()
    result = wl.cli("--hint-propose", "deadbeef", "a session-proposed lesson", "SOURCE:", "note")
    assert result.rc == 0, result.stderr
    ledger = wl.proj / "agent" / "ledgers" / "hint-proposals.jsonl"
    assert ledger.is_file()
    assert "a session-proposed lesson" in ledger.read_text(encoding="utf-8")


# ---- trapguard retirement report (wl_trapfires, PLAN-trap-enforcement.md W4-retire-report) ----------------------------------------------------


def _trapfires():
    return wlfix.import_wl("wl_trapfires")


def _plant_fires(base: pathlib.Path, rule: str, n: int) -> None:
    base.mkdir(parents=True, exist_ok=True)
    with (base / "fires.jsonl").open("a", encoding="utf-8") as fh:
        for i in range(n):
            fh.write('{"rule": "%s", "session": "s%d", "ts": "2026-10-04T00:00:00Z"}\n' % (rule, i))


def test_trapfires_41_unconfirmed_fires_produce_the_note(tmp_path):
    t = _trapfires()
    _plant_fires(tmp_path, "rebase-unverified", t.RETIRE_FIRES + 1)
    note = t.retire_note(tmp_path)
    assert "trapguard retirement candidates" in note, note
    assert "rebase-unverified" in note, note
    assert "41 fires" in note, note


def test_trapfires_41_fires_with_one_confirmation_are_silent(tmp_path):
    t = _trapfires()
    _plant_fires(tmp_path, "rebase-unverified", t.RETIRE_FIRES + 1)
    t.confirm("rebase-unverified", tmp_path)
    assert t.retire_note(tmp_path) == ""


def test_trapfires_exactly_40_fires_are_silent(tmp_path):
    t = _trapfires()
    _plant_fires(tmp_path, "rebase-unverified", t.RETIRE_FIRES)
    assert t.retire_note(tmp_path) == ""


def test_trapfires_a_confirmation_for_another_rule_does_not_silence_this_one(tmp_path):
    t = _trapfires()
    _plant_fires(tmp_path, "rebase-unverified", t.RETIRE_FIRES + 1)
    t.confirm("bws-auth-failure", tmp_path)
    assert "rebase-unverified" in t.retire_note(tmp_path)


def test_trapfires_the_note_reaches_a_clean_stop(wl):
    """The wiring, not just the arithmetic: a planted ledger under the fixture's TRAPGUARD_DIR must surface on an allowed stop."""
    wl.say("All finished.")
    wl.brief_now()
    wl.hand_now()
    _plant_fires(pathlib.Path(wl.env["TRAPGUARD_DIR"]), "rebase-unverified", 41)
    wl.check("allow", "trapguard retirement candidates", "a retirement candidate is advised")


def test_trapfires_no_candidate_leaves_a_clean_stop_quiet(wl):
    wl.say("All finished.")
    wl.brief_now()
    wl.hand_now()
    _plant_fires(pathlib.Path(wl.env["TRAPGUARD_DIR"]), "rebase-unverified", 40)
    wl.check_absent("allow", "trapguard retirement candidates", "40 fires are not a candidate")
