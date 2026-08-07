#!/bin/bash
# Unit test for the no-retry force-cancel decision in
# .ci/scripts/ci/watchdog-monitor.cjs: WHICH failures kill the run immediately,
# and WHAT the kill waits for.
#
# HISTORY. This file was `test-watchdog-cancel-label.sh` and existed for the
# `no-cancel-failure` label, which suppressed the force-cancel so a run could
# finish and report every red at once. The label was removed 2026-08-05: the
# operator's reason is that holding a known-red run open makes every CI
# iteration wait out the expensive legs (E2E, OPS) for information the drain
# below already delivers for the deterministic lanes. What remains under test is
# the part that outlived it -- the branch ordering and the drain -- so the file
# was reduced rather than deleted.
#
# WHY A UNIT TEST AND NOT A MIRROR. It would be easy to re-implement the boolean
# here and assert on the copy; that proves nothing about the watchdog. This calls
# the exported decision and reads WATCHDOG_NO_RETRY_PATTERNS out of the REAL
# watchdog-monitor.yml, so a rename of a pattern or a reordering of the branch
# fails here.
#
# Both directions matter:
#   - Too quiet: a deterministic Quality failure stops killing the run, and one
#     lint error burns the whole 44-minute fleet.
#   - Too loud: a Quality CANCELLATION (a runner flake, not a code verdict) kills
#     a run with zero failed jobs.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

WATCHDOG="$REPO_ROOT/.ci/scripts/ci/watchdog-monitor.cjs"
# The WATCHDOG_* env block lives with the monitor step, which moved from
# ci.yml to the chained watchdog-monitor.yml (ubuntu-slim generations).
CI_WORKFLOW="$REPO_ROOT/.github/workflows/watchdog-monitor.yml"

# The patterns under test are the ones CI actually sets, not a copy: a guard that
# works on invented job names while the real config never matches is the exact
# failure this gate exists to catch.
NO_RETRY_PATTERNS="$(sed -n "s/^ *WATCHDOG_NO_RETRY_PATTERNS: *'\(.*\)'$/\1/p" "$CI_WORKFLOW")"
if [[ -z "$NO_RETRY_PATTERNS" ]]; then
    echo "could not read WATCHDOG_NO_RETRY_PATTERNS from $CI_WORKFLOW" >&2
    exit 1
fi

# verdict <job-name> <is-failure 0|1> -> "cancel" | "continue"
verdict() {
    node -e '
const w = require(process.argv[1]);
const v = w.evaluateNoRetryCancel({
  jobName: process.argv[2],
  isFailure: process.argv[3] === "1",
  noRetryPatterns: process.argv[4].split(",").map(s => s.trim()),
});
process.stdout.write(v.cancel ? "cancel" : "continue");
' "$WATCHDOG" "$1" "$2" "$NO_RETRY_PATTERNS"
}

# drain_mode <job-name> -> "instant" | "drain"
drain_mode() {
    node -e '
const w = require(process.argv[1]);
const v = w.evaluateNoRetryCancel({
  jobName: process.argv[2],
  isFailure: true,
  noRetryPatterns: process.argv[3].split(",").map(s => s.trim()),
});
process.stdout.write(v.noDrain ? "instant" : "drain");
' "$WATCHDOG" "$1" "$NO_RETRY_PATTERNS"
}

# ---------------------------------------------------------------------------

test_patterns_are_real() {
    # Anti-vacuity: if the pattern list stopped covering Quality, every case
    # below would pass for the wrong reason.
    assert_contains "$NO_RETRY_PATTERNS" "Quality" "watchdog-monitor.yml still lists Quality as no-retry"
    assert_contains "$NO_RETRY_PATTERNS" "Review Gate" "watchdog-monitor.yml still lists Review Gate as no-retry"
    log_pass "reading the real WATCHDOG_NO_RETRY_PATTERNS from watchdog-monitor.yml ($NO_RETRY_PATTERNS)"
}

test_quality_failure_cancels() {
    assert_eq "$(verdict 'Quality / Packages' 1)" "cancel" \
        "a Quality failure must force-cancel: a lint or type error is deterministic"
    log_pass "a Quality failure force-cancels the run"
}

test_review_gate_cancels() {
    assert_eq "$(verdict 'Review Gate' 1)" "cancel" \
        "Review Gate fails immediately and force-cancels (CLAUDE.md)"
    log_pass "a Review Gate failure force-cancels the run"
}

test_no_suppression_hatch_remains() {
    # The point of the 2026-08-05 removal, asserted rather than assumed: the
    # decision takes NO argument that can hold the cancel back. Passing the old
    # suppression flag must not change the answer, so a half-reverted removal
    # (the branch restored, the plumbing not) cannot pass silently.
    local out
    out="$(node -e '
const w = require(process.argv[1]);
const patterns = process.argv[2].split(",").map(s => s.trim());
const v = w.evaluateNoRetryCancel({
  jobName: "Quality / Packages",
  isFailure: true,
  skipCancellationOnFailure: true,
  noRetryPatterns: patterns,
});
process.stdout.write(v.cancel ? "cancel" : "continue");
' "$WATCHDOG" "$NO_RETRY_PATTERNS")"
    assert_eq "$out" "cancel" \
        "no ignored/leftover flag may suppress the force-cancel"
    log_pass "the force-cancel has no suppression hatch left"
}

test_non_no_retry_job_is_unaffected() {
    # A job outside the no-retry list never took this branch; it falls through to
    # AI classification downstream.
    assert_eq "$(verdict 'Build (Renet) / Renet (Full)' 1)" "continue" \
        "a non-no-retry failure must not be force-cancelled by this branch"
    log_pass "jobs outside the no-retry list fall through to classification"
}

test_cancellation_is_not_a_failure() {
    # Branch 1 is gated on `failed.includes(job)` on purpose: a non-stuck
    # CANCELLATION of a Quality job is an infra flake, and nuking a 0-failure run
    # for it is wrong.
    assert_eq "$(verdict 'Quality / Packages' 0)" "continue" \
        "a cancelled (not failed) Quality job must not force-cancel the run"
    log_pass "a cancellation is not treated as a failure"
}

test_review_gate_skips_the_drain() {
    # CLAUDE.md: Review Gate fails immediately, full stop. There is no sibling
    # verdict worth collecting when the red means "reply to the review".
    assert_eq "$(drain_mode 'Review Gate')" "instant" "Review Gate kills the run without draining"
    assert_eq "$(drain_mode 'Quality / Review Gate')" "instant" \
        "a job matching both lists must still skip the drain"
    assert_eq "$(drain_mode 'Quality / Packages')" "drain" "a Quality lane waits for its siblings"
    log_pass "Review Gate skips the drain; Quality lanes wait for theirs"
}

# --- Drain-before-cancel (pendingNoRetryJobs) -------------------------------
#
# A Quality failure force-cancels with no retry and no AI. What the drain changes
# is WHEN: it waits for the sibling no-retry jobs to reach a terminal state, so
# one round reports every failing lane instead of only the first. Before this,
# nine other quality jobs were killed mid-flight and their verdicts were never
# reported -- which is why CI gates surfaced exactly one failure per round. This
# is the mechanism that makes a full-run hold unnecessary for the lanes whose
# verdicts arrive in seconds.

# pending <json-jobs> -> comma-joined names of the jobs still holding the cancel
pending() {
    node -e '
const w = require(process.argv[1]);
const out = w.pendingNoRetryJobs({
  jobs: JSON.parse(process.argv[2]),
  noRetryPatterns: process.argv[3].split(",").map(s => s.trim()),
  excludePatterns: (process.argv[4] || "").split(",").map(s => s.trim()).filter(Boolean),
});
process.stdout.write(out.map(j => j.name).join(","));
' "$WATCHDOG" "$1" "$NO_RETRY_PATTERNS" "${2:-}"
}

test_drain_waits_for_running_quality_lanes() {
    local jobs='[
      {"name":"Quality / Code","status":"completed"},
      {"name":"Quality / Content","status":"in_progress"},
      {"name":"Quality / Go","status":"queued"}
    ]'
    assert_eq "$(pending "$jobs")" "Quality / Content,Quality / Go" \
        "a running and a queued lane both hold the cancel"
    log_pass "the force-cancel is held while sibling lanes are still running"
}

test_drain_releases_when_all_terminal() {
    local jobs='[
      {"name":"Quality / Code","status":"completed"},
      {"name":"Quality / Content","status":"completed"}
    ]'
    assert_eq "$(pending "$jobs")" "" \
        "with every lane terminal, nothing holds the cancel"
    log_pass "the force-cancel fires once every no-retry job is terminal"
}

test_drain_ignores_expensive_jobs() {
    # The whole point of force-cancelling is to stop the expensive legs. Those
    # are NOT in the no-retry list, so they must never hold the cancel open --
    # otherwise a lint error would wait 50 minutes for the E2E matrix.
    local jobs='[
      {"name":"Tests + Infra / E2E Workers (fedora-43)","status":"in_progress"},
      {"name":"OPS Tests / OPS Provision (linux-amd64)","status":"in_progress"}
    ]'
    assert_eq "$(pending "$jobs")" "" \
        "E2E and OPS jobs must not delay the cancel"
    log_pass "expensive non-quality jobs do not hold the cancel open"
}

test_drain_never_waits_on_review_gate() {
    # CLAUDE.md: Review Gate fails immediately, full stop. It must not be
    # something the drain waits on either.
    local jobs='[{"name":"Review Gate","status":"in_progress"}]'
    assert_eq "$(pending "$jobs")" "" \
        "Review Gate is excluded from the drain set"
    log_pass "Review Gate never holds the cancel open"
}

test_drain_honours_exclude_patterns() {
    # The watchdog's own job is excluded from monitoring; it must not be able to
    # hold its own cancel open forever.
    local jobs='[
      {"name":"Quality / Watchdog Helper","status":"in_progress"},
      {"name":"Quality / Code","status":"in_progress"}
    ]'
    assert_eq "$(pending "$jobs" "Watchdog Helper")" "Quality / Code" \
        "excluded jobs are dropped from the drain set"
    log_pass "excluded jobs do not hold the cancel open"
}

log_test "test-watchdog-no-retry-cancel"
test_patterns_are_real
test_quality_failure_cancels
test_review_gate_cancels
test_no_suppression_hatch_remains
test_non_no_retry_job_is_unaffected
test_cancellation_is_not_a_failure
test_review_gate_skips_the_drain
test_drain_waits_for_running_quality_lanes
test_drain_releases_when_all_terminal
test_drain_ignores_expensive_jobs
test_drain_never_waits_on_review_gate
test_drain_honours_exclude_patterns
echo ""
log_pass "all tests passed"
