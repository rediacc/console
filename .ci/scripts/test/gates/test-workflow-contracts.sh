#!/bin/bash
# Both-ways test for the reusable-workflow contract checks in
# .ci/scripts/security/check-workflow-gates.sh: CHECK 2 (callers in this repo)
# and CHECK 4 (callers in other repositories, declared in
# .github/external-callers.yml).
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


# ===========================================================================
# CHECK 4 -- external-caller contracts
#
# CHECK 2 above scans .github/workflows only. The callers that can actually
# break live in OTHER repositories: a same-repo caller moves with its callee in
# one commit, a cross-repo caller resolves `@main` at run time, so a callee edit
# merged here breaks their next run an hour later in a log nobody on this PR is
# reading. .github/external-callers.yml declares them and CHECK 4 enforces the
# same three-way contract against the declaration, cross-checks the declaration
# against the caller's real file, and refuses an unregistered external caller.
#
# The registry is the kind of artifact that rots into a comfortable fiction, so
# the too-quiet direction here is not just "a bad contract passes" -- it is "the
# registry stopped describing reality and nothing said so".
# ===========================================================================

EC_ROOT=""

# ec_fixture <dir> -- a callee, one external caller, and a matching registry.
ec_fixture() {
    local d="$1"
    EC_ROOT="$d/tree"
    mkdir -p "$EC_ROOT/.github/workflows" "$EC_ROOT/private/acct/.github/workflows"
    cat >"$EC_ROOT/.github/workflows/callee.yml" <<'YAML'
name: callee
on:
  workflow_call:
    inputs:
      target:
        required: true
        type: string
      opt:
        required: false
        type: string
    secrets:
      TOKEN:
        required: true
jobs:
  j:
    runs-on: ubuntu-latest
    steps:
      - run: echo "${{ secrets.TOKEN }}"
YAML
    cat >"$EC_ROOT/private/acct/.github/workflows/review.yml" <<'YAML'
name: caller
on: push
jobs:
  c:
    uses: rediacc/console/.github/workflows/callee.yml@main
    with:
      target: x
    secrets:
      TOKEN: ${{ secrets.TOKEN }}
YAML
    cat >"$EC_ROOT/registry.yml" <<'YAML'
callers:
  - caller: private/acct/.github/workflows/review.yml
    repo: rediacc/acct
    pinned_at: main
    calls: .github/workflows/callee.yml
    passes_inputs: [target]
    passes_secrets: [TOKEN]
YAML
}

run_ec() {
    local rc=0
    LAST_OUT="$(CI=true \
        WORKFLOWS_DIR="$EC_ROOT/.github/workflows" \
        EXTERNAL_CALLERS_FILE="$EC_ROOT/registry.yml" \
        EXTERNAL_CALLERS_ROOT="$EC_ROOT" \
        bash "$CHECK" 2>&1)" || rc=$?
    return "$rc"
}

test_ec_clean_passes() {
    ec_fixture "$1"
    local rc=0
    run_ec || rc=$?
    assert_exit_code 0 "$rc" "a registry matching both the callee and the caller must pass"
    assert_contains "$LAST_OUT" "1 external caller call-site(s) verified" "reports what it verified"
    log_pass "matching external-caller registry passes"
}

test_ec_registry_declares_undeclared_input() {
    ec_fixture "$1"
    sed -i 's/passes_inputs: \[target\]/passes_inputs: [target, ghost]/' "$EC_ROOT/registry.yml"
    local rc=0
    run_ec || rc=$?
    assert_exit_code 1 "$rc" "declaring an input the callee never declares must fail"
    assert_contains "$LAST_OUT" "passes input ghost" "names the dead wiring"
    log_pass "external caller passing an undeclared input fails"
}

test_ec_registry_omits_required_secret() {
    ec_fixture "$1"
    sed -i 's/passes_secrets: \[TOKEN\]/passes_secrets: []/' "$EC_ROOT/registry.yml"
    local rc=0
    run_ec || rc=$?
    assert_exit_code 1 "$rc" "omitting a required secret must fail"
    assert_contains "$LAST_OUT" "does not pass required secret TOKEN" "names the omitted secret"
    assert_contains "$LAST_OUT" 'is not a fix' "refuses the required:false escape"
    log_pass "external caller omitting a required secret fails"
}

test_ec_caller_drifts_from_registry() {
    # The rot case: the other repo's file changed, the registry did not.
    ec_fixture "$1"
    sed -i 's/^      target: x$/      target: x\n      opt: y/' "$EC_ROOT/private/acct/.github/workflows/review.yml"
    local rc=0
    run_ec || rc=$?
    assert_exit_code 1 "$rc" "a registry that no longer describes the caller must fail"
    assert_contains "$LAST_OUT" "registry declares ['target']" "shows both sides of the drift"
    log_pass "registry drifting from the caller's real file fails"
}

test_ec_pin_drift_is_reported() {
    ec_fixture "$1"
    sed -i 's/callee.yml@main/callee.yml@v1/' "$EC_ROOT/private/acct/.github/workflows/review.yml"
    local rc=0
    run_ec || rc=$?
    assert_exit_code 1 "$rc" "a ref the registry does not claim must fail"
    assert_contains "$LAST_OUT" "registry says @main" "names the expected ref"
    log_pass "caller pinned at an unregistered ref fails"
}

test_ec_unregistered_caller_is_reported() {
    ec_fixture "$1"
    mkdir -p "$EC_ROOT/private/other/.github/workflows"
    cp "$EC_ROOT/private/acct/.github/workflows/review.yml" \
       "$EC_ROOT/private/other/.github/workflows/review.yml"
    local rc=0
    run_ec || rc=$?
    assert_exit_code 1 "$rc" "an external caller nobody registered must fail"
    assert_contains "$LAST_OUT" "private/other/.github/workflows/review.yml" "names the unregistered file"
    assert_contains "$LAST_OUT" "not declared in registry.yml" "says what is missing"
    log_pass "an unregistered external caller fails (completeness)"
}

test_ec_deleted_callee_is_reported() {
    # Deleting a reusable workflow is invisible to CHECK 2 once no local caller
    # remains -- and it is exactly what strands the external ones.
    ec_fixture "$1"
    rm "$EC_ROOT/.github/workflows/callee.yml"
    local rc=0
    run_ec || rc=$?
    assert_exit_code 1 "$rc" "deleting a callee an external caller depends on must fail"
    assert_contains "$LAST_OUT" "the callee does not exist in this repo" "names the stranded call"
    log_pass "deleting an externally-called workflow fails"
}

test_ec_missing_file_in_checked_out_tree() {
    ec_fixture "$1"
    rm "$EC_ROOT/private/acct/.github/workflows/review.yml"
    mkdir -p "$EC_ROOT/private/other/.github/workflows"
    cp "$EC_ROOT/.github/workflows/callee.yml" "$EC_ROOT/private/other/.github/workflows/unrelated.yml"
    local rc=0
    run_ec || rc=$?
    assert_exit_code 1 "$rc" "a registry entry whose file is gone from a checked-out tree must fail"
    assert_contains "$LAST_OUT" "absent from a checked-out tree" "says the entry is stale"
    log_pass "a stale registry entry fails when its tree is present"
}

test_ec_absent_submodule_is_blind_not_pass() {
    # Anti-vacuity in the shape that actually happens: `npm run ci` on a tree
    # with no submodules checked out. Nothing to scan must not read as success.
    ec_fixture "$1"
    rm -rf "$EC_ROOT/private"
    local rc=0
    run_ec || rc=$?
    assert_exit_code 1 "$rc" "no submodule tree means nothing asserted, which must fail"
    assert_contains "$LAST_OUT" "this check is blind" "says the check has nothing to assert"
    log_pass "an absent submodule tree fails rather than passing vacuously"
}

test_ec_empty_registry_is_blind_not_pass() {
    ec_fixture "$1"
    echo "callers: []" >"$EC_ROOT/registry.yml"
    local rc=0
    run_ec || rc=$?
    assert_exit_code 1 "$rc" "an emptied registry must fail rather than assert nothing"
    assert_contains "$LAST_OUT" "declares no callers" "names the empty registry"
    log_pass "emptying the registry fails (anti-vacuity)"
}

test_ec_fixture_tree_skips_cleanly() {
    # CHECK 1/2/3 fixture trees carry no registry. CHECK 4 must stand down for
    # them WITHOUT that becoming a way to silence it on the real tree: the skip
    # is reachable only when EXTERNAL_CALLERS_FILE is unset AND WORKFLOWS_DIR is
    # not the real one.
    local d="$1"
    write_callee "$d"
    write_caller "$d" "$WITH_OK" "$SECRETS_OK"
    local rc=0
    run_check "$d" || rc=$?
    assert_exit_code 0 "$rc" "a CHECK 2 fixture tree must still pass"
    assert_contains "$LAST_OUT" "Skipping external-caller contract check" "says it stood down"
    log_pass "CHECK 4 stands down on fixture trees, audibly"
}

test_ec_real_registry_is_wired() {
    # The registry is only worth having if the real run reads the real file.
    # Without this, every case above could pass against fixtures while the gate
    # checked nothing in CI.
    local rc=0
    LAST_OUT="$(CI=true bash "$CHECK" 2>&1)" || rc=$?
    assert_exit_code 0 "$rc" "the real tree must satisfy its own external-caller registry"
    assert_contains "$LAST_OUT" "external caller call-site(s) verified" "the real run reached CHECK 4"
    log_pass "the real .github/external-callers.yml is enforced, not just fixtures"
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
with_temp_dir test_ec_clean_passes
with_temp_dir test_ec_registry_declares_undeclared_input
with_temp_dir test_ec_registry_omits_required_secret
with_temp_dir test_ec_caller_drifts_from_registry
with_temp_dir test_ec_pin_drift_is_reported
with_temp_dir test_ec_unregistered_caller_is_reported
with_temp_dir test_ec_deleted_callee_is_reported
with_temp_dir test_ec_missing_file_in_checked_out_tree
with_temp_dir test_ec_absent_submodule_is_blind_not_pass
with_temp_dir test_ec_empty_registry_is_blind_not_pass
with_temp_dir test_ec_fixture_tree_skips_cleanly
test_ec_real_registry_is_wired
echo ""
log_pass "all tests passed"
