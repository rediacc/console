"""The TICK line in the writers-now brief, parsed onto the report index row (box T6 of agent/plans/PLAN-tick-tracking.md).

The documented form is the tested form: the TICK example is read straight out of `.claude/commands/writers-now.md`. `wl_report.capture` stores `boxes` on the index row, the five legacy report bodies of round 1104-1 included (through the T1 prose reader).

THE CONTROL is the old Report template ("one block per box signature"), which parses to zero boxes.
"""

from __future__ import annotations

import pathlib

from rediacc_hooks.tests import wlfix

P = wlfix.import_wl("wl_planbox")
RP = wlfix.import_wl("wl_report")
REPO = pathlib.Path(__file__).resolve().parents[3]
DOC = REPO / ".claude" / "commands" / "writers-now.md"
FIX = pathlib.Path(__file__).resolve().parent / "tick_tracking_fixtures" / "planbox"
LEGACY = {
    "live-proof-ladder": "7692f2db",
    "drills-upgrade": "1d17b634",
    "privdrop-probe": "afa91934",
    "sampler": "339bf791",
    "executor-seam": "3d256594",
}
OLD_TEMPLATE = """Report, one block per box signature:
  <sig> <done|present|partial|untouched|blocked-on-dep>
  commits: <shas>
  commands: <each command run, with its exit code>
  remains: <the half still open and the exact command or decision that closes it, or "nothing">
"""


def _example():
    """The doc's TICK example: the `TICK PLAN-...` line and its `close:` line."""
    lines = DOC.read_text(encoding="utf-8").splitlines()
    i = next(n for n, x in enumerate(lines) if x.strip().startswith("TICK PLAN-"))
    return "\n".join(lines[i : i + 2]) + "\n"


def _capture(store, body, agent):
    return RP.capture(
        store,
        "0101-1",
        agent_id="a%s0123456789abcdef" % agent,
        agent_type="general-purpose",
        agent_name=agent,
        session="deadbeef",
        body=body,
        transcript="",
    )


def test_the_documented_tick_example_parses_to_one_box():
    rows = P.parse_tick(_example())
    assert [(r.plan, r.sig, r.state, r.landed, r.owed, r.legacy) for r in rows] == [
        (
            "PLAN-rediaccfile-unprivileged.md",
            "afa91934",
            "partial",
            ("C1",),
            (("C2", "live"),),
            False,
        )
    ]
    assert rows[0].close.startswith("worklist.py --live-proof")


def test_the_documented_grammar_line_is_the_module_grammar():
    assert P.TICK_GRAMMAR in DOC.read_text(encoding="utf-8")


def test_capture_of_two_tick_lines_indexes_two_boxes(tmp_path):
    body = (
        "Both boxes done.\n\n"
        "TICK PLAN-a.md#0123abcd done commits=abc1234 landed=all owed=-\n"
        "  close: nothing\n"
        "TICK PLAN-b.md#89abcdef partial commits=def5678,1234abc landed=C1 owed=C2:live\n"
        "  close: worklist.py --live-proof deadbeef agent/plans/PLAN-b.md 89abcdef --write\n"
    )
    entry = _capture(tmp_path, body, "two")
    assert [(b["plan"], b["sig"], b["state"], b["commits"]) for b in entry["boxes"]] == [
        ("PLAN-a.md", "0123abcd", "done", ["abc1234"]),
        ("PLAN-b.md", "89abcdef", "partial", ["def5678", "1234abc"]),
    ]
    assert entry["boxes"][1]["owed"] == [["C2", "live"]]
    # Review 9079c2c0.3: `owed=-` is an empty list and `landed=all` stays the word, not a leftover dash.
    assert (entry["boxes"][0]["landed"], entry["boxes"][0]["owed"]) == ("all", [])
    assert RP.read_index(tmp_path)[-1]["boxes"] == entry["boxes"]


def test_the_five_legacy_bodies_index_their_box(tmp_path):
    for writer, sig in LEGACY.items():
        body = (FIX / ("%s.report" % writer)).read_text(encoding="utf-8")
        entry = _capture(tmp_path, body, writer)
        assert [b["sig"] for b in entry["boxes"]] == [sig], writer
        assert entry["boxes"][0]["legacy"] is True


def test_a_capture_with_no_tick_line_indexes_an_empty_list(tmp_path):
    assert _capture(tmp_path, "Nothing here names a box.", "none")["boxes"] == []


def _ticks(n, commits=1):
    return "".join(
        "TICK PLAN-a.md#%08x done commits=%s landed=all owed=-\n  close: nothing\n"
        % (0x10000000 + i, ",".join("%07x" % (0xA000000 + i * 16 + c) for c in range(commits)))
        for i in range(n)
    )


def test_seven_boxes_are_capped_and_marked_and_the_audit_reads_all_seven(tmp_path, monkeypatch):
    """Review 9079c2c0.1-2: past BOXES_MAX the index keeps six and says it dropped one; wl_boxaudit then reads the body's seven."""
    audit = wlfix.import_wl("wl_boxaudit")
    entry = _capture(tmp_path, "Seven boxes.\n\n" + _ticks(RP.BOXES_MAX + 1), "seven")
    assert len(entry["boxes"]) == RP.BOXES_MAX
    assert entry["boxes_capped"] is True
    monkeypatch.setattr(RP, "store_root", lambda _root: tmp_path)
    sigs = [row.sig for _rid, row in audit.report_rows(tmp_path)]
    assert len(sigs) == RP.BOXES_MAX + 1
    assert "%08x" % (0x10000000 + RP.BOXES_MAX) in sigs


def test_five_commits_are_capped_and_marked_and_the_audit_reads_all_five(tmp_path, monkeypatch):
    audit = wlfix.import_wl("wl_boxaudit")
    entry = _capture(tmp_path, _ticks(1, commits=RP.BOX_COMMITS_MAX + 1), "commits")
    assert len(entry["boxes"][0]["commits"]) == RP.BOX_COMMITS_MAX
    assert entry["boxes_capped"] is True
    monkeypatch.setattr(RP, "store_root", lambda _root: tmp_path)
    [(_rid, row)] = audit.report_rows(tmp_path)
    assert len(row.commits) == RP.BOX_COMMITS_MAX + 1


def test_control_at_the_bounds_nothing_is_capped(tmp_path):
    entry = _capture(tmp_path, _ticks(RP.BOXES_MAX), "bounds")
    assert len(entry["boxes"]) == RP.BOXES_MAX
    assert "boxes_capped" not in entry
    entry = _capture(tmp_path, _ticks(1, commits=RP.BOX_COMMITS_MAX), "bound-commits")
    assert len(entry["boxes"][0]["commits"]) == RP.BOX_COMMITS_MAX
    assert "boxes_capped" not in entry


def test_fit_shrinks_boxes_under_the_line_cap_and_marks_them():
    """The `_fit` shrink branch: a row over INDEX_LINE_MAX with the title already empty loses boxes from the end, and says so."""
    obj = {
        "ev": "report",
        "id": "x",
        "title": "",
        "transcript": "",
        "boxes": [
            {"plan": "PLAN-%s.md" % ("p" * 120), "sig": "%08x" % i, "commits": []}
            for i in range(RP.BOXES_MAX)
        ],
    }
    got = RP._fit(obj)
    assert 0 < len(got["boxes"]) < RP.BOXES_MAX
    assert got["boxes_capped"] is True
    assert len(RP.json.dumps(got, separators=(",", ":")).encode()) < RP.INDEX_LINE_MAX


def test_the_roster_reads_a_capped_row_from_its_body(tmp_path):
    roster = wlfix.import_wl("wl_roster")
    entry = _capture(tmp_path, _ticks(RP.BOXES_MAX + 1), "roster")
    got = roster._report_boxes(tmp_path, entry)
    assert len(got) == RP.BOXES_MAX + 1


def test_control_the_old_report_template_parses_to_zero_boxes():
    assert P.parse_tick(OLD_TEMPLATE) == []
    assert "one block per box signature" not in DOC.read_text(encoding="utf-8")
