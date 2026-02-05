// Watchdog - monitors workflow jobs, auto-retries transient failures, and force-cancels on failure
// Polls every 15 seconds, exits only when the workflow run completes or a failure is detected.
//
// Auto-retry: On first failure (attempt 1), dispatches rerun-failed.yml to retry failed jobs
// WITHOUT force-cancelling (so only truly failed jobs are retried, not cancelled bystanders).
// On attempt 2+, force-cancels without retry.
//
// Required env vars:
//   WATCHDOG_EXCLUDE_PATTERNS   - Comma-separated job name patterns to exclude from monitoring
//   WATCHDOG_NO_RETRY_PATTERNS  - Comma-separated job name patterns that should never auto-retry
//   WATCHDOG_INDEPENDENT_PATTERNS - Comma-separated job name patterns whose failures don't cancel siblings (optional)
//
// Labels (PR context only):
//   no-cancel-failure  - Skip cancellation on job failure (workflow continues)
//   no-auto-retry      - Skip auto-retry on failure (force-cancel immediately)
//
// Usage (from actions/github-script):
//   script: return await require('./.ci/scripts/ci/watchdog-monitor.cjs')({github, context, core})

module.exports = async ({ github, context, core }) => {
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

  // Jobs whose failures should not cancel sibling jobs (optional env var)
  const independentPatterns = (process.env.WATCHDOG_INDEPENDENT_PATTERNS || '')
    .split(',').map(s => s.trim()).filter(Boolean);
  let independentRerunDispatched = false;

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

  // Helper: log failure details and handle the workflow run.
  // On auto-retry (attempt 1): dispatches rerun without force-cancel so only truly
  // failed jobs are retried. On final attempt: force-cancels the run.
  async function cancelOnFailure(job, reason, runAttempt) {
    const failureMsg = `${reason}: "${job.name}"`;
    console.log('');
    console.log('='.repeat(70));
    console.log(failureMsg);
    if (job.id) {
      console.log(`   Job URL: https://github.com/${context.repo.owner}/${context.repo.repo}/actions/runs/${context.runId}/job/${job.id}`);
    }
    console.log(`   Run attempt: ${runAttempt}/${MAX_ATTEMPTS}`);
    console.log('='.repeat(70));

    if (skipCancellationOnFailure) {
      console.log('');
      console.log('NOTICE: Skipping workflow cancellation due to "no-cancel-failure" label');
      console.log('Workflow will continue running despite this failure.');
      core.setFailed(failureMsg + ' (cancellation skipped due to label)');
      return;
    }

    // Auto-retry: dispatch rerun on first attempt, but do NOT force-cancel.
    // Force-cancelling kills unrelated in-progress jobs, turning them into
    // "cancelled". gh run rerun --failed reruns cancelled jobs too, causing
    // a near-full pipeline rerun instead of retrying just the failed job.
    // By skipping the cancel, other jobs finish naturally and the rerun
    // workflow only picks up the truly failed job(s).
    const isNoRetryJob = noRetryPatterns.some(pattern => job.name.includes(pattern));
    if (runAttempt < MAX_ATTEMPTS && !skipAutoRetry && !isNoRetryJob) {
      console.log(`Attempt ${runAttempt}/${MAX_ATTEMPTS} - triggering auto-retry (skipping force-cancel to avoid cascading reruns)...`);
      await dispatchRerun();
      core.setFailed(failureMsg);
      return;
    } else if (isNoRetryJob) {
      console.log(`Auto-retry skipped: "${job.name}" matches no-retry pattern`);
    } else if (skipAutoRetry) {
      console.log('Auto-retry skipped due to "no-auto-retry" label');
    } else {
      console.log(`Attempt ${runAttempt}/${MAX_ATTEMPTS} - no more retries`);
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
  if (independentPatterns.length > 0) {
    console.log(`Independent patterns (no sibling cancellation): ${independentPatterns.join(', ')}`);
  }
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

    // Separate independent failures from critical failures
    const independentFailed = failed.filter(j =>
      independentPatterns.some(p => j.name.includes(p)));
    const criticalFailed = failed.filter(j =>
      !independentPatterns.some(p => j.name.includes(p)));

    // Log independent failures, dispatch auto-retry once, but don't cancel siblings
    if (independentFailed.length > 0 && !independentRerunDispatched) {
      for (const job of independentFailed) {
        console.log(`[${elapsedMin}m] Independent job failed (no sibling cancellation): "${job.name}"`);
      }
      // Still auto-retry independent failures (handles flaky infra like SSL errors)
      const isNoRetryJob = noRetryPatterns.some(p => independentFailed[0].name.includes(p));
      if (run.run_attempt < MAX_ATTEMPTS && !skipAutoRetry && !isNoRetryJob) {
        console.log(`Dispatching auto-retry for independent job failure...`);
        await dispatchRerun();
      }
      independentRerunDispatched = true;
    } else if (independentFailed.length > 0) {
      console.log(`[${elapsedMin}m] Independent failures (already handled): ${independentFailed.map(j => j.name).join(', ')}`);
    }

    // Cancel on critical failures
    if (criticalFailed.length > 0) {
      await cancelOnFailure(criticalFailed[0], 'Job failed', run.run_attempt);
      return;
    }

    // Same treatment for cancelled jobs
    const independentCancelled = cancelled.filter(j =>
      independentPatterns.some(p => j.name.includes(p)));
    const criticalCancelled = cancelled.filter(j =>
      !independentPatterns.some(p => j.name.includes(p)));

    if (independentCancelled.length > 0) {
      console.log(`[${elapsedMin}m] Independent job cancelled (no action): ${independentCancelled.map(j => j.name).join(', ')}`);
    }

    // Check for individually cancelled jobs (e.g., timeout-killed).
    // Mass cancellation is already handled above.
    if (criticalCancelled.length > 0) {
      await cancelOnFailure(criticalCancelled[0], 'Job cancelled (likely timeout)', run.run_attempt);
      return;
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
