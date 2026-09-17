"""Port of `.ci/scripts/test/gates/test-watchdog-log-capture.sh`.

Failed-step log capture in `.ci/scripts/ci/watchdog-monitor.cjs`.

WHAT BROKE. The watchdog auto-retries failures, and a rerun makes attempt 1's job logs unreachable. Nothing persisted them: fetchJobLogs kept an 80-line excerpt in an in-process Map that dies with the generation, and there was no upload-artifact anywhere in the watchdog path. So the retry destroyed the evidence for the only question worth asking afterwards -- was that a real break
or a flake? -- and it destroyed it as a direct consequence of the action taken in response to it.

WHY THIS IS NOT A UNIT TEST. The claim being tested is an ORDERING claim across the whole monitor: "the log is on disk BEFORE anything reruns the job". A pure-function test cannot see that. So this drives the REAL monitor() with a mocked GitHub client and asserts on the filesystem afterwards.

Both directions matter:
  - Capture must happen on the retry path (or the evidence is still lost).
  - Capture must happen on the fail-fast path too (that log is the one a human
    reads to fix the break).

ONE DELIBERATE DIFFERENCE FROM THE TWIN, and it is about parallelism rather than about the subject. The twin's `test_captured_content_*` and `test_capture_filename_*` READ `$WORK/retry`, a directory the EARLIER `test_capture_before_the_rerun` produced; run out of order, or in isolation, they find nothing and assert on an empty path. pytest does not promise that ordering once `-n 8
--dist loadgroup` distributes items, so each case here mints its own capture directory under `tmp_path` via `capture_retry()`. Same claim, no inter-test coupling.
"""

import pathlib

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-watchdog-log-capture.sh"

WATCHDOG = paths.from_root(".ci", "scripts", "ci", "watchdog-monitor.cjs")

# The harness: mock github/context/core, run the real monitor once, print what it did. Argv: <watchdog> <capture-dir> <job-name> <run-status> [event] [conclusion] [elapsed-minutes]
HARNESS_CJS = r"""
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
"""

MONITOR_ENV = {
    "WATCHDOG_TARGET_RUN_ID": "999",
    "WATCHDOG_EXCLUDE_PATTERNS": "Watchdog,CI Complete",
    "WATCHDOG_NO_RETRY_PATTERNS": "Quality,Review Gate",
    "WATCHDOG_INSTALL_VALIDATION_PATTERNS": "Validate Install Methods / Linux",
    "WATCHDOG_RETRY_ALLOWLIST_PATTERNS": "E2E,OPS,Fork Isolation",
    "CLOUDFLARE_API_TOKEN": "",
    "CLOUDFLARE_ACCOUNT_ID": "",
}

RETRY_JOB = "Tests + Infra / E2E Workers (fedora-43)"
FAST_FAIL_JOB = "Stage Artifacts / Stage Artifacts"


def subject(gate):
    # The four lines this used to hold were byte-identical in three watchdog gate tests;
    # they live in `harness` now. See harness.watchdog_subject for why this one is extractable where an assertion message is not.
    return harness.watchdog_subject(gate, WATCHDOG)


def harness_script(gate, tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "harness.cjs"
    if not path.is_file():
        path.write_text(HARNESS_CJS, encoding="utf-8")
    subject(gate)
    return path


def run_monitor(
    gate,
    tmp_path: pathlib.Path,
    job: str,
    status: str,
    capture_subdir: str,
    event: str = "pull_request",
    deadline: str = "",
    conclusion: str = "failure",
    elapsed: str = "5",
) -> str:
    """The action trace, which is the LAST stdout line the harness prints."""
    capture = tmp_path / capture_subdir if capture_subdir else None
    if capture is not None:
        capture.mkdir(parents=True, exist_ok=True)
    env = dict(MONITOR_ENV)
    env["WATCHDOG_DEADLINE_SECONDS"] = deadline
    result = harness.run(
        [
            "node",
            str(harness_script(gate, tmp_path)),
            str(subject(gate)),
            "" if capture is None else str(capture),
            job,
            status,
            event,
            conclusion,
            elapsed,
        ],
        env=env,
        timeout=300,
    )
    lines = [ln for ln in result.out.splitlines() if ln.strip()]
    if not lines:
        gate.log_fail(
            "the monitor printed no trace at all (rc=%d), so no claim below could be "
            "made about it. stderr: %s" % (result.rc, result.err.strip()[:400])
        )
    return lines[-1]


def captured_files(tmp_path: pathlib.Path, subdir: str) -> int:
    directory = tmp_path / subdir
    if not directory.is_dir():
        return 0
    return len(list(directory.rglob("*.log")))


def capture_retry(gate, tmp_path: pathlib.Path) -> pathlib.Path:
    """Drive the retry path once and hand back the directory it captured into.

    Its own directory per test, so the two cases that inspect the captured FILE do not depend on another test having run first. See the module docstring.
    """
    trace = run_monitor(gate, tmp_path, RETRY_JOB, "completed", "retry")
    if "rerun" not in trace:
        gate.log_fail(
            "the retry path did not run, so there is no captured file to inspect: %s" % trace
        )
    files = sorted((tmp_path / "retry").rglob("*.log"))
    if not files:
        gate.log_fail("the retry path captured no log at all, so the cases below have no subject")
    return files[0]


def test_capture_on_the_fail_fast_path(gate, tmp_path):
    """Stage Artifacts is not on the retry allowlist, so with the classifier unavailable this force-cancels. The log must still be on disk: it is the one a human reads to fix the break."""
    trace = run_monitor(gate, tmp_path, FAST_FAIL_JOB, "in_progress", "fastfail")
    gate.assert_contains(
        trace,
        "force-cancel",
        "a non-allowlisted failure force-cancels when the classifier is down",
    )
    gate.assert_eq(
        captured_files(tmp_path, "fastfail"),
        1,
        "exactly one log was captured on the fail-fast path",
    )
    gate.log_pass("the failed job's log is captured on the fail-fast path (%s)" % trace)


def test_capture_before_the_rerun(gate, tmp_path):
    """THE ORDERING CLAIM. An allowlisted (known-flaky) job with the classifier down takes the retry path. The capture must already be on disk by the time the rerun is dispatched -- after it, attempt 1's logs are unreachable."""
    trace = run_monitor(gate, tmp_path, RETRY_JOB, "completed", "retry")
    gate.assert_contains(
        trace, "rerun", "an allowlisted failure still reruns when the classifier is down"
    )
    gate.assert_not_contains(trace, "force-cancel", "the retry path must not cancel")
    gate.assert_eq(
        captured_files(tmp_path, "retry"), 1, "the log was captured even though the job was rerun"
    )
    # The trace is ordered: the log fetch (which performs the capture) must appear before the rerun request.
    before_rerun = trace.split("request:rerun")[0]
    gate.assert_contains(
        before_rerun,
        "fetched-logs",
        "the log was fetched and captured BEFORE the rerun was dispatched",
    )
    gate.log_pass("the log is captured before the rerun destroys it (%s)" % trace)


def test_captured_content_is_the_whole_log_not_the_excerpt(gate, tmp_path):
    """The excerpt is tuned for the classifier's context window and stops at the first error block. A human debugging afterwards wants everything, and this is the last moment it exists -- so the file must contain the post-error cleanup lines the 80-line excerpt deliberately cuts."""
    body = capture_retry(gate, tmp_path).read_text(encoding="utf-8")
    gate.assert_contains(
        body, "Post job cleanup.", "the captured file holds the COMPLETE log, not the excerpt"
    )
    gate.assert_contains(
        body, "No APT metadata files found", "the captured file holds the error itself"
    )
    gate.log_pass("the captured file is the complete log, not the truncated excerpt")


def test_capture_filename_is_traceable(gate, tmp_path):
    """A job name carries slashes, spaces and parentheses, none of which belong in a filename; the job id disambiguates legs that sanitise alike. The name must still be recognisable or the artifact is useless."""
    base = capture_retry(gate, tmp_path).name
    gate.assert_contains(base, "E2E_Workers", "the sanitised filename still names the job")
    gate.assert_contains(base, "4242", "the filename carries the job id for disambiguation")
    gate.log_pass("captured filenames are sanitised but still traceable (%s)" % base)


def test_no_capture_dir_means_no_capture_and_no_crash(gate, tmp_path):
    """Capture is best-effort by design: an ad-hoc or local invocation sets no directory, and that must not break the watchdog."""
    trace = run_monitor(gate, tmp_path, FAST_FAIL_JOB, "in_progress", "")
    gate.assert_not_contains(trace, "THREW", "an unset capture directory must not throw")
    gate.assert_contains(
        trace, "force-cancel", "the watchdog still does its job with capture disabled"
    )
    gate.log_pass(
        "capture is best-effort: unset directory disables it without breaking the monitor"
    )


def test_a_scheduled_run_records_the_failure_and_keeps_monitoring(gate, tmp_path):
    """THE NIGHTLY PATH. A scheduled run must never be cancelled -- cancelling rewrites its conclusion from `failure` to `cancelled`, which is what hid twelve consecutive red nights.

    The half that is easy to get wrong is "keeps monitoring". If the exemption merely suppressed the cancel and returned, the watchdog chain would END at the first failing job, the nightly would run unwatched from there, and no later failure would get its log captured or its name into a roster.
    """
    trace = run_monitor(gate, tmp_path, FAST_FAIL_JOB, "in_progress", "sched", "schedule", "1")
    gate.assert_not_contains(trace, "force-cancel", "a scheduled run must NOT be force-cancelled")
    gate.assert_not_contains(trace, "request:cancel", "nor cancelled by the fallback path")
    # Phase 3b (2026-08-26): the cancel-exempt path no longer core.setFailed()s, because 63 of 64 repo-wide `failure` conclusions were the watchdog working correctly. The INTENT is unchanged -- the outcome must still be recorded.
    gate.assert_contains(trace, "output:by_design=true", "the outcome is still recorded")
    gate.assert_contains(
        trace,
        "output:by_design_kind=left-uncancelled",
        "and names which by-design path it was",
    )
    gate.assert_contains(
        trace, "output:continue=true", "and the chain keeps monitoring rather than ending"
    )
    gate.assert_eq(
        captured_files(tmp_path, "sched"), 1, "the log is still captured on the nightly path"
    )
    gate.log_pass(
        "a scheduled run records the failure, captures the log, and keeps monitoring (%s)" % trace
    )


def test_a_scheduled_run_still_retries_a_known_flaky_leg(gate, tmp_path):
    """The nightly must not cry wolf. Suppressing the CANCEL must not also suppress the RETRY: a flaky E2E leg blipping on the network should be re-run, not turned into a red nightly that trains everyone to ignore the signal."""
    trace = run_monitor(gate, tmp_path, RETRY_JOB, "completed", "schedretry", "schedule")
    gate.assert_contains(
        trace, "request:rerun", "an allowlisted flaky leg is still retried on the nightly"
    )
    gate.assert_not_contains(trace, "force-cancel", "and the run is still never cancelled")
    gate.assert_eq(captured_files(tmp_path, "schedretry"), 1, "with its log captured first")
    gate.log_pass("a scheduled run still retries a known-flaky leg (%s)" % trace)


def test_a_stuck_job_on_a_scheduled_run_is_never_retried(gate, tmp_path):
    """THE REVIEW FINDING (PR #541, high severity), and a regression from the forceCancel-returns-bool refactor two commits earlier.

    Branch 0 exists to say: a STUCK cancellation never goes near AI or retry, because "the job hung once, retrying would just hang again". It ended with `if (await forceCancel(msg)) return;`. Once forceCancel began returning FALSE on a cancel-exempt run, that return stopped firing on the nightly and execution fell through into branches 1-5. Branch 5 then received `isFailure: false`
    -- correct, it IS a cancellation -- and the "non-stuck cancellation is a runner/infra flake" path resolved it to retry:true. So the one run type that must never burn a pointless hour would have re-run a job that had already hung for STUCK_THRESHOLD_MIN.
    """
    trace = run_monitor(
        gate, tmp_path, RETRY_JOB, "completed", "stuck", "schedule", "1", "cancelled", "90"
    )
    gate.assert_not_contains(
        trace,
        "request:rerun",
        "a STUCK job must never be retried, even on a run where cancelling is suppressed",
    )
    gate.assert_not_contains(trace, "force-cancel", "and an exempt run is still never cancelled")
    gate.assert_contains(trace, "output:by_design=true", "the stuck job is still recorded")
    gate.log_pass("a stuck job on a scheduled run is recorded, not retried (%s)" % trace)


def test_a_stuck_job_on_a_PR_run_still_cancels(gate, tmp_path):  # noqa: N802 -- the twin's case name; parity compares by name
    """The other direction: on a normal PR the stuck branch must still terminate the run exactly as before. If this regressed, the fix would have traded one bug for another."""
    trace = run_monitor(
        gate, tmp_path, RETRY_JOB, "completed", "stuckpr", "pull_request", "1", "cancelled", "90"
    )
    gate.assert_contains(trace, "force-cancel", "a stuck job on a PR run still force-cancels")
    gate.assert_not_contains(trace, "request:rerun", "and is never retried")
    gate.log_pass("a stuck job on a PR run still cancels the run (%s)" % trace)
