// Watchdog - monitors workflow jobs, uses AI to classify failures, and manages retries.
// Polls every 30 seconds, exits when the workflow completes or a failure requires action.
//
// Runs as a CHAIN of short generations on ubuntu-slim (watchdog-monitor.yml):
// the 1-vCPU runner's 15-minute job cap is a hard platform limit, so instead of
// one long monitor job, each generation polls until WATCHDOG_DEADLINE_SECONDS
// and then reports `continue=true` for the workflow to dispatch the next
// generation. Every terminal path (force-cancel done, rerun dispatched, run
// completed, mass-cancel observed) returns WITHOUT that output, ending the
// chain. All decision state is re-derived from the API each poll, so a fresh
// generation picks up exactly where the last one left off.
//
// On first failure: AI classifies logs as transient or code-change.
//   - Transient: the chain holds a PENDING RERUN. Classification of further
//     failures stops, the chain waits for the run to complete, then reruns
//     every failed job itself (POST .../rerun-failed-jobs) and keeps
//     monitoring attempt 2 with a reset generation. There is no separate
//     rerun workflow: that split only existed because the old in-run
//     watchdog died with the run it monitored, and the chain does not.
//   - Code-change: force-cancels immediately (no point waiting for other jobs).
//   - AI unavailable: retries ONLY when a failing job matches
//     WATCHDOG_RETRY_ALLOWLIST_PATTERNS.
//
//     READ THAT PRECISELY: the allowlist decides whether a rerun FIRES, not
//     which jobs come back. GitHub's rerun re-runs EVERY non-successful job in
//     the run, so once the trigger is met the blast radius is the whole run.
//     Observed live on run 30402596980: `Build (Docker) / Devcontainer (amd64)`
//     is on neither the retry allowlist nor the no-retry list, hit its own
//     30-minute timeout, and came back on attempt 2 anyway -- succeeding in
//     5m35s against a 5m29s norm. That was the outcome we wanted, but it is not
//     the outcome the allowlist promised, and the two layers should not be
//     confused when tuning either.
//     (the ones that boot VMs or pull images); everything else fails fast.
//     See evaluateRetryEligibility -- this used to be "retry everything", which
//     meant every failure in the repo was retried on a judgment nobody made.
// On attempt 2+: force-cancels without retry.
//
// TWO THINGS THE WATCHDOG MUST NOT DO, both learned the hard way:
//   - It must never cancel a `schedule` run. Cancelling rewrites the run's
//     conclusion from `failure` to `cancelled`, which reads as "superseded,
//     ignore" -- and that is exactly how twelve consecutive red nightlies went
//     unnoticed. See evaluateCancelExemption.
//   - It must never rerun a job without first persisting that job's log. The
//     rerun makes attempt 1's logs unreachable, so retrying blind destroys the
//     evidence needed to tell a real break from a flake. See persistJobLog.
//
// Required env vars:
//   WATCHDOG_EXCLUDE_PATTERNS            - Comma-separated job name patterns to exclude from monitoring
//   WATCHDOG_NO_RETRY_PATTERNS           - Comma-separated job name patterns that should never auto-retry
//   WATCHDOG_INSTALL_VALIDATION_PATTERNS - Comma-separated job name patterns identifying install-validation jobs
//   WATCHDOG_RETRY_ALLOWLIST_PATTERNS    - Comma-separated job name patterns retryable when the classifier is down
//
// Optional env vars (chained mode; when unset the script monitors its own run,
// reading PR context from the event payload as it always did):
//   WATCHDOG_TARGET_RUN_ID      - CI run to monitor (a dispatched generation's own
//                                 context.runId is the watchdog run, not the target)
//   WATCHDOG_PR_NUMBER          - PR number for live label reads
//   WATCHDOG_DEADLINE_SECONDS   - hand off to the next generation after this long
//   WATCHDOG_PENDING_RERUN      - 'true' when a prior generation classified a
//                                 failure as transient; wait + rerun mode
//   WATCHDOG_SKIP_RERUN         - 'true' when check-rerun-attempt.sh (the dumb,
//                                 deterministic attempt-cap backstop, run as a
//                                 separate workflow step) refused the rerun
//
// Optional env vars (AI failure classification, DeepSeek V4 Pro via Cloudflare's
// OpenAI-compatible /ai/v1/chat/completions endpoint):
//   CLOUDFLARE_API_TOKEN        - Cloudflare API token with Workers AI permission
//   CLOUDFLARE_ACCOUNT_ID       - Cloudflare account ID
//
// Optional env vars (failure-log capture):
//   WATCHDOG_LOG_CAPTURE_DIR    - directory to write failed jobs' COMPLETE logs
//                                 into before any rerun; the workflow uploads it
//                                 as an artifact. Unset = no capture.
//
// Labels (PR context only):
//   no-auto-retry      - Skip AI + retry entirely (force-cancel immediately)
//
// Usage (from actions/github-script):
//   script: return await require('./.ci/scripts/ci/watchdog-monitor.cjs')({github, context, core})

// A downloaded release binary that will not execute is normally a truncated or
// stale CDN download (transient). It is a corrupt build only when no platform's
// install validation survives it. The classifier prompt says as much, but a
// prompt is advice; this signature + cross-job check is the enforcement.
const BINARY_EXEC_FAILURE_RE =
  /is not a valid application for this OS platform|cannot execute binary file|Exec format error/i;

const matchesPatterns = (name, patterns) => patterns.some((p) => name.includes(p));

// Jobs whose force-cancel fires INSTANTLY, without waiting for the drain below.
// Per CLAUDE.md a Review Gate failure means review feedback is outstanding, not
// that code is broken: there is no sibling verdict worth collecting, so holding
// the run open for one buys nothing. Nothing else skips the drain.
const NO_DRAIN_PATTERNS = ['Review Gate'];

// Run events the watchdog must never cancel.
//
// `workflow_dispatch` is here for a reason that is easy to miss. `ci.yml`'s
// dispatch path IS the nightly rehearsal, and its own header calls it
// "schedule-equivalent BY CONSTRUCTION". That claim was false on the single
// dimension that matters most: with only `schedule` exempt, a rehearsal whose
// gate failed got force-cancelled and reported `cancelled`, so the rehearsal
// reproduced the laundering bug instead of proving its absence. A tool built to
// prove the nightly is honest cannot itself be dishonest in the same way.
//
// It is also the right answer independent of the rehearsal. Force-cancelling
// exists to stop burning runners on a run that a newer push has already
// superseded. Nothing supersedes a dispatch: a human asked for it deliberately,
// there is no later commit implying they stopped caring, and the conclusion is
// the entire product of the run. Cancelling it destroys the only thing it was
// for. Retry handling is separate and unaffected, so a flaky leg in a dispatched
// run is still re-run; only the conclusion-rewriting cancel is withheld.
const CANCEL_EXEMPT_EVENTS = ['schedule', 'workflow_dispatch'];

/**
 * May the watchdog cancel this run at all?
 *
 * WHY THIS EXISTS. Cancelling a run REWRITES ITS CONCLUSION. A run whose job
 * genuinely failed reports `conclusion: failure`; the same run, force-cancelled
 * by the watchdog, reports `conclusion: cancelled` -- and everything downstream
 * reads `cancelled` as "superseded by a newer push, ignore me". On a PR that is
 * fine, because a human is watching the PR and the next push supersedes it
 * anyway. On the NIGHTLY it is a disaster, because the nightly is the only thing
 * validating main (`full_suite` is `github.event_name != 'push'`, so
 * push-to-main runs no tests) and nobody is watching it.
 *
 * Measured 2026-07-27: `gh run list --workflow ci.yml --event schedule -L 12`
 * returned TWELVE `cancelled` and ZERO `success`, unbroken back to 2026-07-16.
 * Every one of those nights had a real, fixable gate failure. None of them were
 * noticed, because the run-level rollup said `cancelled`. The individual gate
 * breaks were the symptom; this laundering is why they survived twelve days.
 *
 * WHY IT LIVES IN CODE AND NOT IN A LABEL. Labels are read from the PR, and a
 * `schedule` run has no PR: `prNumber` is null and the label block never runs.
 * The nightly is structurally incapable of wearing a PR-side escape hatch, so
 * the only place this exemption can live is here.
 *
 * FAIL-CLOSED DIRECTION. An unknown or unreadable event is NOT exempt, so it
 * cancels exactly as it does today. The exemption only ever fires on a positive
 * match, which keeps the PR path byte-identical.
 */
function evaluateCancelExemption({ runEvent }) {
  const event = String(runEvent || '');
  const exempt = CANCEL_EXEMPT_EVENTS.includes(event);
  return {
    exempt,
    event,
    reason: exempt
      ? `run event "${event}" is cancel-exempt: cancelling would rewrite this run's conclusion from "failure" to "cancelled", which is what hid twelve consecutive red nightlies`
      : '',
  };
}

/**
 * Is this run merely SUPERSEDED by a newer push, rather than actually failing?
 *
 * WHY THIS EXISTS. Measured on real traffic 2026-07-30, watchdog run
 * 30534675663 monitoring run 30530991847:
 *
 *   [0m] Run: in_progress | Jobs: 10 done, 7 running, 0 queued, 0 failed, 2 cancelled
 *   Retrying: classifier returned transient at confidence 0.8
 *   ##[error]Job cancelled (likely manual / supersession): "Quality / Content"
 *   [1m] Run: in_progress | Jobs: 19 done, 1 running, 0 queued, 0 failed, 11 cancelled
 *   Workflow externally cancelled (11/19 jobs cancelled) - exiting
 *
 * A push created run 30534726467 fifteen seconds before that first poll, which
 * cancelled 30530991847 by concurrency group. That is the most ordinary event in
 * the repo. The watchdog nonetheless treated a superseded job as a failure: it
 * paid for a billed Workers AI classification and called `core.setFailed`, so
 * the watchdog job concluded `failure` for a run nobody broke.
 *
 * WHY THE EXISTING GUARD CANNOT COVER IT. The mass-cancellation check further
 * down only fires once `cancelled >= completed / 2`. During a supersession the
 * jobs flip a few at a time, so on the first poll that ratio is nowhere near
 * met -- here it was 2 of 10 -- and by the time it is met, `setFailed` has
 * already stuck to the step. A ratio cannot express "something newer replaced
 * me"; only the existence of a newer run can.
 *
 * This is the same class as the defect above: a conclusion that reads wrong.
 * Its cost is the mirror image. Laundering `failure` into `cancelled` hid twelve
 * red nightlies; reporting `failure` for a routine supersession trains the
 * operator to ignore watchdog reds, which would eventually hide a real one.
 *
 * FAIL-CLOSED DIRECTION, and it matters more here than anywhere else in this
 * file. A false positive means silently swallowing a genuine failure, so the
 * verdict needs all three of: no job actually failed, at least one was
 * cancelled, and a newer run demonstrably exists. An unreadable or failed
 * lookup passes `newerRunExists: false` and the run reports exactly as it does
 * today.
 *
 * Pure, so the policy is testable without a network round trip.
 */
function evaluateSupersession({ failedCount, normalCancelledCount, newerRunExists }) {
  const noFailures = Number(failedCount) === 0;
  const hasCancellations = Number(normalCancelledCount) > 0;
  const superseded = noFailures && hasCancellations && newerRunExists === true;
  return {
    superseded,
    noFailures,
    hasCancellations,
    reason: superseded
      ? 'a newer run exists for this workflow and branch, and no job in this run failed: these cancellations are a concurrency-group supersession, not a defect'
      : '',
  };
}

/**
 * Ask GitHub whether a newer run exists for the same workflow and branch.
 *
 * Only ever called once the cheap local half of evaluateSupersession already
 * holds, so a healthy run pays nothing. Any error resolves to `false`, which is
 * the fail-closed answer: the run then reports exactly as it would have.
 */
async function hasNewerRun({ github, context, run }) {
  try {
    const { data } = await github.rest.actions.listWorkflowRuns({
      owner: context.repo.owner,
      repo: context.repo.repo,
      workflow_id: run.workflow_id,
      branch: run.head_branch,
      per_page: 20,
    });
    return (data.workflow_runs || []).some((r) => r.id !== run.id && r.run_number > run.run_number);
  } catch (e) {
    console.log(`[supersession] newer-run lookup failed, assuming NOT superseded: ${e.message}`);
    return false;
  }
}

/**
 * Should a failed job force-cancel the run, before any retry handling
 * downstream?
 *
 * A no-retry job (Quality, Review Gate) that genuinely FAILED cancels: a lint
 * or type error is deterministic, so there is nothing to classify and nothing
 * to retry. A CANCELLATION of the same job is not a verdict about the code, so
 * it falls through -- see the branch comment at the call site.
 *
 * `noDrain` rides along because the two questions share the pattern lists: a
 * Review Gate failure cancels the instant it is seen, while everything else
 * waits for its sibling no-retry lanes to settle so one round reports every
 * failing lane (see pendingNoRetryJobs).
 *
 * Extracted and exported so the ordering is testable against the REAL
 * WATCHDOG_NO_RETRY_PATTERNS rather than a copy.
 */
function evaluateNoRetryCancel({ jobName, isFailure, noRetryPatterns }) {
  const noDrain = matchesPatterns(jobName, NO_DRAIN_PATTERNS);
  const matchesNoRetry = matchesPatterns(jobName, noRetryPatterns);
  return {
    cancel: Boolean(isFailure) && matchesNoRetry,
    noDrain,
    matchesNoRetry,
  };
}

/**
 * A failure was not a confident code-change verdict. May it be RETRIED?
 *
 * WHY THIS EXISTS (issue #537). The classifier has been returning HTTP 402, so
 * `classifyFailure` falls back to `{ classification: 'transient', confidence: 0 }`
 * on every single failure. The retry branch only checks for a CONFIDENT
 * code-change verdict, so a confidence-0 fallback always lands in the retry
 * path: every failure in the repo, of every kind, has been auto-retried on the
 * strength of a judgment nobody made.
 *
 * That is only defensible while somebody reads the log afterwards, and nobody
 * does -- worse, the retry itself destroyed the log (see persistJobLog). The
 * 07-27 nightly is the receipt: `Stage Artifacts` failed on a deterministic,
 * perfectly reproducible empty-channel bug, and the watchdog spent a full
 * second attempt (~55 minutes of machine time) re-proving it before cancelling
 * anyway.
 *
 * So when the classifier cannot speak, retry ONLY the jobs whose failures are
 * known to be genuinely flaky -- the ones that boot VMs or pull images across
 * the network -- and fail everything else fast. A deterministic gate failure
 * should cost one attempt, not two.
 *
 * FAIL-CLOSED DIRECTION. Unknown job, empty allowlist, or a classifier that
 * cannot be reached all resolve to NO retry. The permissive answer requires a
 * positive match, so a typo in the allowlist costs an extra red round, never a
 * silent blind retry.
 *
 * Pure so the policy is testable against the REAL allowlist and the REAL job
 * names, not a copy of either.
 */
function evaluateRetryEligibility({
  jobName,
  isFailure,
  classification,
  confidence,
  classifierAvailable,
  threshold,
  retryAllowlistPatterns,
  guardForced = false,
}) {
  // OPERATOR DECISION 2026-07-30: for provisioning legs the ALLOWLIST BEATS a
  // confident code-change verdict. This deliberately re-opens part of #537 and
  // the trade was made with that stated, so it is recorded here rather than
  // buried.
  //
  // What forced it: run 30540751569 job 90867219911. `Tests + Infra / E2E Ceph`
  // failed on "failed to install Docker on node 21: ssh command failed: exit
  // status 6" -- infrastructure -- and the classifier answered code-change at
  // 0.9 with the reasoning "the error message indicates a setup error and E2E
  // tests failed, which suggests a problem with the code under test". That is a
  // tautology over the words "Setup failed", not an analysis, and because 0.9
  // clears the threshold it suppressed the retry and cost a full red round on
  // an allowlisted leg.
  //
  // Why the allowlist is the safer authority HERE specifically: membership is a
  // hand-curated statement that a leg boots VMs or pulls images across the
  // network, which is a claim about the JOB and cannot be wrong about a given
  // failure the way a model's reading of a log can. The cost is bounded and
  // small: MAX_ATTEMPTS caps this at ONE extra attempt.
  //
  // guardForced is the one thing that still wins, and it must. The binary-exec
  // guard synthesises `code-change` at confidence 1 precisely to BLOCK a retry
  // of a job that downloads and executes a released binary; letting a pattern
  // match override that would silently defeat a deliberate safety check. No
  // install-validation job matches the current allowlist, so this is defence in
  // depth rather than a live conflict, and it stays correct if either list moves.
  const allowlistOverridesVerdict =
    Boolean(isFailure) && !guardForced && matchesPatterns(jobName, retryAllowlistPatterns || []);

  if (classification === 'code-change' && confidence >= threshold) {
    if (allowlistOverridesVerdict) {
      return {
        retry: true,
        allowlistOverride: true,
        reason:
          `classifier returned code-change at confidence ${confidence}, but "${jobName}" is on the ` +
          `provisioning retry allowlist, which OVERRIDES the verdict (operator decision 2026-07-30): ` +
          `these legs boot VMs and pull images, so a model reading of the log is less reliable than the ` +
          `curated list. Bounded to one extra attempt by MAX_ATTEMPTS`,
      };
    }
    return {
      retry: false,
      reason: `classifier returned code-change at confidence ${confidence} (>= ${threshold}) -- a retry would re-prove a deterministic failure`,
    };
  }
  if (classifierAvailable) {
    return {
      retry: true,
      reason: `classifier returned ${classification} at confidence ${confidence} -- treating as transient`,
    };
  }
  // THE ALLOWLIST GOVERNS FAILURES ONLY. A non-stuck CANCELLATION is not a
  // verdict about the code: the job never reached one. It is a runner or infra
  // flake, and the branch-1 comment above already states the rule this restores
  // -- "nuking a 0-failure run for it is wrong" -- which is precisely why
  // cancellations are routed to the retry path in the first place.
  //
  // Getting this wrong is not theoretical. The first version of this function
  // applied the allowlist to cancellations too, and PR #541's own CI caught it
  // within one round: `Quality / Built-www Gates` was CANCELLED with zero failed
  // jobs anywhere in the run, and the watchdog force-cancelled the entire
  // pipeline (39 green jobs, 16 killed) on the strength of an allowlist miss.
  // Before the change that cancellation would simply have been re-run.
  //
  // Stuck cancellations never arrive here: they bypass classification entirely
  // at branch 0 and force-cancel, because a job that hung will hang again.
  if (!isFailure) {
    return {
      retry: true,
      reason: `classifier unavailable, but "${jobName}" was CANCELLED rather than failed -- a non-stuck cancellation is a runner/infra flake, not a code verdict, so it is re-run rather than used to kill the run`,
    };
  }
  const allowlisted = matchesPatterns(jobName, retryAllowlistPatterns || []);
  return allowlisted
    ? {
        retry: true,
        reason: `classifier unavailable, but "${jobName}" is on the known-flaky retry allowlist (boots VMs or pulls images), so one retry is warranted`,
      }
    : {
        retry: false,
        reason: `classifier unavailable and "${jobName}" is not on the known-flaky retry allowlist -- failing fast rather than retrying blind`,
      };
}

/**
 * Which no-retry jobs are still in flight?
 *
 * WHY THIS EXISTS. A failed `Quality / *` job used to force-cancel the run the
 * instant it was seen. That is why CI gates surfaced exactly ONE failure per
 * round: nine other quality jobs were killed mid-flight, their verdicts never
 * reported, and the operator learned about the next problem only after fixing
 * this one and pushing again. With gates grouped into ten lanes the same
 * behaviour would be worse, because each kill now discards a whole lane's worth
 * of pending results.
 *
 * So a quality failure now DRAINS: the run is still force-cancelled with no
 * retry and no AI classification (a lint error is deterministic; retrying it is
 * pointless), but only once every other no-retry job has reached a terminal
 * state. The expensive jobs the cancel exists to stop -- the E2E and OPS legs --
 * are not in this set, so they still die at the same moment they used to.
 *
 * NO_DRAIN_PATTERNS jobs (Review Gate) are excluded: CLAUDE.md specifies those
 * fail immediately, full stop, and an outstanding review is not something to
 * wait on.
 *
 * Pure so the ordering is testable against the REAL pattern list.
 */
function pendingNoRetryJobs({ jobs, noRetryPatterns, excludePatterns = [] }) {
  return jobs.filter(
    (j) =>
      j.status !== 'completed' &&
      !excludePatterns.some((p) => j.name.includes(p)) &&
      matchesPatterns(j.name, noRetryPatterns) &&
      !matchesPatterns(j.name, NO_DRAIN_PATTERNS)
  );
}

// Formats the COMPLETE set of failed jobs into a human-readable banner plus a
// one-line summary for the GitHub annotation. The watchdog force-cancels on the
// first failure it classifies, but a single poll can hold several already-failed
// jobs (e.g. lint + types + tests all red at once). Reporting only the one that
// drove the decision forces whoever reads the cancelled run to re-scan every job
// to find the siblings -- so both the banner and the annotation name them all.
// Pure (no closure/env dependency) so it can be unit-tested in isolation.
function formatFailureRoster(failedJobs, { owner, repo, runId }) {
  const jobUrl = (j) => `https://github.com/${owner}/${repo}/actions/runs/${runId}/job/${j.id}`;
  const lines = [];
  lines.push('#'.repeat(70));
  lines.push(`Cancelling: ${failedJobs.length} job(s) failed`);
  for (const j of failedJobs) {
    lines.push(`  ✗ "${j.name}"${j.id ? `  ${jobUrl(j)}` : ''}`);
  }
  lines.push('#'.repeat(70));
  const names = failedJobs.map((j) => `"${j.name}"`).join(', ');
  const summary =
    failedJobs.length === 1 ? `Job failed: ${names}` : `${failedJobs.length} jobs failed: ${names}`;
  return { lines, summary };
}

// Returns null when the guard does not apply (not an install-validation job, or
// no binary-exec signature in the log tail). Otherwise returns the decision:
//   { override: true }  -> the whole matrix failed to execute the binary: corrupt build
//   { override: false } -> at least one platform passed, or did not fail
//   { defer: true }     -> siblings still running; the matrix outcome is not known yet
function evaluateBinaryExecGuard({ job, logTail, jobs, installPatterns }) {
  if (!installPatterns.length || !matchesPatterns(job.name, installPatterns)) return null;
  if (!logTail || !BINARY_EXEC_FAILURE_RE.test(logTail)) return null;

  const installJobs = jobs.filter((j) => matchesPatterns(j.name, installPatterns));

  const passed = installJobs.filter((j) => j.conclusion === 'success');
  if (passed.length > 0) {
    return {
      override: false,
      reason: `binary-exec failure in "${job.name}", but ${passed.length} install-validation job(s) passed (${passed.map((j) => j.name).join(', ')}) -- the build executes elsewhere, treating as a download flake`,
    };
  }

  const unfinished = installJobs.filter((j) => j.status !== 'completed');
  if (unfinished.length > 0) {
    return {
      defer: true,
      reason: `binary-exec failure in "${job.name}", but ${unfinished.length} install-validation job(s) have not finished (${unfinished.map((j) => j.name).join(', ')}) -- deferring until the matrix settles`,
    };
  }

  const nonFailures = installJobs.filter((j) => j.conclusion !== 'failure');
  if (nonFailures.length > 0) {
    return {
      override: false,
      reason: `binary-exec failure in "${job.name}", but ${nonFailures.length} install-validation job(s) did not fail (${nonFailures.map((j) => `${j.name}=${j.conclusion}`).join(', ')})`,
    };
  }

  return {
    override: true,
    reason: `every install-validation job (${installJobs.length}) failed to execute the downloaded binary -- corrupt cross-platform build, not a CDN flake`,
  };
}

const monitor = async ({ github, context, core }) => {
  // Pin the GitHub REST API version on every request from this Octokit
  // instance. Without an explicit X-GitHub-Api-Version header, requests
  // default to 2022-11-28 and emit a per-call deprecation warning (that
  // version sunsets 2028-03-10). Pinning to the latest stable version
  // silences the warning and locks us to a known surface until we
  // deliberately bump. See:
  //   https://docs.github.com/en/rest/about-the-rest-api/api-versions
  //   https://docs.github.com/en/rest/overview/breaking-changes
  // The endpoints used here (createWorkflowDispatch, listJobsForWorkflowRun,
  // getWorkflowRun, force-cancel, cancel, downloadJobLogsForWorkflowRun) have
  // no breaking changes between 2022-11-28 and 2026-03-10 that affect us;
  // createWorkflowDispatch returns 200 with run details instead of 204, but
  // we await without reading the body.
  github.hook.before('request', (options) => {
    options.headers ??= {};
    options.headers['x-github-api-version'] ||= '2026-03-10';
  });

  // Chained-mode parameters (see the header comment). Fallbacks keep the
  // module runnable un-chained against its own run, which is what the gate
  // tests and any ad-hoc github-script invocation exercise.
  const targetRunId = Number(process.env.WATCHDOG_TARGET_RUN_ID || 0) || context.runId;
  const prNumber =
    Number(process.env.WATCHDOG_PR_NUMBER || 0) || context.payload.pull_request?.number || null;
  const deadlineMs = Number(process.env.WATCHDOG_DEADLINE_SECONDS || 0) * 1000;
  // How long a quality force-cancel may be held while its siblings drain.
  // 90s catches a near-simultaneous second failure (the roster the drain
  // exists for) without waiting out a lane that runs for minutes.
  const HELD_CANCEL_MAX_SECONDS = Number(process.env.WATCHDOG_HELD_CANCEL_MAX_SECONDS || 90);
  let pendingRerun = process.env.WATCHDOG_PENDING_RERUN === 'true';
  const skipRerun = process.env.WATCHDOG_SKIP_RERUN === 'true';

  const pollInterval = 30000; // 30 seconds (was 15s; halved API quota per generation)
  const maxRuntime = 10800000; // 3 hours
  const minRuntime = 30000; // 30 seconds minimum before allowing exit
  const startTime = Date.now();

  const MAX_ATTEMPTS = 2;

  // Grace period: wait N consecutive polls with all jobs complete before exiting.
  // Prevents premature exit during partial reruns where new jobs haven't appeared yet.
  const GRACE_POLLS = 3; // 3 polls × 30s = 90 seconds grace period
  let allCompleteStreak = 0;

  // Jobs to exclude from monitoring (required env var)
  if (
    !process.env.WATCHDOG_EXCLUDE_PATTERNS ||
    !process.env.WATCHDOG_NO_RETRY_PATTERNS ||
    !process.env.WATCHDOG_INSTALL_VALIDATION_PATTERNS
  ) {
    throw new Error(
      'WATCHDOG_EXCLUDE_PATTERNS, WATCHDOG_NO_RETRY_PATTERNS and WATCHDOG_INSTALL_VALIDATION_PATTERNS env vars are required'
    );
  }
  // Required too, and deliberately so: defaulting it would let a config drift
  // silently restore retry-everything, which is the behaviour issue #537 is
  // about. Missing config must be loud, not permissive.
  if (!process.env.WATCHDOG_RETRY_ALLOWLIST_PATTERNS) {
    throw new Error(
      'WATCHDOG_RETRY_ALLOWLIST_PATTERNS env var is required (see evaluateRetryEligibility)'
    );
  }
  const excludePatterns = process.env.WATCHDOG_EXCLUDE_PATTERNS.split(',').map((s) => s.trim());

  // Jobs that should not trigger auto-retry (failures are never transient)
  const noRetryPatterns = process.env.WATCHDOG_NO_RETRY_PATTERNS.split(',').map((s) => s.trim());

  // Jobs that download and execute a released binary; subject to the binary-exec guard
  const installValidationPatterns = process.env.WATCHDOG_INSTALL_VALIDATION_PATTERNS.split(',')
    .map((s) => s.trim())
    .filter(Boolean);

  // Jobs whose failures may still be retried when the classifier cannot speak.
  // See evaluateRetryEligibility.
  const retryAllowlistPatterns = process.env.WATCHDOG_RETRY_ALLOWLIST_PATTERNS.split(',')
    .map((s) => s.trim())
    .filter(Boolean);

  // Track jobs already handled to avoid re-logging the same failure every poll
  const handledJobs = new Set();

  // Deferred jobs stay eligible for handling on later polls, so they are tracked
  // separately from handledJobs and only announced once.
  const deferredJobs = new Set();

  // A no-retry (quality) failure has been seen and its force-cancel is being
  // held until the sibling no-retry jobs finish, so one round reports every
  // failing lane. See pendingNoRetryJobs for why.
  let pendingQualityCancel = false;
  // The drain has a DEADLINE. Waiting for every sibling no-retry lane to settle
  // buys a full roster, but only when a sibling is actually about to fail; when
  // nothing else does it is dead time on a run already known to be red.
  //
  // Measured on run 30470189106: Quality/Go failed at 16:25:10 and the cancel was
  // held on Quality/Security. Every OTHER Quality lane had finished by 16:25;
  // Security alone was still running two minutes later. The hold was waiting on
  // the single long pole, and it gained nothing because nothing else failed.
  let heldSince = 0;
  let heldQualityFailureMsg = '';

  // The TARGET run's event, re-read from the API every poll. Not
  // `context.eventName`: in chained mode this process is a `workflow_dispatch`
  // watchdog generation monitoring somebody else's run, so its own event name
  // says nothing about what it is watching. Consumed by evaluateCancelExemption
  // inside forceCancel. Stays null until the first successful fetch, which
  // fails closed (null is not exempt, so it cancels as it always did), and
  // every forceCancel call site sits after that fetch inside the poll loop.
  let targetRunEvent = null;
  let announcedExemption = false;

  // Helper: rerun the target run's failed jobs (the API behind
  // `gh run rerun --failed`). Only valid once the run has completed.
  async function executeRerun() {
    try {
      await github.request('POST /repos/{owner}/{repo}/actions/runs/{run_id}/rerun-failed-jobs', {
        owner: context.repo.owner,
        repo: context.repo.repo,
        run_id: targetRunId,
      });
      console.log(`Rerun of failed jobs triggered for run ${targetRunId}`);
      return true;
    } catch (e) {
      console.log(`WARNING: Failed to rerun failed jobs for run ${targetRunId}: ${e.message}`);
      return false;
    }
  }

  // AI failure classification: fetch job logs, call the classifier model, classify as
  // transient/code-change. Falls back to { classification: 'transient', confidence: 0 }
  // on any error (safe default = retry).
  // DeepSeek V4 Pro is a partner-served (Fireworks) model in Cloudflare's catalog,
  // reached through the OpenAI-compatible /ai/v1/chat/completions endpoint rather
  // than the native-Workers-AI /ai/run/<model> route the previous qwen model used.
  const AI_CONFIDENCE_THRESHOLD = 0.8;
  // NATIVE Workers AI, not a partner-served catalog model, and that distinction
  // is the whole point. This tier was moved to `deepseek/deepseek-v4-pro` on the
  // OpenAI-compatible /ai/v1 route, which is partner-served (Fireworks) and
  // billed from a PREPAID AI GATEWAY BALANCE rather than from the Workers Paid
  // plan. That balance is empty, so tier 1 has been answering
  //   HTTP 402 {"code":2021,"message":"Insufficient balance; add money to your
  //   gateway or use BYOK"}
  // continuously, and every allowlisted CI failure has been taking a blind retry
  // (~500 machine-minutes) with no classification behind it. Verified live
  // 2026-07-30 against the real account: the partner route returns 402 while
  // /ai/run/@cf/meta/llama-3.3-70b-instruct-fp8-fast returns 200 on the SAME
  // credentials, so the subscription is healthy and only the gateway is unfunded.
  // To go back to a partner-served model, fund the gateway or configure BYOK
  // first, and re-probe before trusting it.
  const AI_MODEL = '@cf/meta/llama-3.3-70b-instruct-fp8-fast';
  // Tier 2. Sonnet rather than Haiku deliberately: this verdict decides whether
  // to spend a full retry (~500 machine-minutes), so the marginal token cost of
  // the better model is irrelevant next to being wrong. Overridable for a cheap
  // experiment without editing code.
  const CLAUDE_MODEL = process.env.WATCHDOG_CLAUDE_MODEL || 'claude-sonnet-5';
  // Reasoning model: thinking happens before the answer, so give it a real
  // timeout and enough tokens that the reasoning phase cannot starve the
  // final JSON verdict. Budget-wise 25s still fits the generation deadline
  // (480s poll + ~25s AI + <=5min force-cancel wait < the 15-min slim cap).
  const AI_TIMEOUT = 25000; // 25 seconds
  const AI_MAX_TOKENS = 1024;

  // A non-2xx from either provider used to log the STATUS ONLY, which is how the
  // classifier chain went fully dark without anyone noticing what was wrong:
  // "HTTP 402" and "HTTP 400" say a request failed, not why, and both tiers
  // failing is indistinguishable from both tiers being absent. The body is where
  // the API names the cause (a wrong model id, a quota, a missing beta header),
  // and every one of those is a different fix. Truncated because a provider error
  // page can be an entire HTML document, and this lands in a public run log.
  async function errorBody(response) {
    try {
      const text = (await response.text()).trim().replace(/\s+/g, ' ');
      return text ? text.slice(0, 300) : '(empty body)';
    } catch {
      return '(body unreadable)';
    }
  }

  // A completed job's log never changes, so a deferred job re-examined on the
  // next poll costs no extra API call.
  const logTails = new Map();

  async function getLogTail(job) {
    if (!logTails.has(job.name)) logTails.set(job.name, await fetchJobLogs(job));
    return logTails.get(job.name);
  }

  // Persist a failed job's COMPLETE log to disk so the workflow can upload it
  // as an artifact.
  //
  // WHY THIS EXISTS. A rerun DESTROYS the evidence it was triggered by: once
  // attempt 2 starts, attempt 1's job logs are no longer reachable through the
  // normal run view, and the watchdog retries blind by default (the classifier
  // has been returning HTTP 402, so every failure fell back to
  // `transient, confidence 0` = retry). The only thing that ever saw attempt
  // 1's log was an 80-line in-memory excerpt in `logTails`, which dies with the
  // generation. So the single most common question after an auto-retry -- "was
  // that a real break or a flake?" -- was unanswerable by construction.
  //
  // Best-effort by design: capture must never be able to break the watchdog, so
  // every failure here is swallowed with a log line. No capture directory
  // configured means no capture, which is what ad-hoc/local invocations get.
  const LOG_CAPTURE_DIR = process.env.WATCHDOG_LOG_CAPTURE_DIR || '';
  function persistJobLog(job, fullText) {
    if (!LOG_CAPTURE_DIR) return;
    try {
      const fs = require('fs');
      const path = require('path');
      fs.mkdirSync(LOG_CAPTURE_DIR, { recursive: true });
      // Job names carry slashes, spaces and parentheses ("Tests + Infra / E2E
      // Workers (opensuse-16.0)"), none of which belong in a filename. The id
      // keeps it unique when two legs sanitise to the same string.
      const safeName = String(job.name)
        .replace(/[^A-Za-z0-9._-]+/g, '_')
        .slice(0, 120);
      const file = path.join(LOG_CAPTURE_DIR, `${safeName}-${job.id}.log`);
      fs.writeFileSync(file, fullText);
      console.log(
        `[logs] captured the full log for "${job.name}" (${fullText.length} bytes) before any retry`
      );
    } catch (e) {
      console.log(`[logs] could not capture the log for "${job.name}": ${e.message}`);
    }
  }

  async function fetchJobLogs(job) {
    try {
      const response = await github.rest.actions.downloadJobLogsForWorkflowRun({
        owner: context.repo.owner,
        repo: context.repo.repo,
        job_id: job.id,
      });
      const lines = String(response.data).split('\n');
      // Strip timestamp prefixes and ANSI escape codes.
      // ESC is built from its char code rather than written literally: a raw
      // control character in a regex is what no-control-regex exists to catch,
      // and spelling it out keeps the rule ENABLED for the accidental cases.
      // Same shape as packages/www/scripts/validate-tutorial-cast-output.js.
      const ESC = String.fromCharCode(0x1b);
      const ANSI_SGR_RE = new RegExp(`${ESC}\\[[0-9;]*m`, 'g');
      const stripped = lines.map((l) =>
        l.replace(/^\d{4}-\d{2}-\d{2}T[\d:.]+Z\s?/, '').replace(ANSI_SGR_RE, '')
      );
      // Persist the WHOLE log, not the excerpt below. The excerpt is tuned for
      // the classifier's context window; a human debugging afterwards wants
      // everything, and this is the last moment it exists.
      persistJobLog(job, stripped.join('\n'));
      // Anchor the excerpt at the FIRST failure marker, not the end of the
      // log: a failed job keeps logging through its if:always() cleanup and
      // post-steps, so a plain tail shows successful teardown instead of the
      // error. Run 29931338016 is the receipt: a deterministic `sudo: renet:
      // command not found` sat hundreds of lines before the tail, the
      // classifier was shown post-checkout git-config scrubbing, and it
      // honestly called that "no explicit error messages" -> transient (0.8).
      // The first marker is the root cause; later ones are cascade (failed
      // cleanup). Consecutive ##[error] lines belong to the same annotation.
      // No marker (rare) falls back to the tail. The binary-exec guard reads
      // this same excerpt, so the anchor un-blinds it too.
      let end = stripped.findIndex((l) => l.startsWith('##[error]'));
      if (end >= 0) {
        do {
          end++;
        } while (end < stripped.length && stripped[end].startsWith('##[error]'));
      } else {
        end = stripped.length;
      }
      return stripped.slice(Math.max(0, end - 80), end).join('\n');
    } catch (e) {
      console.log(`[AI] Failed to fetch logs for "${job.name}": ${e.message}`);
      return null;
    }
  }

  // The system prompt is shared by every provider: the verdict contract must not
  // vary by who is answering, or the allowlist tier would be comparing verdicts
  // produced under different rules.
  function readClassifierPrompt() {
    try {
      return require('fs').readFileSync('.ci/prompts/ci-failure-classifier.md', 'utf8').trim();
    } catch (e) {
      console.log(`[AI] Failed to read prompt file: ${e.message}`);
      return null;
    }
  }

  // One parser for every provider. Each returns text that must be the same JSON
  // verdict; validation is deliberately strict, because an unparseable or
  // out-of-contract answer must count as NO ANSWER (fall through to the next
  // tier) rather than as a low-confidence one.
  function parseClassifierVerdict(rawText) {
    try {
      const cleaned = String(rawText)
        .trim()
        .replace(/^```(?:json)?\n?/, '')
        .replace(/\n?```$/, '');
      const parsed = JSON.parse(cleaned);
      if (!['transient', 'code-change'].includes(parsed.classification)) return null;
      if (typeof parsed.confidence !== 'number' || parsed.confidence < 0 || parsed.confidence > 1)
        return null;
      return {
        classification: parsed.classification,
        confidence: parsed.confidence,
        reason: String(parsed.reason || '').slice(0, 200),
      };
    } catch {
      return null;
    }
  }

  // TIER 1: Cloudflare, DeepSeek V4 Pro.
  //
  // Partner-served (Fireworks) catalog model, so it is reached through the
  // OpenAI-compatible /ai/v1/chat/completions route rather than the
  // native-Workers-AI /ai/run/<model> route the previous qwen model used.
  async function callCloudflareClassifier(logTail, systemPrompt) {
    const token = process.env.CLOUDFLARE_API_TOKEN;
    const accountId = process.env.CLOUDFLARE_ACCOUNT_ID;
    if (!token || !accountId) return null;

    const url = `https://api.cloudflare.com/client/v4/accounts/${accountId}/ai/run/${AI_MODEL}`;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), AI_TIMEOUT);
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        // No `model` field: the /ai/run route names the model in the URL, unlike
        // the OpenAI-compatible /ai/v1 route this used to call.
        body: JSON.stringify({
          messages: [
            { role: 'system', content: systemPrompt },
            { role: 'user', content: logTail },
          ],
          max_tokens: AI_MAX_TOKENS,
          temperature: 0.1,
        }),
        signal: controller.signal,
      });
      clearTimeout(timeout);
      if (!response.ok) {
        console.log(
          `[AI] Cloudflare classifier returned HTTP ${response.status}: ${await errorBody(response)}`
        );
        return null;
      }
      const data = await response.json();
      // Reasoning models put their thinking in message.reasoning_content; the
      // verdict must come from content only.
      //
      // TWO SHAPES ON PURPOSE. The /ai/run route wraps everything in `result`,
      // while the OpenAI-compatible /ai/v1 route does not. Accepting both means
      // moving between routes (see AI_MODEL) cannot silently produce "no answer"
      // from a perfectly good reply, which would fall through to the allowlist
      // and look exactly like the outage this tier just came back from.
      const envelope = data.result ?? data;
      const aiResponse = envelope.choices?.[0]?.message?.content ?? envelope.response;
      if (!aiResponse) {
        console.log(`[AI] Cloudflare unexpected response: ${JSON.stringify(data).slice(0, 200)}`);
        return null;
      }
      return parseClassifierVerdict(
        typeof aiResponse === 'string' ? aiResponse : JSON.stringify(aiResponse)
      );
    } catch (e) {
      clearTimeout(timeout);
      console.log(`[AI] Cloudflare ${e.name === 'AbortError' ? 'request timed out' : e.message}`);
      return null;
    }
  }

  // TIER 2: Anthropic direct.
  //
  // WHY A SECOND PROVIDER AT ALL. Tier 1 has been returning HTTP 402 (billing)
  // continuously, which is not a transient outage: it is an unavailable tier.
  // With only one model, every failure fell through to the allowlist, so a
  // judgment nobody made decided whether to spend a ~500-machine-minute retry.
  // The allowlist is a safety net, not a classifier, and it cannot tell a real
  // break in an E2E job from a flake in one.
  //
  // AUTH. Prefers ANTHROPIC_API_KEY (the documented x-api-key path) and falls
  // back to CLAUDE_CODE_OAUTH_TOKEN, which is the credential this org actually
  // has. The OAuth path needs the oauth beta header; without it the API rejects
  // a Bearer token. If neither is set this tier is simply absent and the chain
  // moves on, which is why a missing secret degrades to today's behaviour
  // instead of breaking the watchdog.
  async function callClaudeClassifier(logTail, systemPrompt) {
    const apiKey = process.env.ANTHROPIC_API_KEY || '';
    const oauth = process.env.CLAUDE_CODE_OAUTH_TOKEN || '';
    if (!apiKey && !oauth) return null;

    const headers = {
      'Content-Type': 'application/json',
      'anthropic-version': '2023-06-01',
    };
    if (apiKey) {
      headers['x-api-key'] = apiKey;
    } else {
      headers['Authorization'] = `Bearer ${oauth}`;
      headers['anthropic-beta'] = 'oauth-2025-04-20';
    }

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), AI_TIMEOUT);
    try {
      const response = await fetch('https://api.anthropic.com/v1/messages', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          model: CLAUDE_MODEL,
          max_tokens: AI_MAX_TOKENS,
          temperature: 0.1,
          system: systemPrompt,
          messages: [{ role: 'user', content: logTail }],
        }),
        signal: controller.signal,
      });
      clearTimeout(timeout);
      if (!response.ok) {
        console.log(
          `[AI] Claude classifier returned HTTP ${response.status}: ${await errorBody(response)}`
        );
        return null;
      }
      const data = await response.json();
      // Messages API shape: content is a list of blocks; take the text ones.
      const text = Array.isArray(data.content)
        ? data.content
            .filter((b) => b && b.type === 'text')
            .map((b) => b.text)
            .join('')
        : '';
      if (!text) {
        console.log(`[AI] Claude unexpected response: ${JSON.stringify(data).slice(0, 200)}`);
        return null;
      }
      return parseClassifierVerdict(text);
    } catch (e) {
      clearTimeout(timeout);
      console.log(`[AI] Claude ${e.name === 'AbortError' ? 'request timed out' : e.message}`);
      return null;
    }
  }

  // THE CHAIN. Ordered deliberately, cheapest-capable first:
  //
  //   1. Cloudflare / DeepSeek V4 Pro  (bulk-priced, currently HTTP 402)
  //   2. Anthropic / Claude            (the credential this org actually has)
  //   3. the known-flaky allowlist     (NOT a classifier; a safety net)
  //
  // A provider that returns null has NOT answered, whether it was unconfigured,
  // billing-blocked, timed out, or replied off-contract. Those are all the same
  // thing to the caller and must be, because the only safe reading of "no
  // answer" is to ask the next tier rather than to invent a verdict. Only the
  // exhaustion of tiers 1 and 2 reaches the allowlist.
  // The tier-1 label is DERIVED from AI_MODEL, never written out by hand.
  // It was hardcoded to 'cloudflare/deepseek-v4-pro' and stayed that way after
  // the model moved to @cf/meta/llama-3.3-70b-instruct-fp8-fast, so every log
  // line and every stored `provider` field named a model that was no longer
  // being called. Observed on watchdog run 30541558539:
  // "[AI] verdict from cloudflare/deepseek-v4-pro" while the request went to
  // /ai/run/@cf/meta/llama-3.3-70b-instruct-fp8-fast.
  //
  // Cosmetic only until it is not. This label is the ONLY record of which model
  // produced a verdict that decides whether to spend ~500 machine-minutes on a
  // retry, and the 402 that broke this tier was diagnosed BY MODEL IDENTITY. A
  // label that lies about that sends the next investigation to the wrong
  // provider, which is worse than having no label at all.
  const CLASSIFIER_PROVIDERS = [
    { name: `cloudflare/${AI_MODEL}`, call: callCloudflareClassifier },
    { name: 'anthropic/claude', call: callClaudeClassifier },
  ];

  async function callClassifierModel(logTail) {
    const systemPrompt = readClassifierPrompt();
    if (!systemPrompt) return null;

    for (const provider of CLASSIFIER_PROVIDERS) {
      const verdict = await provider.call(logTail, systemPrompt);
      if (verdict) {
        console.log(
          `[AI] verdict from ${provider.name}: ${verdict.classification} (${verdict.confidence})`
        );
        return { ...verdict, provider: provider.name };
      }
      console.log(`[AI] ${provider.name} did not answer; trying the next tier`);
    }
    return null;
  }

  // `jobs` is the full job list from this poll: the cross-job fact the guard
  // needs, already fetched, so it is threaded in rather than re-queried.
  // Only install-validation jobs can trigger the guard, so no other job pays
  // for a log fetch here.
  async function evaluateGuard(job, jobs) {
    if (!installValidationPatterns.length || !matchesPatterns(job.name, installValidationPatterns))
      return null;
    const logTail = await getLogTail(job);
    if (!logTail) return null;
    return evaluateBinaryExecGuard({
      job,
      logTail,
      jobs,
      installPatterns: installValidationPatterns,
    });
  }

  async function classifyFailure(job, guard) {
    // `classifierAvailable: false` is the load-bearing field, not `confidence: 0`.
    // Downstream needs to tell "the model looked and was unsure" apart from
    // "the model never answered", and those are indistinguishable by confidence
    // alone -- a real verdict may legitimately carry a low confidence. Sniffing
    // `confidence === 0` would conflate them, which is how retry-everything got
    // mistaken for a judgment in the first place.
    const fallback = {
      classification: 'transient',
      confidence: 0,
      reason: 'classifier unavailable',
      classifierAvailable: false,
    };
    const logTail = await getLogTail(job);
    if (!logTail) return { ...fallback, reason: 'no job log available to classify' };

    const ai = await callClassifierModel(logTail);
    if (!ai)
      console.log(`[AI] Classification failed for "${job.name}" -- the classifier did not answer`);
    const result = ai ? { ...ai, classifierAvailable: true } : fallback;

    if (guard) {
      console.log(`[guard] ${guard.reason}`);
      if (guard.override) {
        console.log(
          `[guard] Overriding "${result.classification}" (${result.confidence}) with code-change -- no retry`
        );
        // The guard is a deterministic cross-job check, not a model call, so it
        // counts as an available verdict even when the classifier was down.
        // guardForced marks this verdict as SYNTHESISED by a deterministic
        // cross-job check rather than read off a log. The retry allowlist may
        // override a model's code-change verdict (operator decision
        // 2026-07-30) but must never override this one, so the distinction has
        // to travel with the verdict rather than be inferred from confidence:
        // a real classifier can also answer 1.0.
        return {
          classification: 'code-change',
          confidence: 1,
          reason: guard.reason,
          classifierAvailable: true,
          guardForced: true,
        };
      }
    }
    return result;
  }

  // Helper: log failure details with formatted header
  function logFailure(job, reason, runAttempt) {
    const msg = `${reason}: "${job.name}"`;
    console.log('');
    console.log('='.repeat(70));
    console.log(msg);
    if (job.id) {
      console.log(
        `   Job URL: https://github.com/${context.repo.owner}/${context.repo.repo}/actions/runs/${targetRunId}/job/${job.id}`
      );
    }
    console.log(`   Run attempt: ${runAttempt}/${MAX_ATTEMPTS}`);
    console.log('='.repeat(70));
    return msg;
  }

  // Helper: force-cancel the workflow run.
  // Waits for critical jobs (WATCHDOG_WAIT_PATTERNS) to finish before cancelling,
  // so cleanup traps (e.g., deleting temp D1 databases) can complete.
  //
  // RETURNS true when the run was actually cancelled, false when the cancel was
  // suppressed by the event exemption. Callers use it to decide whether to end
  // the generation: a real cancel is terminal, a suppressed one is not, and the
  // watchdog must keep monitoring an exempt run so later failures still get
  // their logs captured. `await forceCancel(...)` without checking the result
  // would end the chain at the first failure on the nightly, which is precisely
  // the under-diagnosis this wave exists to fix.
  async function forceCancel(failureMsg) {
    // Re-fetch the job list so the cancellation names EVERY job that has failed
    // by now, not only the one that drove the decision. Between the poll that
    // detected the first failure and this call (AI classification + the
    // critical-job wait below both take time) sibling jobs can also flip to
    // failure; without this an operator or agent reading the cancelled run
    // re-scans every job to find failures the watchdog already saw. Best-effort:
    // if the refetch fails we fall back to the driving job's message.
    try {
      const jobsNow = await github.paginate(
        github.rest.actions.listJobsForWorkflowRun,
        { owner: context.repo.owner, repo: context.repo.repo, run_id: targetRunId, per_page: 100 },
        (response) => response.data
      );
      const failedNow = jobsNow.filter(
        (j) => j.conclusion === 'failure' && !excludePatterns.some((p) => j.name.includes(p))
      );
      if (failedNow.length > 0) {
        const { lines, summary } = formatFailureRoster(failedNow, {
          owner: context.repo.owner,
          repo: context.repo.repo,
          runId: targetRunId,
        });
        console.log('');
        for (const line of lines) console.log(line);
        failureMsg = summary;
      }
    } catch (e) {
      console.log(
        `Warning: could not build the full failure roster (${e.message}); reporting the driving job only.`
      );
    }

    // The cancel-exemption check sits AFTER the roster build (an exempt run
    // still gets the full "here is everything that failed" banner) and BEFORE
    // the critical-job drain (there is nothing to drain for if nothing is being
    // cancelled). This is the single chokepoint: all five call sites route
    // through forceCancel, including the no-drain Review Gate path, so the
    // exemption cannot be bypassed by adding a sixth.
    const exemption = evaluateCancelExemption({ runEvent: targetRunEvent });
    if (exemption.exempt) {
      console.log('');
      console.log('#'.repeat(70));
      console.log(`NOT cancelling run ${targetRunId}: ${exemption.reason}`);
      console.log('Leaving the run to finish so GitHub reports its true conclusion.');
      console.log('#'.repeat(70));
      core.setFailed(
        'PIPELINE FAILED (run left uncancelled so it concludes as "failure"): ' + failureMsg
      );
      return false;
    }

    const waitPatternsRaw = process.env.WATCHDOG_WAIT_PATTERNS || '';
    const waitPatterns = waitPatternsRaw
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);

    if (waitPatterns.length > 0) {
      const maxWait = 300000; // 5 minutes
      const waitPoll = 15000; // 15 seconds
      const waitStart = Date.now();

      while (Date.now() - waitStart < maxWait) {
        try {
          const allJobs = await github.paginate(
            github.rest.actions.listJobsForWorkflowRun,
            {
              owner: context.repo.owner,
              repo: context.repo.repo,
              run_id: targetRunId,
              per_page: 100,
            },
            (response) => response.data
          );
          const criticalRunning = allJobs.filter(
            (j) => j.status === 'in_progress' && waitPatterns.some((p) => j.name.includes(p))
          );
          if (criticalRunning.length === 0) break;
          const elapsed = Math.round((Date.now() - waitStart) / 1000);
          console.log(
            `Waiting for critical jobs (${elapsed}s): ${criticalRunning.map((j) => j.name).join(', ')}`
          );
        } catch (e) {
          console.log(`Warning: failed to check critical jobs: ${e.message}`);
          break; // Don't block cancellation on API errors
        }
        await new Promise((r) => setTimeout(r, waitPoll));
      }
    }

    console.log('Force-cancelling workflow run...');
    try {
      await github.request('POST /repos/{owner}/{repo}/actions/runs/{run_id}/force-cancel', {
        owner: context.repo.owner,
        repo: context.repo.repo,
        run_id: targetRunId,
      });
    } catch (e) {
      // Fallback to regular cancel if force-cancel not available
      console.log(`Force-cancel failed (${e.message}), using regular cancel...`);
      await github.rest.actions.cancelWorkflowRun({
        owner: context.repo.owner,
        repo: context.repo.repo,
        run_id: targetRunId,
      });
    }
    core.setFailed('PIPELINE CANCELLED: ' + failureMsg);
    return true;
  }

  // Check for the skip-auto-retry label.
  // Labels are fetched LIVE from the API: the event payload's label list is
  // frozen at the event that created the run, so a label added afterwards
  // (e.g. no-auto-retry added right before rerunning failed jobs) would be
  // invisible in context.payload and silently ignored.
  let skipAutoRetry = false;
  if (prNumber) {
    let labels = context.payload.pull_request?.labels.map((l) => l.name) || [];
    try {
      const liveLabels = await github.rest.issues.listLabelsOnIssue({
        owner: context.repo.owner,
        repo: context.repo.repo,
        issue_number: prNumber,
      });
      labels = liveLabels.data.map((l) => l.name);
    } catch (e) {
      console.log(
        `Could not fetch live PR labels (${e.message}) - falling back to event payload labels`
      );
    }
    skipAutoRetry = labels.includes('no-auto-retry');
    if (skipAutoRetry) {
      console.log('Label "no-auto-retry" detected - will not auto-retry on failures');
    }
  }

  // A refused rerun leaves the pending-rerun chain with nothing to do: in
  // pending mode nothing is classified or cancelled, and the one remaining
  // action just got vetoed by the deterministic backstop. End immediately
  // instead of idle-polling generations until the run completes.
  if (pendingRerun && skipRerun) {
    console.log('Pending rerun refused by the attempt-cap backstop - ending the watchdog chain');
    return;
  }

  console.log('Watchdog started - monitoring jobs for failures...');
  console.log(
    `Target run: ${targetRunId}${deadlineMs ? ` | generation deadline: ${deadlineMs / 60000}m` : ''}`
  );
  console.log(`Exclude patterns: ${excludePatterns.join(', ')}`);
  console.log(`No-retry patterns: ${noRetryPatterns.join(', ')}`);
  console.log(`Install-validation patterns: ${installValidationPatterns.join(', ')}`);
  console.log(`Max runtime: ${maxRuntime / 3600000} hours`);

  // Loop-invariant: parse env var once. Cancelled jobs with elapsed runtime
  // at or above this threshold are treated as "stuck" (likely hit their
  // declared timeout-minutes) and bypass the AI / retry path -- a hung job
  // will hang again on retry.
  const STUCK_THRESHOLD_MIN = parseInt(process.env.STUCK_THRESHOLD_MIN || '60', 10);
  const jobElapsedMin = (j) => {
    if (!j.started_at || !j.completed_at) return 0;
    return Math.round((new Date(j.completed_at) - new Date(j.started_at)) / 60000);
  };
  console.log(
    `Stuck-threshold: ${STUCK_THRESHOLD_MIN}m (cancellations after this are not retried)`
  );

  while (Date.now() - startTime < maxRuntime) {
    const elapsed = Date.now() - startTime;
    const elapsedMin = Math.round(elapsed / 60000);

    // Chained mode: hand off before the slim runner's hard 15-minute cap can
    // kill this job mid-decision. Reaching here means no terminal path fired
    // (those all return without the output), so the run is still live.
    if (deadlineMs && elapsed >= deadlineMs) {
      console.log(
        `[${elapsedMin}m] Generation deadline reached with the run still live - handing off to the next watchdog generation${pendingRerun ? ' (rerun still pending)' : ''}`
      );
      core.setOutput('continue', 'true');
      core.setOutput('pending_rerun', pendingRerun ? 'true' : 'false');
      return;
    }

    // Fetch run status and jobs, retrying on transient API errors (e.g. 401 Bad credentials)
    let run, allJobs;
    try {
      ({ data: run } = await github.rest.actions.getWorkflowRun({
        owner: context.repo.owner,
        repo: context.repo.repo,
        run_id: targetRunId,
      }));
      // Refreshed every poll rather than captured once: a rerun keeps the same
      // run id and the same event, so this is stable, but re-reading it means
      // forceCancel can never act on a stale value from a previous generation.
      targetRunEvent = run.event;

      if (!announcedExemption && evaluateCancelExemption({ runEvent: targetRunEvent }).exempt) {
        announcedExemption = true;
        console.log(
          `Run event "${targetRunEvent}" is cancel-exempt - failures are recorded and the run is left to conclude on its own`
        );
      }

      allJobs = await github.paginate(
        github.rest.actions.listJobsForWorkflowRun,
        {
          owner: context.repo.owner,
          repo: context.repo.repo,
          run_id: targetRunId,
          per_page: 100,
        },
        (response) => response.data
      );
    } catch (e) {
      console.log(`[${elapsedMin}m] API error (will retry next poll): ${e.message}`);
      await new Promise((resolve) => setTimeout(resolve, pollInterval));
      continue;
    }

    // Filter out excluded jobs
    const monitoredJobs = allJobs.filter(
      (j) => !excludePatterns.some((pattern) => j.name.includes(pattern))
    );

    const completed = monitoredJobs.filter((j) => j.status === 'completed');
    const inProgress = monitoredJobs.filter((j) => j.status === 'in_progress');
    const queued = monitoredJobs.filter((j) => j.status === 'queued');
    const failed = monitoredJobs.filter((j) => j.conclusion === 'failure');
    const cancelled = monitoredJobs.filter((j) => j.conclusion === 'cancelled');

    console.log(
      `[${elapsedMin}m] Run: ${run.status} | Jobs: ${completed.length} done, ${inProgress.length} running, ${queued.length} queued, ${failed.length} failed, ${cancelled.length} cancelled`
    );

    // A held quality force-cancel fires as soon as its siblings settle. This sits
    // BEFORE every other exit path in the loop: the all-jobs-complete branch
    // below would otherwise return first and the run would end with no
    // cancellation annotation naming the failures at all.
    if (pendingQualityCancel) {
      const stillRunning = pendingNoRetryJobs({
        jobs: monitoredJobs,
        noRetryPatterns,
        excludePatterns,
      });
      const heldSec = heldSince ? Math.round((Date.now() - heldSince) / 1000) : 0;
      const expired = heldSec >= HELD_CANCEL_MAX_SECONDS;
      if (stillRunning.length === 0 || expired) {
        if (expired) {
          console.log(
            `Held force-cancel EXPIRED after ${heldSec}s with ${stillRunning.length} sibling(s) still running. ` +
              'The drain collects a full roster; it does not keep a known-red run alive behind one slow lane.'
          );
        } else {
          console.log(
            'All no-retry jobs are terminal - firing the held force-cancel with the full roster'
          );
        }
        if (await forceCancel(heldQualityFailureMsg)) return;
        pendingQualityCancel = false; // exempt run: recorded, not cancelled; keep monitoring
      } else {
        console.log(
          `[${elapsedMin}m] Force-cancel held ${heldSec}s/${HELD_CANCEL_MAX_SECONDS}s: ` +
            `waiting on ${stillRunning.length} no-retry job(s)`
        );
      }
    }

    // Check if workflow was externally cancelled (mass cancellation)
    if (cancelled.length > 0 && cancelled.length >= completed.length / 2) {
      console.log(
        `Workflow externally cancelled (${cancelled.length}/${completed.length} jobs cancelled) - exiting`
      );
      return;
    }

    // Distinguish stuck-job timeouts from normal cancellations. A cancelled
    // job that ran longer than STUCK_THRESHOLD_MIN almost certainly hit its
    // declared timeout-minutes (or GitHub's 6h default), not a manual /
    // supersession / watchdog cancel -- those happen within minutes of the
    // job starting. The classifier path treats all cancellations as
    // potentially transient and auto-retries; that's how we ended up with
    // a 4-hour debian-13 hang retried automatically before any human noticed.
    // Stuck jobs go straight to force-cancel with no retry.
    // (STUCK_THRESHOLD_MIN + jobElapsedMin hoisted above the loop as
    // loop-invariants.)
    const stuckCancellations = cancelled.filter((j) => jobElapsedMin(j) >= STUCK_THRESHOLD_MIN);
    const normalCancellations = cancelled.filter((j) => jobElapsedMin(j) < STUCK_THRESHOLD_MIN);

    // Supersession check, and it must come BEFORE the classification below.
    // Once a cancelled job reaches classifyFailure the damage is already done:
    // a billed Workers AI request is spent and core.setFailed marks the step
    // red, and nothing downstream un-marks it. See evaluateSupersession.
    //
    // The cheap local half is evaluated first so a healthy run never pays for
    // the API call, and the answer is re-derived per poll rather than cached
    // because a real failure can land at any time and must flip the verdict
    // back immediately.
    const cheapSupersession = evaluateSupersession({
      failedCount: failed.length,
      normalCancelledCount: normalCancellations.length,
      newerRunExists: false,
    });
    if (cheapSupersession.noFailures && cheapSupersession.hasCancellations) {
      const newerRunExists = await hasNewerRun({ github, context, run });
      const verdict = evaluateSupersession({
        failedCount: failed.length,
        normalCancelledCount: normalCancellations.length,
        newerRunExists,
      });
      if (verdict.superseded) {
        console.log(`[supersession] ${verdict.reason} - exiting without classifying or failing`);
        core.notice(
          `Run ${targetRunId} was superseded by a newer run on "${run.head_branch}". ` +
            `${normalCancellations.length} job(s) cancelled, 0 failed. This is not a pipeline failure.`
        );
        return;
      }
    }

    // Unified failure + cancellation handling.
    // AI classifies the failure and decides: transient (retry + keep monitoring) or
    // code-change (force-cancel everything). Stuck cancellations bypass AI
    // (a hung job will hang again on retry).
    const failedOrCancelled = [...failed, ...normalCancellations, ...stuckCancellations];

    // Filter to only NEW failures (not already handled in a previous poll).
    // In pending-rerun mode classification stops entirely: the retry decision
    // is already made, every failed job gets rerun at completion anyway, and
    // the old exit-after-dispatch design never classified late failures either.
    const newFailures = pendingRerun
      ? []
      : failedOrCancelled.filter((j) => !handledJobs.has(j.name));

    // The binary-exec guard can defer an install-validation failure whose
    // sibling platforms are still running: until the matrix settles, the same
    // log cannot be told apart from a CDN flake and a corrupt build, and both
    // a retry and a cancellation would be premature. Deferring must not starve
    // the other failures in this poll, so pick the first candidate the guard
    // does not defer instead of always taking newFailures[0]. Deferred jobs are
    // left out of handledJobs so a later poll reconsiders them; the 3h watchdog
    // timeout is the backstop.
    let job = null;
    let jobGuard = null;
    for (const candidate of newFailures) {
      const guard = failed.includes(candidate) ? await evaluateGuard(candidate, allJobs) : null;
      if (guard?.defer) {
        if (!deferredJobs.has(candidate.name)) {
          deferredJobs.add(candidate.name);
          console.log(`[guard] ${guard.reason}`);
          console.log(
            `[guard] install matrix unfinished; deferring "${candidate.name}" until it completes`
          );
        }
        continue;
      }
      job = candidate;
      jobGuard = guard;
      break;
    }

    if (job) {
      const jobMin = jobElapsedMin(job);
      const isStuck = stuckCancellations.includes(job);
      const reason = failed.includes(job)
        ? 'Job failed'
        : isStuck
          ? `Job stuck (ran ${jobMin}m before cancellation -- likely timeout-minutes expiry)`
          : 'Job cancelled (likely manual / supersession)';
      // let, not const: the transient branch below widens the message to the
      // full failure roster before recording it.
      let failureMsg = logFailure(job, reason, run.run_attempt);
      handledJobs.add(job.name);

      // Capture this job's log NOW, before any branch below decides what to do
      // about it. Capture is evidence, not classification, and tying the two
      // together loses the evidence exactly where it matters most.
      //
      // It used to happen as a side effect of classifyFailure, which is only
      // reached on the last branch. Every earlier branch -- a no-retry Quality
      // failure, a cancel-exempt scheduled run, max-attempts -- returned or
      // continued without ever fetching a log. So the NIGHTLY, which now takes
      // the exempt path by construction, captured nothing at all. Caught by
      // test-watchdog-log-capture.sh's scheduled-run case, which expected one
      // captured file and found zero.
      //
      // Cached in logTails, so the later classification does not re-fetch.
      await getLogTail(job);

      // 0. Stuck cancellations bypass AI + retry entirely -- the job hung
      // once, retrying would just hang again. Force-cancel and surface a
      // loud annotation so the operator investigates the root cause.
      if (isStuck) {
        console.log(
          `"${job.name}" exceeded ${STUCK_THRESHOLD_MIN}m cancellation threshold -- treating as stuck, no retry`
        );
        core.error(
          `Job '${job.name}' ran ${jobMin}m before cancellation, exceeding the ${STUCK_THRESHOLD_MIN}m stuck-threshold. The job's declared timeout-minutes (or GitHub's 6h default) likely expired. Investigate the underlying step before re-running.`
        );
        if (await forceCancel(failureMsg)) return;

        // Cancel-exempt run (the nightly): the failure is recorded but the run is
        // left to conclude on its own, so forceCancel returned false and did NOT
        // end this generation. The job is nonetheless TERMINAL AND STUCK, so it
        // must not fall through into the branches below.
        //
        // Falling through was a real regression, introduced when forceCancel
        // began returning a boolean and caught in review of PR #541. Branch 4
        // would be reached with `isFailure: failed.includes(job)` === false --
        // correct, it IS a cancellation -- and evaluateRetryEligibility's
        // "non-stuck cancellation is a runner/infra flake" path would resolve it
        // to retry:true. The nightly would then re-run a job that had already
        // hung for STUCK_THRESHOLD_MIN, which is exactly what branch 0 exists to
        // prevent: "the job hung once, retrying would just hang again".
        //
        // sleep+continue rather than a bare `continue`, matching the drain path
        // above: skipping the poll interval would busy-loop.
        await new Promise((resolve) => setTimeout(resolve, pollInterval));
        continue;
      }

      // 1. No-retry jobs (Quality, Review Gate) -- fast fail, no AI.
      // Only for real FAILURES: a Quality failure (lint/type error) is deterministic,
      // so retrying is pointless and we force-cancel fast. A non-stuck CANCELLATION of
      // a Quality job, by contrast, is a runner/infra flake (not a code error) -- nuking
      // a 0-failure run for it is wrong. Let cancellations fall through to the
      // retry handling below so a flaky-cancelled job can be re-run instead.
      //
      // The full roster still reaches the operator in ONE round: the drain below
      // holds this cancel until every sibling no-retry lane is terminal, and
      // forceCancel re-fetches the job list so the annotation names every job
      // that failed by then.
      //
      // NO_DRAIN_PATTERNS is the exception. CLAUDE.md specifies that Review Gate
      // fails immediately and force-cancels, full stop -- there is no sibling
      // verdict worth waiting for when the red means "reply to the review".
      const noRetryVerdict = evaluateNoRetryCancel({
        jobName: job.name,
        isFailure: failed.includes(job),
        noRetryPatterns,
      });
      if (noRetryVerdict.cancel) {
        console.log(
          `"${job.name}" matches no-retry pattern${noRetryVerdict.noDrain ? ' (no drain)' : ''}`
        );

        // Drain before cancelling (see pendingNoRetryJobs). No-drain jobs keep
        // the instant kill; everything else waits for its siblings so one round
        // reports every failing lane instead of the first one.
        const stillRunning = noRetryVerdict.noDrain
          ? []
          : pendingNoRetryJobs({ jobs: monitoredJobs, noRetryPatterns, excludePatterns });
        if (stillRunning.length > 0) {
          pendingQualityCancel = true;
          heldSince = heldSince || Date.now();
          // Keep the FIRST held message: forceCancel re-fetches the job list and
          // builds the full roster itself, so this is only the fallback text for
          // the case where that refetch fails.
          heldQualityFailureMsg = heldQualityFailureMsg || failureMsg;
          console.log(
            `Holding the force-cancel until ${stillRunning.length} sibling no-retry job(s) finish: ` +
              stillRunning.map((j) => `"${j.name}"`).join(', ')
          );
          await new Promise((resolve) => setTimeout(resolve, pollInterval));
          continue;
        }

        if (await forceCancel(failureMsg)) return;

        // Cancel-exempt run: recorded, not cancelled, and this branch has
        // already reached its verdict -- a no-retry job never retries, by
        // definition. Falling through would hand it to branch 4, which
        // independently re-derives "no retry" for a real failure and so reaches
        // the same answer, but only after paying for a classifyFailure call (a
        // billed Workers AI request) and emitting duplicate log lines. Same
        // outcome, wasted work, noisier log. Flagged as a non-blocking nit in
        // review of PR #541; skipping is both cheaper and clearer.
        await new Promise((resolve) => setTimeout(resolve, pollInterval));
        continue;
      }

      // 2. Label: no-auto-retry -- force-cancel immediately
      if (skipAutoRetry) {
        console.log('Force-cancel due to "no-auto-retry" label');
        if (await forceCancel(failureMsg)) return;
      }
      // 3. Max attempts reached -- force-cancel
      else if (run.run_attempt >= MAX_ATTEMPTS) {
        console.log(`Attempt ${run.run_attempt}/${MAX_ATTEMPTS} -- no more retries`);
        if (await forceCancel(failureMsg)) return;
      }
      // 4. First failure: AI classifies.
      // Transient -> hold a PENDING RERUN and keep monitoring. The chain waits
      // for the run to complete, reruns every failed job from this attempt
      // itself, and keeps watching attempt 2. Further failures are not
      // classified while a rerun is pending (they get rerun anyway).
      // Code-change -> force-cancel now, retry would be pointless.
      else {
        const ai = await classifyFailure(job, jobGuard);
        const eligibility = evaluateRetryEligibility({
          jobName: job.name,
          // Failures and non-stuck cancellations both reach this branch; only
          // the former is a verdict about the code. See evaluateRetryEligibility.
          isFailure: failed.includes(job),
          classification: ai.classification,
          confidence: ai.confidence,
          classifierAvailable: ai.classifierAvailable !== false,
          threshold: AI_CONFIDENCE_THRESHOLD,
          retryAllowlistPatterns,
          // The binary-exec guard SYNTHESISES a code-change verdict to block a
          // retry deliberately; the allowlist override must never undo that.
          guardForced: ai.guardForced === true,
        });

        // Make a classifier outage visible at run level rather than letting it
        // hide behind a confident-looking "transient" line. Without this the
        // only symptom of a dead classifier is that everything gets retried,
        // which looks exactly like a healthy classifier meeting a flaky day.
        if (ai.classifierAvailable === false) {
          core.warning(
            `Failure classifier unavailable for "${job.name}" (${ai.reason}). ` +
              `EVERY provider in the chain declined to answer: ` +
              `${CLASSIFIER_PROVIDERS.map((p) => p.name).join(' then ')}. ` +
              `Retry policy fell back to the known-flaky allowlist (a safety net, not a classifier): ` +
              `${eligibility.retry ? 'retrying' : 'failing fast'}. ` +
              `See issue #537.`
          );
        }

        if (!eligibility.retry) {
          console.log(
            `[AI] "${job.name}" -> ${ai.classification} (${ai.confidence}): ${ai.reason}`
          );
          console.log(`No retry: ${eligibility.reason}`);
          if (await forceCancel(failureMsg)) return;
        } else {
          console.log(
            `[AI] "${job.name}" -> ${ai.classification} (${ai.confidence}): ${ai.reason}`
          );
          // The rerun covers every failed job from this attempt, so name
          // them all in the annotation too (not just the classified one).
          if (failed.length > 1) {
            const { summary } = formatFailureRoster(failed, {
              owner: context.repo.owner,
              repo: context.repo.repo,
              runId: targetRunId,
            });
            failureMsg = summary;
            console.log(
              `Will retry all ${failed.length} failed jobs: ${failed.map((j) => `"${j.name}"`).join(', ')}`
            );
          }
          console.log(`Retrying: ${eligibility.reason}`);
          console.log(
            'Holding a pending rerun; the chain reruns the failed jobs once the run completes.'
          );
          pendingRerun = true;
          core.setFailed(failureMsg);
          // DON'T return -- keep monitoring until completion, then rerun below.
        }
      }
    }

    // Pending rerun: the run has finished, so retry its failed jobs and keep
    // monitoring the new attempt (the workflow resets the generation counter).
    // Checked BEFORE the completed-exit below, which would end the chain.
    if (pendingRerun && run.status === 'completed') {
      if (run.run_attempt >= MAX_ATTEMPTS) {
        console.log(
          `Run ${targetRunId} completed but already at attempt ${run.run_attempt}/${MAX_ATTEMPTS} - ending the chain without retry`
        );
        return;
      }
      if (await executeRerun()) {
        core.setOutput('continue', 'true');
        core.setOutput('pending_rerun', 'false');
        core.setOutput('rerun_executed', 'true');
      } else {
        core.setFailed(`Run ${targetRunId} completed but the pending rerun could not be triggered`);
      }
      return;
    }

    // Exit when workflow run is externally completed
    if (run.status === 'completed' && elapsed >= minRuntime) {
      console.log(
        `Workflow run completed (conclusion: ${run.conclusion}) - exiting watchdog (after ${elapsedMin}m)`
      );
      return;
    }

    // Exit when all monitored jobs are complete, with grace period to handle
    // partial reruns. Not while a rerun is pending: the chain must survive to
    // the run's completion to trigger that rerun. (The original deadlock this
    // exit prevented -- the in-run watchdog being the only job keeping
    // run.status in_progress -- no longer exists in chained mode, but the
    // grace period still smooths job-list lag around attempt transitions.)
    if (
      !pendingRerun &&
      monitoredJobs.length > 0 &&
      completed.length === monitoredJobs.length &&
      elapsed >= minRuntime
    ) {
      allCompleteStreak++;
      if (allCompleteStreak >= GRACE_POLLS) {
        console.log(
          `All ${monitoredJobs.length} monitored jobs completed for ${allCompleteStreak} consecutive polls - exiting watchdog (after ${elapsedMin}m)`
        );
        return;
      }
      console.log(
        `[${elapsedMin}m] All jobs complete (${allCompleteStreak}/${GRACE_POLLS} polls) - waiting for possible rerun...`
      );
    } else {
      allCompleteStreak = 0;
    }

    await new Promise((resolve) => setTimeout(resolve, pollInterval));
  }

  // Timeout reached
  console.log('Watchdog reached 3h timeout - exiting');
  core.warning('Watchdog timeout reached');
};

module.exports = monitor;
module.exports.evaluateBinaryExecGuard = evaluateBinaryExecGuard;
module.exports.BINARY_EXEC_FAILURE_RE = BINARY_EXEC_FAILURE_RE;
module.exports.formatFailureRoster = formatFailureRoster;
module.exports.evaluateNoRetryCancel = evaluateNoRetryCancel;
module.exports.pendingNoRetryJobs = pendingNoRetryJobs;
module.exports.NO_DRAIN_PATTERNS = NO_DRAIN_PATTERNS;
module.exports.evaluateCancelExemption = evaluateCancelExemption;
module.exports.CANCEL_EXEMPT_EVENTS = CANCEL_EXEMPT_EVENTS;
module.exports.evaluateRetryEligibility = evaluateRetryEligibility;
module.exports.evaluateSupersession = evaluateSupersession;
