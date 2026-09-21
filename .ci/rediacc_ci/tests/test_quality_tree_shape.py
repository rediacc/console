"""`rediacc_ci.quality.tree_shape`, and the derivation it must not turn into a copy.

THE PURE CORE IS PURE. `split_entries`, the eight finding functions and `bare_relative_sites` take data and return data, so every case here is a literal in and a literal out, with no fixture tree and no git.

THE TWO CASES THAT ARE NOT ABOUT A FINDING are the ones worth reading first: `test_the_real_policy_and_the_real_hook_agree` is the derivation itself against the live tree, and `test_a_relative_constant_joined_to_a_root_is_not_a_finding` pins the precision that took the T6 rule from eleven false positives to zero.
"""

import json
import pathlib

import pytest

from rediacc_ci import paths, policy_paths
from rediacc_ci.quality import shrink_only
from rediacc_ci.quality import tree_shape as TS

ROOT = paths.repo_root()
RESERVED = {"archive", "programs", "worklist", "reggate", "plans", "pr", "legacy"}
TOP_NAMES = {"agent", "docs", "scripts", ".ci", ".claude", "packages"}
CALLEES = {"open", "os.listdir", "os.scandir"}
FS_METHODS = {"glob", "is_dir", "read_text"}


@pytest.fixture(scope="module")
def policy() -> dict:
    return TS.load_policy(ROOT)


# --------------------------------------------------------------------------- The policy file itself.


def test_the_policy_is_registered_in_both_inventories():
    """A policy file in neither POLICY_FILES list is reached by a hardcoded join.

    That is not hypothetical here: `.language-policy-allowlist` landed on 2026-09-07 in the directory and in neither list, and nothing was red for a day.
    """
    assert policy_paths.is_policy_file_name(TS.POLICY_NAME)
    assert TS.policy_path(ROOT).is_file()


def test_the_real_policy_and_the_real_hook_agree(policy):
    """T5 against the LIVE tree, which is the whole point of deriving rather than copying."""
    paths.on_sys_path(paths.hooks_stop_dir(ROOT))
    wl_store = pytest.importorskip("wl_store")
    assert TS.finding_t5(policy, set(wl_store.AGENT_RESERVED_DIRS)) == []


# --------------------------------------------------------------------------- split_entries.


def test_split_entries_infers_directories_from_separators():
    listing = ["README.md", "agent/RULES.md", "agent/abcd1234/STATE.md", "docs/x/y.md"]
    root_files, root_dirs, agent_files, agent_dirs = TS.split_entries(listing)
    assert root_files == {"README.md"}
    assert root_dirs == {"agent", "docs"}
    assert agent_files == {"RULES.md"}
    assert agent_dirs == {"abcd1234"}


def test_split_entries_ignores_an_empty_path():
    assert TS.split_entries(["", "README.md"])[0] == {"README.md"}


# --------------------------------------------------------------------------- The findings.


def test_t1_names_the_stray_and_not_the_permitted(policy):
    found = TS.finding_t1({"README.md", "aa.jsonl"}, policy)
    assert [f.path for f in found] == ["aa.jsonl"]
    assert found[0].code == "T1"


def test_t2_fires_on_a_top_level_directory_nothing_declares(policy):
    assert [f.path for f in TS.finding_t2({"agent", "claude"}, policy)] == ["claude"]


def test_t3_admits_the_three_patterns_and_refuses_anything_else(policy):
    ok = {"PLAN-x.md", "REPORT-y.md", "census-plan-record.jsonl", "README.md", "INDEX.md"}
    assert TS.finding_t3(ok, policy) == []
    assert [f.path for f in TS.finding_t3({"zz.jsonl"}, policy)] == ["agent/zz.jsonl"]


def test_t4_reads_a_session_slug_by_shape(policy):
    assert TS.finding_t4({"abcd1234", "archive"}, policy, RESERVED) == []
    assert [f.path for f in TS.finding_t4({"not-a-session"}, policy, RESERVED)] == [
        "agent/not-a-session"
    ]


def test_t5_fires_in_both_directions_and_names_the_missing_half(policy):
    declared = TS.policy_agent_dirs(policy)
    assert TS.finding_t5(policy, declared) == []
    assert [f.path for f in TS.finding_t5(policy, declared | {"ledgers"})] == ["ledgers"]
    assert [f.path for f in TS.finding_t5(policy, declared - {"pr"})] == ["pr"]


def test_t7_wins_over_every_other_finding(policy):
    """A lost enumeration must not also report zero of everything else as though it looked."""
    codes = {
        f.code
        for f in TS.findings(
            ["README.md", "aa.jsonl"],
            policy=policy,
            reserved=RESERVED,
            bare_sites=[],
            baseline=None,
        )
    }
    assert codes == {"T7"}


def test_t8_reports_a_baseline_entry_that_no_longer_fires(policy):
    clean = _clean_listing()
    codes = {
        f.code
        for f in TS.findings(
            clean, policy=policy, reserved=RESERVED, bare_sites=[], baseline=["aa.jsonl"]
        )
    }
    assert codes == {"T8"}


def test_the_baseline_silences_exactly_its_own_entries(policy):
    listing = [*_clean_listing(), "aa.jsonl", "zz.jsonl"]
    kept = TS.findings(
        listing, policy=policy, reserved=RESERVED, bare_sites=[], baseline=["aa.jsonl"]
    )
    assert [f.path for f in kept] == ["zz.jsonl"]


def test_the_seed_set_ignores_the_baseline(policy):
    listing = [*_clean_listing(), "aa.jsonl"]
    assert TS.live_entries(listing, policy=policy, reserved=RESERVED, bare_sites=[]) == ["aa.jsonl"]


def _clean_listing() -> list[str]:
    return [
        "README.md",
        "package.json",
        "pyproject.toml",
        "conftest.py",
        "run.sh",
        "rdc.sh",
        "LICENSE",
        "Dockerfile",
        "biome.json",
        ".gitignore",
        ".npmrc",
        "CLAUDE.md",
        "agent/README.md",
        "agent/RULES.md",
        "agent/INDEX.md",
        "agent/DECISIONS.md",
        "agent/PLAN-sample.md",
        "agent/plans/PLAN-other.md",
        "agent/archive/0815-1/STATE.md",
        "agent/worklist/abcd1234.jsonl",
        "agent/reggate/main.jsonl",
        "agent/pr/main.md",
        "agent/legacy/STATE.md",
        "agent/programs/thing/README.md",
        "agent/abcd1234/STATE.md",
        "docs/agent-reference/TRAPS.md",
        "scripts/ci-runner/manifest.ts",
        ".ci/rediacc_ci/paths.py",
        ".claude/settings.json",
        "packages/cli/package.json",
    ]


# --------------------------------------------------------------------------- T6, and the precision it was given.


def _sites(source: str) -> list[str]:
    return [
        lit for _line, lit in TS.bare_relative_sites(source, "x.py", TOP_NAMES, CALLEES, FS_METHODS)
    ]


def test_a_relative_constant_joined_to_a_root_is_not_a_finding():
    """The pattern eleven modules in this tree already use, and it is the CORRECT one.

    A rule that flagged construction alone reported all eleven, and every one was `root / TWIN` at the call site. Precision here is what keeps the finding meaningful rather than something a reader learns to scroll past.
    """
    assert _sites('import pathlib\nTWIN = pathlib.Path(".ci") / "lib" / "setup.sh"\n') == []
    assert _sites('import os\nREL = os.path.join(".ci", "scripts", "x.sh")\n') == []


def test_a_literal_the_filesystem_is_touched_through_is_a_finding():
    assert _sites('import pathlib\npathlib.Path("agent").is_dir()\n') == ["agent"]
    assert _sites('import pathlib\npathlib.Path("agent").glob("PLAN-*.md")\n') == ["agent"]
    assert _sites('open("agent/INDEX.md")\n') == ["agent/INDEX.md"]


def test_a_segment_that_is_not_a_top_level_directory_is_skipped():
    assert _sites('import pathlib\npathlib.Path(".").is_dir()\n') == []
    assert _sites('import pathlib\npathlib.Path("node_modules").is_dir()\n') == []
    assert _sites('open("/etc/passwd")\n') == []
    assert _sites('open("../agent/INDEX.md")\n') == []


def test_a_file_that_does_not_parse_is_silent_rather_than_fatal():
    assert TS.bare_relative_sites("def (:\n", "x.py", TOP_NAMES, CALLEES, FS_METHODS) == []


def test_top_level_names_come_from_the_listing():
    assert TS.top_level_names(["agent/x.md", "README.md", "docs/y/z.md"]) == {"agent", "docs"}


# --------------------------------------------------------------------------- The enumeration and the baseline.


def test_enumerate_tree_reports_a_failed_git_rather_than_an_empty_tree(tmp_path):
    found, why = TS.enumerate_tree(tmp_path)
    assert found == []
    assert "ls-files" in why


def test_read_baseline_answers_none_for_an_absent_file(tmp_path):
    assert TS.read_baseline(tmp_path / "nope.json") is None


def test_read_baseline_answers_none_for_a_file_that_does_not_parse(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert TS.read_baseline(bad) is None


def test_read_baseline_reads_the_strays_key(tmp_path):
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"note": "x", "strays": ["a", "b"]}), encoding="utf-8")
    assert TS.read_baseline(good) == ["a", "b"]


def test_the_shrink_only_decision_is_the_shared_one():
    """A second Python copy of this decision is what `shrink_only` exists to prevent."""
    assert shrink_only.baseline_additions(["a", "b", "c"], ["a", "new"]) == ["new"]
    assert shrink_only.write_verdict(baseline_exists=True, first_seed=False, additions=["x"]) == (
        "would-grow"
    )
    assert shrink_only.write_verdict(baseline_exists=False, first_seed=False, additions=[]) == (
        "missing-baseline"
    )
    assert shrink_only.write_verdict(baseline_exists=False, first_seed=True, additions=[]) is None


def test_the_refusal_names_the_file_and_the_remedy():
    missing = TS.render_refusal("missing-baseline", [], 0, 3)
    assert TS.BASELINE_LABEL in missing
    assert "--first-seed" in missing
    grew = TS.render_refusal("would-grow", ["aa.jsonl"], 3, 4)
    assert "aa.jsonl" in grew
    assert policy_paths.policy_rel(TS.POLICY_NAME) in grew


def test_the_root_conftest_carries_the_snapshot_fixture():
    """The runtime half of this gate. Without it a test may write the tree and stay green."""
    text = (pathlib.Path(ROOT) / "conftest.py").read_text(encoding="utf-8")
    assert "_tree_snapshot" in text
    assert 'scope="session", autouse=True' in text
