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
//   - AI unavailable: retries ONLY jobs on WATCHDOG_RETRY_ALLOWLIST_PATTERNS
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
//   no-cancel-failure  - Skip cancellation on job failure (workflow continues)
//   no-auto-retry      - Skip AI + retry entirely (force-cancel immediately)
//
// Usage (from actions/github-script):
//   script: return await require('./.ci/scripts/ci/watchdog-monitor.cjs')({github, context, core})

// A downloaded release binary that will not execute is normally a truncated or
// stale CDN download (transient). It is a corrupt build only when no platform's
// install validation survives it. The classifier prompt says as much, but a
// prompt is advice; this signature + cross-job check is the enforcement.
const BINARY_EXEC_FAILURE_RE = /is not a valid application for this OS platform|cannot execute binary file|Exec format error/i;

const matchesPatterns = (name, patterns) => patterns.some(p => name.includes(p));

// Jobs whose force-cancel `no-cancel-failure` may NOT suppress. Per CLAUDE.md a
// Review Gate failure means review feedback is outstanding, not that code is
// broken, so it is never something to label past. Nothing else is immune.
const LABEL_IMMUNE_PATTERNS = ['Review Gate'];

// Run events the watchdog must never cancel.
const CANCEL_EXEMPT_EVENTS = ['schedule'];

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
 * WHY NOT THE EXISTING LABEL. `no-cancel-failure` already means "record the
 * failure, do not cancel". It cannot help here: labels live on a PR, and a
 * `schedule` run has no PR, so `prNumber` is null and the label block never
 * runs. The nightly is structurally incapable of wearing the one escape hatch
 * that would have saved it.
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
 * Should a failed job force-cancel the run immediately, before any label or
 * retry handling downstream?
 *
 * Extracted and exported so the ordering is testable against the REAL
 * WATCHDOG_NO_RETRY_PATTERNS rather than a copy. The bug this replaces was pure
 * ordering: the no-retry branch returned before the `no-cancel-failure` check,
 * and the pattern list is 'Quality,Review Gate', so the label was unreachable
 * for every Quality job -- the entire class it exists for -- while still being
 * detected and logged as honoured. Run 29825013399.
 */
function evaluateNoRetryCancel({ jobName, isFailure, skipCancellationOnFailure, noRetryPatterns }) {
  const labelImmune = matchesPatterns(jobName, LABEL_IMMUNE_PATTERNS);
  const matchesNoRetry = matchesPatterns(jobName, noRetryPatterns);
  return {
    cancel: Boolean(isFailure) && matchesNoRetry && (labelImmune || !skipCancellationOnFailure),
    labelImmune,
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
}) {
  if (classification === 'code-change' && confidence >= threshold) {
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
 * Label-immune jobs (Review Gate) are excluded: CLAUDE.md specifies those fail
 * immediately, full stop, and an outstanding review is not something to wait on.
 *
 * Pure so the ordering is testable against the REAL pattern list.
 */
function pendingNoRetryJobs({ jobs, noRetryPatterns, excludePatterns = [] }) {
  return jobs.filter(j =>
    j.status !== 'completed' &&
    !excludePatterns.some(p => j.name.includes(p)) &&
    matchesPatterns(j.name, noRetryPatterns) &&
    !matchesPatterns(j.name, LABEL_IMMUNE_PATTERNS)
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
  const names = failedJobs.map(j => `"${j.name}"`).join(', ');
  const summary = failedJobs.length === 1
    ? `Job failed: ${names}`
    : `${failedJobs.length} jobs failed: ${names}`;
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

  const installJobs = jobs.filter(j => matchesPatterns(j.name, installPatterns));

  const passed = installJobs.filter(j => j.conclusion === 'success');
  if (passed.length > 0) {
    return { override: false, reason: `binary-exec failure in "${job.name}", but ${passed.length} install-validation job(s) passed (${passed.map(j => j.name).join(', ')}) -- the build executes elsewhere, treating as a download flake` };
  }

  const unfinished = installJobs.filter(j => j.status !== 'completed');
  if (unfinished.length > 0) {
    return { defer: true, reason: `binary-exec failure in "${job.name}", but ${unfinished.length} install-validation job(s) have not finished (${unfinished.map(j => j.name).join(', ')}) -- deferring until the matrix settles` };
  }

  const nonFailures = installJobs.filter(j => j.conclusion !== 'failure');
  if (nonFailures.length > 0) {
    return { override: false, reason: `binary-exec failure in "${job.name}", but ${nonFailures.length} install-validation job(s) did not fail (${nonFailures.map(j => `${j.name}=${j.conclusion}`).join(', ')})` };
  }

  return { override: true, reason: `every install-validation job (${installJobs.length}) failed to execute the downloaded binary -- corrupt cross-platform build, not a CDN flake` };
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
  const prNumber = Number(process.env.WATCHDOG_PR_NUMBER || 0) || context.payload.pull_request?.number || null;
  const deadlineMs = Number(process.env.WATCHDOG_DEADLINE_SECONDS || 0) * 1000;
  let pendingRerun = process.env.WATCHDOG_PENDING_RERUN === 'true';
  const skipRerun = process.env.WATCHDOG_SKIP_RERUN === 'true';

  const pollInterval = 30000;  // 30 seconds (was 15s; halved API quota per generation)
  const maxRuntime = 10800000; // 3 hours
  const minRuntime = 30000;    // 30 seconds minimum before allowing exit
  const startTime = Date.now();

  const MAX_ATTEMPTS = 2;

  // Grace period: wait N consecutive polls with all jobs complete before exiting.
  // Prevents premature exit during partial reruns where new jobs haven't appeared yet.
  const GRACE_POLLS = 3;     // 3 polls × 30s = 90 seconds grace period
  let allCompleteStreak = 0;

  // Jobs to exclude from monitoring (required env var)
  if (!process.env.WATCHDOG_EXCLUDE_PATTERNS || !process.env.WATCHDOG_NO_RETRY_PATTERNS || !process.env.WATCHDOG_INSTALL_VALIDATION_PATTERNS) {
    throw new Error('WATCHDOG_EXCLUDE_PATTERNS, WATCHDOG_NO_RETRY_PATTERNS and WATCHDOG_INSTALL_VALIDATION_PATTERNS env vars are required');
  }
  // Required too, and deliberately so: defaulting it would let a config drift
  // silently restore retry-everything, which is the behaviour issue #537 is
  // about. Missing config must be loud, not permissive.
  if (!process.env.WATCHDOG_RETRY_ALLOWLIST_PATTERNS) {
    throw new Error('WATCHDOG_RETRY_ALLOWLIST_PATTERNS env var is required (see evaluateRetryEligibility)');
  }
  const excludePatterns = process.env.WATCHDOG_EXCLUDE_PATTERNS.split(',').map(s => s.trim());

  // Jobs that should not trigger auto-retry (failures are never transient)
  const noRetryPatterns = process.env.WATCHDOG_NO_RETRY_PATTERNS.split(',').map(s => s.trim());

  // Jobs that download and execute a released binary; subject to the binary-exec guard
  const installValidationPatterns = process.env.WATCHDOG_INSTALL_VALIDATION_PATTERNS.split(',').map(s => s.trim()).filter(Boolean);

  // Jobs whose failures may still be retried when the classifier cannot speak.
  // See evaluateRetryEligibility.
  const retryAllowlistPatterns = process.env.WATCHDOG_RETRY_ALLOWLIST_PATTERNS.split(',').map(s => s.trim()).filter(Boolean);

  // Track jobs already handled to avoid re-logging the same failure every poll
  const handledJobs = new Set();

  // Deferred jobs stay eligible for handling on later polls, so they are tracked
  // separately from handledJobs and only announced once.
  const deferredJobs = new Set();

  // A no-retry (quality) failure has been seen and its force-cancel is being
  // held until the sibling no-retry jobs finish, so one round reports every
  // failing lane. See pendingNoRetryJobs for why.
  let pendingQualityCancel = false;
  let heldQualityFailureMsg = '';

  // The TARGET run's event, re-read from the API every poll. Not
  // `context.eventName`: in chained mode this process is a `workflow_dispatch`
  // watchdog generation monitoring somebody else's run, so its own event name
  // says nothing about what it is watching. Consumed by evaluateCancelExemption
  // inside forceCancel. Stays null until the first successful fetch, which
  // fails closed (null is not exempt, so it cancels as it always did), and
  // every forceCancel call site sits after that fetch inside the poll loop.
  let targetRunEvent = null;

  // Helper: rerun the target run's failed jobs (the API behind
  // `gh run rerun --failed`). Only valid once the run has completed.
  async function executeRerun() {
    try {
      await github.request('POST /repos/{owner}/{repo}/actions/runs/{run_id}/rerun-failed-jobs', {
        owner: context.repo.owner,
        repo: context.repo.repo,
        run_id: targetRunId
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
  const AI_MODEL = 'deepseek/deepseek-v4-pro';
  // Reasoning model: thinking happens before the answer, so give it a real
  // timeout and enough tokens that the reasoning phase cannot starve the
  // final JSON verdict. Budget-wise 25s still fits the generation deadline
  // (480s poll + ~25s AI + <=5min force-cancel wait < the 15-min slim cap).
  const AI_TIMEOUT = 25000; // 25 seconds
  const AI_MAX_TOKENS = 1024;

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
      const safeName = String(job.name).replace(/[^A-Za-z0-9._-]+/g, '_').slice(0, 120);
      const file = path.join(LOG_CAPTURE_DIR, `${safeName}-${job.id}.log`);
      fs.writeFileSync(file, fullText);
      console.log(`[logs] captured the full log for "${job.name}" (${fullText.length} bytes) before any retry`);
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
      // Strip timestamp prefixes and ANSI escape codes
      const stripped = lines.map(l =>
        l.replace(/^\d{4}-\d{2}-\d{2}T[\d:.]+Z\s?/, '').replace(/\x1b\[[0-9;]*m/g, '')
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
      let end = stripped.findIndex(l => l.startsWith('##[error]'));
      if (end >= 0) {
        do { end++; } while (end < stripped.length && stripped[end].startsWith('##[error]'));
      } else {
        end = stripped.length;
      }
      return stripped.slice(Math.max(0, end - 80), end).join('\n');
    } catch (e) {
      console.log(`[AI] Failed to fetch logs for "${job.name}": ${e.message}`);
      return null;
    }
  }

  async function callClassifierModel(logTail) {
    const token = process.env.CLOUDFLARE_API_TOKEN;
    const accountId = process.env.CLOUDFLARE_ACCOUNT_ID;
    if (!token || !accountId) return null;

    const fs = require('fs');
    let systemPrompt;
    try {
      systemPrompt = fs.readFileSync('.ci/prompts/ci-failure-classifier.md', 'utf8').trim();
    } catch (e) {
      console.log(`[AI] Failed to read prompt file: ${e.message}`);
      return null;
    }

    // OpenAI-compatible chat-completions route: partner-served catalog models
    // (like deepseek/deepseek-v4-pro) are not addressable via /ai/run/<model>.
    const url = `https://api.cloudflare.com/client/v4/accounts/${accountId}/ai/v1/chat/completions`;
    const body = JSON.stringify({
      model: AI_MODEL,
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: logTail }
      ],
      max_tokens: AI_MAX_TOKENS,
      temperature: 0.1
    });

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), AI_TIMEOUT);

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body,
        signal: controller.signal
      });
      clearTimeout(timeout);

      if (!response.ok) {
        console.log(`[AI] Classifier endpoint returned HTTP ${response.status}`);
        return null;
      }

      const data = await response.json();
      // OpenAI response shape. Reasoning models put their thinking in
      // message.reasoning_content; the verdict must come from content only.
      const aiResponse = data.choices?.[0]?.message?.content;
      if (!aiResponse) {
        console.log(`[AI] Unexpected response: ${JSON.stringify(data).slice(0, 200)}`);
        return null;
      }

      const rawText = typeof aiResponse === 'string' ? aiResponse : JSON.stringify(aiResponse);
      const cleaned = rawText.trim().replace(/^```(?:json)?\n?/, '').replace(/\n?```$/, '');
      const parsed = JSON.parse(cleaned);

      if (!['transient', 'code-change'].includes(parsed.classification)) return null;
      if (typeof parsed.confidence !== 'number' || parsed.confidence < 0 || parsed.confidence > 1) return null;

      return {
        classification: parsed.classification,
        confidence: parsed.confidence,
        reason: String(parsed.reason || '').slice(0, 200)
      };
    } catch (e) {
      clearTimeout(timeout);
      console.log(`[AI] ${e.name === 'AbortError' ? 'Request timed out' : e.message}`);
      return null;
    }
  }

  // `jobs` is the full job list from this poll: the cross-job fact the guard
  // needs, already fetched, so it is threaded in rather than re-queried.
  // Only install-validation jobs can trigger the guard, so no other job pays
  // for a log fetch here.
  async function evaluateGuard(job, jobs) {
    if (!installValidationPatterns.length || !matchesPatterns(job.name, installValidationPatterns)) return null;
    const logTail = await getLogTail(job);
    if (!logTail) return null;
    return evaluateBinaryExecGuard({ job, logTail, jobs, installPatterns: installValidationPatterns });
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
    if (!ai) console.log(`[AI] Classification failed for "${job.name}" -- the classifier did not answer`);
    const result = ai ? { ...ai, classifierAvailable: true } : fallback;

    if (guard) {
      console.log(`[guard] ${guard.reason}`);
      if (guard.override) {
        console.log(`[guard] Overriding "${result.classification}" (${result.confidence}) with code-change -- no retry`);
        // The guard is a deterministic cross-job check, not a model call, so it
        // counts as an available verdict even when the classifier was down.
        return { classification: 'code-change', confidence: 1, reason: guard.reason, classifierAvailable: true };
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
      console.log(`   Job URL: https://github.com/${context.repo.owner}/${context.repo.repo}/actions/runs/${targetRunId}/job/${job.id}`);
    }
    console.log(`   Run attempt: ${runAttempt}/${MAX_ATTEMPTS}`);
    console.log('='.repeat(70));
    return msg;
  }

  // Helper: force-cancel the workflow run.
  // Waits for critical jobs (WATCHDOG_WAIT_PATTERNS) to finish before cancelling,
  // so cleanup traps (e.g., deleting temp D1 databases) can complete.
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
        response => response.data
      );
      const failedNow = jobsNow.filter(j =>
        j.conclusion === 'failure' && !excludePatterns.some(p => j.name.includes(p))
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
      console.log(`Warning: could not build the full failure roster (${e.message}); reporting the driving job only.`);
    }

    // The cancel-exemption check sits AFTER the roster build (an exempt run
    // still gets the full "here is everything that failed" banner) and BEFORE
    // the critical-job drain (there is nothing to drain for if nothing is being
    // cancelled). This is the single chokepoint: all five call sites route
    // through forceCancel, including the label-immune Review Gate path, so the
    // exemption cannot be bypassed by adding a sixth.
    const exemption = evaluateCancelExemption({ runEvent: targetRunEvent });
    if (exemption.exempt) {
      console.log('');
      console.log('#'.repeat(70));
      console.log(`NOT cancelling run ${targetRunId}: ${exemption.reason}`);
      console.log('Leaving the run to finish so GitHub reports its true conclusion.');
      console.log('#'.repeat(70));
      core.setFailed('PIPELINE FAILED (run left uncancelled so it concludes as "failure"): ' + failureMsg);
      return;
    }

    const waitPatternsRaw = process.env.WATCHDOG_WAIT_PATTERNS || '';
    const waitPatterns = waitPatternsRaw.split(',').map(s => s.trim()).filter(Boolean);

    if (waitPatterns.length > 0) {
      const maxWait = 300000; // 5 minutes
      const waitPoll = 15000; // 15 seconds
      const waitStart = Date.now();

      while (Date.now() - waitStart < maxWait) {
        try {
          const allJobs = await github.paginate(
            github.rest.actions.listJobsForWorkflowRun,
            { owner: context.repo.owner, repo: context.repo.repo, run_id: targetRunId, per_page: 100 },
            response => response.data
          );
          const criticalRunning = allJobs.filter(j =>
            j.status === 'in_progress' && waitPatterns.some(p => j.name.includes(p))
          );
          if (criticalRunning.length === 0) break;
          const elapsed = Math.round((Date.now() - waitStart) / 1000);
          console.log(`Waiting for critical jobs (${elapsed}s): ${criticalRunning.map(j => j.name).join(', ')}`);
        } catch (e) {
          console.log(`Warning: failed to check critical jobs: ${e.message}`);
          break; // Don't block cancellation on API errors
        }
        await new Promise(r => setTimeout(r, waitPoll));
      }
    }

    console.log('Force-cancelling workflow run...');
    try {
      await github.request('POST /repos/{owner}/{repo}/actions/runs/{run_id}/force-cancel', {
        owner: context.repo.owner,
        repo: context.repo.repo,
        run_id: targetRunId
      });
    } catch (e) {
      // Fallback to regular cancel if force-cancel not available
      console.log(`Force-cancel failed (${e.message}), using regular cancel...`);
      await github.rest.actions.cancelWorkflowRun({
        owner: context.repo.owner,
        repo: context.repo.repo,
        run_id: targetRunId
      });
    }
    core.setFailed('PIPELINE CANCELLED: ' + failureMsg);
  }

  // Check for skip-cancellation and skip-auto-retry labels.
  // Labels are fetched LIVE from the API: the event payload's label list is
  // frozen at the event that created the run, so a label added afterwards
  // (e.g. no-cancel-failure added right before rerunning failed jobs) would
  // be invisible in context.payload and silently ignored.
  let skipCancellationOnFailure = false;
  let skipAutoRetry = false;
  if (prNumber) {
    let labels = context.payload.pull_request?.labels.map(l => l.name) || [];
    try {
      const liveLabels = await github.rest.issues.listLabelsOnIssue({
        owner: context.repo.owner,
        repo: context.repo.repo,
        issue_number: prNumber
      });
      labels = liveLabels.data.map(l => l.name);
    } catch (e) {
      console.log(`Could not fetch live PR labels (${e.message}) - falling back to event payload labels`);
    }
    skipCancellationOnFailure = labels.includes('no-cancel-failure');
    if (skipCancellationOnFailure) {
      console.log('Label "no-cancel-failure" detected - will not cancel on job failures');
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
  console.log(`Target run: ${targetRunId}${deadlineMs ? ` | generation deadline: ${deadlineMs / 60000}m` : ''}`);
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
  console.log(`Stuck-threshold: ${STUCK_THRESHOLD_MIN}m (cancellations after this are not retried)`);

  while (Date.now() - startTime < maxRuntime) {
    const elapsed = Date.now() - startTime;
    const elapsedMin = Math.round(elapsed / 60000);

    // Chained mode: hand off before the slim runner's hard 15-minute cap can
    // kill this job mid-decision. Reaching here means no terminal path fired
    // (those all return without the output), so the run is still live.
    if (deadlineMs && elapsed >= deadlineMs) {
      console.log(`[${elapsedMin}m] Generation deadline reached with the run still live - handing off to the next watchdog generation${pendingRerun ? ' (rerun still pending)' : ''}`);
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
        run_id: targetRunId
      }));
      // Refreshed every poll rather than captured once: a rerun keeps the same
      // run id and the same event, so this is stable, but re-reading it means
      // forceCancel can never act on a stale value from a previous generation.
      targetRunEvent = run.event;

      allJobs = await github.paginate(github.rest.actions.listJobsForWorkflowRun, {
        owner: context.repo.owner,
        repo: context.repo.repo,
        run_id: targetRunId,
        per_page: 100
      }, response => response.data);
    } catch (e) {
      console.log(`[${elapsedMin}m] API error (will retry next poll): ${e.message}`);
      await new Promise(resolve => setTimeout(resolve, pollInterval));
      continue;
    }

    // Filter out excluded jobs
    const monitoredJobs = allJobs.filter(j =>
      !excludePatterns.some(pattern => j.name.includes(pattern))
    );

    const completed = monitoredJobs.filter(j => j.status === 'completed');
    const inProgress = monitoredJobs.filter(j => j.status === 'in_progress');
    const queued = monitoredJobs.filter(j => j.status === 'queued');
    const failed = monitoredJobs.filter(j => j.conclusion === 'failure');
    const cancelled = monitoredJobs.filter(j => j.conclusion === 'cancelled');

    console.log(`[${elapsedMin}m] Run: ${run.status} | Jobs: ${completed.length} done, ${inProgress.length} running, ${queued.length} queued, ${failed.length} failed, ${cancelled.length} cancelled`);

    // A held quality force-cancel fires as soon as its siblings settle. This sits
    // BEFORE every other exit path in the loop: the all-jobs-complete branch
    // below would otherwise return first and the run would end with no
    // cancellation annotation naming the failures at all.
    if (pendingQualityCancel) {
      const stillRunning = pendingNoRetryJobs({ jobs: monitoredJobs, noRetryPatterns, excludePatterns });
      if (stillRunning.length === 0) {
        console.log('All no-retry jobs are terminal - firing the held force-cancel with the full roster');
        await forceCancel(heldQualityFailureMsg);
        return;
      }
      console.log(`[${elapsedMin}m] Force-cancel held: waiting on ${stillRunning.length} no-retry job(s)`);
    }

    // Check if workflow was externally cancelled (mass cancellation)
    if (cancelled.length > 0 && cancelled.length >= completed.length / 2) {
      console.log(`Workflow externally cancelled (${cancelled.length}/${completed.length} jobs cancelled) - exiting`);
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
    const stuckCancellations = cancelled.filter(j => jobElapsedMin(j) >= STUCK_THRESHOLD_MIN);
    const normalCancellations = cancelled.filter(j => jobElapsedMin(j) < STUCK_THRESHOLD_MIN);

    // Unified failure + cancellation handling.
    // AI classifies the failure and decides: transient (retry + keep monitoring) or
    // code-change (force-cancel everything). Stuck cancellations bypass AI
    // (a hung job will hang again on retry).
    const failedOrCancelled = [...failed, ...normalCancellations, ...stuckCancellations];

    // Filter to only NEW failures (not already handled in a previous poll).
    // In pending-rerun mode classification stops entirely: the retry decision
    // is already made, every failed job gets rerun at completion anyway, and
    // the old exit-after-dispatch design never classified late failures either.
    const newFailures = pendingRerun ? [] : failedOrCancelled.filter(j => !handledJobs.has(j.name));

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
          console.log(`[guard] install matrix unfinished; deferring "${candidate.name}" until it completes`);
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

      // 0. Stuck cancellations bypass AI + retry entirely -- the job hung
      // once, retrying would just hang again. Force-cancel and surface a
      // loud annotation so the operator investigates the root cause.
      if (isStuck) {
        console.log(`"${job.name}" exceeded ${STUCK_THRESHOLD_MIN}m cancellation threshold -- treating as stuck, no retry`);
        core.error(`Job '${job.name}' ran ${jobMin}m before cancellation, exceeding the ${STUCK_THRESHOLD_MIN}m stuck-threshold. The job's declared timeout-minutes (or GitHub's 6h default) likely expired. Investigate the underlying step before re-running.`);
        await forceCancel(failureMsg);
        return;
      }

      // 1. No-retry jobs (Quality, Review Gate) -- fast fail, no AI.
      // Only for real FAILURES: a Quality failure (lint/type error) is deterministic,
      // so retrying is pointless and we force-cancel fast. A non-stuck CANCELLATION of
      // a Quality job, by contrast, is a runner/infra flake (not a code error) -- nuking
      // a 0-failure run for it is wrong. Let cancellations fall through to the label /
      // retry handling below so a flaky-cancelled job can be re-run instead.
      //
      // The label check is INSIDE this branch's condition, not after it. Without
      // that, this branch returns before the label handling below, and
      // WATCHDOG_NO_RETRY_PATTERNS is 'Quality,Review Gate' -- so
      // `no-cancel-failure` was unreachable for every Quality job, which is the
      // entire class the label exists to hold the run open for. Worse, the label
      // was still detected and logged ("will not cancel on job failures") two
      // minutes before the run was force-cancelled, so the log asserted the
      // opposite of what happened. Observed on run 29825013399.
      //
      // Honouring the label here does NOT reintroduce retries: the label branch
      // below records the failure via core.setFailed and keeps monitoring; it
      // never dispatches a rerun. "Do not retry" and "do not cancel" are
      // compatible.
      //
      // LABEL_IMMUNE_PATTERNS is the exception. CLAUDE.md specifies that Review
      // Gate fails immediately and force-cancels, full stop -- an outstanding
      // review is not a red to be raced past by labelling the PR. Nothing else
      // is immune.
      const noRetryVerdict = evaluateNoRetryCancel({
        jobName: job.name,
        isFailure: failed.includes(job),
        skipCancellationOnFailure,
        noRetryPatterns,
      });
      if (noRetryVerdict.cancel) {
        console.log(`"${job.name}" matches no-retry pattern${noRetryVerdict.labelImmune ? ' (label-immune)' : ''}`);

        // Drain before cancelling (see pendingNoRetryJobs). Label-immune jobs
        // keep the old instant kill; everything else waits for its siblings so
        // one round reports every failing lane instead of the first one.
        const stillRunning = noRetryVerdict.labelImmune
          ? []
          : pendingNoRetryJobs({ jobs: monitoredJobs, noRetryPatterns, excludePatterns });
        if (stillRunning.length > 0) {
          pendingQualityCancel = true;
          // Keep the FIRST held message: forceCancel re-fetches the job list and
          // builds the full roster itself, so this is only the fallback text for
          // the case where that refetch fails.
          heldQualityFailureMsg = heldQualityFailureMsg || failureMsg;
          console.log(
            `Holding the force-cancel until ${stillRunning.length} sibling no-retry job(s) finish: ` +
            stillRunning.map(j => `"${j.name}"`).join(', ')
          );
          await new Promise(resolve => setTimeout(resolve, pollInterval));
          continue;
        }

        await forceCancel(failureMsg);
        return;
      }

      // 2. Label: no-cancel-failure -- let everything finish
      if (skipCancellationOnFailure) {
        console.log('NOTICE: Skipping cancellation due to "no-cancel-failure" label');
        core.setFailed(failureMsg + ' (cancellation skipped)');
        // DON'T return -- keep monitoring
      }
      // 3. Label: no-auto-retry -- force-cancel immediately
      else if (skipAutoRetry) {
        console.log('Force-cancel due to "no-auto-retry" label');
        await forceCancel(failureMsg);
        return;
      }
      // 4. Max attempts reached -- force-cancel
      else if (run.run_attempt >= MAX_ATTEMPTS) {
        console.log(`Attempt ${run.run_attempt}/${MAX_ATTEMPTS} -- no more retries`);
        await forceCancel(failureMsg);
        return;
      }
      // 5. First failure: AI classifies.
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
        });

        // Make a classifier outage visible at run level rather than letting it
        // hide behind a confident-looking "transient" line. Without this the
        // only symptom of a dead classifier is that everything gets retried,
        // which looks exactly like a healthy classifier meeting a flaky day.
        if (ai.classifierAvailable === false) {
          core.warning(
            `Failure classifier unavailable for "${job.name}" (${ai.reason}). ` +
            `Retry policy fell back to the known-flaky allowlist: ${eligibility.retry ? 'retrying' : 'failing fast'}. ` +
            `See issue #537.`
          );
        }

        if (!eligibility.retry) {
          console.log(`[AI] "${job.name}" -> ${ai.classification} (${ai.confidence}): ${ai.reason}`);
          console.log(`No retry: ${eligibility.reason}`);
          await forceCancel(failureMsg);
          return;
        } else {
          console.log(`[AI] "${job.name}" -> ${ai.classification} (${ai.confidence}): ${ai.reason}`);
          // The rerun covers every failed job from this attempt, so name
          // them all in the annotation too (not just the classified one).
          if (failed.length > 1) {
            const { summary } = formatFailureRoster(failed, {
              owner: context.repo.owner,
              repo: context.repo.repo,
              runId: targetRunId,
            });
            failureMsg = summary;
            console.log(`Will retry all ${failed.length} failed jobs: ${failed.map(j => `"${j.name}"`).join(', ')}`);
          }
          console.log(`Retrying: ${eligibility.reason}`);
          console.log('Holding a pending rerun; the chain reruns the failed jobs once the run completes.');
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
        console.log(`Run ${targetRunId} completed but already at attempt ${run.run_attempt}/${MAX_ATTEMPTS} - ending the chain without retry`);
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
      console.log(`Workflow run completed (conclusion: ${run.conclusion}) - exiting watchdog (after ${elapsedMin}m)`);
      return;
    }

    // Exit when all monitored jobs are complete, with grace period to handle
    // partial reruns. Not while a rerun is pending: the chain must survive to
    // the run's completion to trigger that rerun. (The original deadlock this
    // exit prevented -- the in-run watchdog being the only job keeping
    // run.status in_progress -- no longer exists in chained mode, but the
    // grace period still smooths job-list lag around attempt transitions.)
    if (!pendingRerun && monitoredJobs.length > 0 && completed.length === monitoredJobs.length && elapsed >= minRuntime) {
      allCompleteStreak++;
      if (allCompleteStreak >= GRACE_POLLS) {
        console.log(`All ${monitoredJobs.length} monitored jobs completed for ${allCompleteStreak} consecutive polls - exiting watchdog (after ${elapsedMin}m)`);
        return;
      }
      console.log(`[${elapsedMin}m] All jobs complete (${allCompleteStreak}/${GRACE_POLLS} polls) - waiting for possible rerun...`);
    } else {
      allCompleteStreak = 0;
    }

    await new Promise(resolve => setTimeout(resolve, pollInterval));
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
module.exports.LABEL_IMMUNE_PATTERNS = LABEL_IMMUNE_PATTERNS;
module.exports.evaluateCancelExemption = evaluateCancelExemption;
module.exports.CANCEL_EXEMPT_EVENTS = CANCEL_EXEMPT_EVENTS;
module.exports.evaluateRetryEligibility = evaluateRetryEligibility;
