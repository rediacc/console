"""`check:ci-retired-terms`, driven as a process against fixture trees and fixture stores.

WHAT THIS ADDS TO THE GATE'S OWN `--selftest`. The controls exercise the pure core against the SHIPPED patterns and fold a scratch store through the real writer verbs. They never run the entry point, so the enumeration of a real plan corpus, the exit codes (0 clean, 1 refusal, 2 cannot run), the item advisory versus the `--owner` refusal, the shrink-only baseline's STALE half and the `--write-baseline` refusals are proven here, each by running the gate as a subprocess against a tree this file built.
"""

import json
import pathlib
import sys

from rediacc_ci import paths
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


def _tree(
    tmp_path: pathlib.Path,
    *,
    other_plan: str = "nothing retired here",
    events=None,
    baseline=None,
    term=None,
):
    """A git tree with two live plans and a store, plus a config. Returns (root, config)."""
    root = tmp_path / "tree"
    root.mkdir()
    harness.run(["git", "init", "-q", str(root)])
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
        json.dumps({"terms": [term or TERM], "plan_baseline": baseline or []}), encoding="utf-8"
    )
    return root, config


def _gate(root: pathlib.Path, config: pathlib.Path, *argv: str) -> harness.RunResult:
    return harness.run(
        [sys.executable, str(GATE), "--root", str(root), "--config", str(config), *argv],
        cwd=paths.repo_root(),
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
    assert result.rc != 2, result.combined
    assert "is no file in the tree" not in result.err


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
