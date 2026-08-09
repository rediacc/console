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
}

# pulls_for <TEMP> <sha> <pr-json...>
pulls_for() {
    local t="$1" sha="$2"
    shift 2
    printf '%s\n' "$@" | jq -s '.' >"$t/fixtures/pulls-$sha.json"
}

# run_dispatch <TEMP> [KEY=VALUE ...]
run_dispatch() {
    local t="$1"
    shift
    local rc=0
    LAST_OUT="$(env \
        PATH="$t/bin:$PATH" \
        GH_FIXTURES="$t/fixtures" \
        GH_TOKEN=fake \
        GITHUB_REPOSITORY=rediacc/console \
        GITHUB_SHA="$SHA" \
        GITHUB_RUN_ID=999 \
        DISPATCH_RELEASE_DRY_RUN=1 \
        NO_COLOR=1 \
        "$@" \
        bash "$UNDER_TEST" 2>&1)" || rc=$?
    LAST_RC="$rc"
    return 0
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

test_ci_yml_wires_the_script() {
    local wf job
    wf="$(cat "$CI_WORKFLOW")"
    assert_contains "$wf" "dispatch-release.sh" "ci.yml calls the script"
    job="$(awk '/^  finalize-release-sentinel:/{f=1} f&&/^  [a-z][a-z0-9-]*:$/&&!/^  finalize-release-sentinel:/{exit} f' "$CI_WORKFLOW")"
    assert_contains "$job" ".ci/scripts/ci/dispatch-release.sh" "from the finalize-release-sentinel job"
    assert_not_contains "$job" "gh workflow run cd-v2.yml" \
        "and the inline dispatch is gone, so there is only ONE place the decision can be made"
    assert_contains "$job" "GH_TOKEN" "the script still gets its token"
    log_pass "ci.yml dispatches through the script, with no second inline path"
}

log_test "test-dispatch-release"
with_temp_dir test_bump_none_skips_the_release
with_temp_dir test_an_unlabelled_pr_releases
with_temp_dir test_the_rest_of_the_bump_family_still_releases
with_temp_dir test_an_unmerged_pr_is_never_consulted
with_temp_dir test_a_mixed_pr_set_releases
with_temp_dir test_a_lookup_failure_fails_open
with_temp_dir test_a_commit_with_no_pr_releases
test_the_label_is_declared_and_managed
test_ci_yml_wires_the_script
echo ""
log_pass "all tests passed"
