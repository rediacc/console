#!/bin/bash
# Both-ways test for .ci/scripts/quality/check-ci-job-aggregation.sh.
#
# The gate's promise: `ci-complete`, the single required status check for branch
# protection, can see every top-level job in ci.yml. A job outside its `needs:`
# list, or inside it but with no RESULT_* env var, can go red while the required
# check reports success and the merge button stays enabled.
#
# WHAT IT FOUND. ci.yml declares 24 top-level jobs; `ci-complete` aggregated 18.
# Five of the six gaps are structural (the aggregator itself, two jobs downstream
# of it, a job whose cancellation is routine, and build-renet whose failure
# reaches the verdict only by accident). The sixth, `check-release-state`, was a
# live hole: it fails, `stage-artifacts` skips because its `if:` requires that
# result to be `success` or `skipped`, and the soft tier reads a skip as green,
# so `CI Complete` passed while a release-state assertion failed on main.
#
# That hole is now CLOSED: check-release-state is in ci-complete's `needs:` and
# `env:`, and in SOFT_REQUIRED (soft, because it legitimately skips on every PR).
# The gate is what found it, and `test_real_tree_passes` at the end now asserts
# the repaired state so it cannot regress.
#
# WHY FIXTURES AND NOT THE REAL FILE. Every failure case below plants a synthetic
# defect. A validator that passes when given nothing is broken by definition, and
# the only way to know this one can FIRE is to make it fire, one gap shape at a
# time. Two cases at the end still read the REAL ci.yml, because a parser that
# only understands its own fixtures is a different kind of blind.
#
# Fixtures are written under a temp dir and driven through the gate's
# CI_JOB_AGGREGATION_WORKFLOW / CI_JOB_AGGREGATION_ASSERT seams, so no tracked
# file is ever mutated.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

GATE="$REPO_ROOT/.ci/scripts/quality/check-ci-job-aggregation.sh"
REAL_WORKFLOW="$REPO_ROOT/.github/workflows/ci.yml"

FIXTURE="$(mktemp -d)"
trap 'rm -rf "$FIXTURE"' EXIT

# The five jobs the gate exempts. A fixture must declare them, because the gate
# refuses an exemption that names no job (its liveness check).
EXEMPT_JOBS=(ci-complete finalize-release-sentinel pipeline-sentinel cancel-watchdog build-renet)
# Ordinary jobs. Enough of them, with the exempt five, to clear the gate's
# 10-job anti-vacuity floor.
PLAIN_JOBS=(initialize quality build-cli build-docker tests ops-tests stage-artifacts)

LAST_OUT=""

# scaffold <workflow-path> <assert-path> [--drop-need <job>] [--drop-result <job>]
#          [--drop-job <job>] [--phantom-need <name>] [--drop-tier <VAR>]
#          [--extra-tier <VAR>] [--few-jobs] [--no-needs] [--no-aggregator]
#
# Writes a well-formed pair, then applies exactly the requested defect. Building
# the healthy shape first and perturbing it is what keeps each failure case
# attributable to one cause.
scaffold() {
    local workflow="$1" assert="$2"
    shift 2
    local drop_need="" drop_result="" drop_job="" phantom_need="" drop_tier="" extra_tier=""
    local few_jobs=false no_needs=false no_aggregator=false
    while (($# > 0)); do
        case "$1" in
            --drop-need) drop_need="$2" && shift 2 ;;
            --drop-result) drop_result="$2" && shift 2 ;;
            --drop-job) drop_job="$2" && shift 2 ;;
            --phantom-need) phantom_need="$2" && shift 2 ;;
            --drop-tier) drop_tier="$2" && shift 2 ;;
            --extra-tier) extra_tier="$2" && shift 2 ;;
            --few-jobs) few_jobs=true && shift ;;
            --no-needs) no_needs=true && shift ;;
            --no-aggregator) no_aggregator=true && shift ;;
            *) log_fail "scaffold: unknown option $1" ;;
        esac
    done

    local -a all=() plain=()
    if [[ "$few_jobs" == "true" ]]; then
        plain=(initialize quality)
    else
        plain=("${PLAIN_JOBS[@]}")
    fi
    local j
    for j in "${EXEMPT_JOBS[@]}" "${plain[@]}"; do
        [[ "$j" == "$drop_job" ]] && continue
        [[ "$j" == "ci-complete" && "$no_aggregator" == "true" ]] && continue
        all+=("$j")
    done

    # The aggregated set: every plain job, minus the one this case drops.
    local -a aggregated=()
    for j in "${plain[@]}"; do
        [[ "$j" == "$drop_job" ]] && continue
        [[ "$j" == "$drop_need" ]] && continue
        aggregated+=("$j")
    done

    {
        echo "name: Fixture CI"
        echo "on:"
        echo "  push:"
        echo "    branches: [main]"
        echo "permissions:"
        echo "  contents: read"
        echo "jobs:"
        for j in "${all[@]}"; do
            echo "  ${j}:"
            echo "    name: ${j}"
            echo "    runs-on: ubuntu-latest"
            if [[ "$j" == "ci-complete" ]]; then
                if [[ "$no_needs" != "true" ]]; then
                    local needs_list="${aggregated[*]}"
                    [[ -n "$phantom_need" ]] && needs_list="$needs_list $phantom_need"
                    echo "    needs: [${needs_list// /, }]"
                fi
                echo "    steps:"
                echo "      - run: .ci/scripts/ci/assert-ci-complete.sh"
                echo "        env:"
                local k
                for k in "${aggregated[@]}"; do
                    [[ "$k" == "$drop_result" ]] && continue
                    local var
                    var="RESULT_$(printf '%s' "$k" | tr '[:lower:]-' '[:upper:]_')"
                    echo "          ${var}: \${{ needs.${k}.result }}"
                done
            else
                echo "    steps:"
                echo "      - run: echo ${j}"
            fi
        done
    } >"$workflow"

    # The tier halves, mirroring assert-ci-complete.sh's real shape (one
    # single-line array, one multi-line array, so the parser is exercised on
    # both forms).
    {
        echo "#!/bin/bash"
        echo "set -euo pipefail"
        local -a hard=() soft=()
        local k var
        for k in "${aggregated[@]}"; do
            [[ "$k" == "$drop_result" ]] && continue
            var="$(printf '%s' "$k" | tr '[:lower:]-' '[:upper:]_')"
            [[ "$var" == "$drop_tier" ]] && continue
            if [[ "$k" == "initialize" || "$k" == "build-cli" ]]; then
                hard+=("$var")
            else
                soft+=("$var")
            fi
        done
        echo "HARD_REQUIRED=(${hard[*]})"
        echo "SOFT_REQUIRED=("
        for var in "${soft[@]}"; do echo "    $var"; done
        [[ -n "$extra_tier" ]] && echo "    ${extra_tier#RESULT_}"
        echo ")"
    } >"$assert"
}

# run_gate <workflow> <assert>
#
# Sets LAST_RC and LAST_OUT. Deliberately NOT called inside $(...): command
# substitution runs in a subshell, so LAST_OUT would never reach the caller and
# every assert_contains on it would compare against an empty string -- passing
# or failing for reasons unrelated to the gate.
run_gate() {
    LAST_RC=0
    LAST_OUT="$(CI_JOB_AGGREGATION_WORKFLOW="$1" CI_JOB_AGGREGATION_ASSERT="$2" \
        bash "$GATE" 2>&1)" || LAST_RC=$?
}

# ---------------------------------------------------------------------------

test_healthy_pair_passes() {
    # Baseline. Without this, every failure case below could be passing for the
    # wrong reason (a fixture the parser cannot read fails everything).
    scaffold "$FIXTURE/ok.yml" "$FIXTURE/ok.sh"
    run_gate "$FIXTURE/ok.yml" "$FIXTURE/ok.sh"
    assert_eq "$LAST_RC" "0" "a fully wired workflow must pass: $LAST_OUT"
    assert_contains "$LAST_OUT" "every non-exempt ci.yml job is aggregated" "and say so"
    log_pass "a fully wired workflow and tier list passes"
}

test_job_missing_from_needs_fails() {
    # THE PRIMARY DEFECT, planted. This is the shape check-release-state has in
    # the real ci.yml: a declared job the required check never depends on.
    scaffold "$FIXTURE/n.yml" "$FIXTURE/n.sh" --drop-need ops-tests
    run_gate "$FIXTURE/n.yml" "$FIXTURE/n.sh"
    assert_eq "$LAST_RC" "1" "a job outside ci-complete's needs must fail the gate"
    assert_contains "$LAST_OUT" "NOT in ci-complete's needs" "with the needs diagnostic"
    assert_contains "$LAST_OUT" "ops-tests" "naming the job"
    log_pass "a job missing from the aggregator's needs fails and is named"
}

test_job_missing_result_env_fails() {
    # The second half of the wire. A job can be in needs and still be invisible:
    # assert-ci-complete.sh only reads what the env block passes it.
    scaffold "$FIXTURE/r.yml" "$FIXTURE/r.sh" --drop-result tests
    run_gate "$FIXTURE/r.yml" "$FIXTURE/r.sh"
    assert_eq "$LAST_RC" "1" "a job with no RESULT_ env var must fail the gate"
    assert_contains "$LAST_OUT" "no RESULT_* env var" "with the env diagnostic"
    assert_contains "$LAST_OUT" "RESULT_TESTS" "naming the missing variable"
    log_pass "a job in needs but absent from the env block fails and is named"
}

test_phantom_need_fails() {
    # The reverse break: a needs entry naming nothing. GitHub rejects the whole
    # workflow at parse time, so catching it locally is strictly cheaper.
    scaffold "$FIXTURE/p.yml" "$FIXTURE/p.sh" --phantom-need does-not-exist
    run_gate "$FIXTURE/p.yml" "$FIXTURE/p.sh"
    assert_eq "$LAST_RC" "1" "a needs entry naming no job must fail"
    assert_contains "$LAST_OUT" "naming no such job" "with the phantom diagnostic"
    assert_contains "$LAST_OUT" "does-not-exist" "naming the phantom"
    log_pass "a needs entry naming no job fails and is named"
}

test_untiered_result_var_fails() {
    # A var that is passed and then read by nobody. assert-ci-complete.sh does
    # not error on an extra env var, so this is silent by construction.
    scaffold "$FIXTURE/u.yml" "$FIXTURE/u.sh" --drop-tier OPS_TESTS
    run_gate "$FIXTURE/u.yml" "$FIXTURE/u.sh"
    assert_eq "$LAST_RC" "1" "a RESULT_ var in no tier must fail"
    assert_contains "$LAST_OUT" "neither HARD_REQUIRED nor SOFT_REQUIRED" "with the tier diagnostic"
    assert_contains "$LAST_OUT" "RESULT_OPS_TESTS" "naming the untiered variable"
    log_pass "a RESULT_ var belonging to no tier fails and is named"
}

test_orphan_tier_member_fails() {
    # The other direction of the same wire. assert-ci-complete.sh treats an
    # unset var as a failure, so this makes EVERY run red until someone reads
    # the tier list -- loud, but expensive to diagnose in CI rather than here.
    scaffold "$FIXTURE/o.yml" "$FIXTURE/o.sh" --extra-tier RESULT_GHOST_JOB
    run_gate "$FIXTURE/o.yml" "$FIXTURE/o.sh"
    assert_eq "$LAST_RC" "1" "a tier member nobody passes must fail"
    assert_contains "$LAST_OUT" "never passes" "with the orphan-tier diagnostic"
    assert_contains "$LAST_OUT" "RESULT_GHOST_JOB" "naming the orphan"
    log_pass "a tier member with no matching env var fails and is named"
}

test_dead_exemption_fails() {
    # Liveness. A BLOCKER proves a reason existed; it cannot prove it is still
    # true. Deleting build-renet from the workflow leaves its exemption behind,
    # which is the shape that left 101 electron suppressions in this repo.
    scaffold "$FIXTURE/d.yml" "$FIXTURE/d.sh" --drop-job build-renet
    run_gate "$FIXTURE/d.yml" "$FIXTURE/d.sh"
    assert_eq "$LAST_RC" "1" "an exemption for a deleted job must fail"
    assert_contains "$LAST_OUT" "naming no such job" "with the dead-exemption diagnostic"
    assert_contains "$LAST_OUT" "build-renet" "naming the stale entry"
    log_pass "an exemption whose job no longer exists fails and is named"
}

test_exempt_job_is_not_required_to_be_aggregated() {
    # The exemption must actually do something. In the healthy fixture none of
    # the five exempt jobs is in needs or env, and the gate passes -- so the
    # failure cases above are the exemption being absent, not the check being
    # off.
    scaffold "$FIXTURE/e.yml" "$FIXTURE/e.sh"
    assert_not_contains "$(cat "$FIXTURE/e.yml")" "RESULT_BUILD_RENET" \
        "the fixture must genuinely leave build-renet unaggregated"
    run_gate "$FIXTURE/e.yml" "$FIXTURE/e.sh"
    assert_eq "$LAST_RC" "0" "an exempt job left unaggregated must still pass"
    log_pass "the exempt set suppresses exactly the jobs it names"
}

test_low_effort_blocker_is_rejected() {
    # PROVE THE INSTRUMENT. The exempt block claims to be BLOCKER-validated. A
    # copy of the gate with one reason replaced by a banned phrase must fail on
    # the reason, not sail through to the job checks. Without this the
    # validation could be decorative and nothing would say so.
    # The mutant resolves its libs from its own path, so mirror the .ci layout
    # rather than dropping a copy anywhere. No tracked file is written.
    local mutant="$FIXTURE/.ci/scripts/quality/mutant.sh"
    mkdir -p "$FIXTURE/.ci/scripts/quality" "$FIXTURE/.ci/scripts/lib"
    cp "$REPO_ROOT"/.ci/scripts/lib/*.sh "$FIXTURE/.ci/scripts/lib/"
    sed 's/^# BLOCKER: this IS the aggregator.*$/# BLOCKER: tbd/' "$GATE" >"$mutant"
    assert_contains "$(cat "$mutant")" "# BLOCKER: tbd" "the mutation must have applied"
    scaffold "$FIXTURE/b.yml" "$FIXTURE/b.assert.sh"
    local rc=0
    local out
    out="$(CI_JOB_AGGREGATION_WORKFLOW="$FIXTURE/b.yml" \
        CI_JOB_AGGREGATION_ASSERT="$FIXTURE/b.assert.sh" bash "$mutant" 2>&1)" || rc=$?
    assert_eq "$rc" "1" "a low-effort BLOCKER must fail the gate: $out"
    assert_contains "$out" "low-effort placeholder" "with the validator's own diagnostic"
    log_pass "a banned-phrase BLOCKER in the exempt set is rejected"
}

test_too_few_jobs_is_blind_not_green() {
    # Anti-vacuity. A parser that stops understanding the layout returns a tiny
    # job set, and every check over it passes. That must read as blind, never as
    # "all wired".
    scaffold "$FIXTURE/f.yml" "$FIXTURE/f.sh" --few-jobs
    run_gate "$FIXTURE/f.yml" "$FIXTURE/f.sh"
    assert_eq "$LAST_RC" "1" "a below-floor job count must fail"
    assert_contains "$LAST_OUT" "this gate is blind" "and say it is blind"
    assert_not_contains "$LAST_OUT" "every non-exempt ci.yml job is aggregated" \
        "it must NOT claim everything is wired"
    log_pass "a below-floor job parse reports blindness instead of success"
}

test_aggregator_without_needs_is_blind_not_green() {
    # The degenerate case the primary check cannot distinguish on its own: with
    # zero needs entries, "every job is missing" is true but the useful verdict
    # is that the aggregator aggregates nothing.
    scaffold "$FIXTURE/nn.yml" "$FIXTURE/nn.sh" --no-needs
    run_gate "$FIXTURE/nn.yml" "$FIXTURE/nn.sh"
    assert_eq "$LAST_RC" "1" "an aggregator with no needs must fail"
    assert_contains "$LAST_OUT" "aggregates nothing" "with the empty-needs diagnostic"
    log_pass "an aggregator with an empty needs list reports that it aggregates nothing"
}

test_missing_aggregator_is_named() {
    # A rename of the required status check must break here, loudly, rather than
    # matching an empty block and asserting over nothing.
    scaffold "$FIXTURE/na.yml" "$FIXTURE/na.sh" --no-aggregator
    run_gate "$FIXTURE/na.yml" "$FIXTURE/na.sh"
    assert_eq "$LAST_RC" "1" "a missing aggregator job must fail"
    assert_contains "$LAST_OUT" "No job named 'ci-complete'" "naming what is gone"
    log_pass "a missing aggregator job is reported by name"
}

test_missing_input_file_is_named() {
    # An absent input used to be the classic silent pass: no file, no findings,
    # green. Both inputs are guarded.
    local rc=0
    local out
    out="$(CI_JOB_AGGREGATION_WORKFLOW="$FIXTURE/nope.yml" \
        CI_JOB_AGGREGATION_ASSERT="$FIXTURE/ok.sh" bash "$GATE" 2>&1)" || rc=$?
    assert_eq "$rc" "1" "a missing workflow must fail"
    assert_contains "$out" "input not found" "with the missing-input diagnostic"
    log_pass "a missing input fails instead of asserting over nothing"
}

test_parser_understands_the_real_workflow() {
    # A parser that only reads its own fixtures is a second kind of blind. This
    # runs against the REAL ci.yml and pins that the job set it extracts is the
    # real one -- 24 jobs at the time of writing, floored at 20 so an ordinary
    # job addition or removal does not fail this test for no reason.
    local count
    count="$(CI_JOB_AGGREGATION_WORKFLOW="$REAL_WORKFLOW" bash -c '
        awk "
            /^jobs:[[:space:]]*\$/ { in_jobs = 1; next }
            in_jobs && /^[^[:space:]#]/ { in_jobs = 0 }
            in_jobs && /^  [A-Za-z0-9_-]+:[[:space:]]*\$/ { print }
        " "$CI_JOB_AGGREGATION_WORKFLOW"' | wc -l)"
    if ((count < 20)); then
        log_fail "the real ci.yml parsed to only $count job(s); the gate's parser is blind to the live layout"
    fi
    # And the exempt names must all be live jobs in it, or the gate's own
    # liveness check would be the thing reporting.
    local j
    for j in "${EXEMPT_JOBS[@]}"; do
        assert_contains "$(grep -c "^  ${j}:" "$REAL_WORKFLOW")" "1" \
            "exempt job '$j' must exist exactly once in the real ci.yml"
    done
    log_pass "the parser reads the real ci.yml ($count jobs) and every exempt name is a live job in it"
}

test_real_tree_passes() {
    # This case replaces one that asserted the gate still REPORTED the
    # check-release-state gap. That gap was the finding this gate was built for,
    # and it was real: check-release-state was a declared job that ci-complete
    # did not aggregate, and because stage-artifacts requires its result to be
    # `success` OR `skipped`, a FAILURE made stage-artifacts skip, which the soft
    # tier reads as green. `CI Complete` could therefore pass while a
    # release-state assertion failed on main.
    #
    # It is now wired in (ci.yml's ci-complete `needs:` and `env:`, plus
    # SOFT_REQUIRED in assert-ci-complete.sh), so the durable assertion is the
    # inverse: the real tree must PASS, and must keep passing. A future job added
    # to ci.yml without being aggregated fails here as well as in CI.
    local rc=0
    local out
    out="$(bash "$GATE" 2>&1)" || rc=$?
    if ((rc != 0)); then
        log_fail "the real ci.yml no longer satisfies the aggregation invariant: $out"
    fi
    assert_contains "$out" "every non-exempt ci.yml job is aggregated" \
        "the gate must affirm the real tree, not merely stay silent"
    log_pass "the real ci.yml satisfies the aggregation invariant"
}

log_test "test-ci-job-aggregation"
test_healthy_pair_passes
test_job_missing_from_needs_fails
test_job_missing_result_env_fails
test_phantom_need_fails
test_untiered_result_var_fails
test_orphan_tier_member_fails
test_dead_exemption_fails
test_exempt_job_is_not_required_to_be_aggregated
test_low_effort_blocker_is_rejected
test_too_few_jobs_is_blind_not_green
test_aggregator_without_needs_is_blind_not_green
test_missing_aggregator_is_named
test_missing_input_file_is_named
test_parser_understands_the_real_workflow
test_real_tree_passes
echo ""
log_pass "all tests passed"
