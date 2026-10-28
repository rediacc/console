"""`check:ci-plan-live-proof`, driven as a process against planted git trees.

WHAT THIS ADDS TO THE GATE'S OWN `--selftest`. The selftest plants into fixture TEXT and calls the rule functions with injected oracles; it proves the detectors. This file proves the path from disk and git to exit code: the plan walk, the plan-add dates that decide the V7 PENDING set, `plan-boxes.json` at the merge-base against the working tree, the author date of the ticking commit against `baseline_at` (a rebase keeps it), `--root`, `--base`, `--proof-map` and the exit codes 0, 1 and 77.

THE FIXTURE IS A REAL GIT REPOSITORY, because the forward-only cut is a fact about commits: a plan committed with no `baseline_at` set is in the migration set, a box ticked in a commit after it is bound. Commit dates are pinned through GIT_AUTHOR_DATE and GIT_COMMITTER_DATE, and every git call runs under `controls.fixture_git_env` so an exported GIT_INDEX_FILE cannot point the fixture at the caller's repository.
"""

import json
import pathlib
import subprocess
import sys

import wl_plandeps as D

from rediacc_ci import controls, paths
from rediacc_ci.tests.gates import harness

GATE = paths.from_root(".ci", "scripts", "quality", "check_plan_live_proof.py")
MAP = paths.from_root(".ci", "config", "proof-tiers.json")
BASELINE = "2026-10-28"
BEFORE = "2026-10-01T12:00:00+00:00"
ON_DAY = "2026-10-28T12:00:00+00:00"
AFTER = "2026-11-02T12:00:00+00:00"

_HEAD = (
    "# PLAN: %s\n\nStatus: in-progress\nOwner: cafe0000\n"
    "Depends-On: no-dep -- a fixture plan that stands alone\nPriority: P2\n"
    "Concurrency: parallel\nOwns: %s\n%s\n## Tasks\n\n- [ ] T1 the code\n%s"
)
LINE = "Live-Proof: bench -- the account surface runs on bench"
LP_BOX = "- [ ] LP-bench [live] the bench smoke\n  - Accept: `live-proof bench account-smoke`\n"


def _plan(
    name: str, owns: str = "private/account/src/x.ts", line: str | None = LINE, box: str = LP_BOX
) -> str:
    return _HEAD % (name, owns, line or "", box)


def _git(root: pathlib.Path, *args: str, when: str = BEFORE, committed: str | None = None) -> str:
    """Run git in the fixture. `when` is the author date and, unless `committed` overrides it (a rebased commit), the committer date too."""
    env = controls.fixture_git_env()
    env.update(
        GIT_AUTHOR_DATE=when,
        GIT_COMMITTER_DATE=committed or when,
        GIT_AUTHOR_NAME="fixture",
        GIT_AUTHOR_EMAIL="fixture@example.invalid",
        GIT_COMMITTER_NAME="fixture",
        GIT_COMMITTER_EMAIL="fixture@example.invalid",
    )
    proc = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True, env=env
    )
    return proc.stdout


def _boxes(root: pathlib.Path) -> None:
    """Regenerate the fixture's plan-boxes.json from its plan files, through the same box parser the gate reads."""
    plans = {}
    for path in sorted((root / "agent" / "plans").glob("PLAN-*.md")):
        text = path.read_text(encoding="utf-8")
        boxes = D.plan_boxes(text)
        plans["agent/plans/%s" % path.name] = {
            "status": D.parse_header(text).status,
            "folder": "agent/plans",
            "open_sigs": sorted(b.sig for b in boxes if not b.done),
            "done_sigs": sorted(b.sig for b in boxes if b.done),
        }
    out = root / ".ci" / "config" / "plan-boxes.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"plans": plans}, indent=1), encoding="utf-8")


def _write(root: pathlib.Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _commit(root: pathlib.Path, message: str, when: str) -> None:
    _boxes(root)
    _git(root, "add", "-A", when=when)
    _git(root, "commit", "-q", "-m", message, when=when)


def _seed(tmp_path: pathlib.Path) -> pathlib.Path:
    """`main` at one commit dated before the baseline: a required plan carrying its line and its LP box, and a docs-only plan. A `work` branch is checked out on top."""
    root = tmp_path / "tree"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _write(root, "agent/plans/PLAN-acct.md", _plan("acct"))
    _write(
        root, "agent/plans/PLAN-docs.md", _plan("docs", owns="docs/fixture/**", line=None, box="")
    )
    _commit(root, "seed", BEFORE)
    _git(root, "checkout", "-q", "-b", "work")
    return root


def _map(tmp_path: pathlib.Path, baseline: str | None = BASELINE) -> pathlib.Path:
    """The committed map with a baseline and a bench www check, so LP7 is silent unless a test plants it."""
    raw = json.loads(MAP.read_text(encoding="utf-8"))
    raw["tiers"]["live"]["baseline_at"] = baseline
    raw["tiers"]["live"]["checks"]["www-smoke"] = {
        "targets": ["bench"],
        "surfaces": ["www"],
        "deploy": "unrecorded",
        "what": "fixture",
        "steps": [{"id": "root", "argv": ["curl", "-fsS", "{origin}/"]}],
    }
    out = tmp_path / ("map-%s.json" % (baseline or "unset"))
    out.write_text(json.dumps(raw), encoding="utf-8")
    return out


def _gate(root: pathlib.Path, map_path: pathlib.Path, *argv: str) -> harness.RunResult:
    return harness.run(
        [
            sys.executable,
            str(GATE),
            "--root",
            str(root),
            "--base",
            "main",
            "--proof-map",
            str(map_path),
            *argv,
        ],
        cwd=paths.repo_root(),
    )


def _gate_on_base(root: pathlib.Path, map_path: pathlib.Path, base: str) -> harness.RunResult:
    return harness.run(
        [
            sys.executable,
            str(GATE),
            "--root",
            str(root),
            "--base",
            base,
            "--proof-map",
            str(map_path),
        ],
        cwd=paths.repo_root(),
    )


def _tick_lp(root: pathlib.Path) -> None:
    path = root / "agent" / "plans" / "PLAN-acct.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("- [ ] LP-bench", "- [x] LP-bench"),
        encoding="utf-8",
    )


# --------------------------------------------------------------------------- the subject and its controls


def test_the_subject_exists(gate):
    if not GATE.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(GATE))
    gate.log_pass("subject under test is present")


def test_selftest_alone_is_green(gate):
    result = harness.run([sys.executable, str(GATE), "--selftest"], cwd=paths.repo_root())
    gate.assert_exit(0, result, "the planted controls must pass")
    gate.assert_contains(result.out, "control(s) passed", "the tally is printed")
    gate.log_pass("--selftest is green")


def test_the_real_tree_gets_a_verdict_not_a_crash(gate):
    """0 or 1, never 2 or 77: the live tree's verdict moves with V7's migration, so this pins that a verdict is reached after the controls, not which one."""
    result = harness.run([sys.executable, str(GATE)], cwd=paths.repo_root())
    gate.assert_eq(result.rc in (0, 1), True, "the real tree is judged: %r" % result)
    gate.assert_contains(result.out, "controls first, then the verdict", "controls run first")
    gate.assert_contains(result.out, "required by the surface map", "the corpus shape is printed")
    gate.log_pass("the real tree reaches a verdict after the controls")


# --------------------------------------------------------------------------- planted trees


def test_the_clean_tree_is_green(gate, tmp_path):
    result = _gate(_seed(tmp_path), _map(tmp_path))
    gate.assert_exit(0, result, "a required plan with its line and LP box, nothing ticked")
    gate.assert_contains(
        result.out, "1 required by the surface map", "the account plan is required"
    )
    gate.assert_contains(result.out, "ok plan live proof", "the green line")
    gate.log_pass("the clean fixture is green")


def test_a_plan_committed_after_the_baseline_without_the_line_is_lp1(gate, tmp_path):
    root = _seed(tmp_path)
    _write(root, "agent/plans/PLAN-late.md", _plan("late", line=None, box=""))
    _commit(root, "late plan", AFTER)
    result = _gate(root, _map(tmp_path))
    gate.assert_exit(1, result, "a new required plan with no Live-Proof line")
    gate.assert_contains(result.err, "LP1 agent/plans/PLAN-late.md", "LP1 names the plan")
    gate.log_pass("LP1 fires on a post-baseline plan")


def test_an_uncommitted_plan_without_the_line_is_lp1(gate, tmp_path):
    root = _seed(tmp_path)
    _write(root, "agent/plans/PLAN-draft.md", _plan("draft", line=None, box=""))
    result = _gate(root, _map(tmp_path))
    gate.assert_exit(1, result, "a plan git has never seen is new, never pending")
    gate.assert_contains(result.err, "LP1 agent/plans/PLAN-draft.md", "LP1 names the plan")
    gate.log_pass("LP1 fires on an uncommitted plan")


def test_a_plan_committed_before_the_baseline_without_the_line_is_lp1(gate, tmp_path):
    root = _seed(tmp_path)
    _write(root, "agent/plans/PLAN-old.md", _plan("old", line=None, box=""))
    _commit(root, "old plan", BEFORE)
    result = _gate(root, _map(tmp_path))
    gate.assert_exit(1, result, "once baseline_at is set the V7 migration window is closed")
    gate.assert_contains(result.err, "LP1 agent/plans/PLAN-old.md", "LP1 names the plan")
    gate.log_pass("a pre-baseline plan without the line is LP1 once the baseline lands")


def test_with_no_baseline_a_committed_plan_without_the_line_is_pending(gate, tmp_path):
    root = _seed(tmp_path)
    _write(root, "agent/plans/PLAN-old.md", _plan("old", line=None, box=""))
    _commit(root, "old plan", BEFORE)
    result = _gate(root, _map(tmp_path, baseline=None))
    gate.assert_exit(1, result, "the unset baseline itself is LP7")
    gate.assert_contains(result.out, "PENDING (V7) agent/plans/PLAN-old.md", "the plan is pending")
    gate.assert_eq(
        "LP1 agent/plans/PLAN-old.md" in result.err, False, "and not LP1 while V7 is open"
    )
    gate.log_pass("with no baseline a committed plan without the line is PENDING, not LP1")


def test_an_lp_box_ticked_after_the_baseline_without_a_receipt_is_lp4(gate, tmp_path):
    root = _seed(tmp_path)
    _tick_lp(root)
    _commit(root, "tick the LP box", AFTER)
    result = _gate(root, _map(tmp_path))
    gate.assert_exit(1, result, "a tick with no receipt row")
    gate.assert_contains(result.err, "LP4 agent/plans/PLAN-acct.md", "LP4 names the plan")
    gate.assert_contains(result.out, "1 bound after %s" % BASELINE, "the transition is counted")
    gate.log_pass("LP4 fires on a bound tick")


def test_an_lp_box_ticked_on_the_baseline_day_is_exempt(gate, tmp_path):
    root = _seed(tmp_path)
    _tick_lp(root)
    _commit(root, "tick the LP box", ON_DAY)
    result = _gate(root, _map(tmp_path))
    gate.assert_exit(0, result, "the landing day is amnesty, the device P-A2 uses")
    gate.assert_contains(result.out, "1 LP box(es) among them, 0 bound", "seen and exempt")
    gate.log_pass("a tick on the baseline day is exempt")


def test_a_rebased_tick_keeps_its_author_date(gate, tmp_path):
    """A rebase rewrites the committer date to the rebase instant and keeps the author date; the forward-only cut reads the author date, so a tick made on the landing day stays exempt after the branch is rebased past it."""
    root = _seed(tmp_path)
    _tick_lp(root)
    _boxes(root)
    _git(root, "add", "-A", when=ON_DAY)
    _git(root, "commit", "-q", "-m", "tick the LP box", when=ON_DAY, committed=AFTER)
    result = _gate(root, _map(tmp_path))
    gate.assert_exit(0, result, "authored on the baseline day, committed after it by a rebase")
    gate.assert_contains(result.out, "1 LP box(es) among them, 0 bound", "seen and exempt")
    gate.log_pass("a rebased tick is judged by its author date")


def test_no_merge_base_is_lp7_not_a_skip(gate, tmp_path):
    """LP4 to LP6 judge transitions against a merge-base. When none can be computed they judge nothing, so the run must be red: a green here would mean every tick on the branch went unchecked."""
    result = _gate_on_base(_seed(tmp_path), _map(tmp_path), "no-such-ref")
    gate.assert_exit(1, result, "no merge-base means LP4 to LP6 did not run")
    gate.assert_contains(result.err, "LP7", "the finding is LP7, vacuity")
    gate.assert_contains(result.err, "no merge-base", "and names why")
    gate.log_pass("a missing merge-base is LP7, never a silent skip")


def test_an_unset_baseline_is_lp7(gate, tmp_path):
    result = _gate(_seed(tmp_path), _map(tmp_path, baseline=None))
    gate.assert_exit(1, result, "no forward-only cut is a vacuous gate")
    gate.assert_contains(result.err, "baseline_at", "LP7 names the field")
    gate.log_pass("LP7 fires on an unset baseline_at")


def test_zero_live_plans_cannot_run(gate, tmp_path):
    root = tmp_path / "empty"
    (root / "agent" / "plans").mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    result = _gate(root, _map(tmp_path))
    gate.assert_exit(77, result, "zero parsed plans is CANNOT RUN, never green")
    gate.assert_contains(result.err, "CANNOT RUN", "and says so")
    gate.log_pass("an empty corpus cannot run")
