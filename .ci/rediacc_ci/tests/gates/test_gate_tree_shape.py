"""`check:ci-tree-shape`, driven as a process against real git trees.

WHAT THIS ADDS TO THE GATE'S OWN `--selftest`. Those controls plant into a fixture LISTING and call the pure functions; they prove the classifier works and nothing else. The enumeration, the derivation of `AGENT_RESERVED_DIRS` from a real `.claude/`, the baseline read, the exit codes and the `--write-baseline` refusals are all untested by them, so every case here runs the
entry point as a subprocess against a tree it built.
"""

import json
import pathlib
import shutil
import sys

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

GATE = paths.from_root(".ci", "scripts", "quality", "check_tree_shape.py")
POLICY = paths.from_root(".ci", "policy", "tree-shape.json")
HOOKS = paths.from_root(".claude", "hooks", "stop")

#: Enough root files and top-level directories to clear both vacuity floors, which is what lets a control assert about a FINDING rather than about the refusal.
FILLER_ROOT = (
    "README.md",
    "LICENSE",
    "package.json",
    "pyproject.toml",
    "run.sh",
    "rdc.sh",
    "Dockerfile",
    "biome.json",
    "tsconfig.json",
    "knip.jsonc",
    "regions.json",
)
FILLER_DIRS = ("docs", "scripts", "packages", "compose", "workers")


def _git(repo: pathlib.Path, *args: str) -> str:
    result = harness.run(["git", "-C", str(repo), *args])
    if result.rc != 0:
        raise harness.GateAssertionError(
            "git %s failed in the fixture (rc=%d): %s" % (" ".join(args), result.rc, result.err)
        )
    return result.out


def _gate(root: pathlib.Path, *argv: str) -> harness.RunResult:
    return harness.run(
        [sys.executable, str(GATE), *argv],
        cwd=paths.repo_root(),
        env={"TREE_SHAPE_ROOT": str(root)},
    )


def _write(root: pathlib.Path, rel: str, text: str = "x\n") -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _seed(tmp_path: pathlib.Path, extra: dict[str, str] | None = None) -> pathlib.Path:
    """A committed tree that every class in the real policy permits."""
    root = tmp_path / "tree"
    (root / ".ci" / "policy").mkdir(parents=True)
    shutil.copy(POLICY, root / ".ci" / "policy" / "tree-shape.json")
    # The hook is COPIED rather than stubbed: the gate derives AGENT_RESERVED_DIRS from it, and a stub would be a second copy of the very list the derivation exists to avoid.
    shutil.copytree(
        HOOKS, root / ".claude" / "hooks" / "stop", ignore=shutil.ignore_patterns("__pycache__")
    )
    for name in FILLER_ROOT:
        _write(root, name)
    for name in FILLER_DIRS:
        _write(root, "%s/placeholder.md" % name)
    for name in ("README.md", "RULES.md", "INDEX.md", "DECISIONS.md", "PLAN-sample.md"):
        _write(root, "agent/%s" % name)
    _write(root, "agent/plans/PLAN-other.md")
    _write(root, "agent/worklist/abcd1234.jsonl")
    _write(root, "agent/reggate/main.jsonl")
    _write(root, "agent/pr/main.md")
    _write(root, "agent/legacy/STATE.md")
    _write(root, "agent/archive/0815-1/STATE.md")
    _write(root, "agent/programs/thing/README.md")
    _write(root, "agent/abcd1234/STATE.md")
    for rel, text in (extra or {}).items():
        _write(root, rel, text)
    _git(root, "init", "-q", ".")
    _git(root, "config", "user.email", "fixture@example.invalid")
    _git(root, "config", "user.name", "fixture")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    return root


# --------------------------------------------------------------------------- Preconditions.


def test_git_is_available_or_this_file_asserts_nothing(gate):
    if shutil.which("git") is None:
        gate.log_fail("git is absent; every case in this file would assert nothing")
    gate.log_pass("git is available, so the fixtures below are real repositories")


# --------------------------------------------------------------------------- The real tree.


def test_the_real_tree_passes_and_says_what_it_counted(gate):
    result = harness.run([sys.executable, str(GATE)], cwd=paths.repo_root())
    gate.assert_exit_code(0, result.rc, "the real tree must be green")
    gate.assert_contains(result.out, "✓ tree shape:", "the success line names the corpus")
    gate.assert_contains(result.out, "Blind spot:", "a green says what it did not check")
    gate.log_pass("the real tree passes and reports what it enumerated")


def test_the_controls_run_before_the_verdict(gate):
    result = harness.run([sys.executable, str(GATE)], cwd=paths.repo_root())
    gate.assert_contains(
        result.out, "controls first, then the verdict", "controls are not optional"
    )
    gate.log_pass("controls run on every invocation, not only under --selftest")


def test_selftest_alone_is_green(gate):
    result = harness.run([sys.executable, str(GATE), "--selftest"], cwd=paths.repo_root())
    gate.assert_exit_code(0, result.rc, "the planted controls must pass")
    gate.log_pass("--selftest is green")


def test_the_real_enumeration_sees_more_than_one_top_level_directory(gate):
    """THE VACUITY THIS GATE ALREADY SHIPPED ONCE, caught before it landed.

    The first pathspec was `:(glob)*` plus `agent`, which admits root files and the agent tree and therefore yields exactly ONE top-level directory name. Every other finding still reported, so the gate looked healthy while T2 had nothing it could fire on. The floor is what turns that back into a refusal, and this asserts the real run is above it.
    """
    result = harness.run([sys.executable, str(GATE)], cwd=paths.repo_root())
    gate.assert_not_contains(result.combined, "VACUOUS", "the real run is above every floor")
    gate.assert_contains(result.out, "root director(ies)", "and it prints the count it floored")
    gate.log_pass("the real enumeration clears the top-level-directory floor")


# --------------------------------------------------------------------------- Anti-vacuity.


def _empty_repo(path: pathlib.Path) -> harness.RunResult:
    (path / ".ci" / "policy").mkdir(parents=True, exist_ok=True)
    shutil.copy(POLICY, path / ".ci" / "policy" / "tree-shape.json")
    _git(path, "init", "-q", ".")
    return _gate(path)


def test_an_empty_tree_refuses_rather_than_passing(gate, tmp_path):
    gate.assert_vacuous_tree_fails(
        _empty_repo,
        tmp_path,
        "VACUOUS INPUT",
        "a checkout with almost nothing in it must refuse, not report a clean shape",
    )


def test_a_directory_that_is_not_a_checkout_is_blocked_rather_than_judged(gate, tmp_path):
    bare = tmp_path / "bare"
    bare.mkdir()
    result = _gate(bare)
    gate.assert_exit_code(77, result.rc, "no checkout means no verdict, which is 77 not 0")
    gate.assert_contains(result.combined, "CANNOT RUN", "and it says so rather than passing")
    gate.log_pass("a non-checkout is BLOCKED, never a silent green")


def test_a_tree_without_the_hook_cannot_derive_the_reserved_set(gate, tmp_path):
    """The derivation is load-bearing, so its absence is CANNOT RUN rather than a pass."""
    root = _seed(tmp_path)
    shutil.rmtree(root / ".claude")
    result = _gate(root)
    gate.assert_exit_code(77, result.rc, "without wl_store there is nothing to derive T5 from")
    gate.assert_contains(
        result.combined, "AGENT_RESERVED_DIRS", "the refusal names what is missing"
    )
    gate.log_pass("a missing hook blocks the verdict instead of skipping the derivation")


# --------------------------------------------------------------------------- The findings, end to end.


def test_a_clean_fixture_tree_is_green(gate, tmp_path):
    """The mirror for every case below. Without it the gate could be a function that always reds."""
    result = _gate(_seed(tmp_path))
    gate.assert_exit_code(0, result.rc, "a tree that obeys every class must be silent")
    gate.log_pass("a clean fixture tree is green")


def test_a_stray_root_file_is_fatal(gate, tmp_path):
    root = _seed(tmp_path, {"aa.jsonl": "{}\n"})
    result = _gate(root)
    gate.assert_exit_code(1, result.rc, "a file at the root in no class is a finding")
    gate.assert_contains(result.err, "T1 aa.jsonl", "T1 names the file")
    gate.log_pass("T1 fires on a stray root file")


def test_an_untracked_stray_is_seen_too(gate, tmp_path):
    """`--others --exclude-standard` is the half that catches debris nobody committed.

    Every file the retired bash worklist suites left at the root was UNTRACKED, so a gate reading the index alone would have reported a clean tree throughout.
    """
    root = _seed(tmp_path)
    (root / "zz.jsonl").write_text("{}\n", encoding="utf-8")
    result = _gate(root)
    gate.assert_exit_code(1, result.rc, "an untracked stray is still a stray")
    gate.assert_contains(result.err, "T1 zz.jsonl", "T1 names the untracked file")
    gate.log_pass("an untracked-not-ignored stray is a finding")


def test_a_gitignored_file_is_output_rather_than_a_stray(gate, tmp_path):
    root = _seed(tmp_path)
    (root / ".gitignore").write_text("ignored.log\n", encoding="utf-8")
    (root / "ignored.log").write_text("noise\n", encoding="utf-8")
    _git(root, "add", ".gitignore")
    _git(root, "commit", "-qm", "ignore")
    result = _gate(root)
    gate.assert_exit_code(0, result.rc, "an ignored file is output and must not red the tree")
    gate.assert_not_contains(result.combined, "ignored.log", "and it is not named either")
    gate.log_pass("--exclude-standard keeps build output out of the verdict")


def test_a_new_top_level_directory_is_fatal(gate, tmp_path):
    root = _seed(tmp_path, {"claude/notes.md": "x\n"})
    result = _gate(root)
    gate.assert_exit_code(1, result.rc, "a new top-level directory is a new concept")
    gate.assert_contains(result.err, "T2 claude", "T2 names the directory")
    gate.log_pass("T2 fires on an undeclared top-level directory")


def test_a_loose_file_under_agent_is_fatal(gate, tmp_path):
    root = _seed(tmp_path, {"agent/zz.jsonl": "{}\n"})
    result = _gate(root)
    gate.assert_exit_code(1, result.rc, "a loose file under agent/ is a finding")
    gate.assert_contains(result.err, "T3 agent/zz.jsonl", "T3 names the file")
    gate.log_pass("T3 fires on a loose file under agent/")


def test_a_directory_under_agent_that_is_not_a_session_is_fatal(gate, tmp_path):
    root = _seed(tmp_path, {"agent/not-a-session/NOTES.md": "x\n"})
    result = _gate(root)
    gate.assert_exit_code(1, result.rc, "the hook would report it as a peer session")
    gate.assert_contains(result.err, "T4 agent/not-a-session", "T4 names the directory")
    gate.log_pass("T4 fires on a directory that is neither reserved nor a session slug")


def test_a_policy_that_disagrees_with_the_hook_is_fatal(gate, tmp_path):
    root = _seed(tmp_path)
    policy = json.loads((root / ".ci/policy/tree-shape.json").read_text(encoding="utf-8"))
    policy["agent_dirs"]["classes"] = [
        c for c in policy["agent_dirs"]["classes"] if c["name"] != "pr"
    ]
    (root / ".ci/policy/tree-shape.json").write_text(json.dumps(policy, indent=2), encoding="utf-8")
    result = _gate(root)
    gate.assert_exit_code(1, result.rc, "a policy that has lost a reserved directory is a finding")
    gate.assert_contains(result.err, "T5 ", "T5 fires")
    gate.assert_contains(result.err, "AGENT_RESERVED_DIRS", "and it names the other list")
    gate.log_pass("T5 catches the policy drifting away from the hook")


def test_a_bare_relative_repository_path_is_fatal(gate, tmp_path):
    root = _seed(tmp_path)
    _write(
        root,
        ".ci/rediacc_ci/offender.py",
        'import pathlib\n\n\ndef where():\n    return pathlib.Path("agent").is_dir()\n',
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "offender")
    result = _gate(root)
    gate.assert_exit_code(1, result.rc, "a literal the filesystem is touched through is a finding")
    gate.assert_contains(result.err, "T6 .ci/rediacc_ci/offender.py", "T6 names the file and line")
    gate.log_pass("T6 fires on a repository path built from a bare relative string")


def test_a_relative_constant_joined_to_a_root_is_silent(gate, tmp_path):
    """The mirror for T6, and the reason the rule is worth having rather than noisy."""
    root = _seed(tmp_path)
    _write(
        root,
        ".ci/rediacc_ci/careful.py",
        'import pathlib\n\nTWIN = pathlib.Path(".ci") / "lib" / "setup.sh"\n\n\n'
        "def read(root):\n    return (root / TWIN).read_text()\n",
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "careful")
    result = _gate(root)
    gate.assert_exit_code(0, result.rc, "the correct pattern must not be a finding")
    gate.log_pass("a relative constant a caller joins to a root is silent")


# --------------------------------------------------------------------------- The baseline.


def test_a_baselined_stray_is_silent_and_a_new_one_is_not(gate, tmp_path):
    root = _seed(tmp_path, {"aa.jsonl": "{}\n"})
    _write(
        root,
        ".ci/config/tree-shape-baseline.json",
        json.dumps({"note": "fixture", "strays": ["aa.jsonl"]}, indent=2) + "\n",
    )
    silent = _gate(root)
    gate.assert_exit_code(0, silent.rc, "a baselined stray is frozen debt, not a finding")
    (root / "zz.jsonl").write_text("{}\n", encoding="utf-8")
    loud = _gate(root)
    gate.assert_exit_code(1, loud.rc, "a NEW stray beside a baselined one still fires")
    gate.assert_contains(loud.err, "T1 zz.jsonl", "and only the new one is named")
    gate.assert_not_contains(loud.err, "T1 aa.jsonl", "the baselined one stays silent")
    gate.log_pass("the baseline freezes exactly its own entries")


def test_a_baseline_entry_that_no_longer_fires_is_reported(gate, tmp_path):
    root = _seed(tmp_path)
    _write(
        root,
        ".ci/config/tree-shape-baseline.json",
        json.dumps({"note": "fixture", "strays": ["aa.jsonl"]}, indent=2) + "\n",
    )
    result = _gate(root)
    gate.assert_exit_code(1, result.rc, "a stale baseline entry hides the next regression")
    gate.assert_contains(result.err, "T8 aa.jsonl", "T8 names the stale entry")
    gate.log_pass("T8 reports a baseline entry that no longer fires")


def test_write_baseline_refuses_a_first_seed_that_was_not_declared(gate, tmp_path):
    root = _seed(tmp_path, {"aa.jsonl": "{}\n"})
    result = _gate(root, "--write-baseline")
    gate.assert_exit_code(1, result.rc, "deleting the baseline must not be a way to reseed it")
    gate.assert_contains(result.combined, "--first-seed", "the refusal names the declaration")
    gate.log_pass("--write-baseline refuses a missing baseline unless a first seed is declared")


def test_write_baseline_refuses_growth(gate, tmp_path):
    root = _seed(tmp_path, {"aa.jsonl": "{}\n"})
    _write(
        root,
        ".ci/config/tree-shape-baseline.json",
        json.dumps({"note": "fixture", "strays": ["aa.jsonl"]}, indent=2) + "\n",
    )
    (root / "zz.jsonl").write_text("{}\n", encoding="utf-8")
    result = _gate(root, "--write-baseline")
    gate.assert_exit_code(1, result.rc, "the baseline shrinks and never grows")
    gate.assert_contains(result.combined, "zz.jsonl", "the refusal names what would be added")
    gate.assert_contains(result.combined, "never grows", "and why a total is not the claim")
    gate.log_pass("--write-baseline refuses a reseed that would GROW the set")


def test_write_baseline_seeds_and_then_drains(gate, tmp_path):
    root = _seed(tmp_path, {"aa.jsonl": "{}\n"})
    seeded = _gate(root, "--write-baseline", "--first-seed")
    gate.assert_exit_code(0, seeded.rc, "a declared first seed is allowed")
    path = root / ".ci/config/tree-shape-baseline.json"
    gate.assert_eq(json.loads(path.read_text(encoding="utf-8"))["strays"], ["aa.jsonl"], "seeded")
    gate.assert_exit_code(0, _gate(root).rc, "and the tree is green against its own baseline")
    _git(root, "rm", "-q", "aa.jsonl")
    gate.assert_exit_code(0, _gate(root, "--write-baseline").rc, "a genuine shrink is allowed")
    gate.assert_eq(json.loads(path.read_text(encoding="utf-8"))["strays"], [], "drained to empty")
    gate.log_pass("--write-baseline seeds once, then only ever drains")
