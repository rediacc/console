"""Port of `.ci/scripts/test/gates/test-hydration-clean.sh`, retired in W7 P5.

Tests for `scripts/gates/check-hydration-clean.ts`.

The gate is RED on the real tree today: four React islands compute a different initial state on the server than in the browser, so React discards their server-rendered trees. The fix belongs to a later wave, so this test does NOT pin the verdict -- pinning `exit 1` would turn the gate red the day the bug is fixed. It pins the three properties that make the verdict worth reading:

  1. the gate can FAIL -- its inline controls plant the InstallMethods shape AND
     the indirect ThemeToggle shape, and require both to be reported;
  2. its controls are load-bearing -- mutating the detector out flips them red;
  3. the real scan really ran, over a component count above its floor, and refuses
     an empty tree rather than reporting it clean.

THE MUTANT IS BUILT IN A TEMPDIR AND THE REAL GATE IS NEVER WRITTEN TO, and the port adds the refusal the twin lacks: a `sed` whose pattern stopped matching writes a byte-identical copy whose selftest PASSES, which would make `test_the_control_can_actually_fail` red for the opposite of its stated reason. The occurrence count is asserted before the mutant is run.
"""

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

GATE = paths.from_root("scripts/gates", "check-hydration-clean.ts")

# Blind the one-hop lookup: the indirect control must go red while the direct one stays green.
MUTATION_FROM = "const body = bodies.get(ident);"
MUTATION_TO = "const body = undefined;"


def gate_source(gate) -> str:
    if not GATE.is_file():
        gate.log_fail("gate not found: %s" % GATE)
    return GATE.read_text(encoding="utf-8")


def run(script, *args: str) -> harness.RunResult:
    npx = harness.require_tool(
        "npx", "install node; the subject is a TypeScript program driven through tsx"
    )
    return harness.run([npx, "tsx", str(script), *args], cwd=paths.repo_root())


def test_selftest_passes_and_plants_both_shapes(gate):
    gate_source(gate)  # refuses loudly if the subject is gone, as the twin's `[ -f ]` does
    result = run(GATE, "--selftest")
    out = result.combined
    gate.assert_exit_code(0, result.rc, "the gate's own controls must pass (output: %s)" % out)
    gate.assert_contains(
        out,
        "a `typeof window` branch in a useState initializer is reported",
        "the direct plant must be exercised",
    )
    gate.assert_contains(
        out,
        "a bare function reference whose body tests the environment is reported",
        "the ONE-HOP plant must be exercised -- without it the gate finds one defect "
        "instead of four",
    )
    gate.assert_contains(
        out,
        "an SSR guard inside useEffect is NOT reported",
        "the false-positive control must be exercised, or the gate would flag every SSR guard",
    )
    gate.log_pass("both defect shapes and the false-positive controls are exercised")


def test_the_control_can_actually_fail(gate, tmp_path):
    source = gate_source(gate)
    hits = source.count(MUTATION_FROM)
    if hits == 0:
        gate.log_fail(
            "the one-hop lookup %r no longer appears in %s, so the 'mutant' below is a "
            "byte-identical copy of the gate and this case cannot mean what it says. "
            "Re-point the mutation at the live lookup; do not delete the case."
            % (MUTATION_FROM, paths.relative_to_root(GATE))
        )
    mutant = tmp_path / "mutant.ts"
    mutant.write_text(source.replace(MUTATION_FROM, MUTATION_TO), encoding="utf-8")
    result = run(mutant, "--selftest")
    gate.assert_exit_code(
        1, result.rc, "a gate that stopped following the one hop must FAIL its own controls"
    )
    gate.assert_contains(
        result.combined,
        "FAIL  a bare function reference",
        "the mutant must name the control it broke",
    )
    gate.log_pass(
        "blinding the one-hop lookup flips the gate's controls red "
        "(%d occurrence(s) blinded)" % hits
    )


def test_real_tree_scan_is_not_vacuous(gate):
    """Seam-free: the real invocation over the real component tree. This is the line the manifest's BLOCKER names."""
    result = run(GATE)
    out = result.combined
    gate.assert_not_contains(
        out, "Refusing to run", "the real tree must give the gate enough input to judge"
    )
    gate.assert_contains(out, "component(s)", "the verdict must state how many components it read")
    if result.rc != 0:
        gate.assert_contains(out, "packages/www", "a finding must name the file it is in")
    gate.log_pass(
        "the real scan ran over the real components and reported its coverage (exit %d)" % result.rc
    )


def test_empty_tree_is_refused(gate, tmp_path):
    (tmp_path / "packages" / "www" / "src").mkdir(parents=True, exist_ok=True)
    result = run(GATE, "--root", str(tmp_path))
    gate.assert_exit_code(1, result.rc, "a tree with no components must be REFUSED, never passed")
    gate.assert_contains(result.combined, "Refusing to run", "the refusal must say so")
    gate.log_pass("an empty component tree is refused rather than reported clean")
