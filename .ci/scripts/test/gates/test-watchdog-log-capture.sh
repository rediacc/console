#!/bin/bash
# Behavioural test for failed-step log capture in .ci/scripts/ci/watchdog-monitor.cjs.
#
# WHAT BROKE. The watchdog auto-retries failures, and a rerun makes attempt 1's
# job logs unreachable. Nothing persisted them: fetchJobLogs kept an 80-line
# excerpt in an in-process Map that dies with the generation, and there was no
# upload-artifact anywhere in the watchdog path. So the retry destroyed the
# evidence for the only question worth asking afterwards -- was that a real
# break or a flake? -- and it destroyed it as a direct consequence of the
# action taken in response to it.
#
# WHY THIS IS NOT A UNIT TEST. The claim being tested is an ORDERING claim
# across the whole monitor: "the log is on disk BEFORE anything reruns the job".
# A pure-function test cannot see that. So this drives the REAL monitor() with a
# mocked GitHub client and asserts on the filesystem afterwards.
#
# Both directions matter:
#   - Capture must happen on the retry path (or the evidence is still lost).
#   - Capture must happen on the fail-fast path too (that log is the one a human
#     reads to fix the break).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

WATCHDOG="$REPO_ROOT/.ci/scripts/ci/watchdog-monitor.cjs"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# The harness: mock github/context/core, run the real monitor once, print what
# it did. Argv: <watchdog> <capture-dir> <job-name> <run-status>
cat >"$WORK/harness.cjs" <<'HARNESS'
const monitor = require(process.argv[2]);
const captureDir = process.argv[3];
const jobName = process.argv[4];
const runStatus = process.argv[5];
const runEvent = process.argv[6] || 'pull_request';
const jobConclusion = process.argv[7] || 'failure';
const elapsedMin = Number(process.argv[8] || 5);

const LOG_BODY = [
  'Run some/step@v1',
  'preparing the thing',
  '##[error]No APT metadata files found',
  '##[error]Process completed with exit code 1.',
  'Post job cleanup.',
].join('\n');

const actions = [];
// Two healthy siblings so a single CANCELLED job does not trip the
// mass-cancellation guard (`cancelled >= completed / 2`), which would exit
// before any failure handling and leave the trace empty.
const siblings = [
  { id: 1, name: 'Quality / Code', status: 'completed', conclusion: 'success' },
  { id: 2, name: 'Quality / Static', status: 'completed', conclusion: 'success' },
];
const allJobsRef = () => [job, ...siblings];
const startMs = Date.parse('2026-07-27T04:00:00Z');
const job = { id: 4242, name: jobName, status: 'completed', conclusion: jobConclusion,
              started_at: new Date(startMs).toISOString(),
              completed_at: new Date(startMs + elapsedMin * 60_000).toISOString() };

const github = {
  hook: { before: () => {} },
  paginate: async () => allJobsRef(),
  request: async (route) => { actions.push(`request:${route.includes('force-cancel') ? 'force-cancel' : route.includes('rerun-failed-jobs') ? 'rerun' : route}`); return {}; },
  rest: {
    actions: {
      getWorkflowRun: async () => ({ data: { status: runStatus, conclusion: null, run_attempt: 1, event: runEvent } }),
      listJobsForWorkflowRun: () => {},
      downloadJobLogsForWorkflowRun: async () => { actions.push('fetched-logs'); return { data: LOG_BODY }; },
      cancelWorkflowRun: async () => { actions.push('request:cancel'); return {}; },
    },
    issues: { listLabelsOnIssue: async () => ({ data: [] }) },
  },
};
const core = {
  setFailed: (m) => actions.push(`setFailed:${String(m).slice(0, 40)}`),
  warning: (m) => actions.push(`warning:${String(m).slice(0, 30)}`),
  error: () => {},
  setOutput: (k, v) => actions.push(`output:${k}=${v}`),
  info: () => {},
};
const context = { repo: { owner: 'rediacc', repo: 'console' }, runId: 1, payload: {} };

process.env.WATCHDOG_LOG_CAPTURE_DIR = captureDir;

monitor({ github, context, core })
  .then(() => { console.log(actions.join('|')); })
  .catch((e) => { console.log('THREW:' + e.message); process.exitCode = 3; });
HARNESS

# run <job-name> <run-status> <capture-subdir> -> prints the action trace
run_monitor() {
    local job="$1" status="$2" dir="$WORK/$3" event="${4:-pull_request}" deadline="${5:-}"
    # $6 = job conclusion (failure|cancelled), $7 = elapsed minutes (drives isStuck)
    mkdir -p "$dir"
    WATCHDOG_TARGET_RUN_ID=999 \
        WATCHDOG_EXCLUDE_PATTERNS='Watchdog,CI Complete' \
        WATCHDOG_NO_RETRY_PATTERNS='Quality,Review Gate' \
        WATCHDOG_INSTALL_VALIDATION_PATTERNS='Validate Install Methods / Linux' \
        WATCHDOG_RETRY_ALLOWLIST_PATTERNS='E2E,OPS,Fork Isolation' \
        WATCHDOG_DEADLINE_SECONDS="$deadline" \
        CLOUDFLARE_API_TOKEN='' CLOUDFLARE_ACCOUNT_ID='' \
        node "$WORK/harness.cjs" "$WATCHDOG" "$dir" "$job" "$status" "$event" "${6:-failure}" "${7:-5}" 2>/dev/null | tail -1
}

captured_files() { find "$WORK/$1" -type f -name '*.log' 2>/dev/null | wc -l | tr -d ' '; }

# ---------------------------------------------------------------------------

test_capture_on_the_fail_fast_path() {
    # Stage Artifacts is not on the retry allowlist, so with the classifier
    # unavailable this force-cancels. The log must still be on disk: it is the
    # one a human reads to fix the break.
    local trace
    trace="$(run_monitor 'Stage Artifacts / Stage Artifacts' 'in_progress' 'fastfail')"
    assert_contains "$trace" "force-cancel" "a non-allowlisted failure force-cancels when the classifier is down"
    assert_eq "$(captured_files fastfail)" "1" "exactly one log was captured on the fail-fast path"
    log_pass "the failed job's log is captured on the fail-fast path ($trace)"
}

test_capture_before_the_rerun() {
    # THE ORDERING CLAIM. An allowlisted (known-flaky) job with the classifier
    # down takes the retry path. The capture must already be on disk by the time
    # the rerun is dispatched -- after it, attempt 1's logs are unreachable.
    local trace
    trace="$(run_monitor 'Tests + Infra / E2E Workers (fedora-43)' 'completed' 'retry')"
    assert_contains "$trace" "rerun" "an allowlisted failure still reruns when the classifier is down"
    assert_not_contains "$trace" "force-cancel" "the retry path must not cancel"
    assert_eq "$(captured_files retry)" "1" "the log was captured even though the job was rerun"
    # The trace is ordered: the log fetch (which performs the capture) must
    # appear before the rerun request.
    local before_rerun
    before_rerun="${trace%%request:rerun*}"
    assert_contains "$before_rerun" "fetched-logs" "the log was fetched and captured BEFORE the rerun was dispatched"
    log_pass "the log is captured before the rerun destroys it ($trace)"
}

test_captured_content_is_the_whole_log_not_the_excerpt() {
    # The excerpt is tuned for the classifier's context window and stops at the
    # first error block. A human debugging afterwards wants everything, and this
    # is the last moment it exists -- so the file must contain the post-error
    # cleanup lines the 80-line excerpt deliberately cuts.
    local file
    file="$(find "$WORK/retry" -type f -name '*.log' | head -1)"
    assert_contains "$(cat "$file")" "Post job cleanup." \
        "the captured file holds the COMPLETE log, not the classifier excerpt"
    assert_contains "$(cat "$file")" "No APT metadata files found" "the captured file holds the error itself"
    log_pass "the captured file is the complete log, not the truncated excerpt"
}

test_capture_filename_is_traceable() {
    # A job name carries slashes, spaces and parentheses, none of which belong
    # in a filename; the job id disambiguates legs that sanitise alike. The
    # name must still be recognisable or the artifact is useless.
    local base
    base="$(basename "$(find "$WORK/retry" -type f -name '*.log' | head -1)")"
    assert_contains "$base" "E2E_Workers" "the sanitised filename still names the job"
    assert_contains "$base" "4242" "the filename carries the job id for disambiguation"
    log_pass "captured filenames are sanitised but still traceable ($base)"
}

test_no_capture_dir_means_no_capture_and_no_crash() {
    # Capture is best-effort by design: an ad-hoc or local invocation sets no
    # directory, and that must not break the watchdog.
    local trace
    trace="$(WATCHDOG_TARGET_RUN_ID=999 \
        WATCHDOG_EXCLUDE_PATTERNS='Watchdog,CI Complete' \
        WATCHDOG_NO_RETRY_PATTERNS='Quality,Review Gate' \
        WATCHDOG_INSTALL_VALIDATION_PATTERNS='Validate Install Methods / Linux' \
        WATCHDOG_RETRY_ALLOWLIST_PATTERNS='E2E,OPS,Fork Isolation' \
        CLOUDFLARE_API_TOKEN='' CLOUDFLARE_ACCOUNT_ID='' \
        node "$WORK/harness.cjs" "$WATCHDOG" "" 'Stage Artifacts / Stage Artifacts' 'in_progress' 2>/dev/null | tail -1)"
    assert_not_contains "$trace" "THREW" "an unset capture directory must not throw"
    assert_contains "$trace" "force-cancel" "the watchdog still does its job with capture disabled"
    log_pass "capture is best-effort: unset directory disables it without breaking the monitor"
}

test_a_scheduled_run_records_the_failure_and_keeps_monitoring() {
    # THE NIGHTLY PATH. A scheduled run must never be cancelled -- cancelling
    # rewrites its conclusion from `failure` to `cancelled`, which is what hid
    # twelve consecutive red nights.
    #
    # The half that is easy to get wrong is "keeps monitoring". If the exemption
    # merely suppressed the cancel and returned, the watchdog chain would END at
    # the first failing job, the nightly would run unwatched from there, and no
    # later failure would get its log captured or its name into a roster.
    # Stopping at the first red is how an outage stays under-diagnosed.
    #
    # Deadline of 1s so the generation hands off promptly instead of idling out
    # the 30s poll loop; the handoff (continue=true) IS the "still monitoring"
    # signal.
    local trace
    trace="$(run_monitor 'Stage Artifacts / Stage Artifacts' 'in_progress' 'sched' 'schedule' '1')"
    assert_not_contains "$trace" "force-cancel" "a scheduled run must NOT be force-cancelled"
    assert_not_contains "$trace" "request:cancel" "nor cancelled by the fallback path"
    assert_contains "$trace" "setFailed" "the failure is still recorded"
    assert_contains "$trace" "output:continue=true" "and the chain keeps monitoring rather than ending"
    assert_eq "$(captured_files sched)" "1" "the log is still captured on the nightly path"
    log_pass "a scheduled run records the failure, captures the log, and keeps monitoring ($trace)"
}

test_a_scheduled_run_still_retries_a_known_flaky_leg() {
    # The nightly must not cry wolf. Suppressing the CANCEL must not also
    # suppress the RETRY: a flaky E2E leg blipping on the network should be
    # re-run, not turned into a red nightly that trains everyone to ignore the
    # signal -- which is the same disease as the laundering this wave fixes.
    #
    # An earlier revision of this fix set skipCancellationOnFailure for exempt
    # runs, which sits in an `else if` chain and therefore skipped the retry
    # branch entirely. Caught by reading the branch structure, not by a test,
    # so this is the test that would have caught it.
    local trace
    trace="$(run_monitor 'Tests + Infra / E2E Workers (fedora-43)' 'completed' 'schedretry' 'schedule')"
    assert_contains "$trace" "request:rerun" "an allowlisted flaky leg is still retried on the nightly"
    assert_not_contains "$trace" "force-cancel" "and the run is still never cancelled"
    assert_eq "$(captured_files schedretry)" "1" "with its log captured first"
    log_pass "a scheduled run still retries a known-flaky leg ($trace)"
}

test_a_stuck_job_on_a_scheduled_run_is_never_retried() {
    # THE REVIEW FINDING (PR #541, high severity), and a regression from the
    # forceCancel-returns-bool refactor two commits earlier.
    #
    # Branch 0 exists to say: a STUCK cancellation never goes near AI or retry,
    # because "the job hung once, retrying would just hang again". It ended with
    # `if (await forceCancel(msg)) return;`. Once forceCancel began returning
    # FALSE on a cancel-exempt run, that return stopped firing on the nightly and
    # execution fell through into branches 1-5. Branch 5 then received
    # `isFailure: false` -- correct, it IS a cancellation -- and the
    # "non-stuck cancellation is a runner/infra flake" path resolved it to
    # retry:true. So the one run type that must never burn a pointless hour would
    # have re-run a job that had already hung for STUCK_THRESHOLD_MIN.
    #
    # A cancelled job with elapsed >= STUCK_THRESHOLD_MIN (60m default) is the
    # shape no previous test produced: the other scheduled cases hardcode
    # conclusion 'failure', which never reaches branch 0 at all.
    local trace
    trace="$(run_monitor 'Tests + Infra / E2E Workers (fedora-43)' 'completed' 'stuck' 'schedule' '1' 'cancelled' '90')"
    assert_not_contains "$trace" "request:rerun" \
        "a STUCK job must never be retried, even on a run where cancelling is suppressed"
    assert_not_contains "$trace" "force-cancel" "and an exempt run is still never cancelled"
    assert_contains "$trace" "setFailed" "the stuck job is still recorded"
    log_pass "a stuck job on a scheduled run is recorded, not retried ($trace)"
}

test_a_stuck_job_on_a_PR_run_still_cancels() {
    # The other direction: on a normal PR the stuck branch must still terminate
    # the run exactly as before. If this regressed, the fix would have traded one
    # bug for another.
    local trace
    trace="$(run_monitor 'Tests + Infra / E2E Workers (fedora-43)' 'completed' 'stuckpr' 'pull_request' '1' 'cancelled' '90')"
    assert_contains "$trace" "force-cancel" "a stuck job on a PR run still force-cancels"
    assert_not_contains "$trace" "request:rerun" "and is never retried"
    log_pass "a stuck job on a PR run still cancels the run ($trace)"
}

log_test "test-watchdog-log-capture"
test_capture_on_the_fail_fast_path
test_capture_before_the_rerun
test_captured_content_is_the_whole_log_not_the_excerpt
test_capture_filename_is_traceable
test_no_capture_dir_means_no_capture_and_no_crash
test_a_scheduled_run_records_the_failure_and_keeps_monitoring
test_a_scheduled_run_still_retries_a_known_flaky_leg
test_a_stuck_job_on_a_scheduled_run_is_never_retried
test_a_stuck_job_on_a_PR_run_still_cancels
echo ""
log_pass "all tests passed"
