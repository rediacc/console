#!/bin/bash
# Both-ways test for .ci/scripts/review/review-status.sh -- the script behind
# the `Review Complete` check-run.
#
# WHY THIS CLASS NEEDS A GATE. The thing being replaced (`Review Gate` inside
# Console CI) was green for months while asserting nothing about the review it
# is named after: it runs on `pull_request`, before any review can have
# happened, and its three scripts never look at a SHA. A successor that is
# merely *shaped* like a check is worthless -- so every conclusion this script
# can reach is driven here against planted state, in BOTH directions:
#
#   - Too quiet: a stale marker, an unreviewed head, a failed review run, or a
#     failing hygiene script must produce conclusion=failure. If any of those
#     silently pass, the check is decoration.
#   - Too loud: an empty diff, a submodule-pointer-only diff, and a cancelled
#     (superseded) review run must NOT fail, and a draft PR must be neutral.
#   - The deadlock case: once MAX_REVIEWS_PER_PR is reached the review pipeline
#     refuses to run again, so the marker can NEVER advance. Failing there would
#     make the PR permanently unmergeable. It must pass, with a warning.
#
# GitHub is stubbed with a routing fake `gh` that applies the script's own
# --jq expressions to fixture JSON, so the real jq/sed extraction is exercised
# rather than reimplemented. Every write (check-run POST/PATCH) is captured and
# asserted on, including WHICH SHA it was anchored to.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test gate
source "$SCRIPT_DIR/../lib/test-helpers.sh"

UNDER_TEST="$REPO_ROOT/.ci/scripts/review/review-status.sh"
REAL_GATE="$REPO_ROOT/.ci/scripts/review/claude-review-gate.sh"

OLD_SHA="1111111111111111111111111111111111111111"
NEW_SHA="2222222222222222222222222222222222222222"

LAST_OUT=""
LAST_RC=0

# ---------------------------------------------------------------------------
# Fixture scaffolding
# ---------------------------------------------------------------------------

write_fake_gh() {
    local dir="$1"
    mkdir -p "$dir/bin"
    cat >"$dir/bin/gh" <<'FAKE'
#!/bin/bash
# Routing fake for `gh api`. Serves fixture JSON per endpoint and applies the
# caller's own --jq expression to it (gh applies --jq per page; the fixtures are
# single-page, so this is faithful). Non-GET calls are captured, never served.
set -uo pipefail
method="GET"
explicit_method=0
has_field=0
fields=""
path=""
jqexpr=""
args=("$@")
n=${#args[@]}
i=0
while [ "$i" -lt "$n" ]; do
    a="${args[$i]}"
    case "$a" in
        api) ;;
        -X | --method)
            i=$((i + 1))
            method="${args[$i]}"
            explicit_method=1
            ;;
        --jq)
            i=$((i + 1))
            jqexpr="${args[$i]}"
            ;;
        --input | -f | -F | --field | --raw-field)
            i=$((i + 1))
            has_field=1
            fields="${fields}${args[$i]}
"
            ;;
        --paginate | --silent) ;;
        -*) ;;
        *)
            if [ -z "$path" ]; then path="$a"; fi
            ;;
    esac
    i=$((i + 1))
done
# gh INFERS POST when a field is passed without -X, and so must this fake.
# Without the inference such a call was classified GET, served a fixture, and
# never captured -- so a test asserting "the write happened" passed while
# nothing was written. That is the harness itself failing vacuously, which is
# the one bug class this whole suite exists to catch.
if [ "$explicit_method" -eq 0 ] && [ "$has_field" -eq 1 ]; then
    method="POST"
fi

if [ "$method" != "GET" ]; then
    {
        echo "METHOD=$method PATH=$path"
        cat
        echo
    } >>"$GH_CAPTURE"
    # `-f key=value` fields go to a SIDECAR file, never into $GH_CAPTURE: the
    # check-run assertions parse that file as raw JSON with jq, so anything
    # extra in it would break every existing case. A write whose payload is
    # fields rather than stdin (the attempt marker) is read from here.
    {
        echo "METHOD=$method PATH=$path"
        printf '%s' "$fields"
    } >>"${GH_CAPTURE}.fields"
    echo '{"id": 999}'
    exit 0
fi

key=""
case "$path" in
    # `gh pr view --json additions,deletions` -- how the review budget learns the
    # diff size. Without this the call falls through to "unrouted" and every test
    # silently gets a 0-line diff, i.e. the smallest cap, which would make the
    # size-tiered budget untestable.
    pr) key="pr-size" ;;
    */commits/*/pulls) key="commit-pulls" ;;
    # The workflow_run PR handoff. Two calls: list the run's artifacts, then
    # download the zip. The zip route writes a REAL zip so the script's
    # `unzip -p` runs for real rather than against a stub -- the extraction is
    # part of what can break.
    */actions/runs/*/artifacts) key="run-artifacts" ;;
    */actions/artifacts/*/zip)
        # A REAL zip on stdout, built with python3 because `zip` is not
        # installed on this box (only unzip is) and the suite already requires
        # python3. The script's `unzip -p` therefore runs for real: extraction
        # is part of what can break, so stubbing it away would leave the most
        # fragile step untested.
        if [ -f "$GH_FIXTURES/review-target.txt" ]; then
            python3 -c 'import sys,zipfile,io
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z:
    z.write(sys.argv[1], "review-target.txt")
sys.stdout.buffer.write(buf.getvalue())' "$GH_FIXTURES/review-target.txt"
            exit 0
        fi
        exit 1
        ;;
    */commits/*/check-runs) key="check-runs" ;;
    */issues/*/comments) key="comments" ;;
    */compare/*) key="compare" ;;
    */pulls/*) key="pull" ;;
    *)
        echo "fake gh: unrouted path: $path" >&2
        exit 3
        ;;
esac

file="$GH_FIXTURES/$key.json"
if [ ! -f "$file" ]; then
    echo "fake gh: missing fixture $file" >&2
    exit 4
fi
if [ -n "$jqexpr" ]; then
    jq -r "$jqexpr" "$file"
else
    cat "$file"
fi
FAKE
    chmod +x "$dir/bin/gh"
}

# write_hygiene <dir> <rc-threads> <rc-comments> <rc-reports>
write_hygiene() {
    local dir="$1" a="$2" b="$3" c="$4"
    mkdir -p "$dir/hygiene"
    local names=(check-resolved-threads.sh check-review-comments.sh check-review-report-replies.sh)
    local rcs=("$a" "$b" "$c")
    local i
    for i in 0 1 2; do
        cat >"$dir/hygiene/${names[$i]}" <<EOF
#!/bin/bash
echo "stub ${names[$i]} for PR \${PR_NUMBER:-?}"
exit ${rcs[$i]}
EOF
        chmod +x "$dir/hygiene/${names[$i]}"
    done
}

marker_comment() {
    local sha="$1"
    jq -n --arg sha "$sha" \
        '{id: 1, user: {login: "github-actions[bot]"},
          body: ("<!-- claude-reviewed: " + $sha + " -->\nAutomated Claude review completed.")}'
}

# report_comments <n>  -- n finished review reports, in the shape both this
# script and claude-review-gate.sh count against the cap.
report_comments() {
    local n="$1" i out="[]"
    for ((i = 1; i <= n; i++)); do
        out="$(jq --argjson id "$((100 + i))" \
            '. + [{id: $id, user: {login: "github-actions[bot]"},
                   body: "**Claude finished** the review.\n### Review\nlooks fine"}]' <<<"$out")"
    done
    echo "$out"
}

# Spent review passes: budget burned, NOTHING posted. Counted against the same cap
# as a posted report, because the cost is identical.
attempt_comments() {
    local n="$1" i out="[]"
    for ((i = 1; i <= n; i++)); do
        out="$(jq --argjson id "$((200 + i))" \
            '. + [{id: $id, user: {login: "github-actions[bot]"},
                   body: "<!-- claude-review-attempt: deadbeef -->\nburned its turns"}]' <<<"$out")"
    done
    echo "$out"
}

# setup <TEMP> -- default world: open non-draft PR #42, head NEW_SHA, marker on
# NEW_SHA, no reports, all hygiene green.
setup() {
    local t="$1"
    mkdir -p "$t/fixtures"
    write_fake_gh "$t"
    write_hygiene "$t" 0 0 0
    printf '%s\n' \
        '[submodule "private/renet"]' \
        '	path = private/renet' \
        '	url = git@github.com:rediacc/renet.git' \
        '[submodule "private/account"]' \
        '	path = private/account' \
        '	url = git@github.com:rediacc/account.git' >"$t/.gitmodules"

    echo '[{"number": 42, "state": "open"}]' >"$t/fixtures/commit-pulls.json"
    jq -n --arg sha "$NEW_SHA" '{state: "open", draft: false, head: {sha: $sha}}' \
        >"$t/fixtures/pull.json"
    marker_comment "$NEW_SHA" | jq -s '.' >"$t/fixtures/comments.json"
    echo '{"files": []}' >"$t/fixtures/compare.json"
    echo '{"check_runs": []}' >"$t/fixtures/check-runs.json"
    # Default: a small PR, so the default review budget is the smallest tier.
    echo '{"additions": 100, "deletions": 40}' >"$t/fixtures/pr-size.json"
}

# pr_size <dir> <additions> <deletions> -- resize the PR the fake gh reports.
pr_size() {
    printf '{"additions": %s, "deletions": %s}\n' "$2" "$3" >"$1/fixtures/pr-size.json"
}

# run_status <TEMP> [KEY=VALUE ...] -- runs the script under the fake world.
run_status() {
    local t="$1"
    shift
    local rc=0
    LAST_OUT="$(cd "$t" && env \
        PATH="$t/bin:$PATH" \
        GH_FIXTURES="$t/fixtures" \
        GH_CAPTURE="$t/capture.txt" \
        GH_TOKEN=fake \
        GITHUB_REPOSITORY=rediacc/console \
        REVIEW_STATUS_HYGIENE_DIR="$t/hygiene" \
        NO_COLOR=1 \
        "$@" \
        bash "$UNDER_TEST" 2>&1)" || rc=$?
    LAST_RC="$rc"
    return 0
}

# posted <TEMP> <jq-path> -- field of the captured check-run payload.
posted() {
    local t="$1" expr="$2"
    sed -n '/^METHOD=/,$p' "$t/capture.txt" | sed '1d' | jq -r "$expr"
}

captured_method() {
    # `[ -f ]` guard, not an assumption: a test that asserts NOTHING was posted
    # leaves no capture file at all, and sed erroring on the missing path would
    # make "correctly silent" look like a harness fault.
    [ -f "$1/capture.txt" ] || return 0
    sed -n 's/^METHOD=\([A-Z]*\) .*/\1/p' "$1/capture.txt" | tail -n 1
}

# ---------------------------------------------------------------------------
# Anti-vacuity: the marker prefix must still be parseable out of the real gate
# script, and the review cap must come from ONE shared table.
#
# The cap used to be a constant sed-parsed out of the gate script. It is now
# sized to the diff by review_cap_for() in ../lib/common.sh, which both review
# scripts source. That is a stronger contract, not a weaker one: sed-parsing a
# number out of a sibling file was always one edit away from the two scripts
# disagreeing, and disagreement is precisely the deadlock this suite exists to
# prevent. So this asserts the SHARED function exists and that both scripts see
# identical values for it.
# ---------------------------------------------------------------------------
test_real_gate_constants_parseable() {
    local marker
    marker="$(sed -n "s/^MARKER_PREFIX='\(.*\)'[[:space:]]*$/\1/p" "$REAL_GATE")"
    assert_eq "$marker" '<!-- claude-reviewed:' "marker prefix parsed from the real gate script"

    # shellcheck source=../../lib/common.sh
    # BLOCKER: the shared review-budget table both review scripts depend on
    source "$REPO_ROOT/.ci/scripts/lib/common.sh"
    if ! declare -F review_cap_for >/dev/null; then
        log_fail "review_cap_for() is missing from .ci/scripts/lib/common.sh"
        return
    fi
    # The operator's tiers, asserted at their boundaries so an off-by-one in the
    # comparison cannot pass. A cap that only ever returns its default would
    # satisfy a single-value check.
    assert_eq "$(review_cap_for 0)" "3" "an empty diff gets the smallest budget"
    assert_eq "$(review_cap_for 10000)" "3" "10k lines is still 3 reviews"
    assert_eq "$(review_cap_for 10001)" "5" "just over 10k moves to 5"
    assert_eq "$(review_cap_for 50000)" "5" "50k lines is still 5 reviews"
    assert_eq "$(review_cap_for 50001)" "7" "just over 50k moves to 7"
    assert_eq "$(review_cap_for 250000)" "7" "a huge diff stays at 7, it does not keep growing"
    assert_eq "$(review_cap_for abc)" "3" "an unreadable size falls to the SMALLEST budget, never a larger one"
    log_pass "review budget comes from one shared table and honours every tier boundary"
}

# ---------------------------------------------------------------------------
# Too loud: healthy states must not fail
# ---------------------------------------------------------------------------
test_current_head_succeeds() {
    local t="$1"
    setup "$t"
    run_status "$t" EVENT_NAME=pull_request_review PR_NUMBER=42
    assert_exit_code 0 "$LAST_RC" "healthy PR must not error"
    assert_eq "$(posted "$t" '.conclusion')" success "current marker + clean hygiene"
    assert_eq "$(posted "$t" '.head_sha')" "$NEW_SHA" "check-run anchored to the PR head"
    assert_eq "$(captured_method "$t")" POST "no existing check-run means create"
    log_pass "current head + clean hygiene => success on the head SHA"
}

test_empty_diff_succeeds() {
    local t="$1"
    setup "$t"
    marker_comment "$OLD_SHA" | jq -s '.' >"$t/fixtures/comments.json"
    echo '{"files": []}' >"$t/fixtures/compare.json"
    run_status "$t" EVENT_NAME=pull_request_review PR_NUMBER=42
    assert_eq "$(posted "$t" '.conclusion')" success "empty diff since the reviewed SHA is equivalent"
    log_pass "stale marker with an EMPTY diff => success"
}

test_gitlink_only_succeeds() {
    local t="$1"
    setup "$t"
    marker_comment "$OLD_SHA" | jq -s '.' >"$t/fixtures/comments.json"
    echo '{"files": [{"filename": "private/renet"}, {"filename": "private/account"}]}' \
        >"$t/fixtures/compare.json"
    run_status "$t" EVENT_NAME=pull_request_review PR_NUMBER=42
    assert_eq "$(posted "$t" '.conclusion')" success "submodule pointer bumps are not reviewable code"
    assert_contains "$(posted "$t" '.output.summary')" "only submodule pointer bumps" \
        "summary says why it passed"
    log_pass "stale marker with a GITLINK-ONLY diff => success"
}

test_cancelled_review_run_is_not_a_failure() {
    local t="$1"
    setup "$t"
    # The PR handoff Claude Review now uploads; without it the resolver is
    # correctly silent, so every workflow_run test needs it to reach the
    # behaviour it is actually asserting.
    echo '{"artifacts": [{"id": 42, "name": "review-target"}]}' >"$t/fixtures/run-artifacts.json"
    echo "42" >"$t/fixtures/review-target.txt"
    run_status "$t" EVENT_NAME=workflow_run WR_RUN_ID=4242 WR_CONCLUSION=cancelled \
        WR_HTML_URL=https://example.invalid/run/1
    assert_eq "$(posted "$t" '.conclusion')" success \
        "a superseded (cancelled) review run must not fail the head"
    log_pass "cancelled Claude Review run => success (cancel-in-progress is by design)"
}

test_draft_is_neutral() {
    local t="$1"
    setup "$t"
    jq -n --arg sha "$NEW_SHA" '{state: "open", draft: true, head: {sha: $sha}}' \
        >"$t/fixtures/pull.json"
    run_status "$t" EVENT_NAME=pull_request_review PR_NUMBER=42
    assert_eq "$(posted "$t" '.conclusion')" neutral "a draft PR is not expected to be reviewed"
    log_pass "draft PR => neutral"
}

# ---------------------------------------------------------------------------
# Too quiet: PLANTED DEFECTS that must FIRE
# ---------------------------------------------------------------------------
test_stale_head_fails() {
    local t="$1"
    setup "$t"
    marker_comment "$OLD_SHA" | jq -s '.' >"$t/fixtures/comments.json"
    echo '{"files": [{"filename": "packages/cli/src/commands/repo.ts"}]}' \
        >"$t/fixtures/compare.json"
    run_status "$t" EVENT_NAME=pull_request_review PR_NUMBER=42
    assert_exit_code 0 "$LAST_RC" "a failing verdict is still a successful report"
    assert_eq "$(posted "$t" '.conclusion')" failure "real code changed since the reviewed SHA"
    local summary
    summary="$(posted "$t" '.output.summary')"
    assert_contains "$summary" "$NEW_SHA" "failure names the head SHA"
    assert_contains "$summary" "$OLD_SHA" "failure names the reviewed SHA"
    log_pass "PLANTED stale marker => FAILURE naming both SHAs"
}

test_unreviewed_head_fails() {
    local t="$1"
    setup "$t"
    echo '[]' >"$t/fixtures/comments.json"
    run_status "$t" EVENT_NAME=pull_request_review PR_NUMBER=42
    assert_eq "$(posted "$t" '.conclusion')" failure "no marker at all means nothing was reviewed"
    assert_contains "$(posted "$t" '.output.summary')" "no reviewed-SHA marker" "failure says why"
    log_pass "PLANTED missing marker => FAILURE"
}

test_wrong_marker_prefix_is_seen_as_unreviewed() {
    local t="$1"
    setup "$t"
    # A marker written under a DIFFERENT prefix must not be honoured -- this is
    # the shape a drifted MARKER_PREFIX would take.
    jq -n --arg sha "$NEW_SHA" \
        '[{id: 1, user: {login: "github-actions[bot]"},
           body: ("<!-- reviewed-by-somebody: " + $sha + " -->")}]' \
        >"$t/fixtures/comments.json"
    run_status "$t" EVENT_NAME=pull_request_review PR_NUMBER=42
    assert_eq "$(posted "$t" '.conclusion')" failure "a foreign marker prefix proves nothing"
    log_pass "PLANTED foreign marker prefix => FAILURE"
}

test_failed_review_run_fails() {
    local t="$1"
    setup "$t"
    # The PR handoff Claude Review now uploads; without it the resolver is
    # correctly silent, so every workflow_run test needs it to reach the
    # behaviour it is actually asserting.
    echo '{"artifacts": [{"id": 42, "name": "review-target"}]}' >"$t/fixtures/run-artifacts.json"
    echo "42" >"$t/fixtures/review-target.txt"
    run_status "$t" EVENT_NAME=workflow_run WR_RUN_ID=4242 WR_CONCLUSION=failure \
        WR_HTML_URL=https://example.invalid/run/7
    assert_eq "$(posted "$t" '.conclusion')" failure "the review produced no verdict"
    assert_contains "$(posted "$t" '.output.summary')" "https://example.invalid/run/7" \
        "failure links the run that failed"
    log_pass "PLANTED failed Claude Review run => FAILURE with a link"
}

test_hygiene_failure_fails() {
    local t="$1"
    setup "$t"
    write_hygiene "$t" 0 1 0
    run_status "$t" EVENT_NAME=issue_comment PR_NUMBER=42
    assert_eq "$(posted "$t" '.conclusion')" failure "an unreplied review comment must block"
    assert_contains "$(posted "$t" '.output.summary')" "check-review-comments.sh" \
        "failure names the script that failed"
    log_pass "PLANTED hygiene failure => FAILURE naming the script"
}

test_compare_failure_fails_closed() {
    local t="$1"
    setup "$t"
    marker_comment "$OLD_SHA" | jq -s '.' >"$t/fixtures/comments.json"
    rm -f "$t/fixtures/compare.json" # compare API unavailable
    run_status "$t" EVENT_NAME=pull_request_review PR_NUMBER=42
    assert_eq "$(posted "$t" '.conclusion')" failure "unproven equivalence is not equivalence"
    assert_contains "$(posted "$t" '.output.summary')" "compare API failed" "failure says why"
    log_pass "PLANTED compare-API failure => FAILURE (fails closed)"
}

test_missing_hygiene_dir_hard_fails() {
    local t="$1"
    setup "$t"
    rm -f "$t/hygiene/check-review-report-replies.sh"
    run_status "$t" EVENT_NAME=pull_request_review PR_NUMBER=42
    if [[ "$LAST_RC" -eq 0 ]]; then
        log_fail "a missing hygiene script must abort, not silently reduce the check to currency only"
    fi
    assert_contains "$LAST_OUT" "hygiene script missing" "the abort says what is missing"
    log_pass "PLANTED missing hygiene script => hard exit $LAST_RC (anti-vacuity)"
}

test_unparseable_constants_hard_fail() {
    local t="$1"
    setup "$t"
    # The MARKER renamed, as a drifting refactor would leave it. The cap is no
    # longer parsed from this file (it comes from the shared review_cap_for()),
    # but the marker still is, and a silent default there would make the gate
    # compare against a prefix nothing ever posts.
    printf '%s\n' "MARKER='<!-- claude-reviewed:'" >"$t/fake-gate.sh"
    run_status "$t" EVENT_NAME=pull_request_review PR_NUMBER=42 \
        REVIEW_STATUS_GATE_SCRIPT="$t/fake-gate.sh"
    if [[ "$LAST_RC" -eq 0 ]]; then
        log_fail "an unparseable marker must abort, never fall back to a hard-coded default"
    fi
    assert_contains "$LAST_OUT" "could not parse" "the abort names the parse it could not do"
    log_pass "PLANTED renamed constant => hard exit $LAST_RC instead of a silent default"
}

# ---------------------------------------------------------------------------
# The deadlock guard, driven in BOTH directions so the cap number is proven
# load-bearing rather than incidental.
# ---------------------------------------------------------------------------
test_cap_reached_warns_instead_of_deadlocking() {
    local t="$1"
    setup "$t"
    marker_comment "$OLD_SHA" | jq -s '.' >"$t/comments-marker.json"
    report_comments 3 >"$t/comments-reports.json"
    jq -s 'add' "$t/comments-marker.json" "$t/comments-reports.json" >"$t/fixtures/comments.json"
    echo '{"files": [{"filename": "packages/cli/src/commands/repo.ts"}]}' \
        >"$t/fixtures/compare.json"
    # BOTH prefixes: review-status.sh parses ATTEMPT_PREFIX as well now, because the
    # cap counts posted reports PLUS spent attempts. It REFUSES TO RUN without it,
    # deliberately -- a missing prefix reads the cap LOW and silently recreates the
    # deadlock this very test asserts against. A stub carrying only MARKER_PREFIX
    # therefore exits before posting, which is exactly what this fixture used to do.
    printf '%s\n' "MARKER_PREFIX='<!-- claude-reviewed:'" \
        "ATTEMPT_PREFIX='<!-- claude-review-attempt:'" >"$t/gate-cap3.sh"
    pr_size "$t" 900 100 # 1,000 lines -> smallest tier, cap 3

    run_status "$t" EVENT_NAME=pull_request_review PR_NUMBER=42 \
        REVIEW_STATUS_GATE_SCRIPT="$t/gate-cap3.sh"
    assert_eq "$(posted "$t" '.conclusion')" success \
        "cap reached + stale marker must stay mergeable"
    assert_contains "$(posted "$t" '.output.summary')" "REVIEW CAP REACHED" \
        "the pass is loud, not silent"
    log_pass "cap reached + stale marker => success WITH A WARNING (no permanent block)"
}

# THE SHAPE THAT ACTUALLY HAPPENED, and that the case above cannot see. PR #553 hit
# its cap with ZERO posted reports and THREE spent attempts -- three reviews that
# burned their turn budget and posted nothing. review-status.sh counted posted
# reports alone, read 0/3, concluded the cap was NOT reached, and posted a REQUIRED
# failure, leaving a green, ready, thread-clean PR permanently unmergeable: exactly
# what the guard above exists to prevent. The sibling case passes under EITHER
# numerator, because 3 posted reports look identical to both.
test_cap_reached_by_spent_attempts_alone() {
    local t="$1"
    setup "$t"
    marker_comment "$OLD_SHA" | jq -s '.' >"$t/comments-marker.json"
    attempt_comments 3 >"$t/comments-attempts.json"
    jq -s 'add' "$t/comments-marker.json" "$t/comments-attempts.json" >"$t/fixtures/comments.json"
    echo '{"files": [{"filename": "packages/cli/src/commands/repo.ts"}]}' \
        >"$t/fixtures/compare.json"
    printf '%s\n' "MARKER_PREFIX='<!-- claude-reviewed:'" \
        "ATTEMPT_PREFIX='<!-- claude-review-attempt:'" >"$t/gate-cap3.sh"
    pr_size "$t" 900 100 # 1,000 lines -> smallest tier, cap 3

    run_status "$t" EVENT_NAME=pull_request_review PR_NUMBER=42 \
        REVIEW_STATUS_GATE_SCRIPT="$t/gate-cap3.sh"
    assert_eq "$(posted "$t" '.conclusion')" success \
        "cap reached by SPENT attempts alone must stay mergeable (the #553 deadlock)"
    assert_contains "$(posted "$t" '.output.summary')" "REVIEW CAP REACHED" \
        "the pass is loud here too"
    log_pass "0 posted + 3 spent => cap reached => success WITH A WARNING"
}

test_below_cap_the_same_state_fails() {
    local t="$1"
    setup "$t"
    marker_comment "$OLD_SHA" | jq -s '.' >"$t/comments-marker.json"
    report_comments 3 >"$t/comments-reports.json"
    jq -s 'add' "$t/comments-marker.json" "$t/comments-reports.json" >"$t/fixtures/comments.json"
    echo '{"files": [{"filename": "packages/cli/src/commands/repo.ts"}]}' \
        >"$t/fixtures/compare.json"
    # Identical world, cap raised: the warning must become a failure. If it does
    # not, the cap value is not actually being read.
    # BOTH prefixes: review-status.sh parses ATTEMPT_PREFIX as well now, because the
    # cap counts posted reports PLUS spent attempts. It REFUSES TO RUN without it,
    # deliberately -- a missing prefix reads the cap LOW and silently recreates the
    # deadlock this very test asserts against. A stub carrying only MARKER_PREFIX
    # therefore exits before posting, which is exactly what this fixture used to do.
    printf '%s\n' "MARKER_PREFIX='<!-- claude-reviewed:'" \
        "ATTEMPT_PREFIX='<!-- claude-review-attempt:'" >"$t/gate-cap9.sh"
    # THE POINT OF THE TIERS: identical review count, different verdict, purely
    # because the diff is large enough to earn a bigger budget.
    pr_size "$t" 60000 10000 # 70,000 lines -> top tier, cap 7

    run_status "$t" EVENT_NAME=pull_request_review PR_NUMBER=42 \
        REVIEW_STATUS_GATE_SCRIPT="$t/gate-cap9.sh"
    assert_eq "$(posted "$t" '.conclusion')" failure \
        "below the cap the same stale state must fail"
    assert_not_contains "$(posted "$t" '.output.summary')" "REVIEW CAP REACHED" \
        "no cap warning below the cap"
    log_pass "same state with the cap raised => FAILURE (the parsed cap is load-bearing)"
}

# ---------------------------------------------------------------------------
# SHA-awareness -- the property `Review Gate` structurally cannot have
# ---------------------------------------------------------------------------
test_anchors_to_current_head_not_event_sha() {
    local t="$1"
    setup "$t"
    # The event carries the OLD sha (a late-finishing run for a superseded
    # push); the PR has moved on. The verdict must be posted against the PR's
    # CURRENT head, and must report that head as unreviewed.
    marker_comment "$OLD_SHA" | jq -s '.' >"$t/fixtures/comments.json"
    echo '{"files": [{"filename": "packages/cli/src/commands/repo.ts"}]}' \
        >"$t/fixtures/compare.json"
    # The PR handoff Claude Review now uploads; without it the resolver is
    # correctly silent, so every workflow_run test needs it to reach the
    # behaviour it is actually asserting.
    echo '{"artifacts": [{"id": 42, "name": "review-target"}]}' >"$t/fixtures/run-artifacts.json"
    echo "42" >"$t/fixtures/review-target.txt"
    run_status "$t" EVENT_NAME=workflow_run WR_RUN_ID=4242 WR_CONCLUSION=success \
        WR_HTML_URL=https://example.invalid/run/9
    assert_eq "$(posted "$t" '.head_sha')" "$NEW_SHA" \
        "the check-run is anchored to the PR head, not the event's SHA"
    assert_eq "$(posted "$t" '.conclusion')" failure "the current head is unreviewed"
    log_pass "check-run anchors to the PR's CURRENT head, not the triggering event's SHA"
}

test_existing_check_run_is_patched() {
    local t="$1"
    setup "$t"
    jq -n '{check_runs: [{id: 555, app: {slug: "github-actions"}}]}' >"$t/fixtures/check-runs.json"
    run_status "$t" EVENT_NAME=pull_request_review PR_NUMBER=42
    assert_eq "$(captured_method "$t")" PATCH "an existing check-run is updated, not duplicated"
    assert_contains "$(sed -n 's/^METHOD=[A-Z]* PATH=//p' "$t/capture.txt")" \
        "check-runs/555" "the PATCH targets the existing run"
    assert_eq "$(posted "$t" '.head_sha // "absent"')" absent \
        "head_sha is not a PATCH field and must be stripped"
    log_pass "existing check-run => PATCH without head_sha (no per-comment duplicates)"
}

# ---------------------------------------------------------------------------
# ACYCLICITY -- the invariant that keeps this out of CI's dependency graph.
# ---------------------------------------------------------------------------
test_no_ci_job_references_review_complete() {
    # CONTROL A, planted first: a genuine dependency on the context (a
    # `needs` or `if` style reference, anywhere other than the two
    # documented exceptions below) must still be caught.
    local t control_hits
    t="$(mktemp -d)"
    trap 'rm -rf "$t"' RETURN
    printf 'jobs:\n  bad:\n    if: needs.review.outputs.context == '"'"'Review Complete'"'"'\n' >"$t/planted.yml"
    control_hits="$(grep -n "Review Complete" "$t/planted.yml" |
        grep -v ':.*WATCHDOG_EXCLUDE_PATTERNS:.*Review Complete' || true)"
    [[ -n "$control_hits" ]] || log_fail "CONTROL A failed: a genuine dependency reference on 'Review Complete' was not caught by the narrowed grep below"

    # CONTROL B, review finding 2026-08-01 (PR #550): an EXECUTABLE line
    # inside a file NAMED watchdog-monitor.yml must still be caught by the
    # exact production filter chain -- the comment-line exemption below
    # must not widen into "the whole file is exempt".
    mkdir -p "$t/wf"
    printf 'jobs:\n  bad:\n    if: needs.review.outputs.context == '"'"'Review Complete'"'"'\n' \
        >"$t/wf/watchdog-monitor.yml"
    control_hits="$(grep -rn "Review Complete" "$t/wf" --include='*.yml' |
        grep -v '^.*review-status.yml' |
        grep -v ':.*WATCHDOG_EXCLUDE_PATTERNS:.*Review Complete' |
        grep -vE '^[^:]*watchdog-monitor\.yml:[0-9]+: *#' || true)"
    [[ -n "$control_hits" ]] || log_fail "CONTROL B failed: an executable reference inside watchdog-monitor.yml itself was swallowed by the comment-line exemption"

    # The real assertion. TWO narrow, documented exceptions, both scoped to
    # watchdog-monitor.yml specifically:
    #   1. The WATCHDOG_EXCLUDE_PATTERNS line, which EXCLUDES 'Review
    #      Complete' from the watchdog's failure scan -- the opposite of a
    #      dependency. Verified live 2026-07-31 (run 30660765759, raw
    #      `GET .../actions/runs/{id}/jobs`): the check-run this script
    #      posts is genuinely attributed to the SAME run_id as an unrelated
    #      Console CI run (both ride the github-actions app's shared
    #      check_suite for that head SHA), so the watchdog's per-run job
    #      listing sees it and MUST be told to ignore it, or a
    #      not-yet-re-reviewed head deadlocks the very run that would
    #      re-review it.
    #   2. Comment lines (matched by content, `# ...`, never by wording) in
    #      that same file explaining the exclusion above. Review finding
    #      2026-08-01 (PR #550): the first version of this gate exempted
    #      exactly ONE line by content match, and the explanatory comment
    #      one line above it survived only by ACCIDENT -- it happens to
    #      also contain the substring "review-status.yml", which the
    #      OLDER, unrelated exemption below (meant for review-status.yml's
    #      own self-references) also matches. A comment reword that keeps
    #      the same meaning but drops that one substring would have flipped
    #      this gate red for no functional reason, and CONTROL A alone
    #      could not catch it (it only plants a synthetic executable
    #      reference, never a comment). Comments cannot create a real
    #      `needs`/`if` coupling in GitHub Actions' dependency graph, so
    #      exempting them by shape is sound, not just convenient.
    # Neither exception applies outside watchdog-monitor.yml.
    local hits
    hits="$(grep -rn "Review Complete" "$REPO_ROOT/.github/workflows" \
        --include='*.yml' |
        grep -v '^.*review-status.yml' |
        grep -v ':.*WATCHDOG_EXCLUDE_PATTERNS:.*Review Complete' |
        grep -vE '^[^:]*watchdog-monitor\.yml:[0-9]+: *#' || true)"
    if [[ -n "$hits" ]]; then
        log_fail "a workflow other than review-status.yml references 'Review Complete' outside the documented watchdog exceptions -- that is a cycle:
$hits"
    fi
    if ! grep -q 'Review Complete' "$REPO_ROOT/.ci/scripts/review/review-status.sh"; then
        log_fail "review-status.sh no longer names the check it posts; this acyclicity check went blind"
    fi
    log_pass "no workflow but review-status.yml mentions the 'Review Complete' context, apart from the documented watchdog exceptions"
}

test_workflow_does_not_trigger_on_pull_request() {
    local wf="$REPO_ROOT/.github/workflows/review-status.yml"
    # `pull_request` would run the PR's OWN copy of this workflow, letting a PR
    # edit the logic that judges it. All four real triggers run the default
    # branch copy.
    if grep -qE '^  pull_request:[[:space:]]*$' "$wf"; then
        log_fail "review-status.yml triggers on pull_request; a PR could then edit its own judge"
    fi
    local ev
    for ev in "workflow_run:" "pull_request_review:" "pull_request_review_comment:" "issue_comment:"; do
        grep -q "^  $ev" "$wf" || log_fail "review-status.yml lost its '$ev' trigger"
    done
    grep -q 'checks: write' "$wf" || log_fail "review-status.yml cannot post a check-run without checks: write"
    log_pass "workflow keeps its four default-branch triggers and never uses pull_request"
}

# ---------------------------------------------------------------------------
# workflow_dispatch -- closes the head-SHA gap a workflow_run event hits when
# Claude Review was itself invoked via workflow_dispatch (its head_sha is the
# dispatch ref, e.g. main, never the PR head -- documented GitHub Actions
# behavior). See agent/PLAN-github-actions-workflow-run-trigger-fix.md.
# ---------------------------------------------------------------------------
test_workflow_dispatch_resolves_pr_directly() {
    local t="$1"
    setup "$t"
    # No commit-pulls fixture entry needed at all for this path -- the whole
    # point is EVENT_NAME=workflow_dispatch must never call commits/.../pulls.
    echo '[]' >"$t/fixtures/commit-pulls.json"
    run_status "$t" EVENT_NAME=workflow_dispatch PR_NUMBER=42
    assert_exit_code 0 "$LAST_RC" "workflow_dispatch must resolve without a commit->PR lookup"
    assert_eq "$(posted "$t" '.conclusion')" success "current marker + clean hygiene, same as any other entry point"
    assert_eq "$(posted "$t" '.head_sha')" "$NEW_SHA" "check-run anchored to the PR's live head, not any dispatch ref"
    log_pass "workflow_dispatch (PLANTED: empty commit-pulls) still resolves PR #42 via PR_NUMBER"
}

# THIS TEST USED TO ASSERT THE BUG AS THE SPECIFICATION.
#
# It was `test_workflow_run_with_unassociated_sha_reports_nothing`, and it drove
# EVENT_NAME=workflow_run with main's SHA expecting silent success -- codifying
# the exact no-op that left the REQUIRED `Review Complete` check unposted on
# every PR. Its log line even argued the lookup could not be fixed and a
# separate dispatch path was the answer. Measured 2026-08-06: that arm had never
# resolved a PR in production, so the suite was green on a path that never
# worked.
#
# The three tests below replace it, and they split the case the old one
# conflated: no artifact (a push to main, legitimately PR-less) must stay
# silent, while an artifact that exists and cannot be honoured must be LOUD.
test_workflow_run_without_artifact_is_silent() {
    local t="$1"
    setup "$t"
    # No review-target artifact: the triggering run had no PR. This is the
    # main-push case and silence is correct -- reddening it would redden every
    # push to main.
    echo '{"artifacts": []}' >"$t/fixtures/run-artifacts.json"
    run_status "$t" EVENT_NAME=workflow_run WR_RUN_ID=9001 WR_CONCLUSION=success \
        WR_HTML_URL=https://example.invalid/run/9001
    assert_exit_code 0 "$LAST_RC" "a PR-less triggering run is a no-op, not an error"
    assert_eq "$(captured_method "$t")" "" "nothing is posted when no review-target artifact exists"
    log_pass "workflow_run with no artifact stays silent (main-push safe)"
}

test_workflow_run_with_artifact_posts_the_check() {
    local t="$1"
    setup "$t"
    # The artifact names PR 42, which setup() wires as open at NEW_SHA.
    echo '{"artifacts": [{"id": 77, "name": "review-target"}]}' >"$t/fixtures/run-artifacts.json"
    echo "42" >"$t/fixtures/review-target.txt"
    run_status "$t" EVENT_NAME=workflow_run WR_RUN_ID=9002 WR_CONCLUSION=success \
        WR_HTML_URL=https://example.invalid/run/9002
    assert_exit_code 0 "$LAST_RC" "a resolvable PR reports normally"
    assert_eq "$(captured_method "$t")" "POST" "FIRE: the check-run is posted for the handed-over PR"
    assert_eq "$(posted "$t" '.head_sha')" "$NEW_SHA" "anchored to the PR's live head, not the triggering run's"
    log_pass "FIRE: workflow_run resolves the PR from the artifact and posts (the case that never worked)"
}

test_workflow_run_with_unhonourable_artifact_is_loud() {
    local t="$1"
    setup "$t"
    # The artifact EXISTS but carries no PR number. Under the old code every
    # failure to resolve exited 0; here presence makes it binding, so this must
    # be a non-zero exit rather than another silent success.
    echo '{"artifacts": [{"id": 78, "name": "review-target"}]}' >"$t/fixtures/run-artifacts.json"
    printf '\n' >"$t/fixtures/review-target.txt"
    run_status "$t" EVENT_NAME=workflow_run WR_RUN_ID=9003 WR_CONCLUSION=success \
        WR_HTML_URL=https://example.invalid/run/9003
    assert_exit_code 1 "$LAST_RC" "an artifact that cannot be honoured is a REPORTER failure, not silence"
    assert_eq "$(captured_method "$t")" "" "nothing is posted when the handoff is malformed"
    log_pass "CONTROL: the loud path is reachable -- a present-but-empty artifact exits non-zero"
}

test_workflow_dispatch_requires_pr_number() {
    local t="$1"
    setup "$t"
    run_status "$t" EVENT_NAME=workflow_dispatch
    if [[ "$LAST_RC" -eq 0 ]]; then
        log_fail "workflow_dispatch without PR_NUMBER must abort, not silently report nothing"
    fi
    assert_contains "$LAST_OUT" "PR_NUMBER" "the abort names the missing var"
    log_pass "PLANTED missing PR_NUMBER on workflow_dispatch => hard exit"
}

# ---------------------------------------------------------------------------
# F2 -- a hygiene-only failure (head genuinely reviewed, a hygiene script
# failed) must read differently in the check-run TITLE than a never-reviewed
# head, so the checks list communicates the right next action on its own.
# ---------------------------------------------------------------------------
test_hygiene_only_failure_title_says_reviewed() {
    local t="$1"
    setup "$t"               # marker already on NEW_SHA (current head) by default
    write_hygiene "$t" 0 1 0 # check-review-comments.sh fails; currency stays true
    run_status "$t" EVENT_NAME=pull_request_review PR_NUMBER=42
    assert_eq "$(posted "$t" '.conclusion')" failure "hygiene failure still fails the check"
    assert_eq "$(posted "$t" '.output.title')" "Reviewed, but needs attention (see failures)" \
        "title distinguishes a reviewed-but-unaddressed head from a never-reviewed one"
    log_pass "PLANTED hygiene failure on a CURRENT-head PR => title says 'Reviewed, but needs attention'"
}

test_unreviewed_head_title_unchanged() {
    local t="$1"
    setup "$t"
    echo '[]' >"$t/fixtures/comments.json" # CONTROL: no marker at all
    run_status "$t" EVENT_NAME=pull_request_review PR_NUMBER=42
    assert_eq "$(posted "$t" '.conclusion')" failure "still fails"
    assert_eq "$(posted "$t" '.output.title')" "Review is not complete for this head" \
        "CONTROL: a genuinely unreviewed head keeps the original title"
    log_pass "CONTROL: unreviewed head keeps 'Review is not complete for this head', unaffected by F2"
}

# ===========================================================================
# check-review-comments.sh -- the TOP-LEVEL review summary.
#
# The tests above stub the three hygiene scripts, so nothing here had ever
# driven the real one. That mattered: until 2026-08-05 check-review-comments.sh
# read ONLY repos/{REPO}/pulls/{PR}/comments (the inline review threads), and
# the review's actual verdict is posted as a TOP-LEVEL comment on
# repos/{REPO}/issues/{PR}/comments. So the reviewer could post a full verdict
# with findings, nobody answer it, and this gate report the PR clean.
#
# Live proof, PR #551: issue comment 5189236393, github-actions[bot], 8141
# chars, opening "## Review verdict: approve with one correctness finding to
# fix", sat unanswered while the Review Gate went green.
#
# These cases drive the REAL script (no stub) against a routing fake `gh`,
# separate from the one above so the review-status fixtures stay untouched --
# the review-status fake maps `*/pulls/*` to the PR object, which is the wrong
# body for the inline-comments endpoint.
# ===========================================================================

REVIEW_COMMENTS_GATE="$REPO_ROOT/.ci/scripts/quality/check-review-comments.sh"

# The needle the gate keys off to recognise a review summary, and the file that
# must keep emitting it. Asserted below so the two cannot silently drift apart.
FINDINGS_FENCE_KEY="json:review-findings"

write_fake_gh_comments() {
    local dir="$1"
    mkdir -p "$dir/bin"
    cat >"$dir/bin/gh" <<'FAKE'
#!/bin/bash
# Routing fake for the two comment endpoints check-review-comments.sh reads.
# Anything else is an error, never an empty list: a silently-served [] is the
# exact shape of blindness these tests exist to catch.
set -uo pipefail
# GH_FAIL_ISSUE_COMMENTS=1 makes the REST issues route fail the way a degraded
# API does. It exists so the GraphQL fallback in check-review-report-replies.sh
# can be exercised WITHOUT depending on GitHub actually being unwell -- a test
# that waited for a real outage would never run, and one that hit the live API
# would be flaky by construction.
for a in "$@"; do
    case "$a" in
        graphql)
            [ -f "$GH_FIXTURES/graphql-comments.json" ] || { echo "missing graphql-comments fixture" >&2; exit 4; }
            exec cat "$GH_FIXTURES/graphql-comments.json" ;;
        */issues/*/comments)
            if [ "${GH_FAIL_ISSUE_COMMENTS:-0}" = "1" ]; then
                echo '{"message":"Not Found","status":"404"}' >&2
                echo "gh: Not Found (HTTP 404)" >&2
                exit 1
            fi
            [ -f "$GH_FIXTURES/issue-comments.json" ] || { echo "missing issue-comments fixture" >&2; exit 4; }
            exec cat "$GH_FIXTURES/issue-comments.json" ;;
        */pulls/*/comments)
            [ -f "$GH_FIXTURES/inline-comments.json" ] || { echo "missing inline-comments fixture" >&2; exit 4; }
            exec cat "$GH_FIXTURES/inline-comments.json" ;;
    esac
done
echo "fake gh: unrouted: $*" >&2
exit 3
FAKE
    chmod +x "$dir/bin/gh"
}

# summary_comment <id> <created_at> [body-override]
# The real shape: bot author, plus the machine-readable findings fence that
# claude-review-gate.sh --post-findings uses to locate this very comment.
# The fence delimiter is assembled from a variable rather than written inline:
# three literal backticks inside a shell string are a parsing hazard for no
# benefit.
TICKS='```'
summary_comment() {
    local id="$1" created="$2" body="${3:-}"
    if [[ -z "$body" ]]; then
        body="$(printf '%s\n' \
            '## Review verdict: approve with one correctness finding to fix' \
            '' \
            'The CLI datastore path is stat-ed against the machine default.' \
            '' \
            '<details><summary>machine-readable findings</summary>' \
            '' \
            "${TICKS}${FINDINGS_FENCE_KEY}" \
            '[{"path": "a.ts", "line": 4, "severity": "medium", "title": "t", "body": "b"}]' \
            "${TICKS}" \
            '' \
            '</details>')"
    fi
    jq -n --argjson id "$id" --arg created "$created" --arg body "$body" \
        '{id: $id, created_at: $created, user: {login: "github-actions[bot]"}, body: $body}'
}

# chatter_comment <id> <created_at> <author> <body>
chatter_comment() {
    jq -n --argjson id "$1" --arg created "$2" --arg author "$3" --arg body "$4" \
        '{id: $id, created_at: $created, user: {login: $author}, body: $body}'
}

# A per-finding answer of the shape the operator actually posted on #551
# (2856 chars, no id citation) -- long-form, by a human.
human_answer_body() {
    printf 'The finding was correct and is fixed. The datastore-scoped stat now resolves the named datastore mount before measuring, mirroring recordedDatastoreMount, so a fork out of a named datastore is metered against its real size rather than the 1 GB floor. The nit about the duplicated jq expression is deferred to the follow-up worklist item; the coverage map lists the translation bundles as unreviewed, which is acceptable because they are generated.'
}

# comments_fixture <dir> <json-object...>  -- assemble the issue-comment list
comments_fixture() {
    local dir="$1"
    shift
    printf '%s\n' "$@" | jq -s '.' >"$dir/fixtures/issue-comments.json"
}

setup_comments() {
    local t="$1"
    mkdir -p "$t/fixtures"
    write_fake_gh_comments "$t"
    # No inline threads by default: the top-level path must work on its own,
    # and it used to be unreachable because an empty inline list exited 0 early.
    echo '[]' >"$t/fixtures/inline-comments.json"
    echo '[]' >"$t/fixtures/issue-comments.json"
}

run_comments_gate() {
    local t="$1"
    shift
    local rc=0
    LAST_OUT="$(env PATH="$t/bin:$PATH" GH_FIXTURES="$t/fixtures" GH_TOKEN=fake \
        GITHUB_REPOSITORY=rediacc/console PR_NUMBER=42 NO_COLOR=1 \
        "$@" bash "$REVIEW_COMMENTS_GATE" 2>&1)" || rc=$?
    LAST_RC="$rc"
    return 0
}

# ANTI-VACUITY. The gate recognises the summary by the fence the review
# pipeline emits. If that key is ever renamed in the pipeline and not here, the
# gate goes permanently blind while still reporting "OK" -- the original defect,
# regrown. Assert the key still exists in BOTH producers.
test_findings_fence_key_is_shared_with_the_pipeline() {
    grep -qF -- "$FINDINGS_FENCE_KEY" "$REAL_GATE" ||
        log_fail "claude-review-gate.sh no longer emits/parses '$FINDINGS_FENCE_KEY'; check-review-comments.sh keys off it and just went blind"
    grep -qF -- "$FINDINGS_FENCE_KEY" "$REVIEW_COMMENTS_GATE" ||
        log_fail "check-review-comments.sh no longer keys off '$FINDINGS_FENCE_KEY'; it cannot recognise a review summary"
    grep -qF -- "$FINDINGS_FENCE_KEY" "$REPO_ROOT/.ci/scripts/review/prompts/initial.md" ||
        log_fail "the review prompt no longer mandates the '$FINDINGS_FENCE_KEY' block, so summaries will stop carrying the marker the gate needs"
    log_pass "the review-findings fence is emitted by the prompt, parsed by the review gate, and keyed off by the comment gate"
}

test_unreplied_summary_blocks() {
    local t="$1"
    setup_comments "$t"
    comments_fixture "$t" "$(summary_comment 900 2026-08-05T08:06:53Z)"
    run_comments_gate "$t"
    assert_exit_code 1 "$LAST_RC" "an unanswered top-level review verdict must BLOCK"
    assert_contains "$LAST_OUT" "UNANSWERED REVIEW SUMMARY" "the block names the class"
    assert_contains "$LAST_OUT" "issuecomment-900" "and links the exact comment"
    # Autofix guidance is part of the contract, not decoration: a future agent
    # must be able to act from this output with no rediscovery.
    assert_contains "$LAST_OUT" "gh api repos/rediacc/console/issues/42/comments -X POST" \
        "the output carries the exact command that posts an answer"
    assert_contains "$LAST_OUT" "Re: review summary 900" "pre-filled with the comment id"
    assert_contains "$LAST_OUT" "comments/900/replies" \
        "and warns about the replies endpoints that 404 for an issue comment"
    log_pass "PLANTED unanswered review summary => BLOCKS, with a copy-pasteable answer command"
}

test_answered_summary_passes() {
    local t="$1"
    setup_comments "$t"
    comments_fixture "$t" \
        "$(summary_comment 900 2026-08-05T08:06:53Z)" \
        "$(chatter_comment 903 2026-08-05T10:29:55Z mfbayraktar "$(human_answer_body)")"
    run_comments_gate "$t"
    assert_exit_code 0 "$LAST_RC" "a per-finding human answer addresses the summary"
    assert_contains "$LAST_OUT" "answered by comment 903" "and the pass says which comment answered it"
    log_pass "a substantive human answer => PASSES (the live shape of PR #551 today)"
}

test_ordinary_chatter_is_ignored() {
    local t="$1"
    setup_comments "$t"
    # CONTROL: issues/{PR}/comments carries every kind of PR chatter. None of
    # it is a review verdict, so none of it may block. A gate that blocked here
    # would be suppressed within a day.
    comments_fixture "$t" \
        "$(chatter_comment 800 2026-08-05T07:00:00Z github-actions\[bot\] "Deploy preview is ready: https://pr-42.example.invalid and the bundle grew by 3 kB since the last push, which is within budget.")" \
        "$(chatter_comment 801 2026-08-05T07:10:00Z github-actions\[bot\] "<!-- claude-reviewed: 2222222222222222222222222222222222222222 -->
Automated Claude review completed for commit 2222222. Cost: \$4.66")" \
        "$(chatter_comment 802 2026-08-05T07:20:00Z mfbayraktar "Rebased onto main to pick up the label fix; rerunning the failed jobs now rather than pushing an empty commit.")"
    run_comments_gate "$t"
    assert_exit_code 0 "$LAST_RC" "ordinary PR chatter is not a review verdict"
    assert_contains "$LAST_OUT" "No top-level review summary found" "and the gate says it found none"
    assert_not_contains "$LAST_OUT" "UNANSWERED REVIEW SUMMARY" "nothing was blocked on"
    log_pass "CONTROL: deploy notes, the reviewed-SHA marker and operator notes are all IGNORED"
}

test_second_bot_comment_is_not_a_reply() {
    local t="$1"
    setup_comments "$t"
    # THE TRAP. The pipeline posts several comments in a row under one
    # identity: on #551 the marker comment landed 14 SECONDS after the summary,
    # and the "**Claude finished" wrapper 10 seconds after it. Both are long
    # enough to clear every substance test. If author were ignored, the review
    # would "answer" itself on every PR and this gate could never fire once.
    comments_fixture "$t" \
        "$(summary_comment 900 2026-08-05T08:06:53Z)" \
        "$(chatter_comment 901 2026-08-05T08:07:03Z github-actions\[bot\] "**Claude finished the automated review of 208c8a2**

---

Posted the review. Verdict: approve with one correctness finding. I read the CLI datastore paths deeply and skimmed the generated bundles, which is recorded in the coverage map above.")" \
        "$(chatter_comment 902 2026-08-05T08:07:07Z github-actions\[bot\] "<!-- claude-reviewed: 2222222222222222222222222222222222222222 -->
Automated Claude review completed for commit 208c8a2. Cost: \$4.6617 (claude-sonnet-5 35771out) | 84 turns | 21m3s")"
    run_comments_gate "$t"
    assert_exit_code 1 "$LAST_RC" "the reviewer's own follow-up comments are not an answer to its verdict"
    assert_contains "$LAST_OUT" "UNANSWERED REVIEW SUMMARY" "still reported as unanswered"
    assert_contains "$LAST_OUT" "second comment from the reviewer is not an answer" \
        "and the output says why those two did not count"
    log_pass "PLANTED bot self-replies (report + marker, both substantial) => still BLOCKS"
}

test_low_effort_answer_does_not_clear_the_summary() {
    local t="$1"
    setup_comments "$t"
    comments_fixture "$t" \
        "$(summary_comment 900 2026-08-05T08:06:53Z)" \
        "$(chatter_comment 903 2026-08-05T09:00:00Z mfbayraktar "Acknowledged, all addressed.")"
    run_comments_gate "$t"
    assert_exit_code 1 "$LAST_RC" "a stock acknowledgement does not address a multi-finding verdict"
    log_pass "PLANTED low-effort human answer => still BLOCKS"
}

test_summary_check_survives_an_empty_inline_list() {
    local t="$1"
    setup_comments "$t"
    # REGRESSION GUARD for the shape of the original defect. The gate used to
    # `exit 0` the moment pulls/{PR}/comments came back empty, which is the
    # commonest case: most reviews post a verdict and no inline comment at all.
    # The summary check must run regardless.
    echo '[]' >"$t/fixtures/inline-comments.json"
    comments_fixture "$t" "$(summary_comment 900 2026-08-05T08:06:53Z)"
    run_comments_gate "$t"
    assert_exit_code 1 "$LAST_RC" "an empty inline list must not short-circuit the summary check"
    assert_contains "$LAST_OUT" "No inline review comments found" "the inline path still reports its own emptiness"
    assert_contains "$LAST_OUT" "UNANSWERED REVIEW SUMMARY" "and the summary is still judged"
    log_pass "PLANTED empty inline list + unanswered summary => BLOCKS (no early exit)"
}

test_inline_thread_behaviour_is_unchanged() {
    local t="$1"
    setup_comments "$t"
    # The inline path is correct today and must stay bit-for-bit correct. Both
    # directions in one case: comment 10 has a substantive reply, comment 20 has
    # none. Only 20 may be reported.
    jq -n '[
      {id: 10, in_reply_to_id: null, path: "packages/cli/src/a.ts", line: 4,
       user: {login: "github-actions[bot]"}, body: "**[HIGH]** - stat targets the wrong path"},
      {id: 11, in_reply_to_id: 10, path: "packages/cli/src/a.ts", line: 4,
       user: {login: "mfbayraktar"}, body: "Fixed by resolving the named datastore mount first."},
      {id: 20, in_reply_to_id: null, path: "packages/cli/src/b.ts", line: 9,
       user: {login: "github-actions[bot]"}, body: "**[MEDIUM]** - unchecked exit code"}
    ]' >"$t/fixtures/inline-comments.json"
    run_comments_gate "$t"
    assert_exit_code 1 "$LAST_RC" "an unreplied inline thread still blocks"
    assert_contains "$LAST_OUT" "UNREPLIED COMMENTS (1)" "exactly one thread is unreplied"
    assert_contains "$LAST_OUT" "packages/cli/src/b.ts:9" "and it is the one with no reply"
    assert_not_contains "$LAST_OUT" "packages/cli/src/a.ts:4" "the answered thread is not reported"
    assert_contains "$LAST_OUT" "comments/{COMMENT_ID}/replies" "the inline autofix guidance is intact"
    assert_not_contains "$LAST_OUT" "UNANSWERED REVIEW SUMMARY" "and no summary was invented"
    log_pass "CONTROL: inline-thread behaviour unchanged (replied thread quiet, unreplied thread reported)"
}

test_unreadable_issue_comments_fail_closed() {
    local t="$1"
    setup_comments "$t"
    rm -f "$t/fixtures/issue-comments.json" # the issues endpoint is unavailable
    run_comments_gate "$t"
    if [[ "$LAST_RC" -eq 0 ]]; then
        log_fail "an unfetchable issue-comment list must block, not read as 'the review posted no summary'"
    fi
    assert_contains "$LAST_OUT" "Failing closed" "the abort says it is failing closed"
    log_pass "PLANTED unreadable issues/{PR}/comments => FAILS CLOSED (not a silent clean PR)"
}

# ===========================================================================
# check-review-report-replies.sh -- the pipeline's REPORT WRAPPER.
#
# The second half of the same blind spot. That gate matched the report by its
# "**Claude finished" header AND-ed with "carries the findings fence or a
# '### Review' heading". The header is a producer constant; the second clause
# is a guess about WORDING that no producer emits. On #551 the wrapper
# (5189238220) carried neither marker, so the gate found no report and exited 0
# vacuously while an 8141-char verdict sat unanswered -- it passed that PR
# silently for the same reason check-review-comments.sh did.
#
# The two gates key off two DIFFERENT producer constants (the fence vs the
# header) and own two DIFFERENT comments, so they are complementary. What makes
# that coverage rather than a tax is that they share one reply rule, proven by
# test_one_reply_clears_both_gates below.
# ===========================================================================

REPORT_REPLIES_GATE="$REPO_ROOT/.ci/scripts/quality/check-review-report-replies.sh"

# The header the pipeline writes and this gate matches on.
REPORT_PREFIX_KEY='**Claude finished'

# report_comment <id> <created_at> [body]
# Default body is the LIVE #551 SHAPE: the header, then the model's short
# wrap-up. No findings fence, no "### Review" heading -- the exact shape the
# old selector could not see.
report_comment() {
    local id="$1" created="$2" body="${3:-}"
    if [[ -z "$body" ]]; then
        body="$(printf '%s\n' \
            "${REPORT_PREFIX_KEY} the automated review of 208c8a2**" \
            '' \
            '---' \
            '' \
            'Posted the review. Summary of what I did:' \
            '' \
            'Verdict: approve with one correctness finding. I read the CLI datastore paths deeply and skimmed the generated bundles.')"
    fi
    jq -n --argjson id "$id" --arg created "$created" --arg body "$body" \
        '{id: $id, created_at: $created, user: {login: "github-actions[bot]"}, body: $body}'
}

marker_issue_comment() {
    chatter_comment "$1" "$2" 'github-actions[bot]' "<!-- claude-reviewed: 2222222222222222222222222222222222222222 -->
Automated Claude review completed for commit 208c8a2. Cost: \$4.6617 (claude-sonnet-5 35771out) | 84 turns | 21m3s"
}

run_report_gate() {
    local t="$1"
    shift
    local rc=0
    LAST_OUT="$(env PATH="$t/bin:$PATH" GH_FIXTURES="$t/fixtures" GH_TOKEN=fake \
        GITHUB_REPOSITORY=rediacc/console PR_NUMBER=42 NO_COLOR=1 \
        "$@" bash "$REPORT_REPLIES_GATE" 2>&1)" || rc=$?
    LAST_RC="$rc"
    return 0
}

# ANTI-VACUITY, same shape as the fence test: the header must still be a
# constant BOTH the producer and this consumer carry.
test_report_prefix_is_shared_with_the_pipeline() {
    grep -qF -- "$REPORT_PREFIX_KEY" "$REAL_GATE" ||
        log_fail "claude-review-gate.sh no longer writes '$REPORT_PREFIX_KEY'; check-review-report-replies.sh keys off it and just went blind"
    grep -qF -- "$REPORT_PREFIX_KEY" "$REPORT_REPLIES_GATE" ||
        log_fail "check-review-report-replies.sh no longer keys off '$REPORT_PREFIX_KEY'; it cannot recognise a report"
    log_pass "the report header is a constant the pipeline writes and the report gate reads"
}

# THE REGRESSION PIN. This is the exact live shape that slipped through: a real
# finished report with neither the fence nor a "### Review" heading.
test_report_without_fence_or_heading_blocks() {
    local t="$1"
    setup_comments "$t"
    comments_fixture "$t" "$(report_comment 901 2026-08-05T08:07:03Z)"
    run_report_gate "$t"
    assert_exit_code 1 "$LAST_RC" "a finished report must be gated on its HEADER, not on whether its prose happens to contain a fence or a '### Review' heading"
    assert_contains "$LAST_OUT" "issuecomment-901" "the block links the exact report"
    assert_contains "$LAST_OUT" "gh api repos/rediacc/console/issues/42/comments -X POST" \
        "and carries the exact command that posts an answer"
    assert_contains "$LAST_OUT" "comments/901/replies" \
        "and warns about the replies endpoints that 404 for an issue comment"
    log_pass "PLANTED live #551 report shape (no fence, no '### Review') => BLOCKS"
}

test_report_answered_passes() {
    local t="$1"
    setup_comments "$t"
    comments_fixture "$t" \
        "$(report_comment 901 2026-08-05T08:07:03Z)" \
        "$(chatter_comment 903 2026-08-05T10:29:55Z mfbayraktar "$(human_answer_body)")"
    run_report_gate "$t"
    assert_exit_code 0 "$LAST_RC" "a per-finding human answer addresses the report"
    assert_contains "$LAST_OUT" "answered by comment 903" "and the pass says which comment answered it"
    log_pass "report + substantive human answer => PASSES"
}

test_report_bot_self_reply_does_not_count() {
    local t="$1"
    setup_comments "$t"
    # On #551 the reviewed-SHA marker landed 4 SECONDS after the report and is
    # long enough to clear every substance test. Same identity, so it must not
    # count -- otherwise the pipeline answers itself on every PR.
    comments_fixture "$t" \
        "$(report_comment 901 2026-08-05T08:07:03Z)" \
        "$(marker_issue_comment 902 2026-08-05T08:07:07Z)"
    run_report_gate "$t"
    assert_exit_code 1 "$LAST_RC" "the pipeline's own marker comment is not an answer to its report"
    assert_contains "$LAST_OUT" "second comment from the pipeline is not an answer" \
        "and the output says why it did not count"
    log_pass "PLANTED bot self-reply (the reviewed-SHA marker) => still BLOCKS"
}

test_report_ordinary_chatter_is_ignored() {
    local t="$1"
    setup_comments "$t"
    # CONTROL: no comment carries the report header, so nothing may block.
    comments_fixture "$t" \
        "$(chatter_comment 800 2026-08-05T07:00:00Z github-actions\[bot\] "Deploy preview is ready: https://pr-42.example.invalid and the bundle grew by 3 kB, which is within budget.")" \
        "$(chatter_comment 802 2026-08-05T07:20:00Z mfbayraktar "Rebased onto main to pick up the label fix; rerunning the failed jobs now.")"
    run_report_gate "$t"
    assert_exit_code 0 "$LAST_RC" "ordinary PR chatter is not a review report"
    assert_contains "$LAST_OUT" "No finished review report found" "and the gate says it found none"
    log_pass "CONTROL: deploy notes and operator notes are IGNORED by the report gate"
}

test_report_unreadable_comments_fail_closed() {
    local t="$1"
    setup_comments "$t"
    rm -f "$t/fixtures/issue-comments.json"
    run_report_gate "$t"
    if [[ "$LAST_RC" -eq 0 ]]; then
        log_fail "an unfetchable comment list must block, not read as 'no report was posted'"
    fi
    assert_contains "$LAST_OUT" "Failing closed" "the abort says it is failing closed"
    log_pass "PLANTED unreadable issues/{PR}/comments => FAILS CLOSED (report gate)"
}

# ---------------------------------------------------------------------------
# THE GRAPHQL FALLBACK, and why it is tested at all.
#
# On 2026-08-17 a GitHub incident made repos/<r>/issues/<n>/comments fail most
# calls. This gate then could not RUN, and a gate that cannot run does not judge
# a merge -- it blocks every one of them, which is what happened to a live
# submodule land. The fix reads the same thread over GraphQL when REST fails.
#
# NOTE WHAT IS *NOT* BEING ASSERTED. The endpoint's failure had nothing to do
# with the repo being private, though it looked exactly like that at the time:
# sampled 8 calls per repo, the private one passed ONCE and the public 8/8, and
# a single success rules an access-level cause out. So these cases inject a
# TRANSPORT failure and say nothing about visibility -- pinning a public/private
# distinction here would encode a diagnosis that measurement disproved.
#
# The fallback must not become a softer verdict, so all three directions are
# pinned: it recovers, it still DETECTS, and losing both instruments still
# fails closed.
# ---------------------------------------------------------------------------

# graphql_comments_fixture <dir> <json-object...>
# The same comment objects in GraphQL's shape, so the fixture cannot drift from
# what the fallback actually parses: databaseId/createdAt/author.login rather
# than id/created_at/user.login.
graphql_comments_fixture() {
    local dir="$1"
    shift
    printf '%s\n' "$@" | jq -s '{data: {repository: {pullRequest: {comments: {nodes:
        [.[] | {databaseId: .id, body: .body, createdAt: .created_at,
                author: {login: .user.login}}]}}}}}' >"$dir/fixtures/graphql-comments.json"
}

test_report_graphql_fallback_recovers_when_rest_fails() {
    local t="$1"
    setup_comments "$t"
    local answered=(
        "$(report_comment 901 2026-08-05T08:07:03Z)"
        "$(chatter_comment 903 2026-08-05T10:29:55Z mfbayraktar "$(human_answer_body)")"
    )
    comments_fixture "$t" "${answered[@]}"
    graphql_comments_fixture "$t" "${answered[@]}"
    run_report_gate "$t" GH_FAIL_ISSUE_COMMENTS=1
    assert_exit_code 0 "$LAST_RC" \
        "with REST down the gate must still RUN via GraphQL, not block a merge it cannot judge"
    assert_contains "$LAST_OUT" "903" "and it names the answering comment it found over GraphQL"
    log_pass "PLANTED REST 404 + answered report => GraphQL fallback RUNS and passes"
}

# THE CONTROL. Without this the case above proves only that the gate went quiet.
test_report_graphql_fallback_still_detects_unanswered() {
    local t="$1"
    setup_comments "$t"
    local unanswered=("$(report_comment 901 2026-08-05T08:07:03Z)")
    comments_fixture "$t" "${unanswered[@]}"
    graphql_comments_fixture "$t" "${unanswered[@]}"
    run_report_gate "$t" GH_FAIL_ISSUE_COMMENTS=1
    assert_exit_code 1 "$LAST_RC" \
        "the fallback is a different TRANSPORT, not a softer verdict: an unanswered report must still block"
    assert_contains "$LAST_OUT" "issuecomment-901" "and still links the exact unanswered report"
    log_pass "PLANTED REST 404 + UNANSWERED report => GraphQL fallback still BLOCKS"
}

test_report_both_instruments_down_fails_closed() {
    local t="$1"
    setup_comments "$t"
    comments_fixture "$t" "$(report_comment 901 2026-08-05T08:07:03Z)"
    rm -f "$t/fixtures/graphql-comments.json"
    run_report_gate "$t" GH_FAIL_ISSUE_COMMENTS=1
    assert_exit_code 1 "$LAST_RC" \
        "losing BOTH instruments must fail closed; a fallback that swallows its own failure is worse than no fallback"
    assert_contains "$LAST_OUT" "Failing closed" "the abort still says it is failing closed"
    log_pass "PLANTED REST 404 + GraphQL unreadable => FAILS CLOSED"
}

# ---------------------------------------------------------------------------
# THE PROPERTY THAT MAKES TWO GATES DEFENSIBLE.
#
# One review pass leaves two top-level comments, and the two gates own one
# each. That is only worth having if answering the pass ONCE clears both --
# otherwise the second gate is a tax on the operator and gets suppressed. Both
# scripts are driven here against ONE fixture in the live #551 arrangement, in
# both directions.
# ---------------------------------------------------------------------------
test_one_reply_clears_both_gates() {
    local t="$1"
    setup_comments "$t"
    # The #551 arrangement: reviewer's own summary (fence), then the pipeline's
    # wrapper (header, no fence), then the marker -- all within 14 seconds.
    local unanswered=(
        "$(summary_comment 900 2026-08-05T08:06:53Z)"
        "$(report_comment 901 2026-08-05T08:07:03Z)"
        "$(marker_issue_comment 902 2026-08-05T08:07:07Z)"
    )
    comments_fixture "$t" "${unanswered[@]}"

    run_comments_gate "$t"
    assert_exit_code 1 "$LAST_RC" "unanswered: the summary gate must block"
    run_report_gate "$t"
    assert_exit_code 1 "$LAST_RC" "unanswered: the report gate must block too"

    # ONE reply, posted after all three, by a human. Nothing else changes.
    comments_fixture "$t" "${unanswered[@]}" \
        "$(chatter_comment 903 2026-08-05T10:29:55Z mfbayraktar "$(human_answer_body)")"

    run_comments_gate "$t"
    assert_exit_code 0 "$LAST_RC" "one reply must clear the summary gate"
    assert_contains "$LAST_OUT" "answered by comment 903" "summary gate credits that reply"
    run_report_gate "$t"
    assert_exit_code 0 "$LAST_RC" "the SAME reply must clear the report gate; a second required reply would be a tax, not coverage"
    assert_contains "$LAST_OUT" "answered by comment 903" "report gate credits the same reply"
    log_pass "ONE reply clears BOTH gates (and its absence blocks both) -- the two keys are coverage, not duplication"
}

# Anti-drift for the property above: the shared rule is spelled out in two
# files, so the thresholds must be asserted equal. If one file is tuned and the
# other is not, a reply can satisfy one gate and not the other, and the
# property test above would start failing for a reason nobody could see.
test_reply_thresholds_match_across_both_gates() {
    local name a b
    for name in SUMMARY_MIN_CHARS SUMMARY_LONGFORM_CHARS; do
        a="$(sed -n "s/^${name}=\([0-9]*\)[[:space:]]*$/\1/p" "$REVIEW_COMMENTS_GATE" | head -n 1)"
        b="$(sed -n "s/^${name}=\([0-9]*\)[[:space:]]*$/\1/p" "$REPORT_REPLIES_GATE" | head -n 1)"
        [[ -n "$a" ]] || log_fail "$name is not parseable out of check-review-comments.sh; the two gates can no longer be proven to agree"
        [[ -n "$b" ]] || log_fail "$name is not parseable out of check-review-report-replies.sh; the two gates can no longer be proven to agree"
        assert_eq "$b" "$a" "$name must be identical in both gates so one reply clears both"
    done
    log_pass "both top-level gates carry identical reply thresholds ($(sed -n 's/^SUMMARY_MIN_CHARS=\([0-9]*\)[[:space:]]*$/\1/p' "$REVIEW_COMMENTS_GATE" | head -n 1)/$(sed -n 's/^SUMMARY_LONGFORM_CHARS=\([0-9]*\)[[:space:]]*$/\1/p' "$REVIEW_COMMENTS_GATE" | head -n 1))"
}

test_review_report_count_is_shared_and_unqualified() {
    # The numerator in "X/Y reviews used". Two failures are pinned here because
    # both actually happened.
    #
    # ONE DEFINITION. It existed as identical copies in claude-review-gate.sh
    # (which counts) and review-status.sh (which reports the fraction). Two
    # copies of a numerator drift, and the denominator already lives in
    # common.sh for exactly that reason.
    local lib="$REPO_ROOT/.ci/scripts/lib/common.sh"
    local defs
    defs="$(grep -rlE '^review_report_count\(\)' "$REPO_ROOT/.ci/scripts/" 2>/dev/null | sort)"
    [[ "$defs" == "$lib" ]] ||
        log_fail "review_report_count() must be defined ONLY in .ci/scripts/lib/common.sh, found in: ${defs:-<nowhere>}"

    # NO CONTENT QUALIFIER. Both copies used to AND the header with
    # (json:review-findings OR "### Review"), a guess about the report's wording
    # that no producer emits. Measured live when it was removed: #551 counted 0
    # of 1 -- a completed, marked review registering as never having happened,
    # so the cap never advanced and every push re-reviewed at full price.
    local body
    body="$(sed -n '/^review_report_count()/,/^}/p' "$lib")"
    [[ -n "$body" ]] || log_fail "could not extract review_report_count() from common.sh"
    grep -q 'startswith(\\"\*\*Claude finished' <<<"$body" ||
        log_fail "review_report_count() no longer keys on the **Claude finished header, which is the producer constant claude-review-gate.sh writes verbatim"
    if grep -qE 'json:review-findings|### Review' <<<"$body"; then
        log_fail "review_report_count() has regained a content qualifier; that undercounts real reviews and makes the cap unreachable -- exclude on something the producer emits on purpose, not on its prose"
    fi
    log_pass "review_report_count() is defined once, in common.sh, and keys on the header alone"
}

test_review_status_has_workflow_dispatch_with_pr_number() {
    local wf="$REPO_ROOT/.github/workflows/review-status.yml"
    grep -qE '^  workflow_dispatch:[[:space:]]*$' "$wf" ||
        log_fail "review-status.yml lost its workflow_dispatch trigger"
    grep -q "pr_number:" "$wf" ||
        log_fail "review-status.yml's workflow_dispatch has no pr_number input"
    log_pass "review-status.yml declares workflow_dispatch with a pr_number input"
}

# ---------------------------------------------------------------------------

test_real_gate_constants_parseable
test_no_ci_job_references_review_complete
test_workflow_does_not_trigger_on_pull_request
test_review_status_has_workflow_dispatch_with_pr_number

with_temp_dir test_current_head_succeeds
with_temp_dir test_empty_diff_succeeds
with_temp_dir test_gitlink_only_succeeds
with_temp_dir test_cancelled_review_run_is_not_a_failure
with_temp_dir test_draft_is_neutral

with_temp_dir test_workflow_dispatch_resolves_pr_directly
with_temp_dir test_workflow_run_without_artifact_is_silent
with_temp_dir test_workflow_run_with_artifact_posts_the_check
with_temp_dir test_workflow_run_with_unhonourable_artifact_is_loud
with_temp_dir test_workflow_dispatch_requires_pr_number
with_temp_dir test_hygiene_only_failure_title_says_reviewed
with_temp_dir test_unreviewed_head_title_unchanged

with_temp_dir test_stale_head_fails
with_temp_dir test_unreviewed_head_fails
with_temp_dir test_wrong_marker_prefix_is_seen_as_unreviewed
with_temp_dir test_failed_review_run_fails
with_temp_dir test_hygiene_failure_fails
with_temp_dir test_compare_failure_fails_closed
with_temp_dir test_missing_hygiene_dir_hard_fails
with_temp_dir test_unparseable_constants_hard_fail

with_temp_dir test_cap_reached_warns_instead_of_deadlocking
with_temp_dir test_cap_reached_by_spent_attempts_alone
with_temp_dir test_below_cap_the_same_state_fails

with_temp_dir test_anchors_to_current_head_not_event_sha
with_temp_dir test_existing_check_run_is_patched

test_findings_fence_key_is_shared_with_the_pipeline
with_temp_dir test_unreplied_summary_blocks
with_temp_dir test_answered_summary_passes
with_temp_dir test_ordinary_chatter_is_ignored
with_temp_dir test_second_bot_comment_is_not_a_reply
with_temp_dir test_low_effort_answer_does_not_clear_the_summary
with_temp_dir test_summary_check_survives_an_empty_inline_list
with_temp_dir test_inline_thread_behaviour_is_unchanged
with_temp_dir test_unreadable_issue_comments_fail_closed

test_report_prefix_is_shared_with_the_pipeline
test_reply_thresholds_match_across_both_gates
test_review_report_count_is_shared_and_unqualified
with_temp_dir test_report_without_fence_or_heading_blocks
with_temp_dir test_report_answered_passes
with_temp_dir test_report_bot_self_reply_does_not_count
with_temp_dir test_report_ordinary_chatter_is_ignored
with_temp_dir test_report_unreadable_comments_fail_closed
with_temp_dir test_report_graphql_fallback_recovers_when_rest_fails
with_temp_dir test_report_graphql_fallback_still_detects_unanswered
with_temp_dir test_report_both_instruments_down_fails_closed
with_temp_dir test_one_reply_clears_both_gates

# ---------------------------------------------------------------------------
# THE ATTEMPT BUDGET (2026-08-09). A reportless review attempt used to be
# terminal for its head: it charged a budget unit and its marker said "push a
# change to earn another pass". On PR #560 that stalled a fully-green,
# autopilot-driven PR behind a human, because there was no legitimate change to
# push. An INFRA-CLASS death now gets bounded free re-attempts on the same head.
#
# These cases live in this file, rather than beside the --apply-labels tests,
# because the attempt marker is the SHARED STATE between claude-review-gate.sh
# and review-status.sh, and this file already owns the budget contract that both
# of them read. Splitting it would recreate the #553 split-numerator problem in
# the tests instead of in the code.
# ---------------------------------------------------------------------------

# attempt_marker <id> <sha> <attempts> <class> -- the NEW marker shape.
attempt_marker() {
    jq -nc --argjson id "$1" --arg sha "$2" --arg n "$3" --arg cls "$4" \
        '{id: $id, user: {login: "github-actions[bot]"},
          body: ("<!-- claude-review-attempt: " + $sha + " -->\nattempts: " + $n
                 + "\nclass: " + $cls + "\nA review pass was attempted and produced no report.")}'
}

test_attempt_accounting_helpers() {
    # PURE, so both directions are provable without a network. These functions
    # are the numerator the cap is measured against; the integration cases below
    # can only show one point of the curve each.
    # shellcheck source=../../lib/common.sh
    # BLOCKER: the shared review-budget helpers both review scripts depend on
    source "$REPO_ROOT/.ci/scripts/lib/common.sh"

    local infra=$'aaa\t1\terror_max_turns'
    assert_eq "$(review_chargeable_attempts "$infra")" "0" \
        "the first infra-class attempt on a head is free"
    infra=$'aaa\t2\terror_max_turns'
    assert_eq "$(review_chargeable_attempts "$infra")" "0" \
        "so is the second"
    infra=$'aaa\t3\terror_max_turns'
    assert_eq "$(review_chargeable_attempts "$infra")" "1" \
        "the third is charged"
    assert_eq "$(review_chargeable_attempts $'aaa\t3\terror_during_execution')" "1" \
        "error_during_execution is the same class of failure"

    # CONTROL: an unknown failure keeps the old rule exactly. "We do not know why
    # it died" is the case where retrying forever is most expensive.
    assert_eq "$(review_chargeable_attempts $'aaa\t1\treview step did not succeed')" "1" \
        "a non-infra attempt is charged from the first one"
    assert_eq "$(review_chargeable_attempts $'aaa\t1\t')" "1" \
        "a LEGACY marker with no class line still charges, exactly as before"

    local mixed=$'aaa\t2\terror_max_turns\nbbb\t1\t\nccc\t3\terror_max_turns'
    assert_eq "$(review_chargeable_attempts "$mixed")" "2" \
        "heads are accounted independently (0 + 1 + 1)"

    # The ceiling, both ways.
    review_head_is_exhausted $'aaa\t3\terror_max_turns' aaa &&
        log_pass "  a head with 3 infra attempts is exhausted" ||
        log_fail "a head with 3 infra attempts must be exhausted"
    if review_head_is_exhausted $'aaa\t2\terror_max_turns' aaa; then
        log_fail "a head with 2 infra attempts must NOT be exhausted"
    fi
    if review_head_is_exhausted $'aaa\t9\t' aaa; then
        log_fail "a non-infra head must never be per-head blocked; that would be a NEW restriction"
    fi
    if review_head_is_exhausted $'aaa\t3\terror_max_turns' bbb; then
        log_fail "exhaustion must be keyed on the head, not on any head"
    fi
    log_pass "attempt accounting: infra gets 2 free re-attempts per head, everything else is unchanged"
}

# run_mark <TEMP> <subtype-or-empty> -- drive claude-review-gate.sh --mark.
run_mark() {
    local t="$1" subtype="${2:-}"
    if [[ -n "$subtype" ]]; then
        jq -n --arg s "$subtype" '[{type: "result", subtype: $s, result: ""}]' >"$t/execution.json"
    else
        echo '[]' >"$t/execution.json"
    fi
    local rc=0
    LAST_OUT="$(cd "$t" && env \
        PATH="$t/bin:$PATH" \
        GH_FIXTURES="$t/fixtures" \
        GH_CAPTURE="$t/capture.txt" \
        GH_TOKEN=fake \
        GITHUB_REPOSITORY=rediacc/console \
        PR_NUMBER=42 \
        HEAD_SHA="$NEW_SHA" \
        EXECUTION_FILE="$t/execution.json" \
        REVIEW_OUTCOME=failure \
        NO_COLOR=1 \
        bash "$REAL_GATE" --mark 2>&1)" || rc=$?
    LAST_RC="$rc"
    return 0
}

# marked_body <TEMP> -- the captured attempt write: its method, path and the
# `-f body=` payload the gate sent.
marked_body() {
    cat "$1/capture.txt.fields" 2>/dev/null || true
}

test_mark_records_the_first_infra_attempt_as_retryable() {
    # FIRES: the old code POSTed "Push a change to earn another pass" here, which
    # is the message that stalled #560.
    local t="$1"
    setup "$t"
    echo '[]' >"$t/fixtures/comments.json"
    run_mark "$t" error_max_turns
    assert_eq "$LAST_RC" 0 "--mark must not fail the job (output: $LAST_OUT)"
    local body
    body="$(marked_body "$t")"
    assert_contains "$body" "METHOD=POST" "the first attempt on a head CREATES its marker"
    assert_contains "$body" "attempts: 1" "the marker carries its own count"
    assert_contains "$body" "class: error_max_turns" "and the class the count is judged by"
    assert_contains "$body" "INFRASTRUCTURE-class" "it says why this one is retryable"
    assert_contains "$body" "gh workflow run claude-review.yml" "and names the existing dispatch that retries it"
    assert_not_contains "$body" "Push a change to earn another pass" \
        "an infra failure with re-attempts left must NOT demand a push"
    log_pass "attempt 1 (infra) records a RETRYABLE marker, no push demanded"
}

test_mark_upserts_the_second_attempt() {
    # The marker is upserted, not re-posted: N deaths on one head must be one
    # comment carrying N, or the count cannot be read back at all.
    local t="$1"
    setup "$t"
    attempt_marker 301 "$NEW_SHA" 1 error_max_turns | jq -s '.' >"$t/fixtures/comments.json"
    run_mark "$t" error_max_turns
    local body
    body="$(marked_body "$t")"
    assert_contains "$body" "METHOD=PATCH" "a second attempt UPDATES the existing marker"
    assert_contains "$body" "issues/comments/301" "and patches the one for THIS head"
    assert_contains "$body" "attempts: 2" "the count advances"
    assert_not_contains "$body" "Push a change to earn another pass" \
        "the second infra attempt still has one left"
    log_pass "attempt 2 (infra) upserts the same marker and stays retryable"
}

test_mark_closes_the_head_on_the_third_attempt() {
    # CONTROL for the two above: the bound is real. The third reportless failure
    # on one head reverts to today's terminal message.
    local t="$1"
    setup "$t"
    attempt_marker 301 "$NEW_SHA" 2 error_max_turns | jq -s '.' >"$t/fixtures/comments.json"
    run_mark "$t" error_max_turns
    local body
    body="$(marked_body "$t")"
    assert_contains "$body" "attempts: 3" "the count reaches the ceiling"
    assert_contains "$body" "Push a change to earn another pass" \
        "the third attempt is terminal, exactly as before"
    assert_not_contains "$body" "INFRASTRUCTURE-class" "and it no longer offers a re-run"
    log_pass "attempt 3 (infra) closes the head with today's terminal message"
}

test_mark_keeps_the_old_rule_for_unknown_failures() {
    # CONTROL: a failure the pipeline cannot classify gets no free retries at
    # all. The relaxation is scoped to the classes it was argued for.
    local t="$1"
    setup "$t"
    echo '[]' >"$t/fixtures/comments.json"
    run_mark "$t" ""
    local body
    body="$(marked_body "$t")"
    assert_contains "$body" "attempts: 1" "still counted"
    assert_contains "$body" "class: review step did not succeed" "and its class recorded verbatim"
    assert_contains "$body" "Push a change to earn another pass" \
        "an unclassified failure is terminal on the first attempt, as before"
    log_pass "an unclassified reportless failure keeps the old single-shot rule"
}

# run_gate_decision <TEMP> -- drive the gate's DECISION mode for PR 42 at NEW_SHA.
run_gate_decision() {
    local t="$1" rc=0
    : >"$t/gate-output.txt"
    LAST_OUT="$(cd "$t" && env \
        PATH="$t/bin:$PATH" \
        GH_FIXTURES="$t/fixtures" \
        GH_CAPTURE="$t/capture.txt" \
        GH_TOKEN=fake \
        GITHUB_REPOSITORY=rediacc/console \
        GITHUB_OUTPUT="$t/gate-output.txt" \
        EVENT_NAME=workflow_dispatch \
        PR_NUMBER=42 \
        PR_HEAD_SHA="$NEW_SHA" \
        NO_COLOR=1 \
        bash "$REAL_GATE" 2>&1)" || rc=$?
    LAST_RC="$rc"
    return 0
}

test_gate_refuses_an_exhausted_head() {
    # THE REFUSAL ITSELF. Free re-attempts have to end somewhere and it cannot be
    # the per-PR cap, because the free ones are not charged -- without this a head
    # that dies infra-class would be retried forever at no visible cost.
    local t="$1"
    setup "$t"
    attempt_marker 301 "$NEW_SHA" 3 error_max_turns | jq -s '.' >"$t/fixtures/comments.json"
    run_gate_decision "$t"
    assert_eq "$LAST_RC" 0 "the gate exits cleanly when it declines (output: $LAST_OUT)"
    assert_contains "$(cat "$t/gate-output.txt")" "go=false" "an exhausted head is not reviewed again"
    assert_contains "$LAST_OUT" "spent all 3 attempts" "and the log says why"

    # CONTROL: one attempt fewer and the same head IS reviewed. This is the whole
    # point of the change, so it is asserted rather than assumed.
    setup "$t"
    attempt_marker 301 "$NEW_SHA" 2 error_max_turns | jq -s '.' >"$t/fixtures/comments.json"
    run_gate_decision "$t"
    assert_contains "$(cat "$t/gate-output.txt")" "go=true" \
        "a head with a re-attempt left must still be reviewable WITHOUT a push"
    log_pass "the gate refuses an exhausted head and reviews one that still has an attempt left"
}

test_head_exhaustion_does_not_deadlock_the_pr() {
    # THE #553 SHAPE, ONE LEVEL DOWN. The free attempts are not charged, so a head
    # can exhaust its ceiling while the PR sits well under its cap. The gate then
    # refuses this head; if review-status could not see that, it would post a
    # required FAILURE and leave a green PR permanently unmergeable.
    local t="$1"
    setup "$t"
    marker_comment "$OLD_SHA" >"$t/m.json"
    attempt_marker 301 "$NEW_SHA" 3 error_max_turns >"$t/a.json"
    jq -s '.' "$t/m.json" "$t/a.json" >"$t/fixtures/comments.json"
    echo '{"files": [{"filename": "packages/cli/src/commands/repo.ts"}]}' \
        >"$t/fixtures/compare.json"
    printf '%s\n' "MARKER_PREFIX='<!-- claude-reviewed:'" \
        "ATTEMPT_PREFIX='<!-- claude-review-attempt:'" >"$t/gate-cap3.sh"
    pr_size "$t" 900 100 # cap 3, and only ONE unit charged -- well under it

    run_status "$t" EVENT_NAME=pull_request_review PR_NUMBER=42 \
        REVIEW_STATUS_GATE_SCRIPT="$t/gate-cap3.sh"
    assert_eq "$(posted "$t" '.conclusion')" success \
        "an exhausted head with budget left must stay mergeable"
    assert_contains "$(posted "$t" '.output.summary')" "HEAD REVIEW ATTEMPTS EXHAUSTED" \
        "and say so, rather than passing quietly"

    log_pass "an exhausted head passes with a warning instead of deadlocking the PR"
}

test_retryable_head_with_a_stale_marker_still_fails() {
    # CONTROL for the case above, in its OWN temp dir because `posted` parses the
    # single capture file from the first METHOD= line onward -- a second
    # run_status in the same directory appends a second check-run payload and
    # makes it unparseable. One run per world, like every other case here.
    #
    # One attempt fewer, so the head is still retryable and a stale marker is a
    # real failure again. Without this the new guard could swallow every stale
    # head and nothing would notice.
    local t="$1"
    setup "$t"
    marker_comment "$OLD_SHA" >"$t/m.json"
    attempt_marker 301 "$NEW_SHA" 2 error_max_turns >"$t/a.json"
    jq -s '.' "$t/m.json" "$t/a.json" >"$t/fixtures/comments.json"
    echo '{"files": [{"filename": "packages/cli/src/commands/repo.ts"}]}' \
        >"$t/fixtures/compare.json"
    printf '%s\n' "MARKER_PREFIX='<!-- claude-reviewed:'" \
        "ATTEMPT_PREFIX='<!-- claude-review-attempt:'" >"$t/gate-cap3.sh"
    pr_size "$t" 900 100

    run_status "$t" EVENT_NAME=pull_request_review PR_NUMBER=42 \
        REVIEW_STATUS_GATE_SCRIPT="$t/gate-cap3.sh"
    assert_eq "$(posted "$t" '.conclusion')" failure \
        "a retryable head with a stale marker must still fail"
    assert_not_contains "$(posted "$t" '.output.summary')" "HEAD REVIEW ATTEMPTS EXHAUSTED" \
        "no exhaustion warning while an attempt remains"
    log_pass "a head that still has an attempt left keeps failing on a stale marker"
}

test_attempt_accounting_helpers
with_temp_dir test_mark_records_the_first_infra_attempt_as_retryable
with_temp_dir test_mark_upserts_the_second_attempt
with_temp_dir test_mark_closes_the_head_on_the_third_attempt
with_temp_dir test_mark_keeps_the_old_rule_for_unknown_failures
with_temp_dir test_gate_refuses_an_exhausted_head
with_temp_dir test_head_exhaustion_does_not_deadlock_the_pr
with_temp_dir test_retryable_head_with_a_stale_marker_still_fails
