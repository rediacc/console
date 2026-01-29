// Cancel Watchdog - monitors all CI jobs and force-cancels on failure
// Polls every 15 seconds, exits only when the workflow run completes or a failure is detected.
//
// Labels:
//   no-cancel-failure  - Skip cancellation on job failure (workflow continues)
//
// Usage (from actions/github-script):
//   script: return await require('./.ci/scripts/ci/watchdog-monitor.cjs')({github, context, core})

module.exports = async ({ github, context, core }) => {
  const pollInterval = 15000;  // 15 seconds
  const maxRuntime = 10800000; // 3 hours
  const minRuntime = 30000;    // 30 seconds minimum before allowing exit
  const startTime = Date.now();

  // Grace period: wait N consecutive polls with all jobs complete before exiting.
  // Prevents premature exit during partial reruns where new jobs haven't appeared yet.
  const GRACE_POLLS = 3;     // 3 polls × 15s = 45 seconds grace period
  let allCompleteStreak = 0;

  // Jobs to exclude from monitoring
  const excludePatterns = ['Watchdog', 'CI Complete'];

  // Helper: log failure details and force-cancel the workflow run
  async function cancelOnFailure(job, reason) {
    const failureMsg = `${reason}: "${job.name}"`;
    console.log('');
    console.log('='.repeat(70));
    console.log(failureMsg);
    if (job.id) {
      console.log(`   Job URL: https://github.com/${context.repo.owner}/${context.repo.repo}/actions/runs/${context.runId}/job/${job.id}`);
    }
    console.log('='.repeat(70));

    if (skipCancellationOnFailure) {
      console.log('');
      console.log('NOTICE: Skipping workflow cancellation due to "no-cancel-failure" label');
      console.log('Workflow will continue running despite this failure.');
      core.setFailed(failureMsg + ' (cancellation skipped due to label)');
      return;
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

  // Check for skip-cancellation label
  let skipCancellationOnFailure = false;
  if (context.payload.pull_request) {
    const labels = context.payload.pull_request.labels.map(l => l.name);
    skipCancellationOnFailure = labels.includes('no-cancel-failure');
    if (skipCancellationOnFailure) {
      console.log('Label "no-cancel-failure" detected - will not cancel on job failures');
    }
  }

  console.log('Cancel Watchdog started - monitoring ALL jobs for failures...');
  console.log(`Max runtime: ${maxRuntime / 3600000} hours`);

  while (Date.now() - startTime < maxRuntime) {
    const elapsed = Date.now() - startTime;
    const elapsedMin = Math.round(elapsed / 60000);

    // Check workflow run status first (to detect when run is truly complete)
    const { data: run } = await github.rest.actions.getWorkflowRun({
      owner: context.repo.owner,
      repo: context.repo.repo,
      run_id: context.runId
    });

    // Paginate to get ALL jobs (runs can have 60+ jobs with reusable workflows)
    const allJobs = await github.paginate(github.rest.actions.listJobsForWorkflowRun, {
      owner: context.repo.owner,
      repo: context.repo.repo,
      run_id: context.runId,
      per_page: 100
    }, response => response.data);

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

    // Check for ANY failure - cancel immediately
    if (failed.length > 0) {
      await cancelOnFailure(failed[0], 'Job failed');
      return;
    }

    // Check for individually cancelled jobs (e.g., timeout-killed).
    // Mass cancellation is already handled above.
    if (cancelled.length > 0) {
      await cancelOnFailure(cancelled[0], 'Job cancelled (likely timeout)');
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
  core.warning('Cancel Watchdog timeout reached');
};
