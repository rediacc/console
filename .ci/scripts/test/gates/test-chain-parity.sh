#!/bin/bash
# Both-ways test for scripts/check-ci-chain-parity.ts.
#
# The gate's promise: every gate a workflow runs is also reachable from
# `npm run ci`, so a local run catches CI failures before a push.
#
# WHY THE BARE-PATH CASES MATTER: for its whole life the gate only matched
# `npm run check:*` in workflow YAML. A gate invoked as a bare script path
# (`- run: .ci/scripts/quality/check-foo.sh`) was invisible to it, and 13 real
# gaps sat behind a green "Every workflow gate is reachable from `npm run ci`" --
# including check-workflow-gates.sh and check-silent-failure-patterns.sh, which
# no developer could run locally. A gate that reports success while blind to a
# whole invocation style is worse than no gate, so both styles are pinned here.
#
# Fixtures live under CHAIN_PARITY_ROOT so no tracked file is ever mutated.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test gate
source "$SCRIPT_DIR/../lib/test-helpers.sh"

GATE="$REPO_ROOT/scripts/check-ci-chain-parity.ts"

LAST_OUT=""

run_gate() {
    local root="$1" rc=0
    LAST_OUT="$(cd "$REPO_ROOT" && CHAIN_PARITY_ROOT="$root" npx tsx "$GATE" 2>&1)" || rc=$?
    return "$rc"
}

# scaffold <root> <ci-chain> <workflow-step-line>
scaffold() {
    local root="$1" chain="$2" step="$3"
    mkdir -p "$root/.github/workflows"
    cat >"$root/package.json" <<JSON
{
  "name": "fixture",
  "scripts": {
    "check:ci-alpha": "echo alpha",
    "check:ci-beta": ".ci/scripts/quality/check-beta.sh",
    "ci": "$chain"
  }
}
JSON
    cat >"$root/.github/workflows/quality.yml" <<YAML
name: quality
on: push
jobs:
  q:
    runs-on: ubuntu-latest
    steps:
$step
YAML
}

STEP_NAMED='      - run: npm run check:ci-alpha'

# ---------------------------------------------------------------------------

test_named_gate_in_chain_passes() {
    local d="$1"
    scaffold "$d" "npm run check:ci-alpha" "$STEP_NAMED"

    local rc=0
    run_gate "$d" || rc=$?
    assert_exit_code 0 "$rc" "a named gate present in the chain must pass"
    log_pass "named gate in the chain passes"
}

test_named_gate_missing_from_chain_fails() {
    local d="$1"
    scaffold "$d" "npm run check:ci-beta" "$STEP_NAMED"

    local rc=0
    run_gate "$d" || rc=$?
    assert_exit_code 1 "$rc" "a named gate absent from the chain must fail"
    assert_contains "$LAST_OUT" "check:ci-alpha" "names the missing gate"
    assert_contains "$LAST_OUT" "NOT in \`npm run ci\`" "says what the break is"
    log_pass "named gate missing from the chain fails"
}

test_bare_gate_missing_from_chain_fails() {
    # The blind spot: a gate invoked by path, named by nothing.
    local d="$1"
    scaffold "$d" "npm run check:ci-alpha" "      - run: .ci/scripts/quality/check-orphan.sh"

    local rc=0
    run_gate "$d" || rc=$?
    assert_exit_code 1 "$rc" "a bare shell gate absent from the chain must fail"
    assert_contains "$LAST_OUT" ".ci/scripts/quality/check-orphan.sh" "names the bare gate"
    assert_contains "$LAST_OUT" "invoked directly by a workflow" "distinguishes it from the named break"
    log_pass "bare shell gate missing from the chain fails (the 13-gap blind spot)"
}

test_bare_gate_reachable_via_chain_passes() {
    # check:ci-beta is in the chain and its command IS the script path, so the
    # bare invocation is covered.
    local d="$1"
    scaffold "$d" "npm run check:ci-beta" "      - run: .ci/scripts/quality/check-beta.sh"

    local rc=0
    run_gate "$d" || rc=$?
    assert_exit_code 0 "$rc" "a bare gate whose path is reachable from the chain must pass"
    log_pass "bare gate reachable through a chain step passes"
}

test_bare_path_in_a_comment_is_not_an_invocation() {
    # Too-loud guard: ci-build-renet.yml carries "# Keep the version in sync with
    # .ci/scripts/quality/lint.sh". Prose is not a step.
    local d="$1"
    scaffold "$d" "npm run check:ci-alpha" \
        "      # see .ci/scripts/quality/check-orphan.sh for the rules
$STEP_NAMED"

    local rc=0
    run_gate "$d" || rc=$?
    assert_exit_code 0 "$rc" "a script path inside a YAML comment must not count as an invocation"
    log_pass "a path mentioned in a comment is not treated as a gate invocation"
}

test_non_gate_scripts_are_not_swept_in() {
    # Only .ci/scripts/{quality,security}/check-*.sh are gates. Build, deploy and
    # release helpers are steps and have no business in a local chain.
    local d="$1"
    scaffold "$d" "npm run check:ci-alpha" \
        "      - run: .ci/scripts/deploy/upload-repos-to-r2.sh
      - run: .ci/scripts/build/pack-cli-npm.sh
$STEP_NAMED"

    local rc=0
    run_gate "$d" || rc=$?
    assert_exit_code 0 "$rc" "deploy/build helpers must not be treated as gates"
    log_pass "only quality/security check-*.sh scripts count as gates"
}

test_exemption_clears_a_bare_gate() {
    local d="$1"
    scaffold "$d" "npm run check:ci-alpha" "      - run: .ci/scripts/quality/check-orphan.sh"
    cat >"$d/.ci-chain-exempt" <<'EOF'
# BLOCKER: reads the pull request body through the GitHub API, so there is nothing for a local checkout to validate before the PR exists
.ci/scripts/quality/check-orphan.sh
EOF

    local rc=0
    run_gate "$d" || rc=$?
    assert_exit_code 0 "$rc" "a BLOCKER-gated exemption must clear the finding"
    log_pass "an exempted bare gate passes"
}

test_low_effort_blocker_is_rejected() {
    # The exemption list is a hole in the promise; the reason has to be real.
    local d="$1"
    scaffold "$d" "npm run check:ci-alpha" "      - run: .ci/scripts/quality/check-orphan.sh"
    cat >"$d/.ci-chain-exempt" <<'EOF'
# BLOCKER: tbd
.ci/scripts/quality/check-orphan.sh
EOF

    local rc=0
    run_gate "$d" || rc=$?
    assert_exit_code 1 "$rc" "a low-effort BLOCKER must be rejected by the shared validator"
    assert_contains "$LAST_OUT" "BLOCKER validation failed" "names the validator failure"
    log_pass "a low-effort BLOCKER reason is rejected"
}

test_undefined_script_is_reported() {
    # A workflow naming a script package.json does not define is a hard CI
    # failure ("Missing script"), not a coverage gap.
    local d="$1"
    scaffold "$d" "npm run check:ci-alpha" "      - run: npm run check:ci-ghost"

    local rc=0
    run_gate "$d" || rc=$?
    assert_exit_code 1 "$rc" "a workflow naming an undefined script must fail"
    assert_contains "$LAST_OUT" "check:ci-ghost" "names the undefined script"
    assert_contains "$LAST_OUT" "NOT defined in package.json" "explains the break"
    log_pass "a workflow naming an undefined npm script fails"
}

test_no_workflows_is_not_a_pass() {
    local d="$1"
    mkdir -p "$d/.github/workflows"
    cat >"$d/package.json" <<'JSON'
{ "name": "fixture", "scripts": { "ci": "npm run check:ci-alpha" } }
JSON

    local rc=0
    run_gate "$d" || rc=$?
    assert_exit_code 1 "$rc" "an empty workflow tree means nothing asserted, which must fail"
    log_pass "empty workflow tree fails (anti-vacuity)"
}

log_test "test-chain-parity"
with_temp_dir test_named_gate_in_chain_passes
with_temp_dir test_named_gate_missing_from_chain_fails
with_temp_dir test_bare_gate_missing_from_chain_fails
with_temp_dir test_bare_gate_reachable_via_chain_passes
with_temp_dir test_bare_path_in_a_comment_is_not_an_invocation
with_temp_dir test_non_gate_scripts_are_not_swept_in
with_temp_dir test_exemption_clears_a_bare_gate
with_temp_dir test_low_effort_blocker_is_rejected
with_temp_dir test_undefined_script_is_reported
with_temp_dir test_no_workflows_is_not_a_pass
echo ""
log_pass "all tests passed"
