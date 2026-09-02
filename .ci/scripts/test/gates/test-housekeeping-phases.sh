#!/bin/bash
# Both-ways test for .ci/scripts/housekeeping/cleanup-versions.sh -- specifically
# for the parts of it that had never executed anywhere.
#
# WHY THIS GATE EXISTS. A single `return 1` in Phase 8d, placed inside the
# phase's own `set +e` region, produced three failures at once and every one of
# them was silent:
#
#   1. The nightly reported SUCCESS on every drifted run (08-18 .. 08-23). The
#      return was swallowed by `set +e`, so `cleanup_r2` looked clean.
#   2. It jumped over the `set -e` that closes that region, so Phases 9-12 then
#      ran with errexit OFF for the rest of the script.
#   3. It skipped Phase 8f entirely, disabling apt/rpm/apk/archlinux/npm
#      artifact retention from 2026-08-22 on. Run 32616474098's log jumps
#      straight from `8d:` to `Phase 9:` with no `8f:` line in between.
#
# Nothing caught any of that because nothing ever ran the script's failure paths.
# Phase 9's DELETE arm in particular had never executed anywhere in this repo's
# history -- not in CI, not in a test, not locally: every real run either found
# no stale branch or ran with --dry-run, which took a different branch of the
# code. Its first execution is here.
#
# HOW. The script is driven as a real program with `gh`, `aws` and `curl`
# replaced by routing fakes on PATH, so no test can reach GitHub or R2. Every
# fake records its argv, and the assertions that a call was NOT made are each
# paired with a control proving the recorder does capture that call when it
# happens -- otherwise "no DELETE was issued" would also pass against a fake
# that recorded nothing at all.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

UNDER_TEST="$REPO_ROOT/.ci/scripts/housekeeping/cleanup-versions.sh"

LAST_OUT=""
LAST_RC=0

[ -x "$UNDER_TEST" ] || log_fail "$UNDER_TEST is not executable"

# ---------------------------------------------------------------------------
# FAKES
# ---------------------------------------------------------------------------

write_fake_aws() {
    local dir="$1"
    mkdir -p "$dir/bin"
    cat >"$dir/bin/aws" <<'FAKE'
#!/bin/bash
# Routing fake for the four aws shapes cleanup_r2 uses. Anything unrouted
# returns empty rather than failing, because the phases under test walk past
# prefixes they find nothing in and that is the uninteresting case here.
set -uo pipefail
[ -n "${AWS_CALLS:-}" ] && printf '%s\n' "$*" >>"$AWS_CALLS"
svc="${1:-}"
op="${2:-}"
query=""
prefix=""
args=("$@")
i=0
while [ "$i" -lt "${#args[@]}" ]; do
    case "${args[$i]}" in
        --query)
            i=$((i + 1))
            query="${args[$i]}"
            ;;
        --prefix)
            i=$((i + 1))
            prefix="${args[$i]}"
            ;;
    esac
    i=$((i + 1))
done
fixture() {
    local name="$1"
    [ -f "$AWS_FIXTURES/$name" ] && cat "$AWS_FIXTURES/$name"
    return 0
}
case "$svc/$op" in
    s3/ls)
        target="${3#s3://}"
        fixture "ls.$(printf '%s' "${target#*/}" | tr '/' '~')"
        ;;
    s3api/list-objects-v2)
        case "$query" in
            *ends_with*) fixture "sentinels" ;;
            *LastModified*) echo "None" ;;
            *) echo "None" ;;
        esac
        ;;
    s3api/list-multipart-uploads) echo "[]" ;;
    *) ;;
esac
exit 0
FAKE
    chmod +x "$dir/bin/aws"
}

write_fake_gh() {
    local dir="$1"
    mkdir -p "$dir/bin"
    cat >"$dir/bin/gh" <<'FAKE'
#!/bin/bash
# Routing fake for every `gh` shape the housekeeping phases reach. Unrouted
# read calls return an empty JSON array so the phases that are not under test
# walk through without work; unrouted WRITE calls (-X DELETE to something
# unexpected) are a hard error, because a destructive call landing somewhere
# the test did not model must not read as a pass.
set -uo pipefail
[ -n "${GH_CALLS:-}" ] && printf '%s\n' "$*" >>"$GH_CALLS"
method="GET"
path=""
jqexpr=""
args=("$@")
i=0
while [ "$i" -lt "${#args[@]}" ]; do
    a="${args[$i]}"
    case "$a" in
        api | --paginate | --silent) ;;
        -X)
            i=$((i + 1))
            method="${args[$i]}"
            ;;
        --jq | -q)
            i=$((i + 1))
            jqexpr="${args[$i]}"
            ;;
        -*) ;;
        *) [ -z "$path" ] && path="$a" ;;
    esac
    i=$((i + 1))
done
fixture() {
    [ -f "$GH_FIXTURES/$1" ] && cat "$GH_FIXTURES/$1"
    return 0
}
if [ "$method" = "DELETE" ]; then
    case "$path" in
        */git/refs/heads/*)
            if [ -n "${GH_DELETE_FAIL:-}" ]; then
                echo "gh: Resource not accessible by integration (HTTP 403)" >&2
                exit 1
            fi
            exit 0
            ;;
        *)
            echo "fake gh: unmodelled DELETE: $*" >&2
            exit 3
            ;;
    esac
fi
case "$path" in
    */git/*)
        # Tag-object lookups (Phase 2). Empty output makes that phase skip the
        # tag, which is what keeps this gate focused on Phases 8d and 9.
        ;;
    */tags) fixture "tags" ;;
    */branches\?*)
        repo="${path#repos/}"
        repo="${repo%%/branches*}"
        fixture "branches.$(printf '%s' "$repo" | tr '/' '~')"
        ;;
    */branches/*)
        # Branch names contain slashes; fixtures flatten them to `~`.
        branch="${path##*/branches/}"
        fixture "branchdate.$(printf '%s' "$branch" | tr '/' '~')"
        ;;
    */pulls\?head=*)
        branch="${path##*head=}"
        branch="${branch%%&*}"
        branch="${branch#*:}"
        branch="$(printf '%s' "$branch" | tr '/' '~')"
        if [ -f "$GH_FIXTURES/openpr.$branch" ]; then cat "$GH_FIXTURES/openpr.$branch"; else echo 0; fi
        ;;
    *)
        if [ -n "$jqexpr" ]; then echo ""; else echo "[]"; fi
        ;;
esac
exit 0
FAKE
    chmod +x "$dir/bin/gh"
}

setup() {
    local t="$1"
    rm -rf "${t:?}/fixtures" "${t:?}/aws-fixtures" "${t:?}/bin" "${t:?}/gh-calls.log" "${t:?}/aws-calls.log"
    mkdir -p "$t/fixtures" "$t/aws-fixtures"
    write_fake_gh "$t"
    write_fake_aws "$t"
    # No drift and no branches by default; each test adds only what it needs.
    : >"$t/fixtures/tags"
    : >"$t/aws-fixtures/sentinels"
}

# r2_has_version <TEMP> <version> -- the version prefix exists under cli/ in R2.
r2_has_version() {
    printf '                           PRE %s/\n' "$2" >>"$1/aws-fixtures/ls.cli~"
}

# r2_has_sentinel <TEMP> <version>
r2_has_sentinel() {
    printf '%s\n' "cli/$2/.released" >>"$1/aws-fixtures/sentinels"
}

# git_has_tag <TEMP> <version>
git_has_tag() {
    printf '%s\n' "$2" >>"$1/fixtures/tags"
}

# branch <TEMP> <name> <days-old|-> [open-prs]
branch() {
    local t="$1" name="$2" age="$3" prs="${4:-0}"
    local key
    key="$(printf '%s' "$name" | tr '/' '~')"
    printf '%s\n' "$name" >>"$t/fixtures/branches.rediacc~console"
    if [[ "$age" != "-" ]]; then
        date -u -d "${age} days ago" +%Y-%m-%dT%H:%M:%SZ >"$t/fixtures/branchdate.$key"
    fi
    echo "$prs" >"$t/fixtures/openpr.$key"
}

# run_housekeeping <TEMP> [KEY=VALUE ...] [-- <script-arg> ...]
run_housekeeping() {
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
        AWS_FIXTURES="$t/aws-fixtures" \
        GH_CALLS="$t/gh-calls.log" \
        AWS_CALLS="$t/aws-calls.log" \
        GH_TOKEN=fake \
        GITHUB_ACTIONS=true \
        CLOUDFLARE_R2_ACCESS_KEY_ID=fake \
        CLOUDFLARE_R2_SECRET_ACCESS_KEY=fake \
        CLOUDFLARE_R2_ENDPOINT=https://r2.invalid \
        RSV_GRANDFATHER_BEFORE=v0.0.1 \
        NO_COLOR=1 \
        ${envs[@]+"${envs[@]}"} \
        bash "$UNDER_TEST" ${args[@]+"${args[@]}"} 2>&1)" || rc=$?
    LAST_RC="$rc"
    return 0
}

gh_calls() {
    [[ -f "$1/gh-calls.log" ]] && cat "$1/gh-calls.log" || true
}

# ---------------------------------------------------------------------------
# 8d: DRIFT MUST FAIL THE RUN, AND MUST NOT COST THE PHASES AFTER IT
# ---------------------------------------------------------------------------

test_drift_fails_the_run() {
    # THE FEATURE. A sentinel with no matching git tag is exactly the live
    # state that went unreported for six consecutive nightlies.
    local t="$1"
    setup "$t"
    r2_has_version "$t" v1.2.27
    r2_has_sentinel "$t" v1.2.27
    run_housekeeping "$t"
    assert_exit_code 1 "$LAST_RC" "release-state drift must fail the housekeeping run"
    assert_contains "$LAST_OUT" "drift: cli/v1.2.27/.released exists but git tag v1.2.27 missing" \
        "naming the drifted version"
    assert_contains "$LAST_OUT" "::error title=Release-state drift::" \
        "as a real GHA annotation, not a log_error nobody sees"
    assert_contains "$LAST_OUT" "Housekeeping FAILED" "and the run says it failed"
    log_pass "FIRE: sentinel without a tag => exit 1 plus an ::error annotation"
}

test_no_drift_passes_cleanly() {
    # CONTROL. Same fixture with the tag present must exit 0 and emit no
    # annotation -- otherwise the case above would pass against a script that
    # failed unconditionally.
    local t="$1"
    setup "$t"
    r2_has_version "$t" v1.2.27
    r2_has_sentinel "$t" v1.2.27
    git_has_tag "$t" v1.2.27
    run_housekeeping "$t"
    assert_exit_code 0 "$LAST_RC" "a committed release is not drift"
    assert_not_contains "$LAST_OUT" "::error title=" "and emits no error annotation"
    assert_not_contains "$LAST_OUT" "Housekeeping FAILED" "and does not report failure"
    log_pass "CONTROL: sentinel AND tag => exit 0, no annotation"
}

test_drift_does_not_skip_phase_8f() {
    # THE SECOND DEFECT. The old `return 1` fired before Phase 8f, silently
    # disabling apt/rpm/apk/archlinux/npm retention for anyone with drift.
    local t="$1"
    setup "$t"
    r2_has_version "$t" v1.2.27
    r2_has_sentinel "$t" v1.2.27
    run_housekeeping "$t"
    assert_exit_code 1 "$LAST_RC" "the run still fails"
    assert_contains "$LAST_OUT" "8f: channel artifact retention" \
        "but Phase 8f ran anyway -- the drift finding must not disable package retention"
    assert_contains "$LAST_OUT" "8e: " "and so did Phase 8e"

    # CONTROL: 8f is not simply always in this log for trivial reasons -- prove
    # the same marker appears on the clean path, so its presence above is the
    # phase running rather than a string that shows up regardless of drift.
    setup "$t"
    r2_has_version "$t" v1.2.27
    r2_has_sentinel "$t" v1.2.27
    git_has_tag "$t" v1.2.27
    run_housekeeping "$t"
    assert_contains "$LAST_OUT" "8f: channel artifact retention" \
        "CONTROL: the no-drift run reaches 8f too, so the marker tracks the phase"
    log_pass "drift no longer eats Phase 8f (control: 8f present on the clean run too)"
}

test_drift_does_not_skip_phases_9_to_12() {
    # THE THIRD DEFECT. The old return left errexit OFF for everything after
    # cleanup_r2; the phases still ran, but unprotected. They must run, and the
    # run must still end in a failure.
    local t="$1"
    setup "$t"
    r2_has_version "$t" v1.2.27
    r2_has_sentinel "$t" v1.2.27
    run_housekeeping "$t"
    assert_exit_code 1 "$LAST_RC" "the drift still fails the run at the very end"
    assert_contains "$LAST_OUT" "Phase 9: Cleaning up stale branches" "Phase 9 ran"
    assert_contains "$LAST_OUT" "Phase 10: Cleaning up completed workflow runs" "Phase 10 ran"
    assert_contains "$LAST_OUT" "Phase 11" "Phase 11 ran"
    assert_contains "$LAST_OUT" "Phase 12" "Phase 12 ran"
    assert_contains "$LAST_OUT" "Housekeeping complete" "and the run reached its own end marker"
    log_pass "a drift finding is latched, not thrown: Phases 9-12 all still run"
}

test_no_return_inside_the_errexit_relaxed_region() {
    # STATIC. The `set +e` / `set -e` bracket in cleanup_r2 spans ~340 lines and
    # guards SIGPIPE on `aws | awk` pipes. ANY early exit out of that span leaves
    # errexit off for the rest of the script -- which is the bug this file is
    # named for. The rule is lexical because that is what makes it checkable.
    local found
    found="$(returns_in_relaxed_region "$UNDER_TEST")"
    [[ -z "$found" ]] || log_fail "cleanup_r2 leaves its set +e region early: $found"

    # CONTROL: plant the exact defect on a copy and require it to be reported.
    local tmp
    tmp="$(mktemp)"
    python3 - "$UNDER_TEST" "$tmp" <<'PY'
import sys
src, dst = sys.argv[1], sys.argv[2]
lines = open(src).read().split("\n")
start = next(i for i, l in enumerate(lines) if l.strip() == "set +e")
end = next(i for i, l in enumerate(lines) if i > start and l.strip() == "set -e")
lines.insert((start + end) // 2, "    return 1  # planted control")
open(dst, "w").write("\n".join(lines))
PY
    found="$(returns_in_relaxed_region "$tmp")"
    rm -f "$tmp"
    [[ -n "$found" ]] || log_fail "CONTROL FAILED: the planted 'return 1' inside the set +e region was not reported, so this check cannot detect the original bug"
    log_pass "no early exit inside cleanup_r2's set +e region (control: a planted return IS reported)"
}

# Prints one line per `return`/`exit` lexically between cleanup_r2's `set +e`
# and the `set -e` that closes it; empty output means clean.
returns_in_relaxed_region() {
    python3 - "$1" <<'PY'
import sys, re
lines = open(sys.argv[1]).read().split("\n")
try:
    start = next(i for i, l in enumerate(lines) if l.strip() == "set +e")
    end = next(i for i, l in enumerate(lines) if i > start and l.strip() == "set -e")
except StopIteration:
    print("could not locate the set +e / set -e bracket in cleanup_r2 at all")
    sys.exit(0)
for i in range(start + 1, end):
    body = lines[i].split("#", 1)[0]
    if re.search(r"(^|[;&|{(\s])(return|exit)(\s|$)", body):
        print("line %d leaves the region early: %s" % (i + 1, lines[i].strip()))
PY
}

# ---------------------------------------------------------------------------
# PHASE 9: the delete arm, executing for the first time
# ---------------------------------------------------------------------------

test_a_stale_branch_is_deleted() {
    local t="$1"
    setup "$t"
    branch "$t" feature/old 40
    run_housekeeping "$t"
    assert_exit_code 0 "$LAST_RC" "a clean sweep exits 0"
    assert_contains "$(gh_calls "$t")" "DELETE repos/rediacc/console/git/refs/heads/feature/old" \
        "a 40-day-old branch with no open PR is deleted"
    assert_contains "$LAST_OUT" "Branches (console): deleted 1" "and counted as deleted"
    log_pass "FIRE: 40d branch, no open PR => DELETE issued, reported as deleted 1"
}

test_a_young_branch_is_kept() {
    # CONTROL for age.
    local t="$1"
    setup "$t"
    branch "$t" feature/new 10
    run_housekeeping "$t"
    assert_not_contains "$(gh_calls "$t")" "DELETE " "a 10-day-old branch must not be deleted"
    assert_contains "$LAST_OUT" "Branches (console): deleted 0, kept 1" "and is counted as kept"
    log_pass "CONTROL: 10d branch => no DELETE, kept 1"
}

test_a_stale_branch_with_an_open_pr_is_kept() {
    local t="$1"
    setup "$t"
    branch "$t" feature/reviewing 40 1
    run_housekeeping "$t"
    assert_not_contains "$(gh_calls "$t")" "DELETE " "an open PR protects a stale branch"
    assert_contains "$LAST_OUT" "Branches (console): deleted 0, kept 1" "and it is counted as kept"

    # CONTROL: the same branch at the same age with zero open PRs IS deleted.
    setup "$t"
    branch "$t" feature/reviewing 40 0
    run_housekeeping "$t"
    assert_contains "$(gh_calls "$t")" "DELETE repos/rediacc/console/git/refs/heads/feature/reviewing" \
        "CONTROL: with no open PR the identical branch is deleted, so the open PR is what saved it"
    log_pass "an open PR protects a stale branch (control: zero open PRs deletes it)"
}

test_main_is_never_deleted() {
    local t="$1"
    setup "$t"
    branch "$t" main 900
    run_housekeeping "$t"
    assert_not_contains "$(gh_calls "$t")" "DELETE " "main must never be deleted, at any age"

    # CONTROL: a non-main branch of the same age IS deleted.
    setup "$t"
    branch "$t" ancient/thing 900
    run_housekeeping "$t"
    assert_contains "$(gh_calls "$t")" "DELETE repos/rediacc/console/git/refs/heads/ancient/thing" \
        "CONTROL: 900 days is well past the threshold for any other branch"
    log_pass "main survives at 900 days (control: another 900d branch is deleted)"
}

test_an_undatable_branch_is_kept() {
    local t="$1"
    setup "$t"
    branch "$t" mystery -
    run_housekeeping "$t"
    assert_not_contains "$(gh_calls "$t")" "DELETE " "a branch whose age cannot be resolved is kept"
    assert_contains "$LAST_OUT" "Branches (console): deleted 0, kept 1" "and counted as kept"

    # CONTROL: give the same branch a resolvable stale date and it goes.
    setup "$t"
    branch "$t" mystery 40
    run_housekeeping "$t"
    assert_contains "$(gh_calls "$t")" "DELETE repos/rediacc/console/git/refs/heads/mystery" \
        "CONTROL: the same branch with a resolvable stale date IS deleted"
    log_pass "an unresolvable commit date keeps the branch (control: a resolvable one deletes it)"
}

test_dry_run_deletes_nothing_and_says_so() {
    # The old code incremented the SAME counter in dry-run, so a dry run
    # reported "deleted 7" having deleted nothing.
    local t="$1"
    setup "$t"
    branch "$t" feature/old 40
    run_housekeeping "$t" -- --dry-run
    assert_exit_code 0 "$LAST_RC" "a dry run exits 0"
    assert_contains "$LAST_OUT" "[DRY-RUN] Would delete feature/old" "it says what it would delete"
    assert_contains "$LAST_OUT" "Branches (console): would delete 1, kept 0" \
        "and the summary says WOULD delete, not deleted"
    assert_not_contains "$LAST_OUT" "Branches (console): deleted 1" \
        "a dry run must never claim a deletion"
    assert_not_contains "$(gh_calls "$t")" "DELETE " "and issues no DELETE"
    assert_contains "$LAST_OUT" "Total deletes this run: 0 /" "consuming no delete budget"

    # CONTROL: the identical fixture without --dry-run does issue the DELETE and
    # does consume budget, so the absences above are the flag's doing.
    setup "$t"
    branch "$t" feature/old 40
    run_housekeeping "$t"
    assert_contains "$(gh_calls "$t")" "DELETE repos/rediacc/console/git/refs/heads/feature/old" \
        "CONTROL: the same fixture without --dry-run DOES delete"
    assert_contains "$LAST_OUT" "Total deletes this run: 1 /" "CONTROL: and DOES consume budget"
    log_pass "--dry-run deletes nothing, consumes no budget, and reports 'would delete'"
}

test_the_branch_listing_paginates() {
    # ?per_page=100 without --paginate silently caps the sweep at 100 branches,
    # so any repo with a longer list keeps its stale ones forever.
    local t="$1"
    setup "$t"
    branch "$t" feature/old 40
    run_housekeeping "$t"
    local calls
    calls="$(gh_calls "$t")"
    assert_contains "$calls" "repos/rediacc/console/branches?per_page=100" \
        "the recorder captured the branch listing (so the next assertion is about a call that happened)"
    printf '%s\n' "$calls" | grep -F 'repos/rediacc/console/branches?per_page=100' | grep -q -- '--paginate' ||
        log_fail "the branch listing does not pass --paginate, so it stops at 100 branches"
    log_pass "the branch listing paginates (asserted on a call the recorder actually captured)"
}

test_a_failed_delete_fails_the_run() {
    # A 403 from a token missing contents:write on one repo used to be a
    # log_warn that surfaced nowhere, and the phase reported a clean sweep it
    # had not performed.
    local t="$1"
    setup "$t"
    branch "$t" feature/old 40
    run_housekeeping "$t" GH_DELETE_FAIL=1
    assert_exit_code 1 "$LAST_RC" "a failed branch delete must fail the run"
    assert_contains "$LAST_OUT" "::error title=Stale-branch delete failed::" \
        "as a GHA annotation"
    assert_contains "$LAST_OUT" "HTTP 403" "carrying gh's own stderr, not a generic message"
    assert_contains "$LAST_OUT" "Phase 10" "and the later phases still ran"

    # CONTROL: the same fixture with a succeeding DELETE exits 0 and annotates
    # nothing.
    setup "$t"
    branch "$t" feature/old 40
    run_housekeeping "$t"
    assert_exit_code 0 "$LAST_RC" "CONTROL: a succeeding delete exits 0"
    assert_not_contains "$LAST_OUT" "::error title=Stale-branch delete failed::" \
        "CONTROL: and emits no annotation"
    log_pass "a 403 on DELETE annotates and fails the run (control: a 200 does neither)"
}

log_test "test-housekeeping-phases"
with_temp_dir test_drift_fails_the_run
with_temp_dir test_no_drift_passes_cleanly
with_temp_dir test_drift_does_not_skip_phase_8f
with_temp_dir test_drift_does_not_skip_phases_9_to_12
test_no_return_inside_the_errexit_relaxed_region
with_temp_dir test_a_stale_branch_is_deleted
with_temp_dir test_a_young_branch_is_kept
with_temp_dir test_a_stale_branch_with_an_open_pr_is_kept
with_temp_dir test_main_is_never_deleted
with_temp_dir test_an_undatable_branch_is_kept
with_temp_dir test_dry_run_deletes_nothing_and_says_so
with_temp_dir test_the_branch_listing_paginates
with_temp_dir test_a_failed_delete_fails_the_run
echo ""
log_pass "all tests passed"
