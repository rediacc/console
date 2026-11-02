"""`check:ci-retired-terms`, driven as a process against fixture trees and fixture stores.

WHAT THIS ADDS TO THE GATE'S OWN `--selftest`. The controls exercise the pure core against the SHIPPED patterns and fold a scratch store through the real writer verbs. They never run the entry point, so the enumeration of a real plan corpus, the exit codes (0 clean, 1 refusal, 2 cannot run), the item advisory versus the `--owner` refusal, the shrink-only baseline's STALE half and the `--write-baseline` refusals are proven here, each by running the gate as a subprocess against a tree this file built.

THE FILE SUBJECT. Every fixture tree declares one submodule, `sub/a`, a git repo whose index holds its files (`ls-files` reads the index, so nothing is committed). A tree with no `.gitmodules` is CANNOT RUN by design, which is why the plan and item tests carry the clean submodule too. The drain cannot be driven as a subprocess, because `--write-baseline` refuses `--root` and `--config` on purpose, so it is driven through `gather` and `write_baseline` against a scratch config.
"""

import json
import pathlib
import sys

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import retired_terms as RT
from rediacc_ci.tests.gates import harness

GATE = paths.from_root(".ci", "scripts", "quality", "check_retired_terms.py")

TERM = {
    "id": "zorp",
    "pattern": "zorp",
    "case_sensitive": False,
    "retired": "2026-01-01",
    "reason": "the zorp feature is removed completely in the fixture",
    "retired_by": ["agent/plans/PLAN-retire-zorp.md", "#abcd1234"],
    "must_match": ["install Zorp"],
    "must_not_match": ["install zap"],
}


def _write(root: pathlib.Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _plan(status: str, body: str) -> str:
    return "# PLAN: fixture\nStatus: %s\n\n%s\n" % (status, body)


def _event(ev: dict) -> str:
    base = {"at": "2026-10-15T10:00:00Z", "by": "eeeeeeee"}
    base.update(ev)
    return json.dumps(base) + "\n"


SUB = "sub/a"
CLEAN_FILE = {"README.md": "a plain backup to the chunk store\n"}
GOOD_BLOCKER = "BLOCKER: the fixture file names zorp until the fixture removal box drains it"
MARK_REASON = "this comment records the zorp removal so nobody re-adds it"


def _submodules(
    root: pathlib.Path, declared: list[str], present: dict[str, dict[str, str]]
) -> None:
    (root / ".gitmodules").write_text(
        "".join(
            '[submodule "%s"]\n\tpath = %s\n\turl = https://example.invalid/x.git\n' % (p, p)
            for p in declared
        ),
        encoding="utf-8",
    )
    for sm_path, files in present.items():
        repo = root / sm_path
        harness.run(["git", "init", "-q", str(repo)])
        for rel, text in files.items():
            _write(repo, rel, text)
        harness.run(["git", "-C", str(repo), "add", "-A"])


def _tree(
    tmp_path: pathlib.Path,
    *,
    other_plan: str = "nothing retired here",
    events=None,
    baseline=None,
    term=None,
    files=None,
    file_baseline=None,
    file_exclusions=None,
    declared=None,
):
    """A git tree with two live plans, a store and one submodule, plus a config. Returns (root, config)."""
    root = tmp_path / "tree"
    root.mkdir(parents=True)
    harness.run(["git", "init", "-q", str(root)])
    _submodules(root, [SUB] if declared is None else declared, {SUB: files or CLEAN_FILE})
    _write(root, "agent/plans/PLAN-retire-zorp.md", _plan("active", "- [ ] remove zorp everywhere"))
    _write(root, "agent/plans/PLAN-other.md", _plan("active", other_plan))
    if events is None:
        events = [
            {
                "ev": "add",
                "id": "abcd1234",
                "s": " ",
                "o": "eeeeeeee",
                "t": "(eeeeeeee) retire zorp",
            }
        ]
    _write(root, "agent/worklist/eeeeeeee.jsonl", "".join(_event(e) for e in events))
    config = tmp_path / "retired-terms.json"
    config.write_text(
        json.dumps(
            {
                "terms": [term or TERM],
                "plan_baseline": baseline or [],
                "file_baseline": file_baseline or [],
                "file_exclusions": file_exclusions or [],
            }
        ),
        encoding="utf-8",
    )
    return root, config


def _gate(
    root: pathlib.Path, config: pathlib.Path, *argv: str, ci: str = "false"
) -> harness.RunResult:
    """The gate as a subprocess. `CI` is pinned (local by default), so a test means the same thing on a runner, where CI=true is exported."""
    return harness.run(
        [sys.executable, str(GATE), "--root", str(root), "--config", str(config), *argv],
        cwd=paths.repo_root(),
        env={"CI": ci},
    )


def _open_item(item_id: str, text: str, owner: str = "eeeeeeee") -> dict:
    return {"ev": "add", "id": item_id, "s": " ", "o": owner, "t": "(%s) %s" % (owner, text)}


BASE_ITEM = {
    "ev": "add",
    "id": "abcd1234",
    "s": " ",
    "o": "eeeeeeee",
    "t": "(eeeeeeee) retire zorp",
}


def test_selftest_passes():
    result = harness.run([sys.executable, str(GATE), "--selftest"], cwd=paths.repo_root())
    assert result.rc == 0, result.combined
    assert "control(s) ran" in result.out


def test_clean_fixture_passes_and_prints_its_shape(tmp_path):
    root, config = _tree(tmp_path)
    result = _gate(root, config)
    assert result.rc == 0, result.combined
    assert "1 term(s); 1 item(s) folded, 1 open; 2 live plan(s) of 2 enumerated" in result.err
    assert "1 submodule(s) declared, 1 checked out, 1 file(s) read" in result.err


def test_a_live_plan_naming_the_term_is_refused_as_new(tmp_path):
    root, config = _tree(tmp_path, other_plan="- [ ] bake zorp into the image")
    result = _gate(root, config)
    assert result.rc == 1, result.combined
    assert "NEW plan agent/plans/PLAN-other.md names retired term 'zorp'" in result.err
    assert "Do not add it to the baseline." in result.err


def test_the_same_plan_citing_the_retirement_is_allowed(tmp_path):
    root, config = _tree(tmp_path, other_plan="- [ ] drop zorp, per PLAN-retire-zorp")
    result = _gate(root, config)
    assert result.rc == 0, result.combined


def test_an_open_item_is_advisory_and_refused_only_for_its_owner(tmp_path):
    events = [BASE_ITEM, _open_item("1111aaaa", "bake zorp into the VM image")]
    root, config = _tree(tmp_path, events=events)
    advisory = _gate(root, config)
    assert advisory.rc == 0, advisory.combined
    assert "ADVISORY item #1111aaaa owner eeeeeeee names retired term 'zorp'" in advisory.err
    mine = _gate(root, config, "--owner", "eeeeeeee")
    assert mine.rc == 1, mine.combined
    assert "ITEM #1111aaaa" in mine.err
    other = _gate(root, config, "--owner", "ffffffff")
    assert other.rc == 0, other.combined


def test_a_closed_item_is_ignored(tmp_path):
    events = [
        BASE_ITEM,
        _open_item("2222bbbb", "bake zorp into the VM image"),
        {
            "ev": "state",
            "id": "2222bbbb",
            "s": "x",
            "note": "withdrawn",
            "at": "2026-10-15T10:00:01Z",
        },
    ]
    root, config = _tree(tmp_path, events=events)
    result = _gate(root, config, "--owner", "eeeeeeee")
    assert result.rc == 0, result.combined
    assert "2222bbbb" not in result.combined


def test_an_empty_store_cannot_run(tmp_path):
    root, config = _tree(tmp_path, events=[])
    result = _gate(root, config)
    assert result.rc == 2, result.combined
    assert "ZERO items" in result.err


def test_zero_live_plans_cannot_run(tmp_path):
    root, config = _tree(tmp_path)
    for rel in ("agent/plans/PLAN-retire-zorp.md", "agent/plans/PLAN-other.md"):
        _write(root, rel, _plan("done", "finished"))
    result = _gate(root, config)
    assert result.rc == 2, result.combined
    assert "ZERO live plans" in result.err


def test_a_retired_by_path_naming_no_file_cannot_run(tmp_path):
    term = dict(TERM, retired_by=["agent/plans/PLAN-nowhere.md"])
    root, config = _tree(tmp_path, term=term)
    result = _gate(root, config)
    assert result.rc == 2, result.combined
    assert "PLAN-nowhere.md is no file in the tree" in result.err


def test_a_retired_by_plan_moved_to_done_still_resolves(tmp_path):
    """Review 44fdd3b7.1: a retirement plan that closes moves to _done/ and may lose its stub; its citation still resolves."""
    term = dict(TERM, retired_by=["agent/plans/PLAN-closed-retirement.md"])
    root, config = _tree(tmp_path, term=term)
    _write(root, "agent/plans/_done/PLAN-closed-retirement.md", _plan("done", "finished"))
    result = _gate(root, config)
    # The run reaches a verdict (the fixture's live plan names the term without citing the moved plan, rc 1) instead of stopping at path resolution (CannotRunError, rc 2).
    assert result.rc == 1, result.combined
    assert "is no file in the tree" not in result.combined
    assert "NEW plan agent/plans/PLAN-retire-zorp.md" in result.combined


def test_retired_by_resolution_is_exact(tmp_path):
    """Reviews e34c5d6f.1-.3 and dcd58b41.1: only a top-level plan ref follows a move, nested folders and non-plan names do not, a ref leaving the tree never resolves, and a non-plan ref with `..` that stays inside resolves as written."""
    root = tmp_path / "tree"
    (root / "agent/plans/_done").mkdir(parents=True)
    (root / "agent/plans/sub/_done").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "agent/plans/_done/PLAN-a.md").write_text("x")
    (root / "agent/plans/sub/_done/PLAN-b.md").write_text("x")
    (root / "agent/plans/_done/notes.txt").write_text("x")
    (root / "README.md").write_text("x")
    (tmp_path / "PLAN-out.md").write_text("x")
    assert RT._resolves(root, "agent/plans/PLAN-a.md")
    assert RT._resolves(root, "agent/plans/_removed/PLAN-a.md")
    assert not RT._resolves(root, "agent/plans/sub/PLAN-b.md")
    assert not RT._resolves(root, "agent/plans/notes.txt")
    # `..` that leaves the tree to a file that EXISTS outside it (review bf93555d.4: a missing in-tree target proved nothing).
    assert not RT._resolves(root, "agent/plans/../../../PLAN-out.md")
    assert not RT._resolves(root, "../PLAN-out.md")
    assert RT._resolves(root, "docs/../README.md")
    # A symlink inside the tree pointing out of it never resolves, the moved-plan copies included (reviews bf93555d.1, .2).
    (root / "docs/out.md").symlink_to(tmp_path / "PLAN-out.md")
    assert not RT._resolves(root, "docs/out.md")
    (root / "agent/plans/_removed").mkdir()
    (root / "agent/plans/_removed/PLAN-out.md").symlink_to(tmp_path / "PLAN-out.md")
    assert not RT._resolves(root, "agent/plans/PLAN-out.md")
    # A symlink loop inside the tree is no file, never a crash (review bf93555d.3).
    (root / "docs/loop-a").symlink_to(root / "docs/loop-b")
    (root / "docs/loop-b").symlink_to(root / "docs/loop-a")
    assert not RT._resolves(root, "docs/loop-a")


def test_a_pattern_failing_its_own_texts_cannot_run(tmp_path):
    term = dict(TERM, must_not_match=["zorpify"])
    root, config = _tree(tmp_path, term=term)
    result = _gate(root, config)
    assert result.rc == 2, result.combined
    assert "matches its must_not_match text" in result.err


def test_a_baselined_pair_that_stopped_firing_is_stale(tmp_path):
    baseline = [
        {
            "plan": "agent/plans/PLAN-other.md",
            "term": "zorp",
            "blocker": "BLOCKER: the fixture plan named zorp before the fixture retirement landed",
        }
    ]
    root, config = _tree(tmp_path, baseline=baseline)
    result = _gate(root, config)
    assert result.rc == 1, result.combined
    assert "STALE baseline agent/plans/PLAN-other.md no longer names 'zorp'" in result.err


def test_a_baselined_pair_still_firing_is_held_and_printed(tmp_path):
    baseline = [
        {
            "plan": "agent/plans/PLAN-other.md",
            "term": "zorp",
            "blocker": "BLOCKER: the fixture plan named zorp before the fixture retirement landed",
        }
    ]
    root, config = _tree(tmp_path, other_plan="- [ ] bake zorp", baseline=baseline)
    result = _gate(root, config)
    assert result.rc == 0, result.combined
    assert "BASELINED plan agent/plans/PLAN-other.md" in result.err


def test_write_baseline_refuses_a_foreign_tree_or_config(tmp_path):
    root, config = _tree(tmp_path)
    result = _gate(root, config, "--write-baseline")
    assert result.rc == 2, result.combined
    assert "does not combine with --root, --owner or --config" in result.err


# --------------------------------------------------------------------------- the file subject


def _fb(path: str, count: int, blocker: str = GOOD_BLOCKER) -> dict:
    return {"path": path, "term": "zorp", "count": count, "blocker": blocker}


def test_a_planted_term_in_a_submodule_file_fires_as_new(tmp_path):
    root, config = _tree(tmp_path, files={"doc.md": "intro\ninstall zorp here\n"})
    result = _gate(root, config)
    assert result.rc == 1, result.combined
    assert (
        "NEW file sub/a/doc.md names retired term 'zorp' 1 time(s), baseline allows 0" in result.err
    )
    assert "lines: 2" in result.err
    assert "Do not add it to the baseline." in result.err


def test_a_file_citing_the_retirement_is_still_a_finding(tmp_path):
    root, config = _tree(tmp_path, files={"doc.md": "install zorp, per PLAN-retire-zorp\n"})
    result = _gate(root, config)
    assert result.rc == 1, result.combined
    assert "NEW file sub/a/doc.md" in result.err


def test_a_clean_submodule_is_silent(tmp_path):
    root, config = _tree(tmp_path)
    result = _gate(root, config)
    assert result.rc == 0, result.combined
    assert "NOT CHECKED: none; 0 file pair(s) firing" in result.err
    assert "NEW file" not in result.err


def test_a_marked_line_with_a_reason_is_silent(tmp_path):
    text = "install zorp here  # retired-term-ok(zorp): %s\n" % MARK_REASON
    root, config = _tree(tmp_path, files={"doc.md": text})
    result = _gate(root, config)
    assert result.rc == 0, result.combined
    assert "0 refused marker(s)" in result.err


@pytest.mark.parametrize(
    ("line", "message"),
    [
        ("install zorp  # retired-term-ok(zorp)", "carries no reason"),
        ("install zorp  # retired-term-ok(zorp):   ", "carries no reason"),
        ("install zorp  # retired-term-ok(zorp): no fix", "no fix"),
        ("install zap  # retired-term-ok(zorp): %s" % MARK_REASON, "DEAD marker"),
        ("install zorp  # retired-term-ok(zorpp): %s" % MARK_REASON, "names no term"),
    ],
    ids=["no-reason", "empty-reason", "low-effort", "dead", "unknown-term"],
)
def test_a_bad_marker_is_refused(tmp_path, line, message):
    root, config = _tree(tmp_path, files={"doc.md": line + "\n"})
    result = _gate(root, config)
    assert result.rc == 1, result.combined
    assert "MARKER sub/a/doc.md:1" in result.err
    assert message in result.err


def test_a_baselined_file_is_held_a_rise_is_new_and_a_fall_is_stale(tmp_path):
    two = {"doc.md": "zorp one\nzorp two\n"}
    held_root, held_cfg = _tree(
        tmp_path / "held", files=two, file_baseline=[_fb("sub/a/doc.md", 2)]
    )
    held = _gate(held_root, held_cfg)
    assert held.rc == 0, held.combined
    assert "BASELINED file sub/a/doc.md names 'zorp' 2 time(s)" in held.err

    rise_root, rise_cfg = _tree(
        tmp_path / "rise", files=two, file_baseline=[_fb("sub/a/doc.md", 1)]
    )
    rise = _gate(rise_root, rise_cfg)
    assert rise.rc == 1, rise.combined
    assert (
        "NEW file sub/a/doc.md names retired term 'zorp' 2 time(s), baseline allows 1" in rise.err
    )

    fall_root, fall_cfg = _tree(
        tmp_path / "fall", files=two, file_baseline=[_fb("sub/a/doc.md", 3)]
    )
    fall = _gate(fall_root, fall_cfg)
    assert fall.rc == 1, fall.combined
    assert "STALE file baseline sub/a/doc.md 'zorp' allows 3, now 2" in fall.err


def test_an_excluded_prefix_is_silent_and_a_dead_one_cannot_run(tmp_path):
    files = {"README.md": "clean\n", "drizzle/0001.sql": "-- zorp\n"}
    good = [{"prefix": "sub/a/drizzle/", "blocker": GOOD_BLOCKER}]
    root, config = _tree(tmp_path / "live", files=files, file_exclusions=good)
    result = _gate(root, config)
    assert result.rc == 0, result.combined
    assert "(2 tracked, 1 excluded)" in result.err

    dead = [{"prefix": "sub/a/migrations/", "blocker": GOOD_BLOCKER}]
    root, config = _tree(tmp_path / "dead", files=files, file_exclusions=dead)
    result = _gate(root, config)
    assert result.rc == 2, result.combined
    assert "match no tracked file" in result.err


def test_a_file_baseline_entry_without_a_blocker_cannot_run(tmp_path):
    root, config = _tree(
        tmp_path, files={"doc.md": "zorp\n"}, file_baseline=[_fb("sub/a/doc.md", 1, "later")]
    )
    result = _gate(root, config)
    assert result.rc == 2, result.combined
    assert "carries no `BLOCKER:` reason" in result.err


def test_a_declared_but_absent_submodule_is_not_checked_locally_and_fails_closed_in_ci(tmp_path):
    root, config = _tree(tmp_path, declared=[SUB, "sub/gone"])
    local = _gate(root, config)
    assert local.rc == 0, local.combined
    assert "2 submodule(s) declared, 1 checked out" in local.err
    assert "NOT CHECKED sub/gone" in local.err
    ci = _gate(root, config, ci="true")
    assert ci.rc == 2, ci.combined
    assert "sub/gone" in ci.err
    assert "CANNOT RUN" in ci.err


def test_zero_declared_submodules_cannot_run(tmp_path):
    root, config = _tree(tmp_path, declared=[])
    result = _gate(root, config)
    assert result.rc == 2, result.combined
    assert "declares ZERO submodules" in result.err


def test_the_owner_call_never_reads_files(tmp_path):
    root, config = _tree(tmp_path, files={"doc.md": "install zorp\n"})
    result = _gate(root, config, "--owner", "eeeeeeee")
    assert result.rc == 0, result.combined
    assert "submodule(s) declared" not in result.combined


def test_the_drain_lowers_and_removes_but_never_raises_or_adds(tmp_path, monkeypatch):
    files = {"a.md": "zorp\n", "b.md": "zorp\nzorp\nzorp\n", "c.md": "clean\n", "d.md": "zorp\n"}
    baseline = [_fb("sub/a/a.md", 3), _fb("sub/a/b.md", 1), _fb("sub/a/c.md", 2)]
    root, config = _tree(tmp_path, files=files, file_baseline=baseline)
    monkeypatch.setenv("CI", "false")
    report = RT.gather(root, config)
    assert RT.write_baseline(config, report) == 0
    after = {e["path"]: e["count"] for e in json.loads(config.read_text())["file_baseline"]}
    # a.md lowered 3 -> 1; b.md rose to 3 and stays at its old ceiling 1 (still NEW);
    # c.md fell to 0 and is removed; d.md was never baselined and is not added.
    assert after == {"sub/a/a.md": 1, "sub/a/b.md": 1}


def test_the_drain_refuses_while_a_submodule_is_not_checked(tmp_path, monkeypatch):
    root, config = _tree(
        tmp_path,
        files={"a.md": "zorp\n"},
        file_baseline=[_fb("sub/a/a.md", 1)],
        declared=[SUB, "sub/gone"],
    )
    monkeypatch.setenv("CI", "false")
    before = config.read_text()
    report = RT.gather(root, config)
    assert RT.write_baseline(config, report) == 2
    assert config.read_text() == before
