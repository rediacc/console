import { outputService } from '../services/core/output.js';
import { setExitCode } from '../services/core/request-context.js';
import { type CommandJobOutcome, pendingExitCode } from '../services/jobs/command-job.js';
import { outstandingSteps } from '../services/jobs/run-job.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';

/**
 * Settle the outcome of a converted repo verb's one job. A pending outcome (`--background`, the proxy window, a lost
 * tail) owes its steps to the ticket and only sets the exit code the executor reported. A failed job renders its
 * failure. A finished one has already run its steps inside the attach window, so a step that did not finish is named
 * and fails the command. Returns true when the job finished successfully.
 */
export function settleRepoJob(
  verb: string,
  outcome: CommandJobOutcome,
  failedMessage: string
): boolean {
  if (outcome.kind === 'pending') {
    const code = pendingExitCode(outcome);
    if (code !== undefined) setExitCode(code);
    return false;
  }
  if (!outcome.result.success) {
    renderLocalExecutionFailure(outcome.result, failedMessage);
    return false;
  }
  const unfinished = outstandingSteps(outcome.steps);
  if (unfinished.length > 0) {
    outputService.warn(
      `${verb}: the job finished, but the step(s) ${unfinished.join(', ')} did not; rdc job wait settles them.`
    );
    setExitCode(1);
  }
  return true;
}
