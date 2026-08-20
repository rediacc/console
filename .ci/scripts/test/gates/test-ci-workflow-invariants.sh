#!/bin/bash
# Both-ways test for .ci/scripts/security/check-ci-workflow-invariants.sh.
#
# THE METHOD IS THE POINT: a static check that has never been watched FAILING is
# indistinguishable from `true`. So the invariant is proven in both directions --
# the real ci.yml passes, and a workflow with the invariant broken must exit 1
# with the pinned diagnostic.
#
# The strongest case here is not a synthetic mutation, it is HISTORY: commit
# 6584a8795 is the real main whose `validate-install` lacked the channel
# condition, and it produced "Version mismatch: expected '1.2.27', got '1.2.26'"
# on nightlies 32323997586 and 32208001410. If the gate cannot reject that exact
# file, it would not have caught the bug it exists for. That case is skipped
# rather than failed when the commit is unreachable (a shallow clone), because a
# missing object is not evidence of a working gate.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

GATE="$REPO_ROOT/.ci/scripts/security/check-ci-workflow-invariants.sh"
REAL="$REPO_ROOT/.github/workflows/ci.yml"

FIXTURE="$(mktemp -d)"
trap 'rm -rf "$FIXTURE"' EXIT

# run_gate <workflow-file> -> prints "PASS" or "FAIL"; output lands in a file
# because every call site runs this in a subshell.
run_gate() {
    local rc=0
    WORKFLOW_FILE="$1" bash "$GATE" >"$FIXTURE/out.txt" 2>&1 || rc=$?
    [[ $rc -eq 0 ]] && echo "PASS" || echo "FAIL"
}
last_output() { cat "$FIXTURE/out.txt"; }

test_real_workflow_passes() {
    # Baseline. If this failed, every other case would be meaningless.
    assert_eq "$(run_gate "$REAL")" "PASS" "the real ci.yml satisfies the invariant"
    log_pass "the real ci.yml passes"
}

test_the_historical_defect_is_rejected() {
    # THE CASE THAT MATTERS. The pre-fix main that actually broke the nightlies.
    local old="$FIXTURE/ci-historical.yml"
    if ! git -C "$REPO_ROOT" show 6584a8795:.github/workflows/ci.yml >"$old" 2>/dev/null; then
        log_info "SKIP: commit 6584a8795 is not reachable in this checkout"
        return 0
    fi
    assert_eq "$(run_gate "$old")" "FAIL" "the pre-fix ci.yml (6584a8795) must be rejected"
    assert_contains "$(last_output)" "channel-as-docker-tag" "the right invariant fires"
    assert_contains "$(last_output)" "validate-install" "the offending job is named"
    log_pass "the gate rejects the real workflow that broke nightlies 32323997586 and 32208001410"
}

test_dropping_the_condition_is_caught() {
    # A synthetic mutation of the CURRENT file, so the proof cannot rot as the
    # workflow evolves: if the shape drifts so far that the mutation stops
    # landing, the sanity assertion below fails loudly instead of the test
    # quietly checking nothing.
    local mut="$FIXTURE/ci-mutated.yml"
    grep -v "needs.initialize.outputs.channel != ''" "$REAL" >"$mut"
    assert_not_contains "$(cat "$mut")" "needs.initialize.outputs.channel != ''" \
        "the mutation actually removed the condition"
    # Repair the dangling `&&` the removed line left behind so the file still parses.
    python3 - "$mut" <<'PY'
import io, sys
p = sys.argv[1]
s = io.open(p, encoding='utf-8').read()
s = s.replace("run_install_methods != 'false' &&", "run_install_methods != 'false'", 1)
io.open(p, 'w', encoding='utf-8').write(s)
PY
    assert_eq "$(run_gate "$mut")" "FAIL" "removing the channel condition must be caught"
    assert_contains "$(last_output)" "channel-as-docker-tag" "the right invariant fires"
    log_pass "dropping the channel condition is caught"
}

test_vacuity_guard_when_nothing_is_checked() {
    # A gate whose subject disappeared must not print a green nobody earned.
    local novac="$FIXTURE/ci-no-docker-tag.yml"
    grep -v "docker_tag:" "$REAL" >"$novac"
    assert_eq "$(run_gate "$novac")" "FAIL" "a workflow with no channel-derived docker_tag must not pass silently"
    assert_contains "$(last_output)" "no-candidates" "the vacuity guard is what fires"
    log_pass "the vacuity guard refuses to pass when the gate verified nothing"
}

test_missing_workflow_is_not_green() {
    assert_eq "$(run_gate "$FIXTURE/absent.yml")" "FAIL" "a missing workflow must not read as green"
    assert_contains "$(last_output)" "workflow-missing" "the missing-file guard fires"
    log_pass "a missing workflow file fails rather than passing vacuously"
}

test_a_correctly_gated_job_is_not_flagged() {
    # THE OTHER DIRECTION: the gate must not simply always fail. A minimal
    # workflow that does the right thing has to pass.
    local ok="$FIXTURE/ci-ok.yml"
    cat >"$ok" <<'YAML'
name: fixture
on: push
jobs:
  validate-install:
    if: >-
      always() &&
      needs.initialize.outputs.channel != ''
    uses: ./.github/workflows/ct-install-methods.yml
    with:
      docker_tag: ${{ needs.initialize.outputs.channel }}
YAML
    assert_eq "$(run_gate "$ok")" "PASS" "a correctly gated job must pass"
    log_pass "a correctly gated job is not flagged"
}

log_test "test-ci-workflow-invariants"
test_real_workflow_passes
test_the_historical_defect_is_rejected
test_dropping_the_condition_is_caught
test_vacuity_guard_when_nothing_is_checked
test_missing_workflow_is_not_green
test_a_correctly_gated_job_is_not_flagged
echo ""
log_pass "all tests passed"
