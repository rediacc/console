#!/bin/bash
# Both-ways test for the pr-environment rule in .ci/scripts/quality/check-workflows.sh.
#
# THE BUG IT GUARDS. A job-level `environment:` makes GitHub create the
# environment OBJECT and a deployment record. ci.yml's deploy-preview job
# declared `pr-${{ github.event.pull_request.number }}`, and CI can never clean
# the objects up: deleting one needs Administration:write, which
# check-no-app-admin-perm.sh deliberately forbids the CI App from holding, so a
# leaked token cannot delete `edge` or `stable`. 25 empty `pr-*` shells
# accumulated on /deployments and had to be removed by hand on 2026-09-03.
#
# THE POSITIVE CONTROL IS THE HISTORICAL DEFECT, VERBATIM -- the exact three
# lines removed from ci.yml, not a synthetic mutation. That text is what created
# the 25. A rule that cannot reject it would not have caught the thing it exists
# for.
#
# AND THE SCALAR FORM, which is the case that decides whether this rule is real.
# `environment: pr-${{ ... }}` on one line is equally valid GitHub and is exactly
# what someone writes re-adding this in a hurry; a `grep 'name: pr-'` misses it
# entirely. This repo has already shipped a workflow rule that was born vacuous
# (see test-workflow-env-shell-vars.sh:19-25, an awk `\b` that matched nothing
# while reporting "All workflows are clean"), so the half that is easy to omit
# is the half that gets asserted first.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test gate
source "$SCRIPT_DIR/../lib/test-helpers.sh"

# shellcheck source=../lib/workflow-rule.sh
# BLOCKER: the shared harness for check-workflows.sh's rules; see its header for
# why test-workflow-contracts.sh is deliberately NOT a caller
source "$SCRIPT_DIR/../lib/workflow-rule.sh"

# write_job <path> <lines...> -- lines land at job level, under `j:`.
write_job() {
    local path="$1"
    shift
    {
        echo "name: fixture"
        echo "on: push"
        echo "jobs:"
        echo "  j:"
        echo "    runs-on: ubuntu-latest"
        printf '    %s\n' "$@"
        echo "    steps:"
        echo "      - run: ./script.sh"
    } >"$path"
}

test_mapping_form_is_caught() {
    local d="$1"
    # The literal block deleted from ci.yml:1234-1236.
    write_job "$d/bad.yml" \
        'environment:' \
        '  name: pr-${{ github.event.pull_request.number }}' \
        '  url: https://pr-${{ github.event.pull_request.number }}.rediacc.workers.dev'
    local rc=0
    run_check "$d" || rc=$?
    assert_exit_code 1 "$rc" "the historical ci.yml block is refused"
    assert_contains "$LAST_OUT" "bad.yml:" "and the finding cites the file and line"
    log_pass "the mapping form -- the defect verbatim -- is caught"
}

test_scalar_form_is_caught() {
    local d="$1"
    write_job "$d/bad.yml" 'environment: pr-${{ github.event.pull_request.number }}'
    local rc=0
    run_check "$d" || rc=$?
    assert_exit_code 1 "$rc" "the scalar shorthand is refused too"
    log_pass "the scalar shorthand is caught, so the rule is not a name:-grep"
}

test_real_environments_pass() {
    local d="$1"
    # The three forms production actually uses. If the rule rejected these it
    # would block every deploy, which is a worse failure than the one it fixes.
    write_job "$d/a.yml" 'environment:' '  name: edge'
    write_job "$d/b.yml" 'environment:' '  name: ${{ inputs.target }}'
    write_job "$d/c.yml" 'environment:' '  name: ${{ inputs.target }}-${{ matrix.id }}'
    local rc=0
    run_check "$d" || rc=$?
    assert_exit_code 0 "$rc" "edge, inputs.target and the regional form all pass"
    log_pass "CONTROL: the three real production environments are not flagged"
}

test_a_pr_prefixed_word_is_not_a_pr_environment() {
    local d="$1"
    # `preview` starts with `pr` but is not `pr-`; the anchor must be the dash.
    write_job "$d/a.yml" 'environment:' '  name: preview'
    local rc=0
    run_check "$d" || rc=$?
    assert_exit_code 0 "$rc" "a name merely starting with pr is not pr-"
    log_pass "CONTROL: 'preview' is not mistaken for a pr- environment"
}

# NO "the real tree passes" CASE, deliberately. check:ci-workflows runs this very
# rule over the real .github/workflows on every pre-push run and every CI run, so
# a copy here asserts nothing new -- and it is not free: the full scan took this
# battery from ~2s to 21.6s under the lane's contention, which check:ci-gate-manifest
# correctly refused. The real-tree verdict belongs to the gate; this file's job is
# the two directions the gate cannot show by passing.

log_test "test-workflow-pr-environment"
D="$(mktemp -d)"
trap 'rm -rf "$D"' EXIT
mkdir -p "$D/mapping" "$D/scalar" "$D/real" "$D/prefix"
test_mapping_form_is_caught "$D/mapping"
test_scalar_form_is_caught "$D/scalar"
test_real_environments_pass "$D/real"
test_a_pr_prefixed_word_is_not_a_pr_environment "$D/prefix"
echo ""
log_pass "all tests passed"
