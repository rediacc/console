"""Port of `.ci/scripts/test/gates/test-form-validation.sh`, retired in W7 P5.

Tests for `scripts/gates/check-form-validation.ts`.

The gate is RED on the real tree today: five of the six forms in packages/www disable browser validation without replacing it, or read an input and silently discard it. The fix belongs to a later wave, so this test does NOT pin the verdict. It pins:

  1. the gate can FAIL -- both plants (the captcha-only guard, and the silent
     return) are exercised, AND the one form that gets it right stays clean, which
     is what keeps the rule from being unreasonable;
  2. its controls are load-bearing -- mutating the captcha exclusion out flips them
     red;
  3. the real scan really ran over a form count above its floor, and refuses an
     empty tree rather than reporting it clean.

THE MUTANT IS BUILT IN A TEMPDIR AND THE REAL GATE IS NEVER WRITTEN TO. `sed 's/&& !CAPTCHA_IDENTS.test(i)//' $GATE > $tmp/mutant.ts` in the twin becomes a string replacement here, and the PORT ADDS A REFUSAL THE TWIN DOES NOT HAVE: a replacement that matched NOTHING would hand `tsx` a byte-identical copy of the gate, whose selftest passes, and `test_the_control_can_actually_fail`
would then be red for the opposite of its stated reason -- or, worse, an author "fixing" it would delete the case. The count is asserted before the mutant is run.
"""

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

GATE = paths.from_root("scripts/gates", "check-form-validation.ts")

# The leniency planted by the mutant: accept a captcha guard as validation, which is exactly what would let ContactForm pass while an empty submit still reaches the network.
MUTATION = "&& !CAPTCHA_IDENTS.test(i)"


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
    gate.assert_exit(0, result, "the gate's own controls must pass")
    gate.assert_contains(
        out,
        "PLANT: a captcha guard does not count as input validation",
        "the captcha-only plant must be exercised -- it is what ContactForm actually has",
    )
    gate.assert_contains(
        out,
        "PLANT: a captcha READ FROM AN INPUT still does not count as input validation",
        "the reachable form of the captcha rule must be exercised, or CAPTCHA_IDENTS is a "
        "rule that cannot fire",
    )
    gate.assert_contains(
        out,
        "PLANT: a value read from an input and silently discarded is reported",
        "the dead-button plant must be exercised",
    )
    gate.assert_contains(
        out,
        "a noValidate form WITH a field guard that reports an error is clean",
        "the good form must stay clean, or the rule is asking for the impossible",
    )
    gate.log_pass("both defect shapes and the good-form control are exercised")


def test_the_control_can_actually_fail(gate, tmp_path):
    source = gate_source(gate)
    hits = source.count(MUTATION)
    # THE CONTROL ON THE CONTROL. A mutation that matches nothing produces a byte-identical copy, whose selftest PASSES, and this case then reds while saying the opposite of what happened.
    if hits == 0:
        gate.log_fail(
            "the planted leniency %r no longer appears in %s, so the 'mutant' below is a "
            "byte-identical copy of the gate and this case cannot mean what it says. "
            "Re-point the mutation at the live captcha exclusion; do not delete the case."
            % (MUTATION, paths.relative_to_root(GATE))
        )
    mutant = tmp_path / "mutant.ts"
    mutant.write_text(source.replace(MUTATION, ""), encoding="utf-8")
    result = run(mutant, "--selftest")
    gate.assert_exit(
        1, result, "a gate that counts a captcha guard as validation must FAIL its own controls"
    )
    gate.assert_contains(
        result.combined,
        "FAIL  PLANT: a captcha READ FROM AN INPUT",
        "the mutant must name the control it broke",
    )
    gate.log_pass(
        "accepting a captcha guard as validation flips the gate's controls red "
        "(%d occurrence(s) removed)" % hits
    )


def test_real_tree_scan_is_not_vacuous(gate):
    """Seam-free: the real invocation over the real component tree. This is the line the manifest's BLOCKER names."""
    result = run(GATE)
    out = result.combined
    gate.assert_not_contains(
        out, "Refusing to run", "the real tree must give the gate enough forms to judge"
    )
    gate.assert_contains(out, "form(s)", "the verdict must state how many forms it read")
    if result.rc != 0:
        gate.assert_contains(out, "packages/www", "a finding must name the file it is in")
    gate.log_pass(
        "the real scan ran over the real forms and reported its coverage (exit %d)" % result.rc
    )


def test_empty_tree_is_refused(gate, tmp_path):
    (tmp_path / "packages" / "www" / "src").mkdir(parents=True, exist_ok=True)
    result = run(GATE, "--root", str(tmp_path))
    gate.assert_exit(1, result, "a tree with no forms must be REFUSED, never passed")
    gate.assert_contains(result.combined, "Refusing to run", "the refusal must say so")
    gate.log_pass("a tree with no forms is refused rather than reported clean")
