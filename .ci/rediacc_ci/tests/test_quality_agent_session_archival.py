"""`rediacc_ci.quality.agent_session_archival`, its pure core and the one mirror the gate carries.

WHAT THIS ADDS TO THE GATE'S OWN `--selftest`. Those controls plant into a TEXT roster and assert which directories a finding accuses; they exercise the judgment through one path. The cases here drive the individual functions directly, at their boundaries and with their arguments out of order, which is where a helper that happens to agree with the roster fixture stops agreeing.

THE MIRROR. `check_agent_session_archival.py` restates `wl_store.AGENT_RESERVED_DIRS` as `RESERVED_MIRROR`, used by its controls alone; the running gate reads the hook's own set. The copy exists so the controls still run on a checkout with no `.claude/`, and the only thing that makes that copy payable is a test comparing the two in BOTH directions, which is the first case below.
A mirror nobody compares is a second definition.

THE REST IS THE PURE CORE. `idle_hours`, `due_after_hours`, `classify_due`, `vacuity_reason`, `label_for` and `move_refusal` take data and return data: no git, no filesystem, no clock, so every case is a literal in and a literal out.
"""

import ast
import pathlib
import sys

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import agent_session_archival as ASA

HOOKS = paths.hooks_stop_dir()
GATE_DIR = paths.quality_dir()

NOW = 1_758_500_000.0
HOUR = ASA.SECONDS_PER_HOUR


def _gate_module():
    """`check_agent_session_archival` imported as a MODULE, for its mirror and its fixtures.

    The entry point is a flat script rather than a package member, so it is reached by the same sys.path hop every other gate test in this package uses. Imported for its constants only; nothing here calls `main`.
    """
    paths.on_sys_path(GATE_DIR)
    paths.on_sys_path(paths.ci_dir())
    return pytest.importorskip("check_agent_session_archival")


def _sessions(*pairs: tuple[str, float, bool]) -> list[ASA.Session]:
    return [ASA.Session(name=n, ts=NOW - h * HOUR, dead=d) for n, h, d in pairs]


# --------------------------------------------------------------------------- The mirror.


def test_the_reserved_mirror_matches_the_hook_in_both_directions():
    """A SKIP when `.claude/` is absent, not a failure: that absence is exactly the condition the mirror exists to survive, and failing here would demand the dependency the copy is there to avoid."""
    if not HOOKS.is_dir():
        pytest.skip("%s is absent; the mirror exists precisely for that case" % HOOKS)
    paths.on_sys_path(HOOKS)
    wl_store = pytest.importorskip("wl_store")
    gate = _gate_module()
    assert set(gate.RESERVED_MIRROR) == set(wl_store.AGENT_RESERVED_DIRS)


def test_the_config_on_disk_carries_a_numeric_grace_days():
    """The gate refuses with CANNOT RUN when this key is missing, so its absence would turn every run into an exit 77 that reads as an environment problem rather than as a deleted line."""
    root = paths.repo_root()
    config = ASA.load_config(root)
    assert isinstance(config["grace_days"], (int, float))
    assert float(config["grace_days"]) > 0


# --------------------------------------------------------------------------- The clocks.


def test_idle_hours_is_the_gap_and_idle_days_is_that_over_24():
    session = _sessions(("a", 48.0, True))[0]
    assert ASA.idle_hours(session, NOW) == pytest.approx(48.0)
    assert ASA.idle_days(session, NOW) == pytest.approx(2.0)


def test_a_stamp_in_the_future_reads_as_zero_rather_than_negative():
    """Two machines writing one tree have skewed clocks, and a negative age sorts ahead of everything: the oldest directory would print as the youngest."""
    future = ASA.Session(name="skewed", ts=NOW + 10 * HOUR, dead=True)
    assert ASA.idle_hours(future, NOW) == 0.0
    assert ASA.idle_days(future, NOW) == 0.0


def test_the_due_threshold_stacks_the_grace_on_top_of_the_horizon():
    """14 in the config means 14 days ON TOP of the hook's 24 hours, not 14 in total. A reader who has to work that out from the code is a reader who will retune the wrong number."""
    assert ASA.due_after_hours(14, 24) == 360.0
    assert ASA.due_after_hours(0, 24) == 24.0
    assert ASA.due_after_hours(14, 0) == 336.0


# --------------------------------------------------------------------------- classify_due.


def test_classify_due_needs_both_the_oracle_and_the_clock():
    ancient_live = _sessions(("live", 9000.0, False))
    assert ASA.classify_due(ancient_live, grace_days=14, dead_hours=24, now=NOW) == []
    ancient_dead = _sessions(("gone", 9000.0, True))
    assert [
        s.name for s in ASA.classify_due(ancient_dead, grace_days=14, dead_hours=24, now=NOW)
    ] == ["gone"]


@pytest.mark.parametrize(
    ("hours", "due"),
    [(359.9, False), (360.0, True), (360.1, True), (0.0, False)],
)
def test_the_grace_boundary_is_inclusive_and_fires_on_the_far_side_only(hours, due):
    found = ASA.classify_due(_sessions(("x", hours, True)), grace_days=14, dead_hours=24, now=NOW)
    assert bool(found) is due


def test_the_overdue_list_is_oldest_first_whatever_order_it_arrives_in():
    """Sorted by the stamp rather than by name or by input order: a reader clears the oldest first, and the enumeration's own order is an accident of `iterdir`."""
    scrambled = _sessions(("young", 400.0, True), ("old", 9000.0, True), ("mid", 700.0, True))
    assert [s.name for s in ASA.classify_due(scrambled, grace_days=14, dead_hours=24, now=NOW)] == [
        "old",
        "mid",
        "young",
    ]


def test_an_empty_roster_produces_no_findings_rather_than_raising():
    """The floor is a separate refusal. Making `findings()` raise on empty would put the vacuity decision in two places, and the caller's version would be the one nobody reads."""
    assert ASA.findings([], grace_days=14, dead_hours=24, now=NOW) == []


def test_the_finding_names_the_directory_the_age_and_the_verb():
    found = ASA.findings(
        _sessions(("abcd1234", 400.0, True)), grace_days=14, dead_hours=24, now=NOW
    )
    assert len(found) == 1
    assert found[0].code == "S1"
    assert "agent/abcd1234/" in found[0].message
    assert "16.7 days" in found[0].message
    assert "--move abcd1234" in found[0].message


# --------------------------------------------------------------------------- The floor.


def test_vacuity_reason_is_empty_only_when_the_gate_really_looked():
    live = _sessions(("a", 1.0, False))
    assert ASA.vacuity_reason(live, archive_exists=True) == ""
    assert "below the floor" in ASA.vacuity_reason([], archive_exists=True)
    assert "nowhere to archive" in ASA.vacuity_reason(live, archive_exists=False)


def test_a_missing_archive_is_reported_ahead_of_a_thin_roster():
    """Both wrong at once names the archive, because that is the one a reader can fix: an empty `agent/` is a symptom of a checkout, a missing `agent/archive/` is a directory somebody deleted."""
    assert "nowhere to archive" in ASA.vacuity_reason([], archive_exists=False)


# --------------------------------------------------------------------------- Labels.


@pytest.mark.parametrize(
    ("branch", "label"),
    [
        ("0914-1", "0914-1"),
        ("feature/thing", "feature-thing"),
        ("release/v1.2.3", "release-v1.2.3"),
        ("2026-09-22-backfill", "2026-09-22-backfill"),
        ("", ""),
        ("///", ""),
        ("..", ""),
        (".hidden", "hidden"),
    ],
)
def test_label_for_produces_exactly_one_safe_directory_component(branch, label):
    got = ASA.label_for(branch)
    assert got == label
    assert "/" not in got
    assert not got.startswith(".")


def test_archive_rel_and_session_rel_are_the_only_spellings_of_the_two_paths():
    """Shared by the mover and by every message naming where a directory went, so a refusal cannot describe a path the move would not have used."""
    assert ASA.session_rel("abcd1234") == "agent/abcd1234"
    assert ASA.archive_rel("L", "abcd1234") == "agent/archive/L/abcd1234"
    assert ASA.archive_rel("L", "abcd1234").startswith(ASA.ARCHIVE_DIR + "/")


def test_stamp_text_round_trips_the_heading_format_the_sections_carry():
    assert ASA.stamp_text(NOW).endswith("Z")
    assert len(ASA.stamp_text(NOW)) == len("2026-09-22T00:00:00Z")


# --------------------------------------------------------------------------- move_refusal.

RESERVED = frozenset(
    {"archive", "programs", "worklist", "reggate", "plans", "ledgers", "pr", "legacy"}
)

CLEAN_MOVE = {
    "session": "abcd1234",
    "reserved": RESERVED,
    "exists": True,
    "dead": True,
    "forced": False,
    "dirty": False,
    "target_exists": False,
    "label": "2026-09-22-backfill",
}


def _refuse(**over: object) -> str:
    return ASA.move_refusal(**{**CLEAN_MOVE, **over})  # type: ignore[arg-type]


def test_a_clean_move_is_allowed_so_the_refusals_below_mean_something():
    assert _refuse() == ""


@pytest.mark.parametrize(
    ("over", "needle"),
    [
        ({"session": "archive"}, "reserved directory"),
        ({"session": "a/b"}, "not a session directory name"),
        ({"session": ""}, "not a session directory name"),
        ({"label": ""}, "no archive label"),
        ({"exists": False}, "does not exist"),
        ({"dirty": True}, "race a live writer"),
        ({"dead": False}, "still LIVE"),
        ({"target_exists": True}, "already exists"),
    ],
)
def test_each_rail_refuses_for_its_own_reason(over, needle):
    assert needle in _refuse(**over)


def test_force_opens_the_live_door_and_nothing_else():
    """`--force` is the README's own same-day self-archival path. It must not also wave through a dirty tree, a reserved name or an occupied destination: those are not judgments about liveness."""
    assert _refuse(dead=False) != ""
    assert _refuse(dead=False, forced=True) == ""
    assert _refuse(dirty=True, forced=True) != ""
    assert _refuse(session="archive", forced=True) != ""
    assert _refuse(target_exists=True, forced=True) != ""


def test_a_reserved_name_is_refused_before_anything_reads_the_filesystem():
    """Order is load-bearing rather than tidy: `archive` is itself a name a careless `--move archive` would walk into, so it is refused even when every other fact says the move is fine."""
    assert "reserved directory" in _refuse(session="archive", exists=False, dirty=True, label="")


def test_every_reserved_name_is_refused_rather_than_only_the_first():
    assert all(_refuse(session=name) != "" for name in RESERVED)


def test_the_promotion_reminder_says_it_is_not_a_gate():
    """It is advisory by declaration. Nothing can verify mechanically whether a RULES.md line turned out to be true of the REPO, and a reminder that read as an obligation would be a check that cannot fire."""
    assert "RULES.md" in ASA.PROMOTION_REMINDER
    assert "TRAPS.md" in ASA.PROMOTION_REMINDER
    assert "not a gate" in ASA.PROMOTION_REMINDER


# --------------------------------------------------------------------------- The horizon comes from the hook's own variable.


def test_dead_hours_reads_the_hooks_own_environment_variable():
    assert ASA.dead_hours({}) == ASA.DEFAULT_DEAD_HOURS
    assert ASA.dead_hours({ASA.DEAD_HOURS_ENV: "6"}) == 6.0


def test_an_unparseable_horizon_falls_back_rather_than_raising():
    """A gate that crashed on a malformed env var would report an instrument failure for a value no operator set deliberately; the hook itself takes the same fallback."""
    assert ASA.dead_hours({ASA.DEAD_HOURS_ENV: "not-a-number"}) == ASA.DEFAULT_DEAD_HOURS
    assert ASA.dead_hours({ASA.DEAD_HOURS_ENV: ""}) == ASA.DEFAULT_DEAD_HOURS


def test_the_library_imports_nothing_from_the_hook_tree():
    """The pure half must stay runnable where `.claude/` is absent. The gate's entry point does the sys.path hop; the library must not, or a checkout without the hooks could not even import it to report the refusal."""
    source = pathlib.Path(ASA.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert imported & {"wl_store", "wl_core", "wl_checks"} == set(), imported
    assert "hooks_stop_dir" not in source


def test_the_gate_entry_point_is_importable_and_its_floor_is_met():
    """A floor that is never reached is a floor that cannot fail, so the count is asserted here as well as inside the runner."""
    gate = _gate_module()
    assert gate.CONTROL_FLOOR >= 20
    assert gate.selftest() == 0
    assert sys.modules["check_agent_session_archival"] is gate
