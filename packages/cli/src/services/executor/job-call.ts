/**
 * The executor's side of `runJob` (agent/plans/PLAN-detached-jobs.md section
 * 18): a {@link JobCall} whose start is one executor call. `runJob` mints the
 * request id and writes the ticket; the call carries that id and the step plan
 * (`job start --steps`) through the executor, which runs the job with the
 * entry point's attach window and writes no ticket of its own.
 */

import { currentRequestContext } from '../core/request-context.js';
import type { JobCall, JobStartOutcome, ObservedJob } from '../jobs/run-job.js';
import { getExecutor } from './executor-factory.js';
import type { ExecuteOptions, ExecuteResult, Executor } from './types.js';

/** What a finished or pending executor result tells the step runner about its job. */
export function observedJob(result: ExecuteResult): ObservedJob {
  const state = result.state ?? (result.success ? 'succeeded' : 'failed');
  return {
    state,
    exitCode: result.exitCode,
    ...(result.stdout === undefined ? {} : { output: result.stdout }),
    ...(result.steps ? { markers: result.steps.map((s) => s.name) } : {}),
  };
}

/** Wrap one executor call as the JobCall `runJob` drives. */
export function executorJobCall(
  verb: string,
  options: ExecuteOptions,
  executor: Executor = getExecutor()
): JobCall<ExecuteResult> {
  const repo =
    typeof options.params?.repository === 'string' ? options.params.repository : undefined;
  return {
    verb,
    function: options.functionName,
    machine: options.machineName,
    ...(repo ? { repo } : {}),
    via: { kind: currentRequestContext() ? 'proxy' : 'ssh' },
    async start({ requestId, steps }): Promise<JobStartOutcome<ExecuteResult>> {
      const result = await executor.execute({
        ...options,
        requestId,
        jobSteps: steps,
        externalTicket: true,
      });
      const job = observedJob(result);
      if (result.state === 'running') {
        return { kind: 'pending', ...(result.jobId ? { jobId: result.jobId } : {}), job };
      }
      return { kind: 'finished', jobId: result.jobId ?? '', result, job };
    },
  };
}
