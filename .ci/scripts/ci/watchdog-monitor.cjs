// Watchdog - monitors workflow jobs, uses AI to classify failures, and manages retries.
// Polls every 15 seconds, exits when the workflow completes or a failure requires action.
//
// On first failure: AI classifies logs as transient or code-change.
//   - Transient: dispatches rerun-failed.yml AND EXITS. rerun-failed.yml
//     waits for the original run to complete, then reruns every failed job
//     from that attempt -- no need for the watchdog to keep monitoring.
//   - Code-change: force-cancels immediately (no point waiting for other jobs).
//   - AI unavailable: falls back to retry (same as transient).
// On attempt 2+: force-cancels without retry.
//
// Required env vars:
//   WATCHDOG_EXCLUDE_PATTERNS   - Comma-separated job name patterns to exclude from monitoring
//   WATCHDOG_NO_RETRY_PATTERNS  - Comma-separated job name patterns that should never auto-retry
//
// Optional env vars (AI failure classification):
//   CLOUDFLARE_API_TOKEN        - Cloudflare API token with Workers AI Read permission
//   CLOUDFLARE_ACCOUNT_ID       - Cloudflare account ID
//
// Labels (PR context only):
//   no-cancel-failure  - Skip cancellation on job failure (workflow continues)
//   no-auto-retry      - Skip AI + retry entirely (force-cancel immediately)
//
// Usage (from actions/github-script):
//   script: return await require('./.ci/scripts/ci/watchdog-monitor.cjs')({github, context, core})

module.exports = async ({ github, context, core }) => {
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

  const pollInterval = 15000;  // 15 seconds
  const maxRuntime = 10800000; // 3 hours
  const minRuntime = 30000;    // 30 seconds minimum before allowing exit
  const startTime = Date.now();

  const MAX_ATTEMPTS = 2;
  const RERUN_WORKFLOW = 'rerun-failed.yml';

  // Grace period: wait N consecutive polls with all jobs complete before exiting.
  // Prevents premature exit during partial reruns where new jobs haven't appeared yet.
  const GRACE_POLLS = 3;     // 3 polls × 15s = 45 seconds grace period
  let allCompleteStreak = 0;

  // Jobs to exclude from monitoring (required env var)
  if (!process.env.WATCHDOG_EXCLUDE_PATTERNS || !process.env.WATCHDOG_NO_RETRY_PATTERNS) {
    throw new Error('WATCHDOG_EXCLUDE_PATTERNS and WATCHDOG_NO_RETRY_PATTERNS env vars are required');
  }
  const excludePatterns = process.env.WATCHDOG_EXCLUDE_PATTERNS.split(',').map(s => s.trim());

  // Jobs that should not trigger auto-retry (failures are never transient)
  const noRetryPatterns = process.env.WATCHDOG_NO_RETRY_PATTERNS.split(',').map(s => s.trim());

  // Track jobs already handled to avoid re-logging the same failure every poll
  const handledJobs = new Set();

  // Helper: dispatch rerun-failed.yml to retry failed jobs
  async function dispatchRerun() {
    try {
      // The ref selects which branch's copy of the workflow file to run — it does
      // NOT affect the retried jobs (gh run rerun uses the original run's branch/SHA).
      // Use the PR head branch when available, otherwise fall back to the repo default branch.
      const ref = context.payload.pull_request?.head.ref || context.payload.repository?.default_branch || 'main';
      console.log(`Dispatching ${RERUN_WORKFLOW} on ref '${ref}' for run ${context.runId}...`);
      await github.rest.actions.createWorkflowDispatch({
        owner: context.repo.owner,
        repo: context.repo.repo,
        workflow_id: RERUN_WORKFLOW,
        ref,
        inputs: { run_id: String(context.runId) }
      });
      console.log(`Successfully dispatched ${RERUN_WORKFLOW}`);
      return true;
    } catch (e) {
      console.log(`WARNING: Failed to dispatch ${RERUN_WORKFLOW}: ${e.message}`);
      console.log('Proceeding with force-cancel without retry.');
      return false;
    }
  }

  // AI failure classification: fetch job logs, call Workers AI, classify as transient/code-change.
  // Falls back to { classification: 'transient', confidence: 0 } on any error (safe default = retry).
  const AI_CONFIDENCE_THRESHOLD = 0.8;
  const AI_MODEL = '@cf/qwen/qwen2.5-coder-32b-instruct';
  const AI_TIMEOUT = 10000; // 10 seconds

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
      return stripped.slice(-80).join('\n');
    } catch (e) {
      console.log(`[AI] Failed to fetch logs for "${job.name}": ${e.message}`);
      return null;
    }
  }

  async function callWorkersAI(logTail) {
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

    const url = `https://api.cloudflare.com/client/v4/accounts/${accountId}/ai/run/${AI_MODEL}`;
    const body = JSON.stringify({
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: logTail }
      ],
      max_tokens: 150,
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
        console.log(`[AI] Workers AI returned HTTP ${response.status}`);
        return null;
      }

      const data = await response.json();
      const aiResponse = data.result?.response;
      if (!data.success || !aiResponse) {
        console.log(`[AI] Unexpected response: ${JSON.stringify(data).slice(0, 200)}`);
        return null;
      }

      // Workers AI may return response as string, array, or object depending on model
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

  async function classifyFailure(job) {
    const fallback = { classification: 'transient', confidence: 0, reason: 'AI unavailable, defaulting to retry' };
    const logTail = await fetchJobLogs(job);
    if (!logTail) return fallback;
    const result = await callWorkersAI(logTail);
    if (!result) {
      console.log(`[AI] Classification failed for "${job.name}", falling back to retry`);
      return fallback;
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
      console.log(`   Job URL: https://github.com/${context.repo.owner}/${context.repo.repo}/actions/runs/${context.runId}/job/${job.id}`);
    }
    console.log(`   Run attempt: ${runAttempt}/${MAX_ATTEMPTS}`);
    console.log('='.repeat(70));
    return msg;
  }

  // Helper: force-cancel the workflow run.
  // Waits for critical jobs (WATCHDOG_WAIT_PATTERNS) to finish before cancelling,
  // so cleanup traps (e.g., deleting temp D1 databases) can complete.
  async function forceCancel(failureMsg) {
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
            { owner: context.repo.owner, repo: context.repo.repo, run_id: context.runId, per_page: 100 },
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
        run_id: context.runId
      });
    } catch (e) {
      // Fallback to regular cancel if force-cancel not available
      console.log(`Force-cancel failed (${e.message}), using regular cancel...`);
      await github.rest.actions.cancelWorkflowRun({
        owner: context.repo.owner,
        repo: context.repo.repo,
        run_id: context.runId
      });
    }
    core.setFailed('PIPELINE CANCELLED: ' + failureMsg);
  }

  // Check for skip-cancellation and skip-auto-retry labels
  let skipCancellationOnFailure = false;
  let skipAutoRetry = false;
  if (context.payload.pull_request) {
    const labels = context.payload.pull_request.labels.map(l => l.name);
    skipCancellationOnFailure = labels.includes('no-cancel-failure');
    if (skipCancellationOnFailure) {
      console.log('Label "no-cancel-failure" detected - will not cancel on job failures');
    }
    skipAutoRetry = labels.includes('no-auto-retry');
    if (skipAutoRetry) {
      console.log('Label "no-auto-retry" detected - will not auto-retry on failures');
    }
  }

  console.log('Watchdog started - monitoring jobs for failures...');
  console.log(`Exclude patterns: ${excludePatterns.join(', ')}`);
  console.log(`No-retry patterns: ${noRetryPatterns.join(', ')}`);
  console.log(`Max runtime: ${maxRuntime / 3600000} hours`);

  while (Date.now() - startTime < maxRuntime) {
    const elapsed = Date.now() - startTime;
    const elapsedMin = Math.round(elapsed / 60000);

    // Fetch run status and jobs, retrying on transient API errors (e.g. 401 Bad credentials)
    let run, allJobs;
    try {
      ({ data: run } = await github.rest.actions.getWorkflowRun({
        owner: context.repo.owner,
        repo: context.repo.repo,
        run_id: context.runId
      }));

      allJobs = await github.paginate(github.rest.actions.listJobsForWorkflowRun, {
        owner: context.repo.owner,
        repo: context.repo.repo,
        run_id: context.runId,
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
    const STUCK_THRESHOLD_MIN = parseInt(process.env.STUCK_THRESHOLD_MIN || '60', 10);
    const jobElapsedMin = (j) => {
      if (!j.started_at || !j.completed_at) return 0;
      return Math.round((new Date(j.completed_at) - new Date(j.started_at)) / 60000);
    };
    const stuckCancellations = cancelled.filter(j => jobElapsedMin(j) >= STUCK_THRESHOLD_MIN);
    const normalCancellations = cancelled.filter(j => jobElapsedMin(j) < STUCK_THRESHOLD_MIN);

    // Unified failure + cancellation handling.
    // AI classifies the failure and decides: transient (retry + keep monitoring) or
    // code-change (force-cancel everything). Stuck cancellations bypass AI
    // (a hung job will hang again on retry).
    const failedOrCancelled = [...failed, ...normalCancellations, ...stuckCancellations];

    // Filter to only NEW failures (not already handled in a previous poll)
    const newFailures = failedOrCancelled.filter(j => !handledJobs.has(j.name));

    if (newFailures.length > 0) {
      const job = newFailures[0];
      const jobMin = jobElapsedMin(job);
      const isStuck = stuckCancellations.includes(job);
      const reason = failed.includes(job)
        ? 'Job failed'
        : isStuck
          ? `Job stuck (ran ${jobMin}m before cancellation -- likely timeout-minutes expiry)`
          : 'Job cancelled (likely manual / supersession)';
      const failureMsg = logFailure(job, reason, run.run_attempt);
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

      // 1. No-retry jobs (Quality, Review Gate) -- fast fail, no AI
      if (noRetryPatterns.some(p => job.name.includes(p))) {
        console.log(`"${job.name}" matches no-retry pattern`);
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
      // Transient -> dispatch rerun and exit. rerun-failed.yml waits for the
      // original run to complete and reruns every failed job from that attempt,
      // so the watchdog does not need to stay up monitoring for more failures.
      // Code-change -> force-cancel now, retry would be pointless.
      else {
        const ai = await classifyFailure(job);
        if (ai.classification === 'code-change' && ai.confidence >= AI_CONFIDENCE_THRESHOLD) {
          console.log(`[AI] "${job.name}" -> code-change (${ai.confidence}): ${ai.reason}`);
          await forceCancel(failureMsg);
          return;
        } else {
          console.log(`[AI] "${job.name}" -> ${ai.classification} (${ai.confidence}): ${ai.reason}`);
          console.log('Dispatching auto-retry and exiting watchdog (rerun-failed.yml waits for run completion and picks up every failed job).');
          await dispatchRerun();
          core.setFailed(failureMsg);
          return;
        }
      }
    }

    // Exit when workflow run is externally completed
    if (run.status === 'completed' && elapsed >= minRuntime) {
      console.log(`Workflow run completed (conclusion: ${run.conclusion}) - exiting watchdog (after ${elapsedMin}m)`);
      return;
    }

    // Exit when all monitored jobs are complete, with grace period to handle partial reruns.
    // Without this check, the watchdog deadlocks (it's the only running job keeping
    // run.status === 'in_progress'). The grace period ensures rerun jobs have time to appear.
    if (monitoredJobs.length > 0 && completed.length === monitoredJobs.length && elapsed >= minRuntime) {
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
