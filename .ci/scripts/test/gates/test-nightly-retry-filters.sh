#!/bin/bash
# The nightly retry's FILTERS are the whole feature, so they are what this tests.
#
# Measured baseline, three days of rediacc/console runs: 589 success, 230
# skipped, 117 cancelled, 64 failure -- and 63 of the 64 are
# watchdog-monitor.yml failing BY DESIGN (it cancels the run it monitors, then
# core.setFailed()s to signal that). Exactly ONE genuine failure. A sweeper
# without these filters retries 63 deliberate failures, and if it also accepted
# `cancelled` it would revive 117 superseded pipelines.
#
# So every assertion below is a MEASURED false positive, not a hypothetical:
#   - cancelled is the superseded shape (117 of them)
#   - the watchdog fails on purpose (63 of them)
#   - a dead head is superseded by another route
#   - an attempt-capped run is not going to be fixed by a fourth rerun
#
# HERMETIC: `gh` is shimmed. A gate that needs GitHub up is a gate that gets
# skipped during exactly the outage that produces retryable failures.
#
# WHAT THIS CANNOT SEE: it drives the script's decisions, not GitHub's rerun
# semantics. It cannot prove `rerun-failed-jobs` does the right thing, and it
# cannot prove a retried workflow is idempotent -- that is a review question.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test gate
source "$SCRIPT_DIR/../lib/test-helpers.sh"

SUT="$REPO_ROOT/.ci/scripts/housekeeping/retry-failed-runs.sh"
[[ -f "$SUT" ]] || log_fail "subject under test is missing: $SUT"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

NOW_ISO="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
OLD_ISO="$(date -u -d '10 days ago' +%Y-%m-%dT%H:%M:%SZ)"
LIVE_SHA="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
DEAD_SHA="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

# fake_gh <runs-json> -- a gh that answers branches, the run list, and records
# every rerun POST to $WORK/reran so the test can assert on what was attempted.
fake_gh() {
    local runs="$1"
    mkdir -p "$WORK/bin"
    : >"$WORK/reran"
    cat >"$WORK/bin/gh" <<FAKE
#!/bin/bash
args="\$*"
case "\$args" in
  *branches*)      echo "$LIVE_SHA" ;;
  *rerun-failed-jobs*)
      echo "\$args" | grep -oE 'runs/[0-9]+' | cut -d/ -f2 >> "$WORK/reran"
      echo '{}' ;;
  *actions/runs*)  cat <<'JSON'
$runs
JSON
  ;;
  *) echo '{}' ;;
esac
FAKE
    chmod +x "$WORK/bin/gh"
}

# run_sut -- returns the summary line
run_sut() { PATH="$WORK/bin:$PATH" bash "$SUT" 2>&1; }
reran_ids() { tr '\n' ' ' <"$WORK/reran" | sed 's/ $//'; }

mk() { # mk <id> <name> <path> <sha> <attempt> <created>
    printf '{"id":%s,"name":"%s","path":"%s","head_sha":"%s","run_attempt":%s,"created_at":"%s"}' \
        "$1" "$2" "$3" "$4" "$5" "$6"
}

test_watchdog_is_excluded_by_path() {
    log_test "a watchdog run must NOT be retried (63 of 64 failures are these)"
    fake_gh "[$(mk 1 "Watchdog: run 999 (gen 3)" ".github/workflows/watchdog-monitor.yml" "$LIVE_SHA" 1 "$NOW_ISO")]"
    run_sut >/dev/null
    [[ -z "$(reran_ids)" ]] || log_fail "a by-design watchdog failure was retried: $(reran_ids)"
    log_pass "watchdog excluded by path"
}

test_name_match_would_not_have_worked() {
    log_test "exclusion must key on PATH, because the display name is generated"
    grep -q 'watchdog-monitor.yml' "$SUT" || log_fail "the watchdog path is not excluded at all"
    # A name-based exclusion is unwritable: the name carries a run id and a
    # generation number, so no literal can match it.
    grep -qE 'EXCLUDED_PATHS|is_excluded' "$SUT" ||
        log_fail "exclusion is not path-based; a generated display name cannot be matched"
    log_pass "exclusion is path-keyed"
}

test_genuine_failure_on_live_head_is_retried() {
    log_test "a real failure on a live head IS retried"
    fake_gh "[$(mk 42 "Cleanup PR Preview" ".github/workflows/cleanup-preview.yml" "$LIVE_SHA" 1 "$NOW_ISO")]"
    run_sut >/dev/null
    [[ "$(reran_ids)" == "42" ]] || log_fail "expected run 42 retried, got: '$(reran_ids)'"
    log_pass "the measured real case (Cleanup PR Preview) is retried"
}

test_dead_head_is_skipped() {
    log_test "a run whose head is no longer a branch tip must be skipped"
    fake_gh "[$(mk 43 "Console CI" ".github/workflows/ci.yml" "$DEAD_SHA" 1 "$NOW_ISO")]"
    run_sut >/dev/null
    [[ -z "$(reran_ids)" ]] || log_fail "a superseded head was revived: $(reran_ids)"
    log_pass "dead head skipped"
}

test_attempt_cap_is_honoured() {
    log_test "an attempt-capped run must not be retried nightly forever"
    fake_gh "[$(mk 44 "Console CI" ".github/workflows/ci.yml" "$LIVE_SHA" 3 "$NOW_ISO")]"
    run_sut >/dev/null
    [[ -z "$(reran_ids)" ]] || log_fail "a run at the attempt cap was retried again: $(reran_ids)"
    log_pass "attempt cap honoured"
}

test_age_floor_is_honoured() {
    log_test "an old failure must not be reached on the first execution"
    fake_gh "[$(mk 45 "Console CI" ".github/workflows/ci.yml" "$LIVE_SHA" 1 "$OLD_ISO")]"
    run_sut >/dev/null
    [[ -z "$(reran_ids)" ]] || log_fail "a 10-day-old run was retried: $(reran_ids)"
    log_pass "age floor honoured"
}

test_only_failure_status_is_queried() {
    log_test "cancelled must never enter the candidate set (117 superseded runs)"
    grep -q 'status=failure' "$SUT" ||
        log_fail "the run query is not restricted to status=failure"
    grep -qE 'status=(cancelled|completed)' "$SUT" &&
        log_fail "the query would pull cancelled/completed runs into the candidate set"
    log_pass "query is failure-only"
}

test_fails_closed_without_branch_list() {
    log_test "an unreadable branch list must SKIP, not retry blind"
    mkdir -p "$WORK/bin"
    : >"$WORK/reran"
    cat >"$WORK/bin/gh" <<FAKE
#!/bin/bash
case "\$*" in
  *branches*) exit 1 ;;
  *rerun-failed-jobs*) echo "BAD" >> "$WORK/reran"; echo '{}' ;;
  *) echo '[]' ;;
esac
FAKE
    chmod +x "$WORK/bin/gh"
    run_sut >/dev/null
    [[ -z "$(reran_ids)" ]] || log_fail "retried with no way to tell a superseded head from a live one"
    log_pass "unreadable branch list skips the sweep"
}

test_summary_always_reports() {
    log_test "a legitimate zero must be distinguishable from a broken sweeper"
    fake_gh "[$(mk 1 "Watchdog: run 9 (gen 1)" ".github/workflows/watchdog-monitor.yml" "$LIVE_SHA" 1 "$NOW_ISO")]"
    local out
    out="$(run_sut)"
    grep -q 'considered=' <<<"$out" || log_fail "no breakdown printed; 0 retried reads as broken"
    grep -q 'excluded=1' <<<"$out" || log_fail "the breakdown does not say WHY it skipped"
    log_pass "summary reports the breakdown, not just a count"
}

test_control_removing_the_watchdog_filter_is_caught() {
    log_test "CONTROL: without the path filter, the watchdog IS retried"
    # A real BEHAVIOURAL control, not a file-differs check. The override is
    # inserted immediately after the genuine is_excluded definition -- appending
    # it at the end of the file would define it AFTER the loop already ran, so
    # the mutant would behave identically and the control would pass against
    # unmutated behaviour. That is the vacuity this repo's control-vacuity gate
    # exists to catch, and it is easy to write by accident.
    local mutant="$WORK/mutant.sh"
    awk '
        { print }
        /^is_excluded\(\) \{/ { infn = 1 }
        infn && /^\}/ { print "is_excluded() { return 1; }"; infn = 0 }
    ' "$SUT" >"$mutant"

    grep -q '^is_excluded() { return 1; }' "$mutant" ||
        log_fail "CONTROL WAS NOT PLANTED: the mutant is unmodified"

    fake_gh "[$(mk 1 "Watchdog: run 9 (gen 1)" ".github/workflows/watchdog-monitor.yml" "$LIVE_SHA" 1 "$NOW_ISO")]"
    PATH="$WORK/bin:$PATH" bash "$mutant" >/dev/null 2>&1 || true
    if [[ "$(reran_ids)" == "1" ]]; then
        log_pass "control fires: the mutant retries the watchdog the real script skips"
    else
        log_fail "CONTROL DID NOT FIRE: mutant skipped it too (reran='$(reran_ids)')"
    fi
}

test_watchdog_is_excluded_by_path
test_name_match_would_not_have_worked
test_genuine_failure_on_live_head_is_retried
test_dead_head_is_skipped
test_attempt_cap_is_honoured
test_age_floor_is_honoured
test_only_failure_status_is_queried
test_fails_closed_without_branch_list
test_summary_always_reports
test_control_removing_the_watchdog_filter_is_caught

echo
log_pass "nightly-retry filters: 10/10"
echo "  Blind spot: drives the script's DECISIONS, not GitHub's rerun semantics."
echo "  Cannot prove a retried workflow is idempotent -- that stays a review question."
