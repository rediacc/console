// Cancel Watchdog - monitors all CI jobs and force-cancels on failure
// Polls every 15 seconds, exits when all jobs complete or a failure is detected.
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

  // Jobs to exclude from monitoring
  const excludePatterns = ['Watchdog', 'CI Complete'];

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

    console.log(`[${elapsedMin}m] Run: ${run.status} | Jobs: ${completed.length} done, ${inProgress.length} running, ${queued.length} queued, ${failed.length} failed`);

    // Check if workflow was externally cancelled
    if (cancelled.length > 0 && cancelled.length >= completed.length / 2) {
      console.log(`Workflow externally cancelled (${cancelled.length}/${completed.length} jobs cancelled) - exiting`);
      return;
    }

    // Check for ANY failure - cancel immediately
    if (failed.length > 0) {
      const failedJob = failed[0];
      const failureMsg = `Job failed: "${failedJob.name}"`;
      console.log('');
      console.log('='.repeat(70));
      console.log(failureMsg);
      console.log(`   Job URL: https://github.com/${context.repo.owner}/${context.repo.repo}/actions/runs/${context.runId}/job/${failedJob.id}`);
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
      return;
    }

    // Exit if all monitored jobs are complete (avoids deadlock where
    // watchdog is the only running job keeping the run "in_progress")
    if (monitoredJobs.length > 0 && completed.length === monitoredJobs.length && elapsed >= minRuntime) {
      console.log(`All ${monitoredJobs.length} monitored jobs completed - exiting watchdog (after ${elapsedMin}m)`);
      return;
    }

    // Also check workflow run status (handles edge cases with reusable workflows)
    if (run.status === 'completed' && elapsed >= minRuntime) {
      console.log(`Workflow run completed with conclusion: ${run.conclusion} - exiting watchdog (after ${elapsedMin}m)`);
      return;
    }

    await new Promise(resolve => setTimeout(resolve, pollInterval));
  }

  // Timeout reached
  console.log('Watchdog reached 3h timeout - exiting');
  core.warning('Cancel Watchdog timeout reached');
};
