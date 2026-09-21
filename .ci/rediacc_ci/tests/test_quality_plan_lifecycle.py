"""`rediacc_ci.quality.plan_lifecycle`, and the three mirrors it carries.

WHY MIRRORS AT ALL. `plan_lifecycle` restates `FINISHED_STATES`, `NOT_STARTED_STATES` and the plan-reference regex rather than importing them from `.claude/hooks/stop`. That is the same trade `plan_housekeeping.record_states` makes and for the same reason: a gate under `.ci` must answer on a checkout where `.claude/` is absent. The cost is three copies of a vocabulary, and the
only thing that makes the cost payable is a test comparing them in BOTH directions, which is what the first three cases below do. A mirror nobody compares is just a second definition.

THE REST OF THE FILE IS THE PURE CORE. `classify`, `folder_of`, `last_touch`, `retention_days` and the nine finding functions take data and return data, so every case here is a literal in, a literal out, with no fixture tree and no git.
"""

import datetime as dt
import pathlib
import tempfile

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import plan_lifecycle as PL

HOOKS = paths.hooks_stop_dir()
TODAY = dt.date(2026, 9, 21)
CONFIG = {"terminal_days": 40, "backlog_days": 90}


def _hook_module(name):
    """The Stop hook module `name`, or a skip that says why.

    A SKIP rather than a failure, because the absence of `.claude/` is exactly the condition the mirrors exist to survive; failing here would make the test demand the thing the design refuses to depend on.
    """
    if not HOOKS.is_dir():
        pytest.skip("%s is absent; the mirrors exist precisely for that case" % HOOKS)
    paths.on_sys_path(HOOKS)
    return pytest.importorskip(name)


# --------------------------------------------------------------------------- The mirrors.


def test_finished_states_mirror_the_hook_in_both_directions():
    hook = _hook_module("wl_planfile")
    assert set(PL.FINISHED_STATES) == set(hook.FINISHED_STATES)


def test_not_started_states_mirror_the_hook_in_both_directions():
    hook = _hook_module("wl_planfile")
    assert set(PL.NOT_STARTED_STATES) == set(hook.NOT_STARTED_STATES)


def test_record_states_mirror_the_record_module():
    hook = _hook_module("wl_planrec")
    assert set(PL.RECORD_STATES) == set(hook.RECORD_STATES)


def test_the_reference_regex_is_a_superset_of_the_hook_one():
    """The two regexes differ ON PURPOSE and the difference is one-directional.

    `wl_planrec.PLAN_REF_RE` learns `agent/plans/` in S2 of the tree-lifecycle plan and this one already has it, so the assertion is containment rather than equality: every legacy path the hook matches must match here, and this one may match more. Equality would red the moment either side moved first, which is exactly the coupling a mirror is supposed to avoid.
    """
    hook = _hook_module("wl_planrec")
    for rel in ("agent/PLAN-x.md", "agent/PLAN-a_b-c.1.md"):
        assert hook.PLAN_REF_RE.fullmatch(rel), rel
        assert PL.PLAN_REF_RE.fullmatch(rel), rel
    for rel in (
        "agent/plans/PLAN-x.md",
        "agent/plans/_done/PLAN-x.md",
        "agent/plans/_removed/PLAN-x.md",
    ):
        assert PL.PLAN_REF_RE.fullmatch(rel), rel


def test_the_plan_folders_mirror_the_hook_in_both_directions():
    """`wl_store.AGENT_PLAN_SUBDIRS` is the same list, relative to `agent/`.

    The two cannot be one list: this module must answer on a checkout with no `.claude/`, and the hook must load with no `.ci` on sys.path. So the mirror is compared here, in the only process that can import both, and in BOTH directions.
    """
    hook = _hook_module("wl_store")
    theirs = ["agent/%s" % sub if sub else "agent" for sub in hook.AGENT_PLAN_SUBDIRS]
    assert list(PL.PLAN_DIRS) == theirs


def test_the_stub_probe_agrees_with_the_hook_on_both_answers():
    """A file the two disagree about is a plan in one reader and a pointer in the other."""
    hook = _hook_module("wl_store")
    assert hook.STUB_PROBE_BYTES == PL.STUB_PROBE_BYTES
    stub = PL.stub_text("agent/PLAN-t.md", "agent/plans/_done/PLAN-t.md", "t")
    plan = "# PLAN: t\nStatus: in-progress\n\n- [ ] a box\n"
    with tempfile.TemporaryDirectory() as tmp:
        for name, text, want in (("stub.md", stub, True), ("plan.md", plan, False)):
            path = pathlib.Path(tmp) / name
            path.write_text(text, encoding="utf-8")
            assert hook.is_plan_stub(path) is want, name
            assert PL.looks_like_stub(text) is want, name


# --------------------------------------------------------------------------- folder_of and is_plan_path.


@pytest.mark.parametrize(
    ("rel", "want"),
    [
        ("agent/PLAN-x.md", "agent"),
        ("agent/plans/PLAN-x.md", "agent/plans"),
        ("agent/plans/_done/PLAN-x.md", "agent/plans/_done"),
        ("agent/plans/_removed/PLAN-x.md", "agent/plans/_removed"),
        ("agent/archive/plans/PLAN-x.md", ""),
        ("agent/abcd1234/STATE.md", ""),
        ("agent/plans/_done/deeper/PLAN-x.md", ""),
        ("docs/PLAN-x.md", ""),
    ],
)
def test_folder_of_matches_the_deepest_legal_folder(rel, want):
    assert PL.folder_of(rel) == want


@pytest.mark.parametrize(
    ("rel", "want"),
    [
        ("agent/PLAN-x.md", True),
        ("agent/plans/_done/PLAN-x.md", True),
        ("agent/README.md", False),
        ("agent/plans/notes.md", False),
        ("agent/plans/PLAN-x.txt", False),
    ],
)
def test_is_plan_path(rel, want):
    assert PL.is_plan_path(rel) is want


# --------------------------------------------------------------------------- classify and folder_for.


@pytest.mark.parametrize(
    ("status", "want"),
    [
        ("in-progress", PL.STATE_ACTIVE),
        ("UNKNOWN", PL.STATE_ACTIVE),
        ("done", PL.STATE_DONE),
        ("superseded", PL.STATE_DONE),
        ("draft", PL.STATE_BACKLOG),
        ("removed", PL.STATE_REMOVED),
        ("compacted", PL.STATE_RECORD),
        ("parked", PL.STATE_RECORD),
    ],
)
def test_classify_reads_the_status_and_not_the_folder(status, want):
    text = "# PLAN: t\nStatus: %s\n" % status
    assert PL.classify(PL.parse_plan("agent/plans/_done/PLAN-t.md", text)) == want


def test_a_record_is_not_a_backlog_plan_even_though_parked_is_not_started():
    """`parked` is in NOT_STARTED_STATES and must NOT reach the 90-day sweeper.

    The blob behind a parked record is the only copy of its text. Sweeping the pointer would orphan it, which is the one outcome the whole lifecycle exists to prevent, so the record arm is tested before the not-started arm and this case pins the order.
    """
    plan = PL.parse_plan("agent/plans/PLAN-t.md", "# PLAN: t\nStatus: parked\n")
    assert PL.classify(plan) == PL.STATE_RECORD
    assert PL.retention_days(PL.classify(plan), CONFIG) is None


@pytest.mark.parametrize(
    ("state", "want"),
    [
        (PL.STATE_ACTIVE, PL.PLANS_DIR),
        (PL.STATE_BACKLOG, PL.PLANS_DIR),
        (PL.STATE_RECORD, PL.PLANS_DIR),
        (PL.STATE_DONE, PL.DONE_DIR),
        (PL.STATE_REMOVED, PL.REMOVED_DIR),
        (PL.STATE_STUB, PL.AGENT_DIR),
    ],
)
def test_folder_for(state, want):
    assert PL.folder_for(state) == want


@pytest.mark.parametrize(
    ("state", "want"),
    [
        (PL.STATE_ACTIVE, None),
        (PL.STATE_RECORD, None),
        (PL.STATE_STUB, None),
        (PL.STATE_BACKLOG, 90),
        (PL.STATE_DONE, 40),
        (PL.STATE_REMOVED, 40),
    ],
)
def test_retention_days(state, want):
    assert PL.retention_days(state, CONFIG) == want


# --------------------------------------------------------------------------- The stub.


def test_a_stub_round_trips_and_needs_both_halves():
    text = PL.stub_text("agent/PLAN-t.md", "agent/plans/_done/PLAN-t.md", "t")
    plan = PL.parse_plan("agent/PLAN-t.md", text)
    assert PL.is_stub(plan)
    assert plan.moved_to == "agent/plans/_done/PLAN-t.md"
    assert PL.looks_like_stub(text)
    assert not PL.is_stub(PL.parse_plan("agent/PLAN-t.md", "# PLAN: t\nStatus: moved\n"))
    assert not PL.is_stub(PL.parse_plan("agent/PLAN-t.md", "# PLAN: t\nStatus: done\n"))


def test_looks_like_stub_answers_from_a_truncated_read():
    """The census path reads a PREFIX, so the cheap answer must agree with the full one."""
    text = PL.stub_text("agent/PLAN-t.md", "agent/plans/_done/PLAN-t.md", "t")
    assert PL.looks_like_stub(text[: PL.STUB_PROBE_BYTES])
    assert not PL.looks_like_stub("# PLAN: t\nStatus: in-progress\n\n- [ ] a box\n")


# --------------------------------------------------------------------------- The clocks. Risk 1 of the plan, in three cases.


def test_last_touch_takes_the_older_of_the_two_dates():
    older = PL.parse_plan(
        "agent/plans/PLAN-t.md",
        "# PLAN: t\nStatus: draft\nFirst-Seen: 2025-01-01\n",
        last_commit="2026-09-20T10:00:00+00:00",
    )
    assert PL.last_touch(older) == dt.date(2025, 1, 1)


def test_a_move_cannot_buy_freshness():
    """The migration commits every plan at a new path on the same day.

    Without `First-Seen:` that resets 103 clocks at once and disarms the 90-day sweeper for 90 days. The header is carried from the PRE-move committer date and the minimum is what makes it unforgeable in the direction that matters.
    """
    before = PL.parse_plan(
        "agent/PLAN-t.md", "# PLAN: t\nStatus: draft\n", last_commit="2025-06-01T00:00:00+00:00"
    )
    after = PL.parse_plan(
        "agent/plans/PLAN-t.md",
        "# PLAN: t\nStatus: draft\nFirst-Seen: 2025-06-01\n",
        last_commit="2026-09-21T00:00:00+00:00",
    )
    assert PL.last_touch(before) == PL.last_touch(after) == dt.date(2025, 6, 1)


def test_last_touch_is_none_when_neither_date_exists():
    assert PL.last_touch(PL.parse_plan("agent/plans/PLAN-t.md", "Status: draft\n")) is None


# --------------------------------------------------------------------------- The findings, one case each beyond the gate's own controls.


def _plan(rel, status, **kw):
    lines = ["# PLAN: t", "Status: %s" % status]
    if kw.get("first_seen"):
        lines.append("First-Seen: %s" % kw.pop("first_seen"))
    return PL.parse_plan(rel, "\n".join(lines) + "\n", **kw)


def test_f1_counts_every_legacy_plan_and_no_stub():
    plans = [
        _plan("agent/PLAN-a.md", "in-progress"),
        _plan("agent/plans/PLAN-b.md", "in-progress"),
        PL.parse_plan(
            "agent/PLAN-c.md", PL.stub_text("agent/PLAN-c.md", "agent/plans/PLAN-c.md", "c")
        ),
    ]
    assert [f.rel for f in PL.finding_f1(plans)] == ["agent/PLAN-a.md"]


def test_f2_is_silent_at_the_legacy_path_because_f1_already_owns_it():
    """Two findings on one file is two remedies for one move, and only one is right."""
    assert PL.finding_f2([_plan("agent/PLAN-a.md", "done")]) == []


def test_f3_reads_moved_at_and_not_the_commit_date():
    plan = _plan("agent/plans/_done/PLAN-a.md", "done", moved_at="2026-05-01")
    assert [f.code for f in PL.finding_f3([plan], CONFIG, TODAY)] == ["F3"]
    fresh = _plan("agent/plans/_done/PLAN-a.md", "done", moved_at="2026-09-01")
    assert PL.finding_f3([fresh], CONFIG, TODAY) == []


def test_f4_spares_a_plan_that_is_merely_old_and_active():
    old_active = _plan("agent/plans/PLAN-a.md", "in-progress", first_seen="2024-01-01")
    assert PL.finding_f4([old_active], CONFIG, TODAY) == []
    old_backlog = _plan("agent/plans/PLAN-a.md", "draft", first_seen="2024-01-01")
    assert [f.code for f in PL.finding_f4([old_backlog], CONFIG, TODAY)] == ["F4"]


def test_f6_needs_both_dates_before_it_says_anything():
    """A terminal plan with no recorded move is F3's silence, never F6's accusation."""
    plan = _plan("agent/plans/_done/PLAN-a.md", "done", move_commit="2026-09-01T00:00:00+00:00")
    assert PL.finding_f6([plan]) == []


def test_f7_accepts_a_stub_path_because_a_stub_is_a_file():
    refs = [("agent/INDEX.md", "agent/PLAN-a.md")]
    assert PL.finding_f7(refs, {"agent/PLAN-a.md"}, set()) == []
    assert [f.code for f in PL.finding_f7(refs, set(), set())] == ["F7"]


def test_f8_fires_only_on_a_blob_the_repository_cannot_produce():
    stone = PL.Tombstone("agent/plans/PLAN-a.md", "a", "2026-01-01", "2026-09-01", "a" * 40)
    assert PL.finding_f8([stone], {"a" * 40}) == []
    assert [f.code for f in PL.finding_f8([stone], set())] == ["F8"]


def test_f9_short_circuits_every_other_finding():
    """A lost corpus must not also report zero of everything else as though it had looked."""
    codes = {
        f.code
        for f in PL.findings(
            [_plan("agent/PLAN-a.md", "in-progress")],
            config=CONFIG,
            today=TODAY,
            existing=set(),
            refs=[("agent/INDEX.md", "agent/PLAN-nope.md")],
            tombstones=[],
            blob_resolves=set(),
        )
    }
    assert codes == {"F9"}


# --------------------------------------------------------------------------- The tombstone table.


def test_tombstone_rows_survive_a_render_and_a_reparse():
    rows = [
        PL.Tombstone("agent/plans/_done/PLAN-a.md", "A plan", "2026-01-01", "2026-09-01", "a" * 40),
        PL.Tombstone("agent/plans/PLAN-b.md", "B plan", "2025-01-01", "2026-09-02", "b" * 40),
    ]
    back = PL.parse_tombstones(PL.render_tombstones(rows))
    assert back == sorted(rows, key=lambda r: r.rel)


def test_an_empty_table_renders_as_nothing_and_parses_to_nothing():
    assert PL.render_tombstones([]) == ""
    assert PL.parse_tombstones("") == []


def test_a_tombstone_row_is_not_confused_with_a_record_row():
    """`agent/INDEX.md` already carries a five-column record table. The two must not cross-parse, or a compaction record would read as an expired plan and be offered for revival."""
    record_row = "| agent/PLAN-a.md | compacted | 3 / 0 / 0 | `%s` |\n" % ("a" * 40)
    assert PL.parse_tombstones(record_row) == []


# --------------------------------------------------------------------------- The enumeration keeps its exit status.


def test_enumerate_plans_reports_a_failed_git_rather_than_an_empty_tree(tmp_path):
    """A swallowed enumeration reads exactly like a clean one, which is the whole finding."""
    found, why = PL.enumerate_plans(tmp_path)
    assert found == []
    assert "ls-files" in why


def test_needs_git_dates_asks_only_where_a_clock_is_read():
    assert not PL.needs_git_dates(_plan("agent/PLAN-a.md", "in-progress"))
    assert not PL.needs_git_dates(_plan("agent/plans/PLAN-a.md", "compacted"))
    assert PL.needs_git_dates(_plan("agent/plans/PLAN-a.md", "draft"))
    assert PL.needs_git_dates(_plan("agent/plans/_done/PLAN-a.md", "done"))
