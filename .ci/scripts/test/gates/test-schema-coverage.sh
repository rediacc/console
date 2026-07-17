#!/bin/bash
# Integration test for scripts/check-schema-coverage.ts (check:ci-schema-coverage).
#
# The gate walks RdcConfigSchema's type tree and fails closed on any Zod leaf
# without a SENSITIVITY_REGISTRY entry, and on any registry template that
# matches nothing in the schema. Every gate run proves its own instrument
# first (a control schema with one deliberately unregistered leaf must fire);
# this test asserts the green path, the control, and — via the shared vitest
# suite for the coverage walker — the firing paths on synthetic schemas.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

test_gate_green_on_real_tree() {
    cd "$REPO_ROOT"
    local out rc=0
    out=$(npx tsx scripts/check-schema-coverage.ts 2>&1) || rc=$?
    assert_exit_code 0 "$rc" "gate must pass on the current schema+registry"
    assert_contains "$out" "fires as uncovered" "in-run control must have fired before the green"
    assert_contains "$out" "Schema coverage OK" "green summary line present"
    log_pass "gate is green on the real schema+registry, control fired"
}

test_walker_fires_on_synthetic_unregistered_leaf() {
    # The vitest suite drives computeSchemaCoverage with synthetic schemas:
    # an unregistered leaf must be reported uncovered (exit non-zero here means
    # the instrument cannot fire and the gate's green is meaningless).
    cd "$REPO_ROOT/packages/shared"
    if ! npx vitest run src/config-schema/__tests__/coverage.test.ts --reporter=dot >/dev/null 2>&1; then
        log_fail "coverage walker vitest suite failed — gate instrument broken"
    fi
    log_pass "walker fires on synthetic unregistered leaves (vitest suite green)"
}

log_test "test-schema-coverage"
test_gate_green_on_real_tree
test_walker_fires_on_synthetic_unregistered_leaf
echo ""
log_pass "all tests passed"
