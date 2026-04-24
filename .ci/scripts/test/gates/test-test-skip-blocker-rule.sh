#!/bin/bash
# Integration test for the custom/test-skip-blocker ESLint rule.
#
# Drives the rule through a series of fixture files and confirms each
# known-bad form is rejected while each known-good form is accepted.
#
# The rule is registered in eslint.config.js and scoped to packages/cli/tests,
# packages/e2e, and packages/bridge-tests. To avoid depending on those
# workspaces' own lint clean state, this test invokes eslint directly with
# the rule's source file plus a minimal inline config.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

RULE_FILE="$REPO_ROOT/eslint-rules/test-skip-blocker.js"

# Build a temp eslint config that loads only the rule under test.
make_eslint_config() {
    local tmpdir="$1"
    cat >"$tmpdir/eslint.config.js" <<'CONFIG'
import tseslint from 'typescript-eslint';
import { testSkipBlocker } from './test-skip-blocker.js';
export default [
  {
    files: ['*.test.ts'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      parser: tseslint.parser,
    },
    plugins: {
      custom: { rules: { 'test-skip-blocker': testSkipBlocker } },
    },
    rules: {
      'custom/test-skip-blocker': 'error',
    },
  },
];
CONFIG
    # Copy the rule into the temp dir so the import path stays short.
    cp "$RULE_FILE" "$tmpdir/test-skip-blocker.js"
    # Use the repo's node_modules (typescript-eslint etc.) by symlinking.
    ln -s "$REPO_ROOT/node_modules" "$tmpdir/node_modules"
}

run_eslint() {
    local tmpdir="$1" fixture="$2"
    (cd "$tmpdir" && NODE_OPTIONS=--max-old-space-size=4096 npx eslint "$fixture" 2>&1)
}

assert_rule_accepts() {
    local label="$1" fixture_body="$2"
    local TEMP
    TEMP="$(mktemp -d)"
    # shellcheck disable=SC2064
    # BLOCKER: expand TEMP now so the trap binds the specific path
    trap "rm -rf '$TEMP'" RETURN
    make_eslint_config "$TEMP"
    echo "$fixture_body" >"$TEMP/case.test.ts"
    local out rc=0
    out=$(run_eslint "$TEMP" case.test.ts) || rc=$?
    if [[ $rc -ne 0 ]]; then
        echo "$out"
        log_fail "$label: rule rejected a case it should accept"
    fi
    log_pass "accepts: $label"
}

assert_rule_rejects() {
    local label="$1" fixture_body="$2" expect_substring="$3"
    local TEMP
    TEMP="$(mktemp -d)"
    # shellcheck disable=SC2064
    # BLOCKER: expand TEMP now so the trap binds the specific path
    trap "rm -rf '$TEMP'" RETURN
    make_eslint_config "$TEMP"
    echo "$fixture_body" >"$TEMP/case.test.ts"
    local out rc=0
    out=$(run_eslint "$TEMP" case.test.ts) || rc=$?
    if [[ $rc -eq 0 ]]; then
        echo "$out"
        log_fail "$label: rule accepted a case it should reject"
    fi
    assert_contains "$out" "$expect_substring" "$label: error message"
    log_pass "rejects: $label"
}

log_test "test-test-skip-blocker-rule"

assert_rule_accepts "declaration form (string name, fn body)" '
import { test } from "vitest";
test.skip("should do a thing", () => {});
'

assert_rule_accepts "conditional with substantive reason" '
import { test } from "vitest";
test("demo", () => {
  test.skip(!cond, "E2E VMs not configured: bridge-test requires VM_DEPLOYMENT=true");
});
'

assert_rule_accepts "conditional with long template literal" '
import { test } from "vitest";
test("demo", () => {
  test.skip(!cond, `Image ${name} has not been built in this env; bridge-test pipeline must run first`);
});
'

assert_rule_rejects "bare skip" '
import { test } from "vitest";
test("demo", () => {
  test.skip();
});
' "Bare test.skip() is not allowed"

assert_rule_rejects "1-arg conditional with no reason" '
import { test } from "vitest";
test("demo", () => {
  test.skip(!cond);
});
' "without a reason is not allowed"

assert_rule_rejects "short reason" '
import { test } from "vitest";
test("demo", () => {
  test.skip(!cond, "too short");
});
' "reason is too short"

assert_rule_rejects "banned phrase" '
import { test } from "vitest";
test("demo", () => {
  test.skip(!cond, "tbd");
});
' "matches the banned-phrase list"

echo ""
log_pass "all tests passed"
