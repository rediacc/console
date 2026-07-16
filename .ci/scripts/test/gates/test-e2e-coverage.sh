#!/bin/bash
# Integration test for the FORWARD half of the e2e-coverage gate
# (scripts/check-e2e-coverage.ts), driven through its E2E_COV_* overrides
# against a controlled fixture tree.
#
# "Prove the instrument": the primary test PLANTS a renet function whose only
# mention is a NON-LIVE file (a test the config does not select) plus its
# declared-but-uncalled harness method, and asserts the gate FIRES and names it.
# The negative control plants two verbs a live test genuinely covers (one via the
# harness method map, one via a raw verb literal) and asserts the gate stays
# silent about them. The remaining cases exercise the allowlist pass, the stale-
# entry guard, and the registry↔workflow drift self-check.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

GATE="$REPO_ROOT/scripts/check-e2e-coverage.ts"

# Build a minimal fixture repo at $1. One live suite (01-live) covers live_verb
# (via the harness method map: it calls .liveVerb()) and litonly_verb (via a raw
# 'litonly_verb' literal). One DARK suite (99-dark, unselected by the config's
# '01-*' testMatch) is the only place dead_verb is mentioned or its method called.
build_fixture() {
    local fix="$1"
    mkdir -p "$fix/e2e/tests" "$fix/e2e/src/utils/bridge/methods" \
        "$fix/e2e/src/utils/bridge/helpers" "$fix/workflows"

    cat >"$fix/functions.generated.ts" <<'EOF'
export const RENET_FUNCTIONS = [
  'live_verb',
  'litonly_verb',
  'dead_verb',
] as const;
export const RENET_BRIDGE_FUNCTIONS = ['live_verb', 'litonly_verb', 'dead_verb'] as const;
EOF

    # Plain-object config (no @playwright/test import needed) — the gate reads
    # .default.projects/testDir/testMatch, which is all defineConfig would give.
    cat >"$fix/e2e/playwright.fixture.config.ts" <<'EOF'
export default {
  testDir: './tests',
  projects: [{ name: 'test-01', testMatch: '01-*.test.ts' }],
};
EOF

    cat >"$fix/e2e/src/utils/bridge/methods/FixtureMethods.ts" <<'EOF'
export class FixtureMethods {
  async liveVerb(): Promise<unknown> {
    return this.testFunction({ function: 'live_verb' });
  }
  async deadVerb(): Promise<unknown> {
    return this.testFunction({ function: 'dead_verb' });
  }
}
EOF

    cat >"$fix/e2e/tests/01-live.test.ts" <<'EOF'
test('covers live_verb via the method map', async () => {
  await runner.liveVerb();
  const shellForm = 'litonly_verb';
  expect(shellForm).toBeTruthy();
});
EOF

    # DARK file: not matched by '01-*'. dead_verb lives ONLY here + in the method
    # declaration, so a correct gate must flag it.
    cat >"$fix/e2e/tests/99-dark.test.ts" <<'EOF'
test('this suite is never selected by any live config', async () => {
  await runner.deadVerb();
  const dead = 'dead_verb';
  expect(dead).toBeTruthy();
});
EOF

    cat >"$fix/workflows/ci.yml" <<'EOF'
jobs:
  e2e:
    steps:
      - run: .ci/scripts/test/run-e2e.sh --workers 1 --config playwright.fixture.config.ts
EOF

    : >"$fix/allowlist"
}

# run_gate <fixture> [registry-override] -> sets GATE_OUT / GATE_RC
run_gate() {
    local fix="$1"
    local registry="${2:-playwright.fixture.config.ts}"
    GATE_RC=0
    GATE_OUT="$(
        E2E_COV_E2E_DIR="$fix/e2e" \
            E2E_COV_FUNCTIONS_FILE="$fix/functions.generated.ts" \
            E2E_COV_WORKFLOWS_DIR="$fix/workflows" \
            E2E_COV_ALLOWLIST="$fix/allowlist" \
            E2E_COV_REGISTRY="$registry" \
            npx tsx "$GATE" 2>&1
    )" || GATE_RC=$?
}

test_fires_on_dark_only_verb() {
    local fix
    fix="$(mktemp -d)"
    build_fixture "$fix"
    run_gate "$fix"
    assert_exit_code 1 "$GATE_RC" "gate must fire when a verb is covered only by a dark file"
    assert_contains "$GATE_OUT" "dead_verb" "the red list names the uncovered verb"
    log_pass "RED-FIRST: gate fires and names the dark-only verb"
    rm -rf "$fix"
}

test_negative_control_live_verbs_pass() {
    local fix
    fix="$(mktemp -d)"
    build_fixture "$fix"
    run_gate "$fix"
    # live_verb (method map) and litonly_verb (raw literal) are genuinely covered
    # by the live suite — a gate that flagged them would be crying wolf.
    assert_not_contains "$GATE_OUT" "live_verb" "method-map-covered verb must NOT be flagged"
    assert_not_contains "$GATE_OUT" "litonly_verb" "literal-covered verb must NOT be flagged"
    log_pass "negative control: live-suite-covered verbs are not flagged"
    rm -rf "$fix"
}

test_allowlist_silences_dead_verb() {
    local fix
    fix="$(mktemp -d)"
    build_fixture "$fix"
    cat >"$fix/allowlist" <<'EOF'
# BLOCKER: dead_verb predates the fixture suite; migration into a live test is tracked follow-up work
dead_verb
EOF
    run_gate "$fix"
    assert_exit_code 0 "$GATE_RC" "a BLOCKER-allowlisted uncovered verb should pass"
    log_pass "allowlist with a valid BLOCKER silences the uncovered verb"
    rm -rf "$fix"
}

test_missing_blocker_rejected() {
    local fix
    fix="$(mktemp -d)"
    build_fixture "$fix"
    printf '%s\n' 'dead_verb' >"$fix/allowlist"
    run_gate "$fix"
    assert_exit_code 1 "$GATE_RC" "allowlist entry without a BLOCKER should fail"
    assert_contains "$GATE_OUT" "BLOCKER" "error demands a BLOCKER reason"
    log_pass "allowlist entry without a BLOCKER is rejected"
    rm -rf "$fix"
}

test_stale_allowlist_entry_rejected() {
    local fix
    fix="$(mktemp -d)"
    build_fixture "$fix"
    # live_verb IS covered by the live suite — allowlisting it is stale debt.
    cat >"$fix/allowlist" <<'EOF'
# BLOCKER: live_verb is genuinely covered so this entry is stale by construction for the test
live_verb
EOF
    run_gate "$fix"
    assert_exit_code 1 "$GATE_RC" "an allowlisted-but-covered verb should fail as stale"
    assert_contains "$GATE_OUT" "live_verb" "the stale entry is named"
    log_pass "stale allowlist entry (now covered) is rejected"
    rm -rf "$fix"
}

test_registry_workflow_drift_rejected() {
    local fix
    fix="$(mktemp -d)"
    build_fixture "$fix"
    # Registry names a second config that no workflow runs -> drift.
    run_gate "$fix" "playwright.fixture.config.ts,playwright.ghost.config.ts"
    assert_exit_code 1 "$GATE_RC" "a config in the registry that no workflow runs should fail"
    assert_contains "$GATE_OUT" "playwright.ghost.config.ts" "the drift error names the ghost config"
    log_pass "registry↔workflow drift self-check fires"
    rm -rf "$fix"
}

log_test "test-e2e-coverage"
test_fires_on_dark_only_verb
test_negative_control_live_verbs_pass
test_allowlist_silences_dead_verb
test_missing_blocker_rejected
test_stale_allowlist_entry_rejected
test_registry_workflow_drift_rejected
echo ""
log_pass "all tests passed"
