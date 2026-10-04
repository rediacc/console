"""The QUEUE.md settings block: reader, writer, solo marker, the `--queue-set` verb and the RQ-SETTINGS finding (agent/plans/PLAN-stop-hook-turbo.md boxes T1, T3, T15, T23).

The parser tests drive `wl_planqueue` directly; the verb tests drive the real CLI through `wlfix`; the gate test runs `check_plan_record.py` against a fixture root. Every FIRE has an inverse that differs by one planted fact.
"""

from __future__ import annotations

import dataclasses
import os
import pathlib
import subprocess
import sys

import pytest

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

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


ALL_KEYS = (
    "stop_hook",
    "turbo",
    "batch_size",
    "writer_cap",
    "cadence",
    "agent_hint",
    "agent_pushback",
    "judge",
)


def test_defaults_when_there_is_no_settings_section():
    got, problems = PQ.settings(HEAD + TAIL)
    assert problems == []
    assert got == PQ.Settings()
    assert (got.stop_hook, got.turbo, got.batch_size, got.writer_cap) == (True, False, 1, 4)
    assert (got.cadence, got.agent_hint, got.agent_pushback, got.judge) == (True,) * 4
    assert got.notes == {}
    assert PQ.settings("") == (PQ.Settings(), [])


def test_the_dataclass_is_frozen_with_the_contract_fields():
    names = [f.name for f in dataclasses.fields(PQ.Settings)]
    assert names == [*ALL_KEYS, "notes"]
    with pytest.raises(dataclasses.FrozenInstanceError):
        PQ.Settings().turbo = True  # type: ignore[misc]


def test_every_key_parses_and_notes_are_kept():
    got, problems = PQ.settings(
        block(
            "stop_hook: off -- paused by the operator\nturbo: on\nbatch_size: 7\n"
            "writer_cap: 2 -- cap -- with a second separator\ncadence: off\n"
            "agent_hint: off\nagent_pushback: off\njudge: off"
        )
    )
    assert problems == []
    assert (got.stop_hook, got.turbo, got.batch_size, got.writer_cap) == (False, True, 7, 2)
    assert (got.cadence, got.agent_hint, got.agent_pushback, got.judge) == (False,) * 4
    assert got.notes == {
        "stop_hook": "paused by the operator",
        "writer_cap": "cap -- with a second separator",
    }
    # CONTROL: the same block with the values flipped differs, so the test reads the values.
    other, _ = PQ.settings(block("stop_hook: on\nturbo: off\nbatch_size: 1\nwriter_cap: 4"))
    assert other != got


def test_an_unknown_key_is_a_problem_and_the_rest_still_parse():
    got, problems = PQ.settings(block("turbo: on\nturbx: on\nbatch_size: 3"))
    assert [p for p in problems if "turbx" in p], problems
    assert (got.turbo, got.batch_size) == (True, 3)
    # CONTROL: without the unknown key there is no problem.
    assert PQ.settings(block("turbo: on\nbatch_size: 3"))[1] == []


@pytest.mark.parametrize(
    "line",
    [
        "turbo: onn",
        "turbo: true",
        "turbo:",
        "stop_hook: of",
        "batch_size: 0",
        "batch_size: -1",
        "batch_size: two",
        "batch_size: 1.5",
        "writer_cap: 0",
        "judge: ON",
    ],
)
def test_a_bad_value_falls_back_to_that_keys_default(line):
    key = line.split(":")[0]
    got, problems = PQ.settings(block("%s\ncadence: off" % line))
    assert len(problems) == 1, problems
    assert key in problems[0], problems
    assert getattr(got, key) == getattr(PQ.Settings(), key)
    assert got.cadence is False  # the rest still parses


def test_a_duplicate_key_falls_back_to_the_default():
    got, problems = PQ.settings(block("stop_hook: off\nstop_hook: off\nturbo: on"))
    assert got.stop_hook is True
    assert got.turbo is True
    assert any("stop_hook" in p and "2 times" in p for p in problems), problems


def test_a_line_that_is_not_key_value_is_a_problem():
    _got, problems = PQ.settings(block("turbo on"))
    assert problems
    assert "turbo on" in problems[0]


def test_a_second_fence_is_ignored_and_reported():
    text = block("turbo: on").replace("## Promoted", "```stop-hook\nturbo: off\n```\n\n## Promoted")
    got, problems = PQ.settings(text)
    assert got.turbo is True  # the first fence wins
    assert any("second" in p for p in problems), problems


def test_a_fence_outside_the_section_is_reported():
    text = HEAD + TAIL + "\n```stop-hook\nturbo: on\n```\n"
    got, problems = PQ.settings(text)
    assert got.turbo is False
    assert any("outside" in p for p in problems), problems


def test_the_section_below_promoted_is_reported_and_not_read():
    text = HEAD + TAIL + "\n## Settings\n\n```stop-hook\nturbo: on\nstop_hook: off\n```\n"
    got, problems = PQ.settings(text)
    assert (got.turbo, got.stop_hook) == (False, True)  # the fail-safe direction
    assert any("below" in p for p in problems), problems


def test_an_unclosed_fence_and_a_section_without_a_fence_are_reported():
    _g, unclosed = PQ.settings(HEAD + "## Settings\n\n```stop-hook\nturbo: on\n\n" + TAIL)
    assert unclosed
    _g, empty = PQ.settings(HEAD + "## Settings\n\nProse only.\n\n" + TAIL)
    assert any("no `stop-hook` fence" in p for p in empty), empty


def test_the_section_does_not_leak_into_the_queue_entries():
    text = block("turbo: on")
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
    queue.write_text(block("turbo: on"), encoding="utf-8")
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "t@t")
    git(tmp_path, "config", "user.name", "t")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "base")
    queue.write_text(block("turbo: off\nbatch_size: 5"), encoding="utf-8")
    assert PQ.settings_for(tmp_path)[0].batch_size == 5
    at_head, problems = PQ.settings_for(tmp_path, "HEAD")
    assert (at_head.turbo, at_head.batch_size, problems) == (True, 1, [])
    # CONTROL: the rev read and the working-tree read differ, so neither is the other.
    assert PQ.settings_for(tmp_path)[0].turbo is False
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


def test_set_settings_rewrites_only_the_fence_lines():
    text = block("stop_hook: on -- keep this note\nturbo: off -- old reason\nbatch_size: 1")
    new = PQ.set_settings(text, {"turbo": "on", "writer_cap": "2"}, note="operator test")
    lo, hi = fence_span(text)
    nlo, nhi = fence_span(new)
    assert (text[:lo], text[hi:]) == (new[:nlo], new[nhi:])  # every other byte identical
    assert new[nlo:nhi] == (
        "stop_hook: on -- keep this note\nturbo: on -- operator test\nbatch_size: 1\n"
        "writer_cap: 2 -- operator test\n"
    )
    got, problems = PQ.settings(new)
    assert problems == []
    assert (got.turbo, got.writer_cap, got.batch_size) == (True, 2, 1)
    # The round trip: setting the values already there changes nothing at all.
    assert PQ.set_settings(new, {"turbo": "on", "writer_cap": "2"}, note="operator test") == new


def test_set_settings_note_policy():
    text = block("turbo: off -- reason one")
    assert "reason one" in PQ.set_settings(text, {"turbo": "off"})  # unchanged value keeps it
    flipped = PQ.set_settings(text, {"turbo": "on"})  # a changed value drops the stale reason
    assert "reason one" not in flipped
    assert "turbo: on\n" in flipped


def test_set_settings_drops_later_duplicates_of_an_updated_key():
    text = block("turbo: off\nturbo: off\nbatch_size: 2")
    new = PQ.set_settings(text, {"turbo": "on"})
    assert PQ.settings(new) == (PQ.Settings(turbo=True, batch_size=2), [])
    assert new.count("turbo:") == 1


def test_set_settings_creates_the_section_above_promoted():
    text = HEAD + TAIL
    new = PQ.set_settings(text, {"turbo": "on", "batch_size": "3"}, note="n")
    assert new.index("## Settings") < new.index("## Promoted")
    assert new.startswith(HEAD)
    assert new.endswith(TAIL)
    lo, hi = fence_span(new)
    keys = [line.split(":")[0] for line in new[lo:hi].splitlines()]
    assert keys == list(ALL_KEYS)  # all eight, in the documented order
    got, problems = PQ.settings(new)
    assert problems == []
    assert (got.turbo, got.batch_size) == (True, 3)
    assert got.notes == {"turbo": "n", "batch_size": "n"}
    # With no Promoted heading the section is appended.
    bare = PQ.set_settings("# Plan queue\n", {"turbo": "on"})
    assert bare.startswith("# Plan queue\n")
    assert PQ.settings(bare)[0].turbo is True


@pytest.mark.parametrize(
    ("updates", "note"),
    [
        ({"turbx": "on"}, None),
        ({"turbo": "onn"}, None),
        ({"batch_size": "0"}, None),
        ({"turbo": "on"}, "two\nlines"),
    ],
)
def test_set_settings_refuses_what_the_reader_would_reject(updates, note):
    with pytest.raises(ValueError, match=r"."):
        PQ.set_settings(block("turbo: off"), updates, note)


def test_set_settings_refuses_a_structurally_broken_block():
    below = HEAD + TAIL + "\n## Settings\n\n```stop-hook\nturbo: on\n```\n"
    with pytest.raises(ValueError, match="below"):
        PQ.set_settings(below, {"turbo": "on"})
    with pytest.raises(ValueError, match="no `stop-hook` fence"):
        PQ.set_settings(HEAD + "## Settings\n\nProse.\n\n" + TAIL, {"turbo": "on"})


def test_sources_name_where_each_value_comes_from():
    got = PQ.sources(block("turbo: on\nbatch_size: x"))
    assert got["turbo"] == "QUEUE.md"
    assert got["batch_size"] == "default"  # a bad value falls back, so it is not the file's
    assert got["judge"] == "default"
    assert set(got) == set(ALL_KEYS)


def test_the_live_queue_has_a_clean_block():
    text = (REPO / PQ.QUEUE_REL).read_text(encoding="utf-8")
    got, problems = PQ.settings(text)
    assert problems == [], problems
    assert PQ.sources(text) == dict.fromkeys(ALL_KEYS, "QUEUE.md")
    assert "stop_hook: on" in text
    assert got.stop_hook is True


# ---- the verb ----------------------------------------------------------------------------------


def plant(wl, body: str) -> pathlib.Path:  # noqa: F811
    path = wl.proj / PQ.QUEUE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_queue_set_writes_atomically_prints_git_add_and_never_commits(wl):  # noqa: F811
    wl.reg_repo()
    queue = plant(wl, block("turbo: off -- old\nbatch_size: 1"))
    wl.git("add", "-A")
    wl.git("commit", "-qm", "chore: queue")
    head = wl.git("rev-parse", "HEAD").stdout
    before = queue.read_text(encoding="utf-8")
    got = wl.cli("--queue-set", wlfix.ME, "turbo=on", "batch_size=2", "--note", "operator test")
    assert got.rc == 0, got.err
    assert "turbo: on (QUEUE.md)" in got.out
    assert "batch_size: 2 (QUEUE.md)" in got.out
    assert "git add agent/plans/QUEUE.md" in got.out
    after = queue.read_text(encoding="utf-8")
    assert after != before
    settings, problems = PQ.settings(after)
    assert problems == []
    assert (settings.turbo, settings.batch_size) == (True, 2)
    assert settings.notes["turbo"] == "operator test"
    assert wl.git("rev-parse", "HEAD").stdout == head  # no commit was made
    assert wl.git("status", "--porcelain").stdout.strip() == "M agent/plans/QUEUE.md"
    assert not list(queue.parent.glob(".planrec-*")), "an atomic-write temp file was left behind"


@pytest.mark.parametrize(
    "pairs",
    [
        ["turbo=onn"],
        ["turbo=on", "batch_size=0"],  # one good pair must not be written when another is bad
        ["turbx=on"],
        ["turbo"],
        ["turbo=on", "turbo=off"],
        ["--oops"],
        ["turbo=on", "--note"],
    ],
)
def test_queue_set_refuses_a_bad_call_and_leaves_the_file_untouched(wl, pairs):  # noqa: F811
    queue = plant(wl, block("turbo: off\nbatch_size: 1"))
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
    assert wl.cli("--queue-set", wlfix.ME, "turbo=on").rc == 0
    assert queue.read_bytes() != before


def test_queue_set_refuses_a_broken_block_and_a_missing_file(wl):  # noqa: F811
    missing = wl.cli("--queue-set", wlfix.ME, "turbo=on")
    assert missing.rc == 2
    assert "unreadable" in missing.err
    assert not (wl.proj / PQ.QUEUE_REL).exists()  # a refusal does not create the file
    queue = plant(wl, HEAD + TAIL + "\n## Settings\n\n```stop-hook\nturbo: on\n```\n")
    before = queue.read_bytes()
    got = wl.cli("--queue-set", wlfix.ME, "turbo=off")
    assert got.rc == 2
    assert "below" in got.err
    assert queue.read_bytes() == before


def test_queue_set_checks_the_identity_like_the_other_verbs(wl):  # noqa: F811
    queue = plant(wl, block("turbo: off"))
    before = queue.read_bytes()
    foreign = wl.cli("--queue-set", "cafe1234", "turbo=on")
    assert foreign.rc != 0, (foreign.rc, foreign.err)
    assert queue.read_bytes() == before
    usage = wl.cli("--queue-set")
    assert usage.rc == 2
    assert "usage: --queue-set" in usage.err


def test_queue_set_bare_prints_values_sources_and_problems(wl):  # noqa: F811
    plant(wl, block("turbo: on -- operator test\nbatch_size: x\nturbx: on"))
    got = wl.cli("--queue-set", wlfix.ME)
    assert got.rc == 0, got.err
    lines = got.out.splitlines()
    assert "turbo: on (QUEUE.md) -- operator test" in lines
    assert "batch_size: 1 (default)" in lines  # the bad value fell back
    assert "judge: on (default)" in lines
    assert any(line.startswith("PROBLEM") and "turbx" in line for line in lines), got.out
    assert any(line.startswith("PROBLEM") and "batch_size" in line for line in lines), got.out
    assert [ln.split(":")[0] for ln in lines if not ln.startswith("PROBLEM")] == list(ALL_KEYS)
    # No file at all: every value is a default and nothing is written.
    (wl.proj / PQ.QUEUE_REL).unlink()
    bare = wl.cli("--queue-set", wlfix.ME)
    assert bare.rc == 0
    assert "turbo: off (default)" in bare.out
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
    good = "# Plan queue\n\n" + block("turbo: on").split("# Plan queue\n\n", 1)[1]
    finding = (
        "RQ-SETTINGS: agent/plans/QUEUE.md"  # the selftest's own PASS lines say RQ-SETTINGS too
    )
    assert finding not in gate_output(tmp_path / "ok", good)
    bad = gate_output(tmp_path / "bad", good.replace("turbo: on", "turbo: onn"))
    assert finding + ": turbo: expected on|off, got 'onn'" in bad, bad[-600:]
