"""G-A5 is NEVER-DELETE: the end-to-end half `check_plan_boxes.py --selftest` cannot do.

NEW TEST, NOT A PORT, so there is no `.ci/scripts/test/gates/test-*.sh` named here.

WHY THIS FILE EXISTS BESIDE A 31-CONTROL SELFTEST. Every control in that selftest drives `transition_problems()` with `base_ledger`, `renames_into_archive`, `_touched_plans`, `_added_plans` and `_content_age_days` all stubbed out through `globals()`. That is the right shape for a rule table, and it is structurally incapable of catching the thing that actually decides the verdict
here: whether the GIT plumbing feeding those five functions produces the inputs the rule table expects.
Age comes out of `git log -1 --format=%cI <base> -- <path>`, the archive exemption
comes out of `git diff --find-renames -M100%`, and the base ledger comes out of `git show <base>:.ci/config/plan-boxes.json`. A stub agrees with whatever it is told.

So every case below builds a REAL git repository, commits real plan files with real committer dates, and drives the gate as a PROCESS through `PLAN_BOXES_ROOT` and `PLAN_BOXES_BASE`, which is how CI invokes it.

WHAT WAS TRUE BEFORE 2026-09-09, measured exactly this way and the reason for the 41-day fixture: a plan older than `delete_days` was exempt from BOTH G-A1 and G-A5 by an age amnesty, so deleting one wholesale and losing its only open box exited 0 -- and the success line ASSERTED "21 box(es) open at <base> all survive at HEAD" on a base that held 22. The amnesty existed to avoid a
deadlock with the housekeeping gate, and that gate's remedy is no longer deletion (`check-plan-housekeeping.sh:51`).

AND THE HALF THE CHANGE UNCOVERED. G-A1 never consulted `renames_into_archive`, so a plan `git mv`d untouched into the archive -- the exact remedy G-A1's own message prints -- reddened, unless the age amnesty happened to cover it. `test_an_r100_archive_ is_silent_at_both_ages` is that pair, and it is a PAIR because a control run only at 999 days would have passed over the bug for
as long as the amnesty stood.

THE LIVE TREE IS NEVER MUTATED. Each case builds its own repository under `tmp_path`.
"""

import datetime as dt
import pathlib
import shutil
import subprocess
import sys

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

GATE = paths.from_root(".ci", "scripts", "quality", "check_plan_boxes.py")
HOOKS = paths.from_root(".claude", "hooks", "stop")
LIFECYCLE = paths.from_root(".ci", "config", "plan-lifecycle.json")

# One more than PLAN_BOXES_MIN_PLANS (20). The floor is a real anti-vacuity clause and lowering it through its env override would be testing a different gate.
FILLERS = 21


def _git(repo: pathlib.Path, *args: str, when: str | None = None) -> str:
    env = {}
    if when is not None:
        env = {"GIT_COMMITTER_DATE": when, "GIT_AUTHOR_DATE": when}
    result = harness.run(["git", "-C", str(repo), *args], env=env)
    if result.rc != 0:
        raise harness.GateAssertionError(
            "git %s failed in the fixture (rc=%d): %s" % (" ".join(args), result.rc, result.err)
        )
    return result.out


def _iso_days_ago(days: int) -> str:
    return (dt.datetime.now(dt.UTC) - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _plan(title: str, box: str) -> str:
    return "Owner: nobody\nStatus: executing\n\n# %s\n\n- [ ] %s\n" % (title, box)


def _gate(root: pathlib.Path, base: str | None = None, update: bool = False):
    env = {"PLAN_BOXES_ROOT": str(root)}
    if base is not None:
        env["PLAN_BOXES_BASE"] = base
    argv = [sys.executable, str(GATE)] + (["--update"] if update else [])
    return harness.run(argv, cwd=paths.repo_root(), env=env)


def _seed(tmp_path: pathlib.Path, subject: str, age_days: int) -> tuple[pathlib.Path, str]:
    """A repo with FILLERS live plans plus `subject`, committed `age_days` ago.

    Returns (root, base_sha). The ledger is written by the gate itself rather than by hand: a hand-built ledger is a second implementation of the thing under test.
    """
    root = tmp_path / "tree"
    (root / "agent").mkdir(parents=True)
    (root / ".ci" / "config").mkdir(parents=True)
    (root / ".claude" / "hooks").mkdir(parents=True)
    shutil.copytree(HOOKS, root / ".claude" / "hooks" / "stop")
    shutil.copy(LIFECYCLE, root / ".ci" / "config" / "plan-lifecycle.json")
    for i in range(FILLERS):
        (root / "agent" / ("PLAN-filler%d.md" % i)).write_text(
            _plan("Filler %d" % i, "box number %d of the corpus" % i), encoding="utf-8"
        )
    (root / "agent" / subject).write_text(
        _plan("Subject", "the one box whose survival this case is about"), encoding="utf-8"
    )
    _git(root, "init", "-q", ".")
    _git(root, "config", "user.email", "fixture@example.invalid")
    _git(root, "config", "user.name", "fixture")
    seeded = _gate(root, update=True)
    if seeded.rc != 0:
        raise harness.GateAssertionError(
            "fixture ledger could not be written: %s" % seeded.combined
        )
    _git(root, "add", "-A", "--", ".")
    _git(root, "commit", "-qm", "base", when=_iso_days_ago(age_days))
    return root, _git(root, "rev-parse", "HEAD").strip()


def _regenerate_and_commit(root: pathlib.Path, message: str) -> None:
    written = _gate(root, update=True)
    if written.rc != 0:
        raise harness.GateAssertionError("fixture ledger regen failed: %s" % written.combined)
    _git(root, "add", "-A", "--", ".")
    _git(root, "commit", "-qm", message)


def test_deleting_a_41_day_old_plan_that_loses_a_box_is_refused(gate, tmp_path):
    """THE CASE THAT PASSED. 41 > delete_days (33), one box, surviving nowhere."""
    gate.log_test("a 41-day-old plan deleted wholesale, its one open box surviving nowhere")
    root, base = _seed(tmp_path, "PLAN-old.md", 41)
    _git(root, "rm", "-q", "agent/PLAN-old.md")
    _regenerate_and_commit(root, "delete the aged plan wholesale")

    result = _gate(root, base)
    gate.assert_exit_code(1, result.rc, "age must not license losing a box")
    gate.log_pass(
        "a 41-day-old plan losing its only open box is REFUSED (it passed until 2026-09-09)"
    )

    gate.assert_contains(result.combined, "was DELETED, losing 1 open box", "G-A5 names the loss")
    gate.log_pass("G-A5 fires and counts the boxes lost")
    gate.assert_contains(result.combined, "is GONE at HEAD", "G-A1 fires too")
    gate.log_pass("G-A1 fires as well -- the amnesty covered both rules, so both had to lose it")
    gate.assert_contains(
        result.combined, "--plan-compact --park", "the remedy is compaction, by name"
    )
    gate.log_pass("the message names `worklist.py --plan-compact --park`, not deletion")
    gate.assert_not_contains(
        result.combined,
        "Deletion is for",
        "no message may offer deletion as a remedy any more",
    )
    gate.log_pass("no remedy in the output offers deletion")


def test_the_success_line_never_claims_boxes_it_did_not_compare(gate, tmp_path):
    """The old amnesty did not merely permit the loss, it ASSERTED survival.

    This is the anti-vacuity half and it is a separate case because a rule that fires is not the same claim as a summary that stops lying.
    """
    gate.log_test("the transitions summary over an aged deletion")
    root, base = _seed(tmp_path, "PLAN-old.md", 41)
    _git(root, "rm", "-q", "agent/PLAN-old.md")
    _regenerate_and_commit(root, "delete the aged plan wholesale")

    result = _gate(root, base)
    gate.assert_not_contains(
        result.out,
        "all survive at HEAD",
        "a run that destroyed a box must not print a survival claim",
    )
    gate.log_pass("the survival claim is absent from a run where a box did not survive")


def test_an_r100_archive_is_silent_at_both_ages(gate, tmp_path):
    """The three doors must not red, and AGE MUST NOT DECIDE WHICH DOOR IS OPEN.

    Both ages, deliberately. Until 2026-09-09 the 999-day half was silent and the 1-day half reported "is GONE at HEAD ... not archived" about a plan that had just been archived exactly as that sentence instructs.
    """
    for age in (1, 999):
        gate.log_test("`git mv` untouched into the archive, plan aged %d day(s)" % age)
        root, base = _seed(tmp_path / ("age%d" % age), "PLAN-old.md", age)
        (root / "agent" / "archive" / "plans").mkdir(parents=True)
        _git(root, "mv", "agent/PLAN-old.md", "agent/archive/plans/PLAN-old.md")
        _regenerate_and_commit(root, "archive it untouched")

        rename = _git(
            root,
            "diff",
            "--name-status",
            "--find-renames",
            "-M100%",
            "%s...HEAD" % base,
            "--",
            "agent/",
        )
        gate.assert_contains(rename, "R100\t", "the fixture must really be a byte-identical rename")
        result = _gate(root, base)
        gate.assert_exit_code(0, result.rc, "archiving is a legal home at age %d" % age)
        gate.log_pass("an R100 archive is silent at age %d -- one predicate, no age term" % age)


def test_an_aged_husk_whose_boxes_moved_is_still_free(gate, tmp_path):
    """Never-delete must not become never-tidy: a file whose boxes all live
    elsewhere costs nothing to remove, and firing there would punish the tidying."""
    gate.log_test("an aged plan deleted after its box was moved into a live plan")
    root, base = _seed(tmp_path, "PLAN-old.md", 999)
    moved = (root / "agent" / "PLAN-old.md").read_text(encoding="utf-8")
    (root / "agent" / "PLAN-filler0.md").write_text(
        (root / "agent" / "PLAN-filler0.md").read_text(encoding="utf-8")
        + moved.split("\n\n", 2)[2],
        encoding="utf-8",
    )
    _git(root, "rm", "-q", "agent/PLAN-old.md")
    _regenerate_and_commit(root, "move the box into a live plan, then drop the husk")

    result = _gate(root, base)
    gate.assert_exit_code(0, result.rc, "a husk whose boxes survive elsewhere is free to remove")
    gate.log_pass("an aged husk whose box moved to a live plan is silent")


def test_the_selftest_runs_and_records_the_never_delete_controls(gate):
    """The rule table's own controls, driven as a process on the real tree.

    Named individually rather than counted: a count moves for reasons that have nothing to do with this rule, and a floor that only counts cannot tell which control went missing.
    """
    gate.log_test("check_plan_boxes.py --selftest on the real tree")
    result = harness.run([sys.executable, str(GATE), "--selftest"], cwd=paths.repo_root())
    gate.assert_exit_code(0, result.rc, "the rule table's controls must pass")
    for needle in (
        "G-A5: a 41-day-old plan whose one open box survives NOWHERE is refused",
        "G-A5 PRECONDITION: 41 is past delete_days",
        "G-A5: no message offers deletion as a remedy",
        "G-A1/G-A5 CONTROL: an R100 archive is silent at age 1",
        "G-A1/G-A5 CONTROL: an R100 archive is silent at age 999",
    ):
        gate.assert_contains(result.combined, needle, "the selftest still carries this control")
        gate.log_pass("selftest carries: %s" % needle)
    gate.assert_not_contains(
        result.combined,
        "deleting an AGED plan is permitted",
        "the control asserting the old amnesty must be gone, not merely inverted elsewhere",
    )
    gate.log_pass("the control that asserted the amnesty is gone")


def test_git_is_available_or_this_file_asserts_nothing(gate):
    """A missing tool is a loud failure with the fix in the message, never a skip.

    Every case above builds a real repository; without git they would all error in
    fixture setup, which reads as flake rather than as an unrun test.
    """
    gate.log_test("the fixture's own precondition")
    found = shutil.which("git")
    if found is None:
        gate.log_fail(
            "git is not on PATH, so every case in this file builds nothing and proves "
            "nothing. Install git; there is no stubbed fallback here on purpose, because "
            "the git plumbing IS the half the selftest cannot reach."
        )
    gate.log_pass("git is available at %s, so the fixtures are real repositories" % found)
    probe = subprocess.run([found, "--version"], capture_output=True, text=True, check=False)
    gate.assert_exit_code(0, probe.returncode, "git --version must answer")
    gate.log_pass("git answers: %s" % probe.stdout.strip())
