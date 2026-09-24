"""Port of `.ci/scripts/test/gates/test-layout-overflow.sh`, retired in W7 P5.

`scripts/gates/check-layout-overflow.ts`, the CSS horizontal-overflow scan.

WHAT THIS MAY AND MAY NOT ASSERT, carried over unchanged because it is the whole shape of the file. The gate is RED on the real tree today, deliberately: four CSS rules make the site scroll sideways and the fix belongs to a later wave. So the VERDICT is not pinned -- an `exit 1` assertion would go red the day the bug is fixed, which is exactly backwards. What is pinned instead is
everything that makes the verdict MEAN something:

  1. the gate can FAIL -- its inline controls plant both cause shapes and require
     detection, including the pseudo-element one that no browser-driven scan can
     see, because `querySelectorAll` returns no pseudo-elements;
  2. the gate really SCANNED -- the run reports a declaration-block count rather
     than reporting on an empty glob;
  3. the gate REFUSES an empty tree instead of printing a checkmark over nothing.

Together those three separate "this gate is red" from "this gate is noise", and they hold whether the tree is red or green.

THE MUTANT'S HOME IS NOT AN ACCIDENT, and the twin records three earlier shapes that were wrong, the first two in opposite directions. A bare copy into a temp directory died on `Cannot find module ./lib/shrink-only-baseline.ts` once the gate gained that import: the run ended before a single control executed, and the assertion below then reported "the mutant must name the failing
control" while the gate had never started. Writing the mutant BESIDE the gate fixed the imports and made the test a real-tree writer, which the pool-writer-safety gate correctly flagged. Copying `scripts/lib/` in beside the mutant satisfied the imports THEN, and touched nothing tracked, which is what both the bash twin and this port do. The gate's own import later moved to
`../lib/shrink-only- baseline.js` (one level up, `.js` extension, `check-layout-overflow.ts` living under `scripts/gates/`), so "beside the mutant" stopped resolving; the mutant now lives at `tmp_path/gates/mutant.ts` with `lib/` copied to `tmp_path/lib`, mirroring the real tree's own relative depth rather than the gate's absolute directory name.

NO `xdist_group`. Every case runs `tsx` in a subprocess and writes only into pytest's own `tmp_path`; nothing is bound and no module global is mutated. The real-tree cases only READ.
"""

import shutil

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

GATE = paths.from_root("scripts", "gates", "check-layout-overflow.ts")
LIB = paths.from_root("scripts", "lib")

# The one expression the mutant removes. Written out rather than matched loosely, so a rewording of the detector makes the mutation FAIL TO APPLY (and say so) instead of silently producing a copy identical to the gate.
DETECTOR = "d.get('white-space') === 'nowrap' &&"


def run_gate(gate, script, *args: str) -> harness.RunResult:
    """Drive a TypeScript program through the workspace `npx tsx`, from the repo root.

    Streams MERGED: the twin captures `2>&1` into one variable and asserts on the merged text, and the gate writes its findings to stderr and its verdict to stdout. Comparing against a split stream here would be a different claim from the one the twin makes.
    """
    if not GATE.is_file():
        gate.log_fail("gate not found: %s" % paths.relative_to_root(GATE))
    npx = harness.require_tool(
        "npx", "install node; the subject is a TypeScript program driven through tsx"
    )
    return harness.run([npx, "tsx", str(script), *args], cwd=paths.repo_root())


def test_selftest_passes_and_plants_both_shapes(gate):
    gate.log_test("the gate's own controls plant both cause shapes on every invocation")
    result = run_gate(gate, GATE, "--selftest")
    gate.assert_exit(0, result, "the gate's own controls must pass")
    gate.assert_contains(
        result.combined,
        "PLANT: `left: -9999px` offscreen hiding is reported",
        "the RTL offscreen plant must be exercised",
    )
    gate.assert_contains(
        result.combined,
        "PLANT: an invisible nowrap PSEUDO-ELEMENT is reported",
        "the pseudo-element plant must be exercised -- this is the shape querySelectorAll "
        "cannot see",
    )
    gate.log_pass("both cause shapes are planted and detected")


def test_the_control_can_actually_fail(gate, tmp_path):
    """MUTATE THE GATE, not the tree.

    Without this, the PASS lines above prove only that a string was printed. Stripping the nowrap detector must make the gate declare its OWN controls broken.
    """
    gate.log_test("CONTROL: a gate that stopped detecting the nowrap shape must fail itself")
    shutil.copytree(LIB, tmp_path / "lib")
    source = GATE.read_text(encoding="utf-8")
    mutated = source.replace(DETECTOR, "false &&")
    if mutated == source:
        gate.log_fail(
            "the mutation did not apply (%r is no longer in the gate), so this control "
            "would be testing the unmutated gate" % DETECTOR
        )
    mutant = tmp_path / "gates" / "mutant.ts"
    mutant.parent.mkdir(parents=True, exist_ok=True)
    mutant.write_text(mutated, encoding="utf-8")
    result = run_gate(gate, mutant, "--selftest")
    gate.assert_exit(
        1, result, "a gate that stopped detecting the nowrap shape must FAIL its own controls"
    )
    gate.assert_contains(result.combined, "FAIL", "the mutant must name the failing control")
    gate.log_pass(
        "removing the detector flips the gate's controls red (the controls are load-bearing)"
    )


def test_real_tree_scan_is_not_vacuous(gate):
    """Seam-free: the real invocation over the real stylesheets.

    The VERDICT is deliberately not asserted (the tree is red by design until the overflow fix lands); what is asserted is that a real scan HAPPENED, in both the green and the red arm, because "no findings" and "found nothing because the scan is blind" are the same exit code.
    """
    gate.log_test("the real scan must report its coverage, whichever verdict it reaches")
    result = run_gate(gate, GATE)
    gate.assert_not_contains(
        result.combined,
        "Refusing to run",
        "the real tree must give the gate enough input to judge",
    )
    if result.rc == 0:
        gate.assert_contains(
            result.combined,
            "declaration block(s)",
            "a green verdict must state how many blocks it read",
        )
    else:
        gate.assert_contains(
            result.combined,
            "declaration block(s)",
            "a red verdict must state how many blocks it read",
        )
        gate.assert_contains(
            result.combined, "packages/www", "a finding must name the file it is in"
        )
    gate.log_pass(
        "the real scan ran over the real stylesheets and reported its coverage (exit %d)"
        % result.rc
    )


def test_empty_tree_is_refused(gate, tmp_path):
    gate.log_test("ANTI-VACUITY: a tree with no stylesheets is refused, not reported clean")
    (tmp_path / "packages" / "www" / "src" / "styles").mkdir(parents=True)
    result = run_gate(gate, GATE, "--root", str(tmp_path))
    gate.assert_exit(1, result, "a tree with no stylesheets must be REFUSED, never passed")
    gate.assert_contains(result.combined, "Refusing to run", "the refusal must say so")
    gate.log_pass("an empty style tree is refused rather than reported clean")
