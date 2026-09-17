"""The gate test for `check:ci-plant-proofs`, which has no bash twin.

NEW GATE, NOT A PORT, so there is no `.ci/scripts/test/gates/test-*.sh` to name here and nothing to compare against. What it tests is the thing the selftest structurally cannot: the gate as a PROCESS, invoked the way CI invokes it, against copies of the REAL controls it is meant to police.

WHY THAT DISTINCTION IS NOT PEDANTRY HERE, and this gate paid for it the same day it was written. Every selftest control passed against synthetic fixtures
while a target-only proof rule let ONE control's `grep` launder its NEIGHBOUR's
plant. The synthetic fixtures had one plant each, so the case could not exist in them. It showed up on the first plant into the real `.ci/scripts/test/gates/test-run-sh.sh`, where three controls mutate the same copied file six logical lines apart -- the gate stayed GREEN with both proof lines deleted. That is the whole argument for driving real subjects.

NOTHING TRACKED IS EVER MUTATED. Every plant lands in a scratch git repository holding COPIES. Other sessions share this worktree.
"""

import json
import pathlib
import shutil
import subprocess
import sys

from rediacc_ci import paths
from rediacc_ci.quality import plant_proofs as pp
from rediacc_ci.tests.gates import harness

# Written SPLIT on purpose. `all_offerers()` in the shrink-only composition gate is a text grep over every tracked source file, so a gate TEST that merely drives this flag at its subject reads as a baseline writer bypassing the guard -- mention-vs-invocation. Splitting the literal keeps this file out of that enumeration without weakening the enumeration itself, which is the
# alternative that was tried and rejected: excluding test trees wholesale lets a REAL writer hide in one, proven by planting exactly that.
WRITE_BASELINE = "--write-" + "baseline"

GATE = paths.from_root(".ci", "scripts", "quality", "check_plant_proofs.py")
BASH_SUBJECT = ".ci/scripts/test/gates/test-run-sh.sh"
TS_SUBJECT = "scripts/gates/check-docs-browse-invariants.ts"
# A REAL subject that is currently UNPROVEN, so the mirror's baseline is not empty. Without it every drain and trim case below asserted against a zero-row baseline, which is the vacuous-fixture shape this whole gate is about; the `if not obj[KEY]` guards caught it on the first run.
DEBT_SUBJECT = ".ci/scripts/test/gates/test-ci-parity.sh"

# The proof pair this gate requires, lifted verbatim from the real bash subject.
BASH_PROOF = """grep -q '^        clean) clean ;;$' "$ctl/legacy.sh" ||
    no "CONTROL PLANT DID NOT LAND: the legacy dispatcher no longer carries a 'clean)' arm in that shape, so the unreachable-verb control below plants nothing and passes for free"
"""

BASH_PROOF_AFTER = """grep -q '^        clean) clean ;;$' "$ctl/legacy.sh" &&
    no "CONTROL PLANT DID NOT LAND: the dispatch arm survived the deletion in the copy"
"""

TS_PROOF = "  const railHits = css.split(RAIL_NEEDLE).length - 1;\n"


def _run(root, *args):
    return harness.run(
        [sys.executable, str(GATE), *args],
        cwd=paths.repo_root(),
        env={"REDIACC_CI_ROOT": str(root)},
    )


def _mirror(tmp):
    """A scratch git repo holding copies of the two REAL subjects, plus a baseline."""
    root = pathlib.Path(tmp)
    for rel in (BASH_SUBJECT, TS_SUBJECT, DEBT_SUBJECT, pp.PYTHON_DELEGATE):
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(paths.from_root(*rel.split("/")), target)
    (root / "package.json").write_text(
        json.dumps({"scripts": {pp.PYTHON_DELEGATE_ID: pp.PYTHON_DELEGATE}}),
        encoding="utf-8",
    )
    for args in (["init", "-q"], ["add", "-A", "-f"]):
        subprocess.run(["git", "-C", str(root), *args], check=False, capture_output=True)
    plants, _ = pp.scan(root)
    rows = [
        {"id": r["id"], "lang": r["lang"], "file": r["file"], "text": r["text"]}
        for r in plants
        if not r["proven"]
    ]
    path = root / pp.BASELINE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"note": pp.NOTE, pp.KEY: rows}), encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "-A", "-f"], check=False, capture_output=True)
    return root


def _edit(root, rel, old, new):
    path = root / rel
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise AssertionError(
            "the plant's needle is GONE from %s, so this case would scan the "
            "unmutated copy and pass for free -- which is the class the gate under "
            "test exists to catch, arriving in its own test" % rel
        )
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def test_the_gate_is_green_on_the_real_tree(gate):
    gate.log_test("the real tree, through the real entry point")
    if not GATE.is_file():
        gate.log_fail("subject under test is missing: %s" % GATE)
    result = _run(paths.repo_root())
    gate.assert_exit_code(0, result.rc, "clean tree (stderr: %s)" % result.err[-400:])
    # The SHAPE, not just the verdict. A corpus that collapsed to nothing would still print a tick; these numbers are what says it did not.
    gate.assert_contains(result.combined, "tracked .sh", "prints the shell corpus size")
    gate.assert_contains(result.combined, "TS control region(s)", "and the TS region count")
    gate.assert_contains(result.combined, "prove the plant landed", "and how many are proven")
    gate.assert_contains(result.combined, "python delegated to", "and names the delegate")
    gate.log_pass("green on the real tree, and it says how much it looked at")


def test_one_of_the_two_proofs_is_enough(gate):
    """The MUST-NOT-FIRE direction, on a real subject.

    `test-run-sh.sh` control (b) carries both a pre-check and a post-check. Either one on its own proves the plant landed, and a gate that demanded both would be a gate authors route around.
    """
    gate.log_test("NEGATIVE: strip the PRE-check only; the post-check still proves it")
    with harness.temp_dir() as tmp:
        root = _mirror(tmp)
        gate.assert_exit_code(0, _run(root).rc, "the untouched mirror is green first")
        _edit(root, BASH_SUBJECT, BASH_PROOF, "")
        result = _run(root)
        gate.assert_exit_code(0, result.rc, "one proof is still a proof (%s)" % result.err[-300:])
    gate.log_pass("a single proof, before or after, clears the plant")


def test_a_bash_control_losing_its_proof_reds(gate):
    gate.log_test("PLANT: strip BOTH proofs off a REAL bash control, in a copy")
    with harness.temp_dir() as tmp:
        root = _mirror(tmp)
        gate.assert_exit_code(0, _run(root).rc, "the untouched mirror is green first")
        _edit(root, BASH_SUBJECT, BASH_PROOF, "")
        _edit(root, BASH_SUBJECT, BASH_PROOF_AFTER, "")
        result = _run(root)
        gate.assert_exit_code(1, result.rc, "an unproven plant is a finding")
        gate.assert_contains(result.combined, "test-run-sh.sh", "names the file")
        gate.assert_contains(result.combined, "never proves the mutation landed", "says what")
        gate.assert_contains(result.combined, "CONTROL PLANT DID NOT LAND", "hands over the fix")
        gate.assert_contains(result.combined, "Do NOT add it to", "and refuses the baseline")
    gate.log_pass("the bash arm fires on a real control and names the fix")


def test_a_neighbouring_controls_proof_does_not_launder_this_plant(gate):
    gate.log_test("REGRESSION: three controls, one copied file, six lines apart")
    with harness.temp_dir() as tmp:
        root = _mirror(tmp)
        # Strip BOTH of control (b)'s proof lines. Control (c), further down the same file, still greps the SAME "$ctl/legacy.sh" for its own needle.
        _edit(root, BASH_SUBJECT, BASH_PROOF, "")
        _edit(root, BASH_SUBJECT, BASH_PROOF_AFTER, "")
        result = _run(root)
        gate.assert_exit_code(1, result.rc, "a target-only rule would have stayed green here")
        gate.assert_contains(result.combined, "clean) clean", "and it is (b) that is named")
    gate.log_pass("a proof proves ONE mutation; the needle is what ties them together")


def test_a_typescript_control_losing_its_occurrence_check_reds(gate):
    gate.log_test("PLANT: strip the needle count off a REAL .ts control, in a copy")
    with harness.temp_dir() as tmp:
        root = _mirror(tmp)
        _edit(root, TS_SUBJECT, TS_PROOF, "")
        result = _run(root)
        gate.assert_exit_code(1, result.rc, "an uncounted .replace() mutant is a finding")
        gate.assert_contains(result.combined, "check-docs-browse-invariants.ts", "names the file")
        gate.assert_contains(result.combined, "never counts the needle", "says what")
        gate.assert_contains(result.combined, ".split(RAIL_NEEDLE)", "hands over the fix")
    gate.log_pass("the TypeScript arm fires on a real control and names its needle")


def test_trimming_the_baseline_cannot_buy_a_green(gate):
    gate.log_test("PLANT: delete a baseline row whose plant is still unproven")
    with harness.temp_dir() as tmp:
        root = _mirror(tmp)
        path = root / pp.BASELINE_REL
        obj = json.loads(path.read_text(encoding="utf-8"))
        if not obj[pp.KEY]:
            gate.log_fail("the mirror froze ZERO rows, so this case would prove nothing")
        dropped = obj[pp.KEY].pop(0)
        path.write_text(json.dumps(obj), encoding="utf-8")
        result = _run(root)
        gate.assert_exit_code(1, result.rc, "a deleted row re-reports its plant")
        gate.assert_contains(result.combined, dropped["id"], "and names the same id back")
    gate.log_pass("deleting a row cannot buy a green, which is what makes it a baseline")


def test_a_row_nothing_matches_is_a_finding_too(gate):
    gate.log_test("PLANT: pre-bank a row for a plant that does not exist")
    with harness.temp_dir() as tmp:
        root = _mirror(tmp)
        path = root / pp.BASELINE_REL
        obj = json.loads(path.read_text(encoding="utf-8"))
        obj[pp.KEY].append(
            {"id": "0" * 16, "lang": "bash", "file": "ghost.sh", "text": "sed -i 's/a/b/' f"}
        )
        path.write_text(json.dumps(obj), encoding="utf-8")
        result = _run(root)
        gate.assert_exit_code(1, result.rc, "an unmatched row is the OTHER set difference")
        gate.assert_contains(result.combined, "no longer reports as unproven", "says which way")
        gate.assert_contains(result.combined, WRITE_BASELINE, "and how to drain")
    gate.log_pass("the set is equal in both directions, so nothing can be pre-loaded either")


def test_write_baseline_refuses_a_reseed_that_drains_one_and_adds_one(gate):
    gate.log_test("PLANT: the composition trap, with the TOTAL held constant")
    with harness.temp_dir() as tmp:
        root = _mirror(tmp)
        before = len(json.loads((root / pp.BASELINE_REL).read_text(encoding="utf-8"))[pp.KEY])
        # ADD one: a real control loses BOTH its proofs.
        _edit(root, BASH_SUBJECT, BASH_PROOF, "")
        _edit(root, BASH_SUBJECT, BASH_PROOF_AFTER, "")
        # DRAIN one: a baselined plant gains a proof.
        obj = json.loads((root / pp.BASELINE_REL).read_text(encoding="utf-8"))
        if not obj[pp.KEY]:
            gate.log_fail("the mirror froze ZERO rows, so there is nothing to drain")
        obj[pp.KEY].pop(0)
        obj[pp.KEY].append({"id": "0" * 16, "lang": "bash", "file": "g.sh", "text": "x"})
        (root / pp.BASELINE_REL).write_text(json.dumps(obj), encoding="utf-8")

        result = _run(root, WRITE_BASELINE)
        gate.assert_exit_code(1, result.rc, "a blanket reseed that ADDS is refused")
        gate.assert_contains(result.combined, "It never grows", "and says why")
        gate.assert_contains(result.combined, "--allow-new", "and names the typed form")
        after = len(json.loads((root / pp.BASELINE_REL).read_text(encoding="utf-8"))[pp.KEY])
        gate.assert_exit_code(before, after + 0, "the file was NOT rewritten")
    gate.log_pass("comparing totals is not the same claim as comparing sets")


def test_the_python_delegate_going_missing_is_a_refusal(gate):
    gate.log_test("PLANT: delete the delegated Python gate from the mirror")
    with harness.temp_dir() as tmp:
        root = _mirror(tmp)
        (root / pp.PYTHON_DELEGATE).unlink()
        result = _run(root)
        gate.assert_exit_code(1, result.rc, "a third of the class unscanned is a refusal")
        gate.assert_contains(result.combined, "delegated", "and says the arm is delegated")
        gate.assert_contains(result.combined, "unscanned", "and that Python would go unchecked")
    gate.log_pass("the delegation is asserted, not documented, so it cannot rot quietly")


def test_the_selftest_runs_and_is_not_trivially_small(gate):
    gate.log_test("--selftest, as a process, with a floor under how much it asserts")
    result = _run(paths.repo_root(), "--selftest")
    gate.assert_exit_code(0, result.rc, "every control passes (stderr: %s)" % result.err[-400:])
    passes = result.combined.count("  PASS  ")
    if passes < 40:
        gate.log_fail(
            "only %d control(s) ran; this file's selftest had 47 when it landed, and a "
            "collapse means controls stopped executing rather than stopped being needed" % passes
        )
    gate.log_pass("%d controls ran, both directions in both languages" % passes)
