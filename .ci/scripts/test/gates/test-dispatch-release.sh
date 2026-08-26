#!/bin/bash
# Both-ways test for .ci/scripts/ci/dispatch-release.sh -- the step that decides
# whether a merge to main earns a release at all.
#
# WHY THIS CLASS NEEDS A GATE. The decision is invisible when it is wrong in the
# direction that matters. A release that should not have happened is noticed
# immediately (a tag appears); a release that was silently WITHHELD looks like
# nothing at all, and stays looking like nothing until somebody wonders why the
# version stream stopped. So the fail-open paths are tested as carefully as the
# skip: an API failure, an unresolvable commit, and a mixed PR set must all end
# in a dispatch, and each of those is asserted here rather than reasoned about.
#
# The dispatch itself is driven through DISPATCH_RELEASE_DRY_RUN so no test can
# reach `gh workflow run`, and the GitHub API is a routing fake serving per-SHA
# fixtures -- the same shape test-detect-bump-type.sh uses against the same
# endpoint, because both scripts resolve a commit to its merged PRs the same way.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

UNDER_TEST="$REPO_ROOT/.ci/scripts/ci/dispatch-release.sh"
CI_WORKFLOW="$REPO_ROOT/.github/workflows/ci.yml"
LABELS_FILE="$REPO_ROOT/.github/labels.yml"
SHA="abc1234def5678901234567890123456789abcde"

LAST_OUT=""
LAST_RC=0

[ -x "$UNDER_TEST" ] || log_fail "$UNDER_TEST is not executable"

write_fake_gh() {
    local dir="$1"
    mkdir -p "$dir/bin"
    cat >"$dir/bin/gh" <<'FAKE'
#!/bin/bash
# Routing fake for `gh api repos/<repo>/commits/<sha>/pulls`, applying the
# caller's own --jq so the real extraction runs. `gh workflow run` is NOT
# routed: the tests drive the dry-run seam instead, so a bug that reached the
# real dispatch would fail loudly here rather than being quietly served.
set -uo pipefail
# Argv recorder. Asserting that a call was NOT made is only meaningful if the
# recorder proves calls land in it at all, so the tests check both directions
# against this file.
if [ -n "${GH_CALLS:-}" ]; then
    printf '%s\n' "$*" >>"$GH_CALLS"
fi
if [ -n "${GH_FAIL_ALL:-}" ]; then
    echo "fake gh: forced API failure" >&2
    exit 1
fi
path=""
jqexpr=""
args=("$@")
n=${#args[@]}
i=0
while [ "$i" -lt "$n" ]; do
    a="${args[$i]}"
    case "$a" in
        api) ;;
        --jq)
            i=$((i + 1))
            jqexpr="${args[$i]}"
            ;;
        --paginate | --silent) ;;
        -*) ;;
        *)
            if [ -z "$path" ]; then path="$a"; fi
            ;;
    esac
    i=$((i + 1))
done
case "$path" in
    */commits/*/pulls)
        sha="${path#*/commits/}"
        sha="${sha%/pulls}"
        file="$GH_FIXTURES/pulls-$sha.json"
        [ -f "$file" ] || file="$GH_FIXTURES/pulls-default.json"
        [ -f "$file" ] || { echo "fake gh: no fixture for $sha" >&2; exit 1; }
        if [ -n "$jqexpr" ]; then jq -r "$jqexpr" "$file"; else cat "$file"; fi
        ;;
    *)
        echo "fake gh: unrouted call: $*" >&2
        exit 3
        ;;
esac
FAKE
    chmod +x "$dir/bin/gh"
}

# merged_pr <number> <comma-separated-labels>
merged_pr() {
    jq -nc --argjson n "$1" --arg l "$2" \
        '{number: $n, merged_at: "2026-08-01T00:00:00Z", state: "closed",
          labels: ($l | if . == "" then [] else split(",") end | map({name: .}))}'
}

# open_pr <number> <labels> -- an UNMERGED PR, which must never be consulted:
# its label describes a release that has not happened.
open_pr() {
    jq -nc --argjson n "$1" --arg l "$2" \
        '{number: $n, merged_at: null, state: "open",
          labels: ($l | if . == "" then [] else split(",") end | map({name: .}))}'
}

setup() {
    local t="$1"
    mkdir -p "$t/fixtures"
    write_fake_gh "$t"
    echo '[]' >"$t/fixtures/pulls-default.json"
    rm -f "$t/github-output" "$t/gh-calls.log"
}

# pulls_for <TEMP> <sha> <pr-json...>
pulls_for() {
    local t="$1" sha="$2"
    shift 2
    printf '%s\n' "$@" | jq -s '.' >"$t/fixtures/pulls-$sha.json"
}

# run_dispatch <TEMP> [KEY=VALUE ...] [-- <script-arg> ...]
#
# Everything before `--` is an environment override; everything after it is
# passed to the script itself, which is how the mode flags get driven.
run_dispatch() {
    local t="$1"
    shift
    local envs=() args=()
    while [[ $# -gt 0 ]]; do
        if [[ "$1" == "--" ]]; then
            shift
            args=("$@")
            break
        fi
        envs+=("$1")
        shift
    done
    local rc=0
    LAST_OUT="$(env \
        PATH="$t/bin:$PATH" \
        GH_FIXTURES="$t/fixtures" \
        GH_CALLS="$t/gh-calls.log" \
        GH_TOKEN=fake \
        GITHUB_REPOSITORY=rediacc/console \
        GITHUB_SHA="$SHA" \
        GITHUB_RUN_ID=999 \
        GITHUB_OUTPUT="$t/github-output" \
        DISPATCH_RELEASE_DRY_RUN=1 \
        NO_COLOR=1 \
        ${envs[@]+"${envs[@]}"} \
        bash "$UNDER_TEST" ${args[@]+"${args[@]}"} 2>&1)" || rc=$?
    LAST_RC="$rc"
    return 0
}

# The $GITHUB_OUTPUT this run produced (empty string when the script wrote none).
step_output() {
    local t="$1"
    [[ -f "$t/github-output" ]] && cat "$t/github-output" || true
}

gh_calls() {
    local t="$1"
    [[ -f "$t/gh-calls.log" ]] && cat "$t/gh-calls.log" || true
}

assert_dispatched() {
    assert_contains "$LAST_OUT" "DRY-RUN: gh workflow run cd-v2.yml" "$1"
    assert_contains "$LAST_OUT" "ci_run_id=999" "the run id is passed through"
}

assert_not_dispatched() {
    assert_not_contains "$LAST_OUT" "DRY-RUN: gh workflow run" "$1"
}

# ---------------------------------------------------------------------------

test_bump_none_skips_the_release() {
    # THE FEATURE. A merged PR labelled bump-none earns no release at all.
    local t="$1"
    setup "$t"
    pulls_for "$t" "$SHA" "$(merged_pr 561 bump-none)"
    run_dispatch "$t"
    assert_exit_code 0 "$LAST_RC" "the decision must never fail the sentinel job"
    assert_not_dispatched "a bump-none PR must NOT dispatch cd-v2"
    assert_contains "$LAST_OUT" "::notice title=Release skipped::" "it announces the skip as an annotation"
    assert_contains "$LAST_OUT" "#561" "naming the PR that carried the label"
    assert_contains "$LAST_OUT" "no tag, no GitHub release, no R2 upload, no edge deploy" \
        "and stating exactly what was skipped"
    assert_contains "$LAST_OUT" "ship with the next release-worthy merge" \
        "and that the commits are not lost"
    log_pass "FIRE: bump-none on the merged PR => release skipped, with a notice naming the PR"
}

test_an_unlabelled_pr_releases() {
    # CONTROL: same shape, no label. If this dispatched either way the case
    # above would prove nothing.
    local t="$1"
    setup "$t"
    pulls_for "$t" "$SHA" "$(merged_pr 561 "")"
    run_dispatch "$t"
    assert_exit_code 0 "$LAST_RC" "a normal release path exits clean"
    assert_dispatched "an unlabelled PR must dispatch cd-v2"
    assert_not_contains "$LAST_OUT" "Release skipped" "and say nothing about skipping"
    log_pass "CONTROL: no bump-none => the release dispatches as before"
}

test_the_rest_of_the_bump_family_still_releases() {
    # bump-none is the only member that subtracts. bump-minor and bump-major
    # size a release; they must never suppress one.
    local t="$1" label
    for label in bump-minor bump-major; do
        setup "$t"
        pulls_for "$t" "$SHA" "$(merged_pr 561 "$label")"
        run_dispatch "$t"
        assert_dispatched "$label must still dispatch cd-v2"
    done
    log_pass "CONTROL: bump-minor and bump-major size the release, they do not skip it"
}

test_an_unmerged_pr_is_never_consulted() {
    # An OPEN PR can also contain the commit, and its label describes a release
    # that has not happened. Reading it would let an in-flight PR suppress
    # somebody else's release.
    local t="$1"
    setup "$t"
    pulls_for "$t" "$SHA" "$(open_pr 900 bump-none)"
    run_dispatch "$t"
    assert_dispatched "an unmerged bump-none PR must not suppress the release"
    log_pass "CONTROL: an OPEN bump-none PR is ignored; only merged PRs decide"
}

test_a_mixed_pr_set_releases() {
    # The dangerous direction. If the commit is in a bump-none PR AND a
    # release-worthy one, withholding would lose a real release. Fail toward
    # releasing, and say why in the log.
    local t="$1"
    setup "$t"
    pulls_for "$t" "$SHA" "$(merged_pr 561 bump-none)" "$(merged_pr 562 "")"
    run_dispatch "$t"
    assert_dispatched "a mixed PR set must still release"
    assert_contains "$LAST_OUT" "#562" "the release-worthy PR is named"
    assert_contains "$LAST_OUT" "releasing" "and the reason is logged rather than left implicit"
    log_pass "CONTROL: bump-none plus a release-worthy PR on one commit => releases"
}

test_a_lookup_failure_fails_open() {
    # FAIL OPEN. A flaky API must never silently kill a release.
    local t="$1"
    setup "$t"
    run_dispatch "$t" GH_FAIL_ALL=1
    assert_exit_code 0 "$LAST_RC" "a lookup failure must not fail the job either"
    assert_dispatched "an unresolvable PR must still dispatch"
    assert_contains "$LAST_OUT" "PR lookup failed" "and say the lookup failed"
    assert_contains "$LAST_OUT" "rather than risking a silently withheld release" \
        "naming the asymmetry that decides the direction"
    log_pass "FAIL OPEN: a failed PR lookup releases anyway, loudly"
}

test_a_commit_with_no_pr_releases() {
    # A direct push to main, or a commit the API knows no PR for.
    local t="$1"
    setup "$t"
    run_dispatch "$t"
    assert_dispatched "a commit with no merged PR must dispatch"
    assert_contains "$LAST_OUT" "no merged PR contains" "and say so"
    log_pass "FAIL OPEN: a commit with no merged PR releases as before"
}

test_the_label_is_declared_and_managed() {
    # The script keys on a literal label name. If labels.yml stopped declaring
    # it, check:ci-label-inventory would fail the repo and this script would key
    # on a label nothing can apply.
    local skip_label
    skip_label="$(sed -n "s/^SKIP_LABEL='\(.*\)'$/\1/p" "$UNDER_TEST")"
    assert_eq "$skip_label" "bump-none" "the skip label is parseable out of the script"
    grep -qE "^- name: ${skip_label}$" "$LABELS_FILE" ||
        log_fail "the script skips on '$skip_label', which .github/labels.yml does not declare"
    grep -q "bump-none" "$REPO_ROOT/.ci/scripts/review/claude-review-gate.sh" ||
        log_fail "nothing in the review applier can apply '$skip_label', so the skip could never fire"
    log_pass "the skip label is declared in labels.yml and appliable by the review"
}

# ---------------------------------------------------------------------------
# MODES
# ---------------------------------------------------------------------------

test_decide_only_signals_the_skip() {
    # THE FIX. The CI job has to know the answer BEFORE it seals the version, so
    # --decide-only answers the question and touches nothing.
    local t="$1"
    setup "$t"
    pulls_for "$t" "$SHA" "$(merged_pr 570 bump-none)"
    run_dispatch "$t" -- --decide-only
    assert_exit_code 0 "$LAST_RC" "the decide step must never fail the sentinel job"
    assert_not_dispatched "--decide-only must not dispatch, ever"
    assert_contains "$(step_output "$t")" "skip_release=true" \
        "a bump-none merge must set the output the seal and dispatch steps are guarded on"
    assert_contains "$LAST_OUT" "decision: skip" "and say so on stdout"
    assert_contains "$LAST_OUT" "::notice title=Release skipped::" \
        "the skip is still announced -- this is now the ONLY step that runs the decision"
    log_pass "FIRE: --decide-only + bump-none => skip_release=true, nothing dispatched"
}

test_decide_only_stays_silent_for_a_release() {
    # CONTROL for the case above. If the output file got skip_release=true here
    # too, the assertion above would prove nothing -- and every release in the
    # repo would silently stop.
    local t="$1"
    setup "$t"
    pulls_for "$t" "$SHA" "$(merged_pr 570 "")"
    run_dispatch "$t" -- --decide-only
    assert_exit_code 0 "$LAST_RC" "the decide step exits clean on the release path too"
    assert_not_contains "$(step_output "$t")" "skip_release" \
        "an unlabelled PR must leave the output EMPTY so the != 'true' guards let both steps run"
    assert_contains "$LAST_OUT" "decision: release" "and say release on stdout"
    log_pass "CONTROL: --decide-only on an unlabelled PR emits no skip signal at all"
}

test_decide_only_fail_open_paths_never_signal_skip() {
    # THE DANGEROUS DIRECTION, three ways. Each of these is a path the script
    # takes when it could NOT answer the question confidently, and every one of
    # them must release. If any leaked skip_release=true, the guarded seal and
    # dispatch steps would both skip and the release would vanish with a green
    # job -- which is exactly the failure mode the guard polarity is built for.
    local t="$1"

    setup "$t"
    run_dispatch "$t" GH_FAIL_ALL=1 -- --decide-only
    assert_exit_code 0 "$LAST_RC" "a lookup failure must not fail the decide step"
    assert_not_contains "$(step_output "$t")" "skip_release" "a failed PR lookup must not withhold the release"
    assert_contains "$LAST_OUT" "decision: release" "it decides to release"
    assert_contains "$LAST_OUT" "PR lookup failed" "and still says the lookup failed"

    setup "$t"
    run_dispatch "$t" -- --decide-only
    assert_not_contains "$(step_output "$t")" "skip_release" "a commit with no merged PR must not withhold the release"
    assert_contains "$LAST_OUT" "decision: release" "it decides to release"

    setup "$t"
    pulls_for "$t" "$SHA" "$(merged_pr 570 bump-none)" "$(merged_pr 571 "")"
    run_dispatch "$t" -- --decide-only
    assert_not_contains "$(step_output "$t")" "skip_release" "a mixed PR set must not withhold the release"
    assert_contains "$LAST_OUT" "decision: release" "it decides to release"

    # CONTROL, in this same function: the recorder and the output file DO work.
    # Without this, all three assertions above would also pass against a script
    # that never wrote $GITHUB_OUTPUT under any circumstances.
    setup "$t"
    pulls_for "$t" "$SHA" "$(merged_pr 570 bump-none)"
    run_dispatch "$t" -- --decide-only
    assert_contains "$(step_output "$t")" "skip_release=true" \
        "CONTROL: the same harness DOES capture a skip signal when one is owed"
    log_pass "FAIL OPEN: all three unconfident paths emit no skip signal (control: bump-none does)"
}

test_dispatch_only_asks_nothing_and_dispatches() {
    # The decision was already made by the decide step. Asking again would
    # double the API calls and could answer differently if a label moved in
    # between -- and would re-introduce a second place the decision is made.
    local t="$1"
    setup "$t"
    pulls_for "$t" "$SHA" "$(merged_pr 570 bump-none)"
    run_dispatch "$t" -- --dispatch-only
    assert_exit_code 0 "$LAST_RC" "--dispatch-only exits clean"
    assert_dispatched "--dispatch-only dispatches unconditionally"
    assert_not_contains "$(gh_calls "$t")" "commits/" \
        "and makes NO commits/<sha>/pulls lookup, even with a bump-none fixture sitting right there"
    assert_not_contains "$(step_output "$t")" "skip_release" "it writes no step output"

    # CONTROL: the recorder is not simply always empty. The same fixture under
    # --decide-only must land a call in it.
    setup "$t"
    pulls_for "$t" "$SHA" "$(merged_pr 570 bump-none)"
    run_dispatch "$t" -- --decide-only
    assert_contains "$(gh_calls "$t")" "commits/${SHA}/pulls" \
        "CONTROL: --decide-only DOES record the lookup, so the absence above is real"
    log_pass "--dispatch-only dispatches with zero API lookups (control: --decide-only records one)"
}

test_dispatch_only_survives_a_dead_api() {
    # CONTROL for the fail-open doctrine at the mode boundary: if --dispatch-only
    # ever grew a lookup, a dead API would show up here as a non-dispatch.
    local t="$1"
    setup "$t"
    run_dispatch "$t" GH_FAIL_ALL=1 -- --dispatch-only
    assert_exit_code 0 "$LAST_RC" "a dead API cannot fail the dispatch step"
    assert_dispatched "--dispatch-only dispatches even when every gh call would fail"
    log_pass "CONTROL: --dispatch-only with GH_FAIL_ALL=1 still dispatches"
}

test_an_unknown_flag_is_a_wiring_bug() {
    # A typo'd flag must not be silently treated as "no flag" -- that would
    # quietly restore the old lookup-and-dispatch behaviour in the seal step.
    local t="$1"
    setup "$t"
    run_dispatch "$t" -- --decide-onlyy
    assert_exit_code 2 "$LAST_RC" "an unknown mode flag fails loudly rather than defaulting"
    assert_not_dispatched "and dispatches nothing"
    log_pass "an unrecognised flag exits 2 instead of falling through to the legacy path"
}

# ---------------------------------------------------------------------------
# ci.yml WIRING
#
# The two predicates below take JOB TEXT rather than reading ci.yml themselves,
# which is the whole reason a control is possible: each is run against the real
# job AND against a synthetic block carrying the exact defect, and the synthetic
# one must be reported. A predicate that has never been shown to fire is a
# predicate that proves nothing.
# ---------------------------------------------------------------------------

# One line per ordering violation; empty output means clean.
ordering_violations() {
    local job="$1" decide_line seal_line
    decide_line="$(printf '%s\n' "$job" | grep -n -- '--decide-only' | cut -d: -f1 | head -1 || true)"
    seal_line="$(printf '%s\n' "$job" | grep -n 'write-release-sentinel.sh' | cut -d: -f1 | head -1 || true)"
    if [[ -z "$decide_line" ]]; then
        # NO DECIDE STEP HERE IS NOW CORRECT, and that is the 2026-08-26 fix
        # rather than a regression. The decision moved to initialize.sh (step 6b)
        # because this job `needs: ci-complete` and is therefore DOWNSTREAM of
        # stage-artifacts, the job that writes R2 -- so deciding here arrived
        # after the uploader had already advanced the channel pointer.
        #
        # The ordering invariant still holds, more strongly: a decision made in
        # an upstream job cannot follow this job's seal. But "absent" must not be
        # confused with "unguarded", so absence is only acceptable when the job
        # demonstrably READS the upstream decision.
        if printf '%s\n' "$job" | grep -q 'needs.initialize.outputs.skip_release'; then
            return 0
        fi
        echo "no --decide-only step AND no read of needs.initialize.outputs.skip_release: nothing decides"
        return 0
    fi
    if [[ -z "$seal_line" ]]; then
        echo "no write-release-sentinel.sh step in the job at all"
        return 0
    fi
    if [[ "$decide_line" -ge "$seal_line" ]]; then
        echo "the release decision (line $decide_line) does not precede the seal (line $seal_line)"
    fi
}

# One line per polarity violation; empty output means clean.
polarity_violations() {
    local job="$1" inverted wrong
    inverted="$(printf '%s\n' "$job" | grep -c "skip_release != 'true'" || true)"
    wrong="$(printf '%s\n' "$job" | grep -c "skip_release == 'true'" || true)"
    if [[ "$wrong" -ne 0 ]]; then
        echo "$wrong guard(s) use == 'true'; a cancelled or OOM-killed decide step would then skip BOTH the seal and the dispatch on a green job"
    fi
    if [[ "$inverted" -ne 2 ]]; then
        echo "expected exactly 2 steps guarded with != 'true' (the seal and the dispatch), found $inverted"
    fi
}

finalize_job_text() {
    awk '/^  finalize-release-sentinel:/{f=1} f&&/^  [a-z][a-z0-9-]*:$/&&!/^  finalize-release-sentinel:/{exit} f' "$CI_WORKFLOW"
}

test_ci_yml_wires_the_script() {
    local wf job
    wf="$(cat "$CI_WORKFLOW")"
    assert_contains "$wf" "dispatch-release.sh" "ci.yml calls the script"
    job="$(finalize_job_text)"
    assert_contains "$job" ".ci/scripts/ci/dispatch-release.sh" "from the finalize-release-sentinel job"
    assert_not_contains "$job" "gh workflow run cd-v2.yml" \
        "and the inline dispatch is gone, so there is only ONE place the decision can be made"
    assert_contains "$job" "GH_TOKEN" "the script still gets its token"
    # THE DECISION MOVED OUT OF THIS JOB (2026-08-26), and that is the fix, not a
    # regression. It used to live here as a step with `id: release-decision`, but
    # this job `needs: ci-complete` and is therefore DOWNSTREAM of stage-artifacts
    # -- the job that writes R2 -- so the answer arrived after the uploader had
    # already advanced the channel pointer. It is now decided once in
    # initialize.sh (step 6b) and merely READ here.
    #
    # The invariant this replaces is strictly stronger: instead of "the decide
    # step exists", assert that this job does NOT decide and DOES read the single
    # shared output. One evaluation, five readers.
    assert_not_contains "$job" "--decide-only" \
        "finalize no longer re-decides; asking twice can answer differently if a label moves"
    assert_contains "$job" "needs.initialize.outputs.skip_release" \
        "and it reads the ONE decision made in initialize"
    log_pass "ci.yml dispatches through the script, with no second inline path"
}

test_ci_yml_decides_before_it_seals() {
    # THE ROOT CAUSE, asserted structurally. Sealing before deciding is what put
    # cli/v1.2.27/.released in R2 with no v1.2.27 tag.
    local job found
    job="$(finalize_job_text)"
    found="$(ordering_violations "$job")"
    [[ -z "$found" ]] || log_fail "finalize-release-sentinel orders its steps wrongly: $found"

    # CONTROL: the same predicate over TODAY'S-BUG order must report it.
    local broken
    broken="      - name: Write release sentinels
        run: .ci/scripts/deploy/write-release-sentinel.sh --version v1.2.27
      - name: Dispatch cd-v2 release
        run: .ci/scripts/ci/dispatch-release.sh --decide-only"
    found="$(ordering_violations "$broken")"
    [[ -n "$found" ]] || log_fail "CONTROL FAILED: ordering_violations passed a block that seals before it decides, so it cannot detect the bug it exists for"
    assert_contains "$found" "does not precede the seal" "and the control names the defect"
    log_pass "ci.yml decides before it seals (control: the pre-fix order IS reported)"
}

test_ci_yml_guards_fail_toward_releasing() {
    # POLARITY. != 'true' releases on every degenerate state; == 'true' would
    # withhold on every degenerate state, green and silent.
    local job found
    job="$(finalize_job_text)"
    found="$(polarity_violations "$job")"
    [[ -z "$found" ]] || log_fail "finalize-release-sentinel's step guards are wrong: $found"

    # CONTROL 1: the inverted polarity must be rejected.
    local broken
    broken="      - name: Write release sentinels
        if: steps.release-decision.outputs.skip_release == 'true'
      - name: Dispatch cd-v2 release
        if: steps.release-decision.outputs.skip_release == 'true'"
    found="$(polarity_violations "$broken")"
    [[ -n "$found" ]] || log_fail "CONTROL FAILED: polarity_violations accepted == 'true' on both steps"
    assert_contains "$found" "== 'true'" "and the control names the inverted comparison"

    # CONTROL 2: guarding only ONE of the two steps must also be rejected -- a
    # guarded dispatch with an unguarded seal is the original bug exactly.
    broken="      - name: Write release sentinels
        run: .ci/scripts/deploy/write-release-sentinel.sh
      - name: Dispatch cd-v2 release
        if: steps.release-decision.outputs.skip_release != 'true'"
    found="$(polarity_violations "$broken")"
    [[ -n "$found" ]] || log_fail "CONTROL FAILED: polarity_violations accepted a block where only the dispatch is guarded"
    assert_contains "$found" "found 1" "and the control counts the guards"
    log_pass "both steps carry != 'true' (controls: == 'true' rejected, single-guard rejected)"
}

log_test "test-dispatch-release"
with_temp_dir test_bump_none_skips_the_release
with_temp_dir test_an_unlabelled_pr_releases
with_temp_dir test_the_rest_of_the_bump_family_still_releases
with_temp_dir test_an_unmerged_pr_is_never_consulted
with_temp_dir test_a_mixed_pr_set_releases
with_temp_dir test_a_lookup_failure_fails_open
with_temp_dir test_a_commit_with_no_pr_releases
with_temp_dir test_decide_only_signals_the_skip
with_temp_dir test_decide_only_stays_silent_for_a_release
with_temp_dir test_decide_only_fail_open_paths_never_signal_skip
with_temp_dir test_dispatch_only_asks_nothing_and_dispatches
with_temp_dir test_dispatch_only_survives_a_dead_api
with_temp_dir test_an_unknown_flag_is_a_wiring_bug
test_the_label_is_declared_and_managed
test_ci_yml_wires_the_script
test_ci_yml_decides_before_it_seals
test_ci_yml_guards_fail_toward_releasing
echo ""
log_pass "all tests passed"
