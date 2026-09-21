"""`check:ci-plan-folders`, driven as a process against real git trees.

WHAT THIS ADDS TO THE GATE'S OWN `--selftest`. Those controls plant into fixture TEXT and call the pure functions; they prove the DETECTOR works and nothing else. Everything between the detector and a verdict is untested by them: the enumeration, the git clocks, the ledger read, the exit code, and the two verbs that write. So every case here runs the entry point as a subprocess
against a tree it built, and reads the exit code rather than a return value.

THE FIXTURE IS A REAL GIT REPOSITORY because three of the four things under test are git: `enumerate_plans` shells `ls-files`, the clocks shell `log`, and `--move` shells `mv`. A directory of files would pass an enumeration that had stopped working.
"""

import json
import pathlib
import shutil
import subprocess
import sys

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

GATE = paths.from_root(".ci", "scripts", "quality", "check_plan_folders.py")
LIFECYCLE = paths.from_root(".ci", "config", "plan-lifecycle.json")

#: One more than the gate's own floor, so a fixture can lose a plan to a control without the floor firing instead of the finding under test.
FILLERS = 22


def _git(repo: pathlib.Path, *args: str, when: str | None = None) -> str:
    env = {"GIT_COMMITTER_DATE": when, "GIT_AUTHOR_DATE": when} if when else {}
    result = harness.run(["git", "-C", str(repo), *args], env=env)
    if result.rc != 0:
        raise harness.GateAssertionError(
            "git %s failed in the fixture (rc=%d): %s" % (" ".join(args), result.rc, result.err)
        )
    return result.out


def _gate(root: pathlib.Path, *argv: str) -> harness.RunResult:
    env = {"PLAN_FOLDERS_ROOT": str(root)}
    return harness.run([sys.executable, str(GATE), *argv], cwd=paths.repo_root(), env=env)


def _write(root: pathlib.Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _seed(tmp_path: pathlib.Path, extra: dict[str, str] | None = None) -> pathlib.Path:
    """A committed tree with FILLERS plans under agent/plans/ plus whatever `extra` names."""
    root = tmp_path / "tree"
    (root / ".ci" / "config").mkdir(parents=True)
    shutil.copy(LIFECYCLE, root / ".ci" / "config" / "plan-lifecycle.json")
    for i in range(FILLERS):
        _write(
            root,
            "agent/plans/PLAN-filler-%02d.md" % i,
            "# PLAN: filler %d\nStatus: in-progress\n\n- [ ] a box\n" % i,
        )
    for rel, text in (extra or {}).items():
        _write(root, rel, text)
    _git(root, "init", "-q", ".")
    _git(root, "config", "user.email", "fixture@example.invalid")
    _git(root, "config", "user.name", "fixture")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    return root


def _ledger(root: pathlib.Path, rows: dict[str, dict]) -> None:
    _write(root, ".ci/config/plan-boxes.json", json.dumps({"plans": rows}, indent=2) + "\n")


# --------------------------------------------------------------------------- Preconditions. A missing tool is an unrun test, never flake.


def test_git_is_available_or_this_file_asserts_nothing(gate):
    if shutil.which("git") is None:
        gate.log_fail("git is absent; every case in this file would assert nothing")
    gate.log_pass("git is available, so the fixtures below are real repositories")


def test_the_subject_exists_and_is_executable(gate):
    if not GATE.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(GATE))
    gate.log_pass("subject under test is present")


# --------------------------------------------------------------------------- The real tree.


def test_the_real_tree_passes_and_says_what_it_counted(gate):
    result = harness.run([sys.executable, str(GATE)], cwd=paths.repo_root())
    gate.assert_exit_code(0, result.rc, "the real tree must be green with F1 fatal")
    gate.assert_contains(result.out, "✓ plan folders:", "the success line names the corpus")
    gate.assert_contains(result.out, "Blind spot:", "a green says what it did not check")
    gate.log_pass("the real tree passes and reports its corpus")


def test_the_controls_run_before_the_verdict(gate):
    result = harness.run([sys.executable, str(GATE)], cwd=paths.repo_root())
    gate.assert_contains(
        result.out, "controls first, then the verdict", "controls are not optional"
    )
    gate.assert_contains(result.out, "control(s) passed", "the control tally is printed")
    gate.log_pass("controls run on every invocation, not only under --selftest")


def test_selftest_alone_is_green(gate):
    result = harness.run([sys.executable, str(GATE), "--selftest"], cwd=paths.repo_root())
    gate.assert_exit_code(0, result.rc, "the planted controls must pass")
    gate.log_pass("--selftest is green")


# --------------------------------------------------------------------------- Anti-vacuity.


def _empty_repo(path: pathlib.Path) -> harness.RunResult:
    """An initialised repository with a config and no plans at all.

    THE REPOSITORY IS REAL ON PURPOSE. A bare directory answers exit 77, which the ci-runner classifies as BLOCKED and which is the honest answer to "this is not a checkout". The vacuity hole is one folder in from there: a tree that IS a checkout, where the enumeration returns nothing and a naive gate reports a clean layout.
    """
    (path / ".ci" / "config").mkdir(parents=True, exist_ok=True)
    shutil.copy(LIFECYCLE, path / ".ci" / "config" / "plan-lifecycle.json")
    _git(path, "init", "-q", ".")
    return _gate(path)


def test_an_empty_tree_refuses_rather_than_passing(gate, tmp_path):
    gate.assert_vacuous_tree_fails(
        _empty_repo,
        tmp_path,
        "VACUOUS INPUT",
        "a checkout with no plans must refuse, not report a clean layout",
    )


def test_a_directory_that_is_not_a_checkout_is_blocked_rather_than_judged(gate, tmp_path):
    bare = tmp_path / "bare"
    bare.mkdir()
    result = _gate(bare)
    gate.assert_exit_code(77, result.rc, "no checkout means no verdict, which is 77 not 0")
    gate.assert_contains(result.combined, "CANNOT RUN", "and it says so rather than passing")
    gate.log_pass("a non-checkout is BLOCKED, never a silent green")


def test_a_tree_below_the_floor_refuses(gate, tmp_path):
    root = tmp_path / "thin"
    (root / ".ci" / "config").mkdir(parents=True)
    shutil.copy(LIFECYCLE, root / ".ci" / "config" / "plan-lifecycle.json")
    _write(root, "agent/plans/PLAN-only.md", "# PLAN: only\nStatus: in-progress\n")
    _git(root, "init", "-q", ".")
    _git(root, "config", "user.email", "fixture@example.invalid")
    _git(root, "config", "user.name", "fixture")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    result = _gate(root)
    gate.assert_exit_code(1, result.rc, "one plan is below the floor and must refuse")
    gate.assert_contains(result.combined, "floor is", "the refusal names the floor")
    gate.log_pass("a corpus below the floor refuses rather than reporting a clean layout")


def test_a_config_without_the_retention_keys_is_a_setup_error(gate, tmp_path):
    root = _seed(tmp_path)
    doc = json.loads((root / ".ci/config/plan-lifecycle.json").read_text(encoding="utf-8"))
    del doc["terminal_days"]
    _write(root, ".ci/config/plan-lifecycle.json", json.dumps(doc, indent=2))
    result = _gate(root)
    gate.assert_exit_code(2, result.rc, "a missing retention key is a setup error, not a verdict")
    gate.assert_contains(result.combined, "terminal_days", "the refusal names the missing key")
    gate.log_pass("a config missing a clock refuses with exit 2 rather than defaulting")


# --------------------------------------------------------------------------- The findings, end to end.


def test_a_legacy_plan_is_fatal(gate, tmp_path):
    """F1 stopped being an advisory when the 103 moved; the flag went with them."""
    root = _seed(tmp_path, {"agent/PLAN-old.md": "# PLAN: old\nStatus: in-progress\n"})
    result = _gate(root)
    gate.assert_exit_code(1, result.rc, "a plan at the legacy path is a red, not a note")
    gate.assert_contains(result.err, "F1 agent/PLAN-old.md", "the finding goes to stderr")
    gate.assert_eq(
        "PLAN_FOLDERS_STRICT" in GATE.read_text(encoding="utf-8"),
        False,
        "the escape hatch is gone rather than left behind switched off",
    )
    gate.log_pass("F1 is fatal, and the flag that made it advisory no longer exists")


def test_a_stub_at_the_legacy_path_is_not_a_finding(gate, tmp_path):
    """The mirror F1 needs now that it is fatal: the legacy path is where a stub LIVES."""
    root = _seed(
        tmp_path,
        {
            "agent/plans/PLAN-old.md": "# PLAN: old\nStatus: in-progress\n",
            "agent/PLAN-old.md": (
                "# PLAN: old (moved)\nStatus: moved\nMoved-To: agent/plans/PLAN-old.md\n\nmoved\n"
            ),
        },
    )
    result = _gate(root)
    gate.assert_exit_code(0, result.rc, "a stub at the old path is the mechanism, not a defect")
    gate.log_pass("a stubbed move is green under the strict rule")


def test_a_finished_plan_in_the_active_folder_is_fatal(gate, tmp_path):
    root = _seed(tmp_path, {"agent/plans/PLAN-shipped.md": "# PLAN: shipped\nStatus: shipped\n"})
    result = _gate(root)
    gate.assert_exit_code(1, result.rc, "F2 is fatal from the day the gate lands")
    gate.assert_contains(result.err, "F2 agent/plans/PLAN-shipped.md", "F2 names the file")
    gate.assert_contains(result.err, "agent/plans/_done", "the message names where it belongs")
    gate.log_pass("F2 fires on a folder that disagrees with the status")


def test_a_terminal_plan_past_its_retention_is_fatal(gate, tmp_path):
    root = _seed(
        tmp_path,
        {"agent/plans/_done/PLAN-gone.md": "# PLAN: gone\nStatus: done\nFirst-Seen: 2024-01-01\n"},
    )
    _ledger(root, {"agent/plans/_done/PLAN-gone.md": {"moved_at": "2024-02-01"}})
    result = _gate(root)
    gate.assert_exit_code(1, result.rc, "a terminal plan past 40 days is a finding")
    gate.assert_contains(result.err, "F3 agent/plans/_done/PLAN-gone.md", "F3 names the file")
    gate.log_pass("F3 reads moved_at out of the ledger and fires past the retention")


def test_a_stub_pointing_at_nothing_is_fatal(gate, tmp_path):
    root = _seed(
        tmp_path,
        {
            "agent/PLAN-ghost.md": (
                "# PLAN: ghost (moved)\nStatus: moved\n"
                "Moved-To: agent/plans/_done/PLAN-ghost.md\n\nmoved\n"
            )
        },
    )
    result = _gate(root)
    gate.assert_exit_code(1, result.rc, "a stub whose target is missing is a dead citation")
    gate.assert_contains(result.err, "F5 agent/PLAN-ghost.md", "F5 names the stub")
    gate.log_pass("F5 fires on a stub that resolves to nothing")


def test_a_citation_in_the_generated_ledger_must_resolve(gate, tmp_path):
    root = _seed(tmp_path)
    _ledger(root, {"agent/plans/PLAN-never-written.md": {"moved_at": ""}})
    result = _gate(root)
    gate.assert_exit_code(1, result.rc, "a ledger key naming no file is a broken citation")
    gate.assert_contains(result.err, "F7 ", "F7 fires")
    gate.assert_contains(result.err, "PLAN-never-written.md", "the message names the citation")
    gate.log_pass("F7 fires on a generated file citing a path that does not exist")


def test_a_clean_fixture_tree_is_green(gate, tmp_path):
    """The mirror for every case above. Without it the gate could be a function that always reds."""
    root = _seed(tmp_path)
    result = _gate(root)
    gate.assert_exit_code(0, result.rc, "a tree that obeys every rule must be silent")
    gate.assert_contains(result.out, "✓ plan folders:", "and must say so")
    gate.log_pass("a clean fixture tree is green")


# --------------------------------------------------------------------------- The verbs that write.


def test_sweep_refuses_to_delete_without_write(gate, tmp_path):
    root = _seed(
        tmp_path,
        {"agent/plans/_done/PLAN-gone.md": "# PLAN: gone\nStatus: done\nFirst-Seen: 2024-01-01\n"},
    )
    _ledger(root, {"agent/plans/_done/PLAN-gone.md": {"moved_at": "2024-02-01"}})
    result = _gate(root, "--sweep")
    gate.assert_exit_code(0, result.rc, "a dry run is a report, not a verdict")
    gate.assert_contains(result.combined, "Refusing to delete", "it says why it did nothing")
    gate.assert_eq(
        (root / "agent/plans/_done/PLAN-gone.md").is_file(),
        True,
        "the file must still be there after a dry run",
    )
    gate.log_pass("--sweep without --write names what would go and deletes nothing")


def test_sweep_with_write_deletes_and_leaves_a_tombstone(gate, tmp_path):
    root = _seed(
        tmp_path,
        {"agent/plans/_done/PLAN-gone.md": "# PLAN: gone\nStatus: done\nFirst-Seen: 2024-01-01\n"},
    )
    _ledger(root, {"agent/plans/_done/PLAN-gone.md": {"moved_at": "2024-02-01"}})
    result = _gate(root, "--sweep", "--write")
    gate.assert_exit_code(0, result.rc, "the sweep must succeed")
    gate.assert_eq(
        (root / "agent/plans/_done/PLAN-gone.md").exists(),
        False,
        "the expired plan is deleted",
    )
    index = (root / "agent/INDEX.md").read_text(encoding="utf-8")
    gate.assert_contains(index, "## Expired plans", "the tombstone section is written")
    gate.assert_contains(index, "PLAN-gone.md", "the row names the plan")
    blob = index.split("`")[-2]
    shown = subprocess.run(
        ["git", "-C", str(root), "cat-file", "blob", blob],
        capture_output=True,
        text=True,
        check=False,
    )
    gate.assert_exit_code(0, shown.returncode, "the tombstone blob must resolve")
    gate.assert_contains(shown.stdout, "Status: done", "and must hold the plan's own text")
    gate.log_pass("--sweep --write deletes the file and keeps its text in a resolvable blob")


def test_move_leaves_a_stub_and_stamps_both_clocks(gate, tmp_path):
    root = _seed(
        tmp_path, {"agent/PLAN-closing.md": "# PLAN: closing\nStatus: done\n\n- [x] a box\n"}
    )
    _ledger(root, {"agent/PLAN-closing.md": {"status": "done", "open": 0, "done": 1}})
    result = _gate(root, "--move", "agent/PLAN-closing.md")
    gate.assert_exit_code(0, result.rc, "the move must succeed")
    moved = root / "agent/plans/_done/PLAN-closing.md"
    gate.assert_eq(moved.is_file(), True, "the plan is at its new path")
    gate.assert_contains(moved.read_text(encoding="utf-8"), "First-Seen:", "the clock is stamped")
    stub = (root / "agent/PLAN-closing.md").read_text(encoding="utf-8")
    gate.assert_contains(stub, "Status: moved", "a stub is left at the old path")
    gate.assert_contains(
        stub, "Moved-To: agent/plans/_done/PLAN-closing.md", "and it points forward"
    )
    rows = json.loads((root / ".ci/config/plan-boxes.json").read_text(encoding="utf-8"))["plans"]
    gate.assert_eq("agent/PLAN-closing.md" in rows, False, "the old ledger key is gone")
    gate.assert_contains(
        rows["agent/plans/_done/PLAN-closing.md"]["moved_at"], "-", "moved_at is a date"
    )
    gate.log_pass("--move renames, stubs, stamps First-Seen and re-keys the ledger row")


def test_move_refuses_a_stub(gate, tmp_path):
    root = _seed(
        tmp_path,
        {
            "agent/PLAN-ghost.md": (
                "# PLAN: ghost (moved)\nStatus: moved\n"
                "Moved-To: agent/plans/_done/PLAN-ghost.md\n\nmoved\n"
            )
        },
    )
    result = _gate(root, "--move", "agent/PLAN-ghost.md")
    gate.assert_exit_code(1, result.rc, "a plan moves exactly once")
    gate.assert_contains(result.combined, "already a stub", "the refusal says why")
    gate.log_pass("--move refuses a second hop")


def test_move_refuses_a_plan_with_no_clock_to_carry(gate, tmp_path):
    """An uncommitted plan has no `%cI`, so a move would start its 90-day clock today."""
    root = _seed(tmp_path)
    _write(root, "agent/PLAN-fresh.md", "# PLAN: fresh\nStatus: draft\n")
    result = _gate(root, "--move", "agent/PLAN-fresh.md")
    gate.assert_exit_code(1, result.rc, "a move must not reset a clock it cannot read")
    gate.assert_contains(result.combined, "must not buy freshness", "the refusal names the risk")
    gate.log_pass("--move refuses a plan whose pre-move date cannot be read")


def test_move_refuses_a_terminal_plan_with_no_ledger_row(gate, tmp_path):
    """`moved_at` is CARRIED from the box ledger, so a row-less terminal move starts no clock.

    Found by the migration's own retention test: `_record_move` re-keys an existing row and returns silently when there is none, which leaves a plan in `_done/` whose 40-day clock never starts and which `--sweep` can never reach. A move into an ACTIVE folder is spared, because nothing there reads `moved_at`.
    """
    root = _seed(
        tmp_path,
        {
            "agent/PLAN-orphan.md": "# PLAN: orphan\nStatus: done\n\n- [x] a box\n",
            "agent/PLAN-live.md": "# PLAN: live\nStatus: in-progress\n\n- [ ] a box\n",
        },
    )
    _ledger(root, {})
    result = _gate(root, "--move", "agent/PLAN-orphan.md")
    gate.assert_exit_code(1, result.rc, "a terminal move that starts no clock is refused")
    gate.assert_contains(result.combined, "retention clock would never start", "and says why")
    gate.assert_eq((root / "agent/plans/_done/PLAN-orphan.md").exists(), False, "and nothing moved")
    spared = _gate(root, "--move", "agent/PLAN-live.md")
    gate.assert_exit_code(0, spared.rc, "an active plan needs no moved_at and is spared")
    gate.assert_eq(
        (root / "agent/plans/PLAN-live.md").is_file(), True, "so that one really did move"
    )
    gate.log_pass("--move refuses a terminal move whose retention clock would never start")


def test_status_reports_without_a_verdict(gate, tmp_path):
    root = _seed(tmp_path)
    result = _gate(root, "--status")
    gate.assert_exit_code(0, result.rc, "--status never reaches a verdict")
    gate.assert_contains(result.out, "due for sweep:", "it says how much is due")
    gate.assert_contains(result.out, "active", "and buckets the corpus by state")
    gate.log_pass("--status reports the layout and reaches no verdict")
