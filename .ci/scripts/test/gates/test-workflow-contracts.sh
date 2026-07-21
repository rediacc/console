#!/bin/bash
# Both-ways test for the reusable-workflow contract check in
# .ci/scripts/security/check-workflow-gates.sh (CHECK 2).
#
# WHY THIS CLASS NEEDS A GATE AT ALL: inside a reusable workflow, `secrets.FOO`
# for a secret nobody declared under on.workflow_call.secrets evaluates to the
# EMPTY STRING -- no warning, no failure, no log line. cd-deploy-account.yml read
# OTLP_CLIENT_CREDENTIALS_{EU,US,ASIA} that way, so every deployed account Worker
# ran with a blank telemetry credential. The failure is invisible at every layer
# except a parser that compares declaration to use, which is what this asserts.
#
# The check is driven against fixture trees via WORKFLOWS_DIR, so the test never
# depends on the real .github/workflows census.
#
# Both directions matter:
#   - Too quiet: a dropped secret ships an empty credential to production.
#   - Too loud: `secrets: inherit`, GITHUB_TOKEN, optional inputs and script
#     filenames ending in "-secrets.sh" must NOT be reported.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test gate
source "$SCRIPT_DIR/../lib/test-helpers.sh"

CHECK="$REPO_ROOT/.ci/scripts/security/check-workflow-gates.sh"

LAST_OUT=""

run_check() {
    local dir="$1" rc=0
    LAST_OUT="$(CI=true WORKFLOWS_DIR="$dir" bash "$CHECK" 2>&1)" || rc=$?
    return "$rc"
}

# write_callee <dir> <extra-secret-read>
# A reusable workflow declaring one required input and one required secret.
write_callee() {
    local d="$1" extra="${2:-}"
    cat >"$d/callee.yml" <<YAML
name: callee
on:
  workflow_call:
    inputs:
      target:
        required: true
        type: string
    secrets:
      DECLARED:
        required: true
      OPTIONAL_ONE:
        required: false
jobs:
  j:
    runs-on: ubuntu-latest
    steps:
      - run: echo "\${{ secrets.DECLARED }}${extra}"
YAML
}

# write_caller <dir> <with-block> <secrets-block>
write_caller() {
    local d="$1" with="$2" secrets="$3"
    {
        echo "name: caller"
        echo "on: push"
        echo "jobs:"
        echo "  c:"
        echo "    uses: ./.github/workflows/callee.yml"
        printf '%s\n' "$with"
        printf '%s\n' "$secrets"
    } >"$d/caller.yml"
}

WITH_OK=$'    with:\n      target: stable'
SECRETS_OK=$'    secrets:\n      DECLARED: ${{ secrets.DECLARED }}'

# ---------------------------------------------------------------------------

test_clean_contract_passes() {
    local d="$1"
    write_callee "$d"
    write_caller "$d" "$WITH_OK" "$SECRETS_OK"

    local rc=0
    run_check "$d" || rc=$?
    assert_exit_code 0 "$rc" "a complete, matching contract must pass"
    log_pass "matching caller/callee contract passes"
}

test_undeclared_secret_read_in_callee() {
    # The OTLP bug itself: read but never declared -> silently "".
    local d="$1"
    write_callee "$d" ' ${{ secrets.NEVER_DECLARED }}'
    write_caller "$d" "$WITH_OK" "$SECRETS_OK"

    local rc=0
    run_check "$d" || rc=$?
    assert_exit_code 1 "$rc" "reading an undeclared secret must fail"
    assert_contains "$LAST_OUT" "reads secrets.NEVER_DECLARED" "names the undeclared secret"
    assert_contains "$LAST_OUT" 'silently evaluate to ""' "explains why it is invisible"
    log_pass "callee reading an undeclared secret fails (the OTLP class)"
}

test_caller_omits_required_secret() {
    local d="$1"
    write_callee "$d"
    write_caller "$d" "$WITH_OK" $'    secrets:\n      OPTIONAL_ONE: ${{ secrets.OPTIONAL_ONE }}'

    local rc=0
    run_check "$d" || rc=$?
    assert_exit_code 1 "$rc" "omitting a required secret must fail"
    assert_contains "$LAST_OUT" "does not pass required secret DECLARED" "names the omitted secret"
    log_pass "caller omitting a required secret fails"
}

test_caller_passes_undeclared_secret() {
    # Dead wiring: it reads as if the value flows, and it does not.
    local d="$1"
    write_callee "$d"
    write_caller "$d" "$WITH_OK" "$SECRETS_OK"$'\n      GHOST: ${{ secrets.GHOST }}'

    local rc=0
    run_check "$d" || rc=$?
    assert_exit_code 1 "$rc" "passing a secret the callee never declares must fail"
    assert_contains "$LAST_OUT" "passes secret GHOST" "names the dead wiring"
    log_pass "caller passing an undeclared secret fails (dead wiring)"
}

test_input_contract_both_directions() {
    local d="$1"
    write_callee "$d"

    write_caller "$d" $'    with:\n      bogus: x' "$SECRETS_OK"
    local rc=0
    run_check "$d" || rc=$?
    assert_exit_code 1 "$rc" "missing required input + undeclared input must fail"
    assert_contains "$LAST_OUT" "does not pass required input target" "names the omitted input"
    assert_contains "$LAST_OUT" "passes input bogus" "names the undeclared input"
    log_pass "input contract is asserted in both directions"
}

test_optional_secret_may_be_omitted() {
    # Too-loud guard: `required: false` means exactly that.
    local d="$1"
    write_callee "$d"
    write_caller "$d" "$WITH_OK" "$SECRETS_OK"

    local rc=0
    run_check "$d" || rc=$?
    assert_exit_code 0 "$rc" "omitting an optional secret must not be reported"
    log_pass "optional secrets may be omitted without a finding"
}

test_secrets_inherit_is_not_flagged() {
    # `secrets: inherit` forwards everything; there is nothing to compare.
    local d="$1"
    write_callee "$d"
    write_caller "$d" "$WITH_OK" "    secrets: inherit"

    local rc=0
    run_check "$d" || rc=$?
    assert_exit_code 0 "$rc" "secrets: inherit must not be treated as a missing secret"
    log_pass "secrets: inherit is accepted"
}

test_github_token_is_implicit() {
    # GITHUB_TOKEN is always available and is never declared under workflow_call.
    local d="$1"
    write_callee "$d" ' ${{ secrets.GITHUB_TOKEN }}'
    write_caller "$d" "$WITH_OK" "$SECRETS_OK"

    local rc=0
    run_check "$d" || rc=$?
    assert_exit_code 0 "$rc" "GITHUB_TOKEN must not be reported as undeclared"
    log_pass "GITHUB_TOKEN is treated as implicit"
}

test_script_filename_is_not_a_secret_reference() {
    # Regression guard on the matcher: a naive /secrets\.(\w+)/ reads the "sh" in
    # "set-account-worker-secrets.sh" as a secret named `sh`.
    local d="$1"
    write_callee "$d"
    cat >>"$d/callee.yml" <<'YAML'
      - run: .ci/scripts/deploy/set-account-worker-secrets.sh
YAML
    write_caller "$d" "$WITH_OK" "$SECRETS_OK"

    local rc=0
    run_check "$d" || rc=$?
    assert_exit_code 0 "$rc" "a filename ending in -secrets.sh must not read as secrets.sh"
    log_pass "script filenames are not mistaken for secret references"
}

test_missing_callee_is_reported() {
    local d="$1"
    write_caller "$d" "$WITH_OK" "$SECRETS_OK"

    local rc=0
    run_check "$d" || rc=$?
    assert_exit_code 1 "$rc" "calling a workflow that does not exist must fail"
    assert_contains "$LAST_OUT" "does not exist" "names the missing callee"
    log_pass "a call to a nonexistent local workflow fails"
}

test_empty_tree_is_not_a_pass() {
    local d="$1"
    mkdir -p "$d/empty"

    local rc=0
    run_check "$d/empty" || rc=$?
    assert_exit_code 1 "$rc" "no workflows means nothing asserted, which must fail"
    assert_contains "$LAST_OUT" "blind" "says the check has nothing to assert"
    log_pass "empty workflow tree fails (anti-vacuity)"
}

log_test "test-workflow-contracts"
with_temp_dir test_clean_contract_passes
with_temp_dir test_undeclared_secret_read_in_callee
with_temp_dir test_caller_omits_required_secret
with_temp_dir test_caller_passes_undeclared_secret
with_temp_dir test_input_contract_both_directions
with_temp_dir test_optional_secret_may_be_omitted
with_temp_dir test_secrets_inherit_is_not_flagged
with_temp_dir test_github_token_is_implicit
with_temp_dir test_script_filename_is_not_a_secret_reference
with_temp_dir test_missing_callee_is_reported
with_temp_dir test_empty_tree_is_not_a_pass
echo ""
log_pass "all tests passed"
