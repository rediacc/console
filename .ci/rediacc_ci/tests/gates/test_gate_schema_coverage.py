"""Port of `.ci/scripts/test/gates/test-schema-coverage.sh`.

Integration test for `scripts/gates/check-schema-coverage.ts` (`check:ci-schema-coverage`).

The gate walks `RdcConfigSchema`'s type tree and fails closed on any Zod leaf without a `SENSITIVITY_REGISTRY` entry, and on any registry template that matches nothing in the schema. Every gate run proves its own instrument FIRST -- a control schema with one deliberately unregistered leaf must fire -- and this asserts the green path, that in-run control, and, via the shared vitest
suite for the coverage walker, the firing paths on synthetic schemas.

WHY BOTH HALVES ARE HERE. Asserting only the green would pass against a gate that had stopped walking anything: `Schema coverage OK` over zero leaves reads exactly like `Schema coverage OK` over all of them. The `fires as uncovered` line is the gate's own statement that its control fired before it printed the verdict, and the vitest suite is the same claim proven against synthetic
schemas the real tree cannot produce.

WHERE THE PORT REIMPLEMENTS THE TWIN. It does not. The twin runs `npx tsx` and `npx vitest`; the port runs the same two commands through the repo-local binaries (`node_modules/.bin/tsx`, `node_modules/.bin/vitest`) so a missing install is a named refusal here rather than npx silently reaching for a registry it cannot reach. That is the only difference, and it changes which failure
a reader sees, never which verdict.

NO `xdist_group`. Both cases are read-only subprocesses: one runs the gate over the real tree, the other runs a vitest file that builds its schemas in memory. Neither writes anything, so two of them side by side share nothing.
"""

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-schema-coverage.sh"

SUT = paths.from_root("scripts/gates", "check-schema-coverage.ts")
TSX = paths.from_root("node_modules", ".bin", "tsx")
SHARED = paths.from_root("packages", "shared")
# HOISTED, NOT PER-WORKSPACE, and the first draft of this port got it wrong. npm hoists vitest to the ROOT node_modules in this monorepo, so a probe at `packages/shared/node_modules/.bin/vitest` refuses on every machine. The twin never noticed because `npx vitest` walks up the tree for it. That was a defect in the CONTROL, not in the gate: the probe was looking in a directory that
# has never existed here. Fixed by pointing at the hoisted binary and running it with cwd inside packages/shared, which is where the suite path resolves from.
VITEST = paths.from_root("node_modules", ".bin", "vitest")
WALKER_SUITE = "src/config-schema/__tests__/coverage.test.ts"


def test_gate_green_on_real_tree(gate):
    gate.log_test("the gate is green on the real schema+registry, and says its control fired")
    if not SUT.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(SUT))
    if not TSX.is_file():
        gate.log_fail(
            "node_modules/.bin/tsx is absent, so the gate could not be executed at all -- "
            "which is a FAILURE and not a pass. Fix: npm install && npm run install:natives"
        )
    result = harness.run([str(TSX), str(SUT)], cwd=paths.repo_root())
    gate.assert_exit_code(0, result.rc, "gate must pass on the current schema+registry")
    gate.assert_contains(
        result.combined,
        "fires as uncovered",
        "in-run control must have fired before the green",
    )
    gate.assert_contains(result.combined, "Schema coverage OK", "green summary line present")
    gate.log_pass("gate is green on the real schema+registry, control fired")


def test_walker_fires_on_synthetic_unregistered_leaf(gate):
    gate.log_test("the walker itself fires on schemas the real tree cannot produce")
    # The vitest suite drives computeSchemaCoverage with synthetic schemas: an unregistered leaf must be reported uncovered. A non-zero exit here means the instrument cannot fire and the gate's green above is meaningless.
    if not VITEST.is_file():
        gate.log_fail(
            "node_modules/.bin/vitest is absent, so the walker's own "
            "controls could not run at all -- which is a FAILURE and not a pass. "
            "Fix: npm install && npm run install:natives"
        )
    if not (SHARED / WALKER_SUITE).is_file():
        gate.log_fail(
            "the walker suite is missing at packages/shared/%s, so nothing below it was "
            "exercised" % WALKER_SUITE
        )
    result = harness.run(
        [str(VITEST), "run", WALKER_SUITE, "--reporter=dot"], cwd=SHARED, timeout=600
    )
    if result.rc != 0:
        gate.log_fail(
            "coverage walker vitest suite failed -- gate instrument broken\n"
            "--- stdout ---\n%s\n--- stderr ---\n%s" % (result.out, result.err)
        )
    gate.assertions += 1
    gate.log_pass("walker fires on synthetic unregistered leaves (vitest suite green)")


def test_the_gate_reports_a_non_trivial_leaf_count(gate):
    """PORT-ONLY. `Schema coverage OK` is a string, and a walk that visited nothing prints it just as happily as a walk that visited the whole schema. The gate names its numbers; this reads one back and refuses a zero, so the green above is a claim about a corpus rather than about a line of text."""
    gate.log_test("the green above covered a non-empty schema")
    result = harness.run([str(TSX), str(SUT)], cwd=paths.repo_root())
    digits = [int(token) for token in result.combined.replace(",", " ").split() if token.isdigit()]
    if not digits or max(digits) < 1:
        gate.log_fail(
            "the gate's output carries no positive count, so its green cannot be "
            "distinguished from a walk over an empty schema. Output:\n%s" % result.combined
        )
    gate.assertions += 1
    gate.log_pass("the gate reported counts up to %d, so its walk was not empty" % max(digits))
