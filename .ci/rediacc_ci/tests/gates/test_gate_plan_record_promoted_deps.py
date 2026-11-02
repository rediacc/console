"""RQ-DEPS, its `--update` repair and RP: the end-to-end half `check_plan_record.py --selftest` cannot do.

NEW TEST, NOT A PORT, so there is no `.ci/scripts/test/gates/test-*.sh` named here.

The selftest drives `promoted_dep_problems`, `promoted_dep_order` and `rp_verdict` as functions. This file drives the gate as a PROCESS over a scratch git repository through `PLAN_RECORD_ROOT`, the way an agent runs it after every tick (`--rendered-only --update`), so the wiring is what is under test: that the repair runs before the queue render, that the check judges the repaired file, that a second run writes nothing, and that `--write-baseline` cannot grow the RP baseline.

THE LIVE TREE IS NEVER MUTATED. Each case builds its own repository under `tmp_path`.
"""

import json
import pathlib
import shutil
import sys

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

GATE = paths.from_root(".ci", "scripts", "quality", "check_plan_record.py")
HOOKS = paths.from_root(".claude", "hooks", "stop")
CONFIG = paths.from_root(".claude", "config")
# The Promoted progress block counts boxes through `rediacc_hooks.plan_gate`, reached by `.claude/rediacc_hooks/syspath.py`.
REDIACC_HOOKS = paths.from_root(".claude", "rediacc_hooks")
QUEUE_REL = "agent/plans/QUEUE.md"
BASELINE_REL = ".ci/config/plan-priority-seed-baseline.json"
# One more than PLAN_RECORD_MIN_PLANS (20): the floor is a real anti-vacuity clause, and lowering it through its env override would test a different gate.
FILLERS = 21


def _plan(deps: str = "no-dep -- the fixture stands alone on purpose", priority: str = "") -> str:
    return (
        "# PLAN: fixture\nStatus: approved\nDepends-On: %s\nPriority: %s\nOwner: abcd1234\n\n"
        "## Tasks\n\n- [ ] T1 build the fixture thing -- acceptance: `true` exits 0\n"
        % (deps, priority or "P2 -- a fixture priority reason")
    )


def _queue(*rels: str) -> str:
    entries = "".join("%d. %s -- operator note %d\n" % (i, r, i) for i, r in enumerate(rels, 1))
    return (
        "# Queue\n\n## Promoted\n\n" + entries + "\n## Generated\n\n"
        "<!-- queue:generated:begin -->\n<!-- queue:generated:end -->\n"
    )


def _git(root: pathlib.Path, *args: str) -> None:
    result = harness.run(["git", "-C", str(root), *args])
    if result.rc != 0:
        raise harness.GateAssertionError(
            "git %s failed in the fixture (rc=%d): %s" % (" ".join(args), result.rc, result.err)
        )


def _gate(root: pathlib.Path, *argv: str):
    env = {"PLAN_RECORD_ROOT": str(root), "PLAN_FOLDERS_MAIN": "HEAD"}
    return harness.run([sys.executable, str(GATE), *argv], cwd=paths.repo_root(), env=env)


def _seed(tmp_path: pathlib.Path, plans: dict[str, str], promoted: list[str], baseline=None):
    """A committed repository holding FILLERS plans, `plans`, a queue promoting `promoted`, and an RP baseline."""
    root = tmp_path / "tree"
    (root / "agent" / "plans").mkdir(parents=True)
    (root / ".ci" / "config").mkdir(parents=True)
    (root / ".claude").mkdir(parents=True)
    shutil.copytree(HOOKS, root / ".claude" / "hooks" / "stop")
    shutil.copytree(CONFIG, root / ".claude" / "config")
    shutil.copytree(
        REDIACC_HOOKS,
        root / ".claude" / "rediacc_hooks",
        ignore=shutil.ignore_patterns("tests", "__pycache__"),
    )
    for i in range(FILLERS):
        (root / "agent" / "plans" / ("PLAN-filler%d.md" % i)).write_text(_plan(), encoding="utf-8")
    for rel, text in plans.items():
        (root / rel).write_text(text, encoding="utf-8")
    (root / QUEUE_REL).write_text(_queue(*promoted), encoding="utf-8")
    (root / BASELINE_REL).write_text(
        json.dumps({"findings": baseline or {}}, indent=2) + "\n", encoding="utf-8"
    )
    _git(root, "init", "-q", ".")
    _git(root, "config", "user.email", "fixture@example.invalid")
    _git(root, "config", "user.name", "fixture")
    _git(root, "add", "-A", "--", ".")
    _git(root, "commit", "-qm", "base")
    return root


def _promoted(root: pathlib.Path) -> list[str]:
    text = (root / QUEUE_REL).read_text(encoding="utf-8")
    body = text.split("## Promoted", 1)[1].split("\n## ", 1)[0]
    return [ln.split(" ", 2)[1] for ln in body.splitlines() if ln[:1].isdigit()]


A, B, C = ("agent/plans/PLAN-%s.md" % n for n in ("a", "b", "c"))


def test_update_inserts_the_transitive_closure_once(gate, tmp_path):
    gate.log_test(
        "--rendered-only --update pulls a promoted plan's prerequisites in, deepest first"
    )
    root = _seed(tmp_path, {A: _plan("PLAN-b.md"), B: _plan("PLAN-c.md"), C: _plan()}, [A])

    refused = _gate(root, "--rendered-only")
    gate.assert_exit(1, refused, "the check refuses the unordered queue before any repair")
    gate.assert_contains(
        refused.combined,
        "PLAN-a.md needs PLAN-b.md needs PLAN-c.md",
        "the finding names the whole chain",
    )
    gate.log_pass("the check refuses, naming the chain A needs B needs C")

    first = _gate(root, "--rendered-only", "--update")
    gate.assert_exit(0, first, "the repaired queue passes in the same run")
    gate.assert_contains(
        first.out, "inserted PLAN-c.md into Promoted ahead of PLAN-b.md", "C first"
    )
    gate.assert_contains(first.out, "inserted PLAN-b.md into Promoted ahead of PLAN-a.md", "then B")
    if _promoted(root) != [C, B, A]:
        raise harness.GateAssertionError("Promoted order is %s, wanted C, B, A" % _promoted(root))
    gate.log_pass("both prerequisites inserted, deepest first, one line each, and the run is green")

    written = (root / QUEUE_REL).read_bytes()
    second = _gate(root, "--rendered-only", "--update")
    gate.assert_exit(0, second, "a second repair is a no-op")
    gate.assert_not_contains(second.out, "inserted", "nothing is inserted twice")
    if (root / QUEUE_REL).read_bytes() != written:
        raise harness.GateAssertionError("the second --update rewrote QUEUE.md")
    gate.log_pass("a second --update changes no byte")


def test_a_prerequisite_behind_its_dependant_is_moved(gate, tmp_path):
    gate.log_test("a promoted prerequisite listed after what needs it is moved ahead, note kept")
    root = _seed(tmp_path, {A: _plan("PLAN-b.md"), B: _plan()}, [A, B])

    refused = _gate(root, "--rendered-only")
    gate.assert_exit(1, refused, "a misordered prerequisite is refused")
    gate.assert_contains(
        refused.combined, "is Promoted entry 2, behind it", "the misorder is named"
    )
    gate.log_pass("the check names the misorder")

    fixed = _gate(root, "--rendered-only", "--update")
    gate.assert_exit(0, fixed, "the moved queue passes")
    gate.assert_contains(fixed.out, "moved Promoted entry PLAN-b.md ahead of PLAN-a.md", "said")
    text = (root / QUEUE_REL).read_text(encoding="utf-8")
    gate.assert_contains(text, "1. agent/plans/PLAN-b.md -- operator note 2", "note travels")
    gate.log_pass("B moved ahead of A with its operator note, renumbered")


def test_rp_baseline_cannot_grow(gate, tmp_path):
    gate.log_test("a stale Priority seed claim fails and --write-baseline will not freeze it")
    stale = _plan(priority="P3 -- seed: Status proposed, 0 open box(es)")
    root = _seed(tmp_path, {A: stale}, [])
    _gate(root, "--rendered-only", "--update")

    refused = _gate(root, "--rendered-only")
    gate.assert_exit(1, refused, "a new seed-claim finding fails")
    gate.assert_contains(refused.combined, "Do not add it to", "the message refuses baselining")
    gate.log_pass("RP refuses a stale seed claim and says not to baseline it")

    writer = _gate(root, "--write-baseline")
    gate.assert_exit(1, writer, "the writer refuses to absorb a new finding")
    doc = json.loads((root / BASELINE_REL).read_text(encoding="utf-8"))
    if doc["findings"]:
        raise harness.GateAssertionError("--write-baseline added %s" % doc["findings"])
    gate.log_pass("--write-baseline exits 1 and the baseline stays empty")
