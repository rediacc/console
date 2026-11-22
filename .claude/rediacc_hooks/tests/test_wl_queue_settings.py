"""The QUEUE.md settings block: reader, writer, solo marker, the `--queue-set` verb and the RQ-SETTINGS finding, the effort level that resolves into it (agent/plans/PLAN-stop-hook-effort.md box E2), and its shrink to `effort` alone (agent/plans/PLAN-simple-two-tree-loop.md B5).

The parser tests drive `wl_planqueue` directly; the verb tests drive the real CLI through `wlfix`; the gate test runs `check_plan_record.py` against a fixture root. Every FIRE has an inverse that differs by one planted fact.
"""

from __future__ import annotations

import dataclasses
import os
import pathlib
import subprocess
import sys
from typing import Any

import pytest

from rediacc_hooks.tests import wlfix

PQ = wlfix.import_wl("wl_planqueue")
REPO = pathlib.Path(__file__).resolve().parents[3]

HEAD = "# Plan queue\n\nProse with `## Settings` and a ```stop-hook mention inline.\n\n"
TAIL = (
    "## Promoted\n\n"
    "1. agent/plans/PLAN-a.md -- operator pick\n"
    "2. agent/plans/PLAN-b.md -- operator pick -- solo\n"
    "3. agent/plans/PLAN-c.md -- solo, not at the end -- later\n"
    "4. agent/plans/PLAN-d.md -- -- soloish\n"
    "5. agent/plans/PLAN-e.md -- solo\n\n"
    "## Generated\n\n<!-- queue:generated:begin -->\n"
    "1. agent/plans/PLAN-f.md -- P2, approved, not started\n"
    "2. agent/plans/PLAN-g.md -- P2, approved, not started -- solo\n"
    "<!-- queue:generated:end -->\n"
)


def block(body: str) -> str:
    return HEAD + "## Settings\n\nProse.\n\n```stop-hook\n%s\n```\n\n" % body + TAIL


ALL_KEYS = ("effort", "judge", "cadence", "agent_hint", "agent_pushback")
# The knobs agent/plans/PLAN-simple-two-tree-loop.md ruling 11 deleted or fixed in code, and the bundle switches the level alone decides: each is refused as a fence line.
RETIRED = (
    "turbo: on",
    "turbo_push: batch-end",
    "batch_size: 3",
    "plan_concurrency: 5",
    "writer_cap: 4",
    "commit_remind_min: 15",
    "backup_push_h: 4",
    "judge: core",
    "cadence: off",
    "agent_hint: off",
    "agent_pushback: off",
    "stop_hook: off",
)
E = wlfix.import_wl("wl_effort")


def test_defaults_when_there_is_no_settings_section():
    got, problems = PQ.settings(HEAD + TAIL)
    assert problems == []
    assert got == PQ.Settings()
    # The fail-safe level is `high`: every check and the full judge, as before the dial existed.
    assert (got.effort, got.cadence, got.agent_hint, got.agent_pushback, got.judge) == (
        "high",
        True,
        True,
        True,
        "full",
    )
    assert got.notes == {}
    assert PQ.settings("") == (PQ.Settings(), [])


# ---- the effort level (agent/plans/PLAN-stop-hook-effort.md E2) ------------------------------------


@pytest.mark.parametrize("level", ["quiet", "low", "smart", "high"])
def test_every_level_resolves_its_bundle(level):
    got, problems = PQ.settings(block("effort: %s" % level))
    assert problems == []
    want = E.bundle(level)
    assert set(want) == set(E.BUNDLE_TYPES), want  # the table gives every level every switch
    assert got.effort == level
    for key, value in want.items():
        assert getattr(got, key) == value, (level, key)
    assert PQ.sources(block("effort: %s" % level))["judge"] == "effort %s" % level


def test_the_levels_differ_where_the_plan_says_they_do():
    assert E.LEVELS == ("quiet", "low", "smart", "high")
    by = {lv: PQ.settings(block("effort: %s" % lv))[0] for lv in E.LEVELS}
    assert [by[lv].judge for lv in E.LEVELS] == ["off", "off", "core", "full"]
    assert [by[lv].agent_pushback for lv in E.LEVELS] == [False, False, True, True]


def test_ultra_is_refused_and_falls_back_to_high():
    """B5: `ultra` left with the throughput knobs, so `effort: ultra` is a problem naming the levels, and the level is the fail-safe one."""
    got, problems = PQ.settings(block("effort: ultra"))
    assert problems == ["%s: effort: expected quiet|low|smart|high, got 'ultra'" % PQ.QUEUE_REL]
    assert got.effort == "high"
    with pytest.raises(ValueError, match=r"expected quiet\|low\|smart\|high, got .ultra."):
        PQ.set_settings(block("effort: low"), {"effort": "ultra"})
    # CONTROL: `effort: quiet` parses with no problem, and is not the fail-safe level.
    quiet, none = PQ.settings(block("effort: quiet"))
    assert (quiet.effort, quiet.judge, none) == ("quiet", "off", [])


@pytest.mark.parametrize("line", RETIRED)
def test_any_key_but_effort_is_refused_by_name_with_the_line_to_delete(line):
    """B5: the fence takes `effort` alone. Any other line is a problem that names the key and the exact line to delete, and changes no value: the level still decides."""
    key = line.split(":")[0]
    got, problems = PQ.settings(block("effort: smart\n%s -- operator note" % line))
    assert problems == [
        "%s: %r is not a setting (effort is the only one); delete the line `%s -- operator note`"
        % (PQ.QUEUE_REL, key, line)
    ], problems
    assert got == PQ.settings(block("effort: smart"))[0]
    assert not hasattr(got, "turbo")
    # CONTROL: the same block without the line is clean.
    assert PQ.settings(block("effort: smart"))[1] == []


def test_a_turbo_fence_is_refused_by_name_and_quiets_nothing():
    got, problems = PQ.settings(block("turbo: on"))
    assert any("'turbo' is not a setting" in p and "`turbo: on`" in p for p in problems), problems
    assert got == PQ.Settings()  # no `effort:` line: the fail-safe level, every check


def test_an_empty_value_drops_the_effort_line_so_high_decides():
    text = block("effort: smart -- why")
    new = PQ.set_settings(text, {"effort": ""})
    assert "effort:" not in new
    got, problems = PQ.settings(new)
    assert (got.effort, problems) == ("high", [])
    with pytest.raises(ValueError, match="'stop_hook' is not a setting"):
        PQ.set_settings(text, {"stop_hook": ""})


def test_the_dataclass_is_frozen_with_the_contract_fields():
    names = [f.name for f in dataclasses.fields(PQ.Settings)]
    assert names == [*ALL_KEYS, "notes"]
    assert tuple(ALL_KEYS) == PQ.KNOWN_KEYS
    assert PQ.SETTINGS_KEYS == ("effort",)
    assert set(PQ.BUNDLE_KEYS) == set(E.BUNDLE_TYPES)
    settings: Any = PQ.Settings()
    with pytest.raises(dataclasses.FrozenInstanceError):
        settings.effort = "low"


def test_cadence_comes_from_the_level_and_the_env_seam_alone(monkeypatch):
    """The fence takes no `cadence:` line (B5), so the fixtures turn the cadence off through WORKLIST_CADENCE, the twin of WORKLIST_JUDGE (wl_checks.cadence_on): `on` or `off` overrides, any other value is ignored and the level decides."""
    checks = wlfix.import_wl("wl_checks")
    on_level = PQ.settings(block("effort: high"))[0]
    off_level = dataclasses.replace(on_level, cadence=False)
    monkeypatch.delenv("WORKLIST_CADENCE", raising=False)
    assert (checks.cadence_on(on_level), checks.cadence_on(off_level)) == (True, False)
    monkeypatch.setenv("WORKLIST_CADENCE", "off")
    assert checks.cadence_on(on_level) is False
    monkeypatch.setenv("WORKLIST_CADENCE", "on")
    assert checks.cadence_on(off_level) is True
    # CONTROL: a misspelled value is ignored, so the level's value stands either way.
    monkeypatch.setenv("WORKLIST_CADENCE", "Off")
    assert (checks.cadence_on(on_level), checks.cadence_on(off_level)) == (True, False)


def test_effort_parses_and_its_note_is_kept():
    got, problems = PQ.settings(block("effort: low -- quiet for the operator -- with a second one"))
    assert problems == []
    assert (got.effort, got.judge, got.agent_hint) == ("low", "off", False)
    assert got.notes == {"effort": "quiet for the operator -- with a second one"}
    # CONTROL: another level differs, so the test reads the value.
    other, _ = PQ.settings(block("effort: high"))
    assert other != got


@pytest.mark.parametrize("line", ["effort: medium", "effort: off", "effort:", "effort: HIGH"])
def test_a_bad_effort_value_falls_back_to_high(line):
    got, problems = PQ.settings(block(line))
    assert len(problems) == 1, problems
    assert "effort" in problems[0], problems
    assert got == PQ.Settings()


def test_a_duplicate_effort_line_falls_back_to_the_default():
    got, problems = PQ.settings(block("effort: quiet\neffort: quiet"))
    assert got.effort == "high"
    assert any("effort" in p and "2 times" in p for p in problems), problems


def test_a_line_that_is_not_key_value_is_a_problem():
    _got, problems = PQ.settings(block("effort quiet"))
    assert problems
    assert "effort quiet" in problems[0]


def test_a_second_fence_is_ignored_and_reported():
    text = block("effort: low").replace(
        "## Promoted", "```stop-hook\neffort: quiet\n```\n\n## Promoted"
    )
    got, problems = PQ.settings(text)
    assert got.effort == "low"  # the first fence wins
    assert any("second" in p for p in problems), problems


def test_a_fence_outside_the_section_is_reported():
    text = HEAD + TAIL + "\n```stop-hook\neffort: quiet\n```\n"
    got, problems = PQ.settings(text)
    assert got.effort == "high"
    assert any("outside" in p for p in problems), problems


def test_the_section_below_promoted_is_reported_and_not_read():
    text = HEAD + TAIL + "\n## Settings\n\n```stop-hook\neffort: quiet\n```\n"
    got, problems = PQ.settings(text)
    assert got.effort == "high"  # the fail-safe direction
    assert any("below" in p for p in problems), problems


def test_an_unclosed_fence_and_a_section_without_a_fence_are_reported():
    _g, unclosed = PQ.settings(HEAD + "## Settings\n\n```stop-hook\neffort: low\n\n" + TAIL)
    assert unclosed
    _g, empty = PQ.settings(HEAD + "## Settings\n\nProse only.\n\n" + TAIL)
    assert any("no `stop-hook` fence" in p for p in empty), empty


def test_the_section_does_not_leak_into_the_queue_entries():
    text = block("effort: low")
    assert PQ.entries(text) == (
        [
            "agent/plans/PLAN-a.md",
            "agent/plans/PLAN-b.md",
            "agent/plans/PLAN-c.md",
            "agent/plans/PLAN-d.md",
            "agent/plans/PLAN-e.md",
        ],
        ["agent/plans/PLAN-f.md", "agent/plans/PLAN-g.md"],
    )
    assert PQ.entries(text) == PQ.entries(HEAD + TAIL)  # byte-for-byte the same readers' view


def git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    ).stdout


def test_settings_for_reads_the_working_tree_and_a_rev(tmp_path):
    assert PQ.settings_for(tmp_path) == (PQ.Settings(), [])  # no file: defaults, no problem
    queue = tmp_path / PQ.QUEUE_REL
    queue.parent.mkdir(parents=True)
    queue.write_text(block("effort: low"), encoding="utf-8")
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "t@t")
    git(tmp_path, "config", "user.name", "t")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "base")
    queue.write_text(block("effort: smart"), encoding="utf-8")
    assert PQ.settings_for(tmp_path)[0].effort == "smart"
    at_head, problems = PQ.settings_for(tmp_path, "HEAD")
    assert (at_head.effort, problems) == ("low", [])
    bad, problems = PQ.settings_for(tmp_path, "no-such-rev")
    assert bad == PQ.Settings()
    assert problems
    assert "unreadable" in problems[0]
    queue.write_bytes(b"\xff\xfe not utf-8")
    assert PQ.settings_for(tmp_path)[0] == PQ.Settings()
    assert "unreadable" in PQ.settings_for(tmp_path)[1][0]


def fence_span(text: str) -> tuple[int, int]:
    start = text.index("```stop-hook\n") + len("```stop-hook\n")
    return start, text.index("\n```\n", start) + 1


def test_set_settings_rewrites_only_the_effort_line():
    text = block("effort: smart -- old reason\nturbo: off -- a retired line the lead deletes")
    new = PQ.set_settings(text, {"effort": "low"}, note="operator test")
    lo, hi = fence_span(text)
    nlo, nhi = fence_span(new)
    assert (text[:lo], text[hi:]) == (new[:nlo], new[nhi:])  # every other byte identical
    assert new[nlo:nhi] == (
        "effort: low -- operator test\nturbo: off -- a retired line the lead deletes\n"
    )
    got, _problems = PQ.settings(new)
    assert got.effort == "low"
    # The round trip: setting the value already there changes nothing at all.
    assert PQ.set_settings(new, {"effort": "low"}, note="operator test") == new


def test_set_settings_note_policy():
    text = block("effort: low -- reason one")
    assert "reason one" in PQ.set_settings(text, {"effort": "low"})  # unchanged value keeps it
    flipped = PQ.set_settings(text, {"effort": "smart"})  # a changed value drops the stale reason
    assert "reason one" not in flipped
    assert "effort: smart\n" in flipped


def test_set_settings_drops_later_duplicates_of_the_effort_line():
    text = block("effort: low\neffort: low")
    new = PQ.set_settings(text, {"effort": "smart"})
    assert PQ.settings(new) == (PQ.settings(block("effort: smart"))[0], [])
    assert new.count("effort:") == 1


def test_set_settings_creates_the_section_above_promoted():
    text = HEAD + TAIL
    new = PQ.set_settings(text, {"effort": "smart"}, note="n")
    assert new.index("## Settings") < new.index("## Promoted")
    assert new.startswith(HEAD)
    assert new.endswith(TAIL)
    lo, hi = fence_span(new)
    assert new[lo:hi] == "effort: smart -- n\n"
    got, problems = PQ.settings(new)
    assert problems == []
    assert (got.effort, got.notes) == ("smart", {"effort": "n"})
    # With no Promoted heading the section is appended.
    bare = PQ.set_settings("# Plan queue\n", {"effort": "low"})
    assert bare.startswith("# Plan queue\n")
    assert PQ.settings(bare)[0].effort == "low"


@pytest.mark.parametrize(
    ("updates", "note"),
    [
        ({"turbo": "on"}, None),
        ({"writer_cap": "4"}, None),
        ({"cadence": "off"}, None),
        ({"effort": "ultra"}, None),
        ({"effort": "low"}, "two\nlines"),
    ],
)
def test_set_settings_refuses_what_the_reader_would_reject(updates, note):
    text = block("effort: high")
    with pytest.raises(ValueError, match=r"."):
        PQ.set_settings(text, updates, note)


def test_set_settings_refuses_a_structurally_broken_block():
    below = HEAD + TAIL + "\n## Settings\n\n```stop-hook\neffort: low\n```\n"
    with pytest.raises(ValueError, match="below"):
        PQ.set_settings(below, {"effort": "low"})
    with pytest.raises(ValueError, match="no `stop-hook` fence"):
        PQ.set_settings(HEAD + "## Settings\n\nProse.\n\n" + TAIL, {"effort": "low"})


def test_sources_name_where_each_value_comes_from():
    got = PQ.sources(block("effort: smart\nwriter_cap: 9"))
    assert got == {
        "effort": "QUEUE.md",
        "judge": "effort smart",
        "cadence": "effort smart",
        "agent_hint": "effort smart",
        "agent_pushback": "effort smart",
    }
    assert PQ.sources(block("turbo: on"))["effort"] == "default"  # no `effort:` line
    assert set(got) == set(ALL_KEYS)


def test_solo_marker():
    text = block("effort: low")
    assert PQ.solo_plans(text) == {
        "agent/plans/PLAN-b.md",
        "agent/plans/PLAN-e.md",
        "agent/plans/PLAN-g.md",
    }
    # `-- solo` mid-note and `-- soloish` are not the marker.
    assert "agent/plans/PLAN-c.md" not in PQ.solo_plans(text)
    assert "agent/plans/PLAN-d.md" not in PQ.solo_plans(text)
    assert (
        PQ.solo_plans(HEAD + TAIL.replace(" -- solo", "")) == set()
    )  # CONTROL: the marker is the delta


def test_the_live_queue_has_a_clean_block():
    text = (REPO / PQ.QUEUE_REL).read_text(encoding="utf-8")
    got, problems = PQ.settings(text)
    assert problems == [], problems
    src = PQ.sources(text)
    assert src["effort"] == "QUEUE.md", src  # the live block names its level
    assert set(src.values()) <= {"QUEUE.md", "effort %s" % got.effort}, src
    # No pin on which live entry is solo: PLAN-ci-consolidation's `-- solo` entry was retired with the plan (worklist #7b9fe4f1), and the solo parse is pinned on a fixture in test_wl_queue_progress.
    # NO PIN ON A SWITCH'S VALUE. The level is the operator's to turn, so asserting one here would turn check:ci-pytest red on an operator decision. The block parsing clean, with the level named in the file, is what this test owns.
    assert got.effort in E.LEVELS


# ---- the verb ----------------------------------------------------------------------------------


def plant(wl, body: str) -> pathlib.Path:
    path = wl.proj / PQ.QUEUE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_queue_set_writes_atomically_prints_git_add_and_never_commits(wl):
    wl.reg_repo()
    queue = plant(wl, block("effort: high -- old"))
    wl.git("add", "-A")
    wl.git("commit", "-qm", "chore: queue")
    head = wl.git("rev-parse", "HEAD").stdout
    before = queue.read_text(encoding="utf-8")
    got = wl.cli("--queue-set", wlfix.ME, "effort=smart", "--note", "operator test")
    assert got.rc == 0, got.err
    assert "effort: smart (QUEUE.md) -- operator test" in got.out
    assert "judge: core (effort smart)" in got.out
    assert "git add agent/plans/QUEUE.md" in got.out
    after = queue.read_text(encoding="utf-8")
    assert after != before
    settings, problems = PQ.settings(after)
    assert problems == []
    assert settings.effort == "smart"
    assert settings.notes["effort"] == "operator test"
    assert wl.git("rev-parse", "HEAD").stdout == head  # no commit was made
    assert wl.git("status", "--porcelain").stdout.strip() == "M agent/plans/QUEUE.md"
    assert not list(queue.parent.glob(".planrec-*")), "an atomic-write temp file was left behind"


@pytest.mark.parametrize(
    "pairs",
    [
        ["effort=medium"],
        ["effort=low", "turbo=on"],  # one good pair must not be written when another is refused
        ["writer_cap=25"],
        ["effort=ultra"],
        ["effort"],
        ["effort=low", "effort=smart"],
        ["--oops"],
        ["effort=low", "--note"],
    ],
)
def test_queue_set_refuses_a_bad_call_and_leaves_the_file_untouched(wl, pairs):
    queue = plant(wl, block("effort: high"))
    before = queue.read_bytes()
    mtime = queue.stat().st_mtime_ns
    got = wl.cli("--queue-set", wlfix.ME, *pairs)
    assert got.rc == 2, (got.rc, got.out, got.err)
    assert "REFUSED" in got.err, got.err
    assert "unchanged" in got.err, got.err
    assert got.out == ""
    assert queue.read_bytes() == before
    assert queue.stat().st_mtime_ns == mtime
    # CONTROL: the same file accepts the one good pair.
    assert wl.cli("--queue-set", wlfix.ME, "effort=low").rc == 0
    assert queue.read_bytes() != before


def test_queue_set_refuses_a_broken_block_and_a_missing_file(wl):
    # setup() writes `effort: high` into QUEUE.md; this case needs the file gone.
    (wl.proj / PQ.QUEUE_REL).unlink(missing_ok=True)
    missing = wl.cli("--queue-set", wlfix.ME, "effort=low")
    assert missing.rc == 2
    assert "unreadable" in missing.err
    assert not (wl.proj / PQ.QUEUE_REL).exists()  # a refusal does not create the file
    queue = plant(wl, HEAD + TAIL + "\n## Settings\n\n```stop-hook\neffort: low\n```\n")
    before = queue.read_bytes()
    got = wl.cli("--queue-set", wlfix.ME, "effort=smart")
    assert got.rc == 2
    assert "below" in got.err
    assert queue.read_bytes() == before


def test_queue_set_checks_the_identity_like_the_other_verbs(wl):
    queue = plant(wl, block("effort: high"))
    before = queue.read_bytes()
    foreign = wl.cli("--queue-set", "cafe1234", "effort=low")
    assert foreign.rc != 0, (foreign.rc, foreign.err)
    assert queue.read_bytes() == before
    usage = wl.cli("--queue-set")
    assert usage.rc == 2
    assert "usage: --queue-set" in usage.err


def test_queue_set_bare_prints_values_sources_and_problems(wl):
    plant(wl, block("turbo: on -- operator test\nwriter_cap: 4"))
    got = wl.cli("--queue-set", wlfix.ME)
    assert got.rc == 0, got.err
    lines = got.out.splitlines()
    assert "judge: full (effort high)" in lines
    assert "effort: high (default)" in lines
    assert any(line.startswith("PROBLEM") and "'turbo' is not a setting" in line for line in lines)
    assert any(line.startswith("PROBLEM") and "`writer_cap: 4`" in line for line in lines), got.out
    assert any(line.startswith("checks at effort high: ") for line in lines), got.out
    assert [
        ln.split(":")[0] for ln in lines if not ln.startswith(("PROBLEM", "checks at effort"))
    ] == list(ALL_KEYS)
    # No file at all: every value is the fail-safe level's and nothing is written.
    (wl.proj / PQ.QUEUE_REL).unlink()
    bare = wl.cli("--queue-set", wlfix.ME)
    assert bare.rc == 0
    assert "cadence: on (effort high)" in bare.out
    assert "PROBLEM" not in bare.out
    assert not (wl.proj / PQ.QUEUE_REL).exists()


# ---- the RQ-SETTINGS finding ---------------------------------------------------------------------


def gate_output(tmp_path, queue_text: str) -> str:
    root = tmp_path / "gateroot"
    (root / "agent" / "plans").mkdir(parents=True)
    (root / ".claude").symlink_to(REPO / ".claude")
    (root / ".ci").symlink_to(REPO / ".ci")
    (root / PQ.QUEUE_REL).write_text(queue_text, encoding="utf-8")
    env = dict(os.environ, PLAN_RECORD_ROOT=str(root), PLAN_RECORD_MIN_PLANS="0")
    got = subprocess.run(
        [sys.executable, str(REPO / ".ci/scripts/quality/check_plan_record.py")],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=300,
    )
    return got.stdout + got.stderr


def test_rq_settings_is_a_finding_for_a_malformed_block_and_silent_for_a_good_one(tmp_path):
    good = "# Plan queue\n\n" + block("effort: low").split("# Plan queue\n\n", 1)[1]
    finding = (
        "RQ-SETTINGS: agent/plans/QUEUE.md"  # the selftest's own PASS lines say RQ-SETTINGS too
    )
    assert finding not in gate_output(tmp_path / "ok", good)
    bad = gate_output(tmp_path / "bad", good.replace("effort: low", "effort: low\nturbo: on"))
    assert (
        finding + ": 'turbo' is not a setting (effort is the only one); delete the line `turbo: on`"
        in bad
    ), bad[-600:]


# ---- the in-flight block (operator order 2026-10-06) ---------------------------------------------
# The render is driven from planted `InFlight` values, one per loop shape; the stop-hook suite (test_wl_pr_scope_stop.py) drives the same block through the real Stop hook. Every case reads the mode line back with `inflight_mode`, and the planted wrong-mode render shows that reading fails on a block that lies about a switch.

P = wlfix.import_wl("wl_prscope")
OWN = "agent/plans/PLAN-own.md"


def inflight(**kw):
    base = {
        "settings": PQ.Settings(),
        "kind": P.LIVE,
        "branch": "1006-2",
        "session": "d778be9d",
        "writers": (),
    }
    base.update(kw)
    return PQ.InFlight(**base)


def as_dict(settings) -> dict[str, str]:
    out = {}
    for key in ALL_KEYS:
        value = getattr(settings, key)
        out[key] = ("on" if value else "off") if isinstance(value, bool) else str(value)
    return out


def rendered(inf) -> str:
    """The block as it lands in a queue file."""
    return PQ.with_inflight(block("effort: high"), PQ.render_inflight(inf))


def assert_mode_matches(text: str, settings) -> None:
    got = PQ.inflight_mode(text)
    assert got == as_dict(settings), "the in-flight mode line %r disagrees with the settings %r" % (
        got,
        as_dict(settings),
    )


def test_inflight_names_the_level_its_switches_and_the_fixed_writer_cap():
    settings = PQ.settings(block("effort: smart"))[0]
    inf = inflight(
        settings=settings,
        pr=612,
        plans=(PQ.PlanLine(OWN, "the PR body's `Plan:` line", 2, 5),),
        writers=("a1e6524bd31efbbcd",),
        next_plan="agent/plans/PLAN-three.md",
        next_why="Promoted entry 3",
    )
    text = rendered(inf)
    assert_mode_matches(text, settings)
    body = PQ.inflight_text(text)
    assert "- Mode: effort smart; judge core; cadence on; agent_hint on; agent_pushback on." in body
    assert (
        "- Writers: 1 live of writer_cap 25 (session d778be9d): worker:a1e6524bd31efbbcd." in body
    )


def test_inflight_carries_no_phase_line():
    """The phase verb is gone (agent/plans/PLAN-simple-two-tree-loop.md B10), so the block names no wind-down."""
    text = rendered(inflight(pr=612))
    assert "- Phase:" not in text
    assert "- Branch: 1006-2, PR #612 open." in text


def test_inflight_no_pr_names_the_queue_head_the_first_push_binds():
    text = rendered(
        inflight(
            kind=P.NO_PR,
            queue_head="agent/plans/PLAN-ci-consolidation.md",
            next_plan="agent/plans/PLAN-ci-consolidation.md",
            next_why="Promoted entry 1 (solo)",
            next_when="starts when this branch's PR binds it on its first push",
        )
    )
    body = PQ.inflight_text(text)
    assert "- Branch: 1006-2, no PR yet." in body
    assert (
        "writes the queue head, agent/plans/PLAN-ci-consolidation.md, as its `Plan:` line" in body
    )
    assert (
        "- Next plan: agent/plans/PLAN-ci-consolidation.md, Promoted entry 1 (solo); starts when"
        in body
    )


def test_inflight_a_pr_with_a_plan_line_lists_its_plans_and_their_sources():
    text = rendered(
        inflight(
            pr=543,
            plans=(
                PQ.PlanLine(
                    "agent/plans/PLAN-pre.md",
                    "a prerequisite pulled in (an unfinished `Depends-On:` of the set)",
                    1,
                    2,
                ),
                PQ.PlanLine(OWN, "the PR body's `Plan:` line", 1, 2),
                PQ.PlanLine(
                    "agent/plans/PLAN-or.md",
                    "added to the `Plan:` line under `Operational-Reason:`",
                    0,
                    -1,
                ),
            ),
        )
    )
    body = PQ.inflight_text(text)
    assert "- Branch: 1006-2, PR #543 open." in body
    assert "- Plans on the PR (3):" in body
    assert "  - agent/plans/PLAN-own.md -- 1 of 2 boxes ticked, the PR body's `Plan:` line" in body
    assert "  - agent/plans/PLAN-pre.md -- 1 of 2 boxes ticked, a prerequisite pulled in" in body
    assert (
        "  - agent/plans/PLAN-or.md -- unreadable, added to the `Plan:` line under `Operational-Reason:`"
        in body
    )
    assert "- Work outside the PR's plans: none." in body


def test_inflight_a_branch_with_only_planless_epics_names_them_and_no_plan():
    text = rendered(
        inflight(
            kind=P.NO_PR,
            epics=(PQ.EpicLine("97672f9f", "Operator 2026-10-06 follow-ups", "", 29, 0),),
            leases=(("f28caf3f", "a1e6524bd31efbbcd", "d778be9d"),),
        )
    )
    body = PQ.inflight_text(text)
    assert "- Plans on the PR: none." in body
    assert (
        "  - epic 97672f9f, no plan, 29 commit(s) on the branch, 0 open item(s): Operator 2026-10-06 follow-ups"
        in body
    )
    assert "- Leased items: 1: #f28caf3f (worker:a1e6524bd31efbbcd, d778be9d)." in body
    assert "- Next plan: none" in body


def test_inflight_planted_wrong_mode_render_fails_the_mode_check():
    """CONTROL: a block that shows another level than the one in force, or drops the mode line, must fail the reading every case above relies on."""
    settings = PQ.settings(block("effort: low"))[0]
    good = rendered(inflight(settings=settings))
    assert_mode_matches(good, settings)
    planted = good.replace("effort low;", "effort high;")
    assert planted != good
    with pytest.raises(AssertionError, match="disagrees with the settings"):
        assert_mode_matches(planted, settings)
    with pytest.raises(AssertionError, match="disagrees with the settings"):
        assert_mode_matches(good.replace(PQ.MODE_LABEL, "- Mood: "), settings)


def test_inflight_block_sits_between_settings_and_promoted_and_keeps_every_other_byte():
    text = block("effort: low")
    once = PQ.with_inflight(text, "- one\n")
    assert once.index("## Settings") < once.index(PQ.INFLIGHT_HEADING) < once.index("## Promoted")
    assert (
        once.replace(once[once.index(PQ.INFLIGHT_HEADING) : once.index("## Promoted")], "") == text
    )
    twice = PQ.with_inflight(once, "- two\n")
    assert twice == once.replace("- one\n", "- two\n")
    assert PQ.entries(twice) == PQ.entries(text)
    assert PQ.settings(twice) == PQ.settings(text)


def test_inflight_block_is_never_compared_by_the_queue_gate(tmp_path):
    """RQ compares only the generated block: an in-flight block of any content is no finding, and `--update` leaves its bytes alone. CONTROL: a stale generated block in the same file still is one."""
    root = tmp_path / "root"
    (root / "agent" / "plans").mkdir(parents=True)
    plan = root / "agent" / "plans" / "PLAN-q.md"
    plan.write_text(
        "# PLAN: q\n\nStatus: approved\n\n## Tasks\n\n- [ ] T1 open\n", encoding="utf-8"
    )
    path = root / PQ.QUEUE_REL
    path.write_text(PQ.SKELETON, encoding="utf-8")
    assert PQ.problems(root, update=True) == []
    fresh = path.read_text(encoding="utf-8")
    for body in ("- Mode: effort low.\n", "- anything at all, 1. agent/plans/PLAN-x.md\n"):
        planted = PQ.with_inflight(fresh, body)
        path.write_text(planted, encoding="utf-8")
        assert PQ.problems(root) == [], body
        assert PQ.problems(root, update=True) == []
        assert path.read_text(encoding="utf-8") == planted
    stale = planted.replace("agent/plans/PLAN-q.md --", "agent/plans/PLAN-zz.md --")
    path.write_text(stale, encoding="utf-8")
    assert PQ.problems(root) != []


def test_queue_set_refreshes_the_inflight_block(wl):
    path = wl.proj / PQ.QUEUE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(block("effort: high"), encoding="utf-8")
    got = wl.cli("--queue-set", wlfix.ME, "effort=smart")
    assert got.rc == 0, got.err
    text = path.read_text(encoding="utf-8")
    assert PQ.inflight_text(text) is not None, text
    assert_mode_matches(text, PQ.settings(text)[0])
    assert PQ.inflight_mode(text)["effort"] == "smart"
    assert wl.cli("--queue-set", wlfix.ME, "effort=low").rc == 0
    assert PQ.inflight_mode(path.read_text(encoding="utf-8"))["effort"] == "low"
