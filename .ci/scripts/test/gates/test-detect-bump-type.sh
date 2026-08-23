#!/bin/bash
# Both-ways test for .ci/scripts/version/detect-bump-type.sh -- the script that
# turns PR labels into the version bump a release takes.
#
# WHY THIS CLASS NEEDS A GATE. The thing being replaced was green forever while
# answering nothing. It resolved the PR by grepping `(#123)` out of the HEAD
# commit TITLE, which only a squash merge produces; this repo went rebase-merge
# on 2026-07-30 and 0 of the following 60 commits on main carried that shape.
# So every release took the "no PR numbers found" fallback and shipped patch,
# and bump-major / bump-minor were declared, documented and DEAD. Nothing said
# so, because "patch" is also the correct answer most of the time.
#
# That is the trap this suite is built around: patch is the fallback for EVERY
# failure mode, so a test that asserts patch proves nothing on its own. Every
# case below therefore either
#   - asserts a NON-patch answer (the only direction that cannot be reached by
#     accident), or
#   - asserts patch AND that the API was actually reached (GH_CALLS non-empty),
#     so a broken harness reads as a failure instead of a pass.
#
# GitHub is stubbed with a routing fake `gh` that serves a per-SHA fixture and
# applies the script's own --jq expression to it, so the real extraction runs
# rather than a reimplementation of it. The git repository is real: the range
# arithmetic (tag..HEAD, the cap, the no-tag fallback) is half of what can
# break, and a fake `git` would test none of it.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test gate
source "$SCRIPT_DIR/../lib/test-helpers.sh"

UNDER_TEST="$REPO_ROOT/.ci/scripts/version/detect-bump-type.sh"
LABELS_FILE="$REPO_ROOT/.github/labels.yml"

LAST_OUT=""
LAST_ERR=""
LAST_RC=0

# ---------------------------------------------------------------------------
# Fixture scaffolding
# ---------------------------------------------------------------------------

write_fake_gh() {
    local dir="$1"
    mkdir -p "$dir/bin"
    cat >"$dir/bin/gh" <<'FAKE'
#!/bin/bash
# Routing fake for `gh api repos/<repo>/commits/<sha>/pulls`. Serves the
# per-SHA fixture (falling back to pulls-default.json, which is how a commit
# with no associated PR is expressed) and applies the caller's own --jq to it.
# EVERY call is appended to $GH_CALLS: see the header for why a test that
# expects "patch" must also prove the API was reached.
set -uo pipefail
printf '%s\n' "$*" >>"$GH_CALLS"
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
        if [ ! -f "$file" ]; then file="$GH_FIXTURES/pulls-default.json"; fi
        if [ ! -f "$file" ]; then
            echo "fake gh: no fixture for $sha and no default" >&2
            exit 4
        fi
        ;;
    *)
        echo "fake gh: unrouted path: $path" >&2
        exit 3
        ;;
esac

if [ -n "$jqexpr" ]; then
    jq -r "$jqexpr" "$file"
else
    cat "$file"
fi
FAKE
    chmod +x "$dir/bin/gh"
}

setup() {
    local t="$1"
    # Idempotent: a case that drives two different worlds (same fixtures, moved
    # tag) calls this twice in one temp dir, and a leftover repo would make the
    # second world inherit the first one's tags.
    # ${t:?} so an unset TEMP can never turn this into `rm -rf /repo`.
    rm -rf "${t:?}/fixtures" "${t:?}/repo"
    mkdir -p "$t/fixtures" "$t/repo"
    write_fake_gh "$t"
    : >"$t/calls.txt"
    # A commit with no associated PR. Not an error: most commits in a range
    # resolve to one PR, some to none.
    echo '[]' >"$t/fixtures/pulls-default.json"
    git -C "$t/repo" init -q -b main
    git -C "$t/repo" config user.email "gate-test@example.invalid"
    git -C "$t/repo" config user.name "Gate Test"
    git -C "$t/repo" config commit.gpgsign false
}

# commit <TEMP> <subject> -- one real commit in the scratch repo; prints its SHA.
commit() {
    local t="$1" subject="$2"
    printf '%s\n' "$subject" >>"$t/repo/file.txt"
    git -C "$t/repo" add file.txt
    git -C "$t/repo" commit -q -m "$subject"
    git -C "$t/repo" rev-parse HEAD
}

# merged_pr <number> <labels-csv>
merged_pr() {
    jq -nc --argjson n "$1" --arg l "$2" \
        '{number: $n, merged_at: "2026-08-01T00:00:00Z", state: "closed",
          labels: ($l | if . == "" then [] else split(",") end | map({name: .}))}'
}

# open_pr <number> <labels-csv> -- contains the commit, but nothing is released
# from it yet, so its label must not count.
open_pr() {
    jq -nc --argjson n "$1" --arg l "$2" \
        '{number: $n, merged_at: null, state: "open",
          labels: ($l | if . == "" then [] else split(",") end | map({name: .}))}'
}

# pulls_for <TEMP> <sha> <pr-json...>
pulls_for() {
    local t="$1" sha="$2"
    shift 2
    printf '%s\n' "$@" | jq -s '.' >"$t/fixtures/pulls-$sha.json"
}

# run_detect <TEMP> [KEY=VALUE ...]
run_detect() {
    local t="$1"
    shift
    local rc=0
    LAST_OUT="$(cd "$t/repo" && env \
        PATH="$t/bin:$PATH" \
        GH_FIXTURES="$t/fixtures" \
        GH_CALLS="$t/calls.txt" \
        GH_TOKEN=fake \
        GITHUB_REPOSITORY=rediacc/console \
        NO_COLOR=1 \
        "$@" \
        bash "$UNDER_TEST" --verbose 2>"$t/err.txt")" || rc=$?
    LAST_RC="$rc"
    LAST_ERR="$(cat "$t/err.txt")"
    return 0
}

assert_api_was_reached() {
    local t="$1" msg="$2"
    if [[ ! -s "$t/calls.txt" ]]; then
        log_fail "$msg: the fake gh was never called, so this verdict came from a fallback and asserts nothing"
    fi
}

# ---------------------------------------------------------------------------
# FIRE: the answers that cannot happen by accident
# ---------------------------------------------------------------------------
test_head_pr_minor_yields_minor() {
    local t="$1" c1 c2
    setup "$t"
    c1="$(commit "$t" "released work")"
    git -C "$t/repo" tag v1.0.0 "$c1"
    c2="$(commit "$t" "new capability")"
    pulls_for "$t" "$c2" "$(merged_pr 100 bump-minor)"

    run_detect "$t"
    assert_exit_code 0 "$LAST_RC" "the script always exits 0"
    assert_eq "$LAST_OUT" "minor" "FIRE: a bump-minor label on the merged PR must escalate the release"
    assert_contains "$LAST_ERR" "PR #100" "the verbose log names the PR it read"
    log_pass "FIRE: bump-minor on the PR containing HEAD => minor"
}

test_major_beats_minor_in_either_order() {
    local t="$1" c1 c2 c3
    setup "$t"
    c1="$(commit "$t" "released work")"
    git -C "$t/repo" tag v1.0.0 "$c1"
    c2="$(commit "$t" "a feature")"
    c3="$(commit "$t" "a break")"
    pulls_for "$t" "$c2" "$(merged_pr 100 bump-minor)"
    pulls_for "$t" "$c3" "$(merged_pr 101 bump-major)"
    run_detect "$t"
    assert_eq "$LAST_OUT" "major" "major outranks minor when it is nearest HEAD"

    # SAME range, priorities swapped between the two commits. The scan walks
    # newest-first, so this is the case a short-circuit could get wrong: it must
    # not stop at the first bump label it meets.
    setup "$t"
    c1="$(commit "$t" "released work")"
    git -C "$t/repo" tag v1.0.0 "$c1"
    c2="$(commit "$t" "a break")"
    c3="$(commit "$t" "a feature")"
    pulls_for "$t" "$c2" "$(merged_pr 100 bump-major)"
    pulls_for "$t" "$c3" "$(merged_pr 101 bump-minor)"
    run_detect "$t"
    assert_eq "$LAST_OUT" "major" "major outranks minor when it is DEEPER in the range than the minor"
    log_pass "FIRE: major beats minor from either end of the range"
}

# THE UNION PROPERTY, and the reason the range exists rather than HEAD alone.
# CI auto-cancels superseded pushes, so the commit that finally releases need
# not belong to the PR that carried the label.
test_label_on_a_non_head_commit_still_escalates() {
    local t="$1" c1 c2 c3
    setup "$t"
    c1="$(commit "$t" "released work")"
    git -C "$t/repo" tag v1.0.0 "$c1"
    c2="$(commit "$t" "the labelled PR")"
    c3="$(commit "$t" "an unlabelled follow-up")"
    pulls_for "$t" "$c2" "$(merged_pr 100 bump-minor)"
    pulls_for "$t" "$c3" "$(merged_pr 101 "")"

    run_detect "$t"
    assert_eq "$LAST_OUT" "minor" \
        "FIRE: a label on a PR inside tag..HEAD counts even when HEAD's own PR carries none (HEAD-only resolution answers patch here)"
    log_pass "FIRE: bump-minor on a non-HEAD commit in range => minor (the union, not just the tip)"
}

# ---------------------------------------------------------------------------
# The range is load-bearing: the SAME fixtures must answer differently when
# only the tag moves.
# ---------------------------------------------------------------------------
test_commits_before_the_tag_are_out_of_range() {
    local t="$1" c1 c2 c3
    setup "$t"
    c1="$(commit "$t" "an older release")"
    c2="$(commit "$t" "a breaking change, released as v1.0.0")"
    c3="$(commit "$t" "todays work")"
    pulls_for "$t" "$c2" "$(merged_pr 99 bump-major)"
    pulls_for "$t" "$c3" "$(merged_pr 100 "")"

    # v1.0.0 IS the breaking change's release. Its label was consumed then, and
    # re-reading it now would ship a second major for the same work.
    git -C "$t/repo" tag v1.0.0 "$c2"
    run_detect "$t"
    assert_eq "$LAST_OUT" "patch" \
        "a bump-major already consumed by the release that tagged it must not escalate the next one"
    assert_api_was_reached "$t" "out-of-range case"
    assert_not_contains "$LAST_ERR" "PR #99" "the out-of-range PR is never even queried"

    # CONTROL: identical fixtures, tag moved back exactly one commit so PR #99
    # falls INSIDE the range. If this does not flip to major, the range is not
    # being read and the assertion above is vacuous.
    git -C "$t/repo" tag -d v1.0.0 >/dev/null
    git -C "$t/repo" tag v1.0.0 "$c1"
    : >"$t/calls.txt"
    run_detect "$t"
    assert_eq "$LAST_OUT" "major" \
        "CONTROL: the same bump-major, one tag position earlier, DOES escalate"
    log_pass "the tag..HEAD range is load-bearing (same fixtures, tag moved by one, verdict flips)"
}

test_range_cap_is_real() {
    local t="$1" c1 c2 c3 c4
    setup "$t"
    c1="$(commit "$t" "released work")"
    git -C "$t/repo" tag v1.0.0 "$c1"
    c2="$(commit "$t" "the labelled PR")"
    c3="$(commit "$t" "filler")"
    c4="$(commit "$t" "head")"
    pulls_for "$t" "$c2" "$(merged_pr 100 bump-minor)"
    pulls_for "$t" "$c3" "$(merged_pr 101 "")"
    pulls_for "$t" "$c4" "$(merged_pr 102 "")"

    run_detect "$t"
    assert_eq "$LAST_OUT" "minor" "CONTROL: uncapped, the label three commits deep is seen"

    : >"$t/calls.txt"
    run_detect "$t" DETECT_BUMP_MAX_COMMITS=1
    assert_eq "$LAST_OUT" "patch" "capped at 1 commit, the deeper label is out of reach"
    assert_api_was_reached "$t" "capped case"
    log_pass "DETECT_BUMP_MAX_COMMITS genuinely bounds the scan (3 commits => minor, 1 => patch)"
}

test_no_tag_scans_head_alone() {
    local t="$1" c1 c2
    setup "$t"
    # initialize.sh calls this BEFORE its own `git fetch --tags`, so a shallow
    # checkout with no tags is a real state, not a hypothetical.
    c1="$(commit "$t" "an old breaking change")"
    c2="$(commit "$t" "todays work")"
    pulls_for "$t" "$c1" "$(merged_pr 99 bump-major)"
    pulls_for "$t" "$c2" "$(merged_pr 100 bump-minor)"

    run_detect "$t"
    assert_eq "$LAST_OUT" "minor" \
        "with no tag the scan is HEAD ALONE: a blind window of history would re-read PR #99 and escalate to major"
    assert_not_contains "$LAST_ERR" "PR #99" "the older PR is never queried without a range to justify it"
    log_pass "no usable tag => HEAD alone, not a blind history window"
}

# ---------------------------------------------------------------------------
# Fallbacks: patch, but PROVEN to be patch-for-the-right-reason
# ---------------------------------------------------------------------------
test_no_merged_prs_yields_patch() {
    local t="$1" c1
    setup "$t"
    c1="$(commit "$t" "direct push")"
    git -C "$t/repo" tag v1.0.0 "$c1"
    commit "$t" "another direct push" >/dev/null

    run_detect "$t"
    assert_eq "$LAST_OUT" "patch" "a range with no merged PR is a patch release"
    assert_api_was_reached "$t" "no-PR case"
    assert_contains "$LAST_ERR" "no merged PRs found" "and it says so rather than blaming a failure"
    log_pass "no merged PRs in range => patch, with the API actually consulted"
}

test_open_pr_label_is_ignored() {
    local t="$1" c1 c2
    setup "$t"
    c1="$(commit "$t" "released work")"
    git -C "$t/repo" tag v1.0.0 "$c1"
    c2="$(commit "$t" "work in flight")"
    pulls_for "$t" "$c2" "$(open_pr 100 bump-major)"

    run_detect "$t"
    assert_eq "$LAST_OUT" "patch" "an UNMERGED PR's label describes a release that has not happened"
    assert_api_was_reached "$t" "open-PR case"

    # CONTROL: the only difference is merged_at. If this does not flip, the
    # merged filter is not what produced the patch above.
    pulls_for "$t" "$c2" "$(merged_pr 100 bump-major)"
    : >"$t/calls.txt"
    run_detect "$t"
    assert_eq "$LAST_OUT" "major" "CONTROL: the same PR, merged, DOES escalate"
    log_pass "open PRs are ignored and merged ones are not (merged_at is the only difference)"
}

test_api_failure_yields_patch() {
    local t="$1" c1 c2
    setup "$t"
    c1="$(commit "$t" "released work")"
    git -C "$t/repo" tag v1.0.0 "$c1"
    c2="$(commit "$t" "new capability")"
    pulls_for "$t" "$c2" "$(merged_pr 100 bump-major)"

    run_detect "$t" GH_FAIL_ALL=1
    assert_exit_code 0 "$LAST_RC" "an API failure must not fail the release job"
    assert_eq "$LAST_OUT" "patch" "unresolvable PRs fail OPEN and SMALL"
    assert_api_was_reached "$t" "API-failure case"
    assert_contains "$LAST_ERR" "every commits/<sha>/pulls lookup failed" "the fallback names its reason"
    log_pass "total API failure => patch (fail open and small), with the reason logged"
}

test_missing_token_yields_patch_without_calling_the_api() {
    local t="$1"
    setup "$t"
    commit "$t" "work" >/dev/null
    run_detect "$t" GH_TOKEN=
    assert_eq "$LAST_OUT" "patch" "no token means no lookup"
    if [[ -s "$t/calls.txt" ]]; then
        log_fail "the API was called without a token; the prerequisite check is not running"
    fi
    log_pass "no GH_TOKEN => patch, and the API is not called (proves calls.txt discriminates)"
}

# ---------------------------------------------------------------------------
# THE CLEAN BREAK. The old resolution path must be gone, asserted by BEHAVIOUR
# rather than by grepping for its absence.
# ---------------------------------------------------------------------------
test_commit_title_pr_number_is_never_used() {
    local t="$1" c1 c2
    setup "$t"
    c1="$(commit "$t" "released work")"
    git -C "$t/repo" tag v1.0.0 "$c1"
    # A squash-merge-shaped title naming a DIFFERENT PR than the API reports.
    c2="$(commit "$t" "fix the thing (#999)")"
    pulls_for "$t" "$c2" "$(merged_pr 100 bump-minor)"

    run_detect "$t"
    assert_eq "$LAST_OUT" "minor" "the API's PR #100 is the answer, not the title's #999"
    # SHAs MASKED FIRST. This asserted a bare "999" against a file that records
    # whole gh command lines -- including 40-hex commit SHAs -- so it went red on
    # CI run 32659064316 because that run's generated SHA happened to contain the
    # digits (...c089991d...). Roughly a 1-in-100 flake, latent since the case was
    # written, and nothing to do with PR numbers. The intent is "no call carries
    # the TITLE's PR number", so mask the one field that can spell three digits by
    # coincidence and assert on what is left.
    assert_not_contains "$(sed -E 's/[0-9a-f]{40}/<sha>/g' "$t/calls.txt")" "999" \
        "PR #999 is never queried (commit SHAs masked, since hex can spell 999)"
    assert_not_contains "$(cat "$t/calls.txt")" "pr view" "and no per-PR gh pr view call is made at all"
    log_pass "the commit TITLE is not a PR source any more (title says #999, API says #100, answer follows the API)"
}

# ---------------------------------------------------------------------------
# Anti-drift with the declaration file: the labels this script matches on must
# exist in .github/labels.yml, or the inventory gates cannot keep them alive.
# ---------------------------------------------------------------------------
test_bump_labels_are_declared() {
    local l
    for l in bump-major bump-minor; do
        grep -qE "^- name: ${l}$" "$LABELS_FILE" ||
            log_fail "detect-bump-type.sh matches '$l' but .github/labels.yml does not declare it"
        grep -qF "\"$l\"" "$UNDER_TEST" ||
            log_fail "detect-bump-type.sh no longer matches '$l'; the label is declared and consumed by nothing"
    done
    log_pass "both bump labels are declared in labels.yml and still matched by the script"
}

# ---------------------------------------------------------------------------

test_bump_labels_are_declared

with_temp_dir test_head_pr_minor_yields_minor
with_temp_dir test_major_beats_minor_in_either_order
with_temp_dir test_label_on_a_non_head_commit_still_escalates
with_temp_dir test_commits_before_the_tag_are_out_of_range
with_temp_dir test_range_cap_is_real
with_temp_dir test_no_tag_scans_head_alone

with_temp_dir test_no_merged_prs_yields_patch
with_temp_dir test_open_pr_label_is_ignored
with_temp_dir test_api_failure_yields_patch
with_temp_dir test_missing_token_yields_patch_without_calling_the_api

with_temp_dir test_commit_title_pr_number_is_never_used
