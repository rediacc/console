/**
 * The job attributes of the command span (PLAN-detached-jobs Design 13).
 *
 * One call per job writes `rediacc.job.id`, `rediacc.job.function` and
 * `rediacc.job.follow`, and adds `rediacc.job.outcome` once the run's result is
 * known, and `rediacc.job.start_latency_ms` (from the start of the call, which
 * includes the connection, to the first event). `rediacc.job.polls` is written
 * only when the caller passes a count, and the proxy poll loop does not yet. A
 * command that runs several jobs leaves the attributes of the last one.
 */

import { telemetryService } from '../telemetry/telemetry.js';

/** How the run was followed: a live tail, short polls, not at all, or it ended inside the attach. */
export type JobFollowKind = 'tail' | 'poll' | 'background' | 'attached-finished';

export interface JobSpanInput {
  jobId?: string;
  function: string;
  follow: JobFollowKind;
  /** `succeeded`, `failed`, `cancelled`, or `running` when the ticket was handed back. */
  outcome: string;
  startLatencyMs?: number;
  polls?: number;
}

/** The span attributes for one job, with every unknown left out. */
export function jobSpanAttributes(input: JobSpanInput): Record<string, string | number> {
  return {
    ...(input.jobId ? { 'rediacc.job.id': input.jobId } : {}),
    'rediacc.job.function': input.function,
    'rediacc.job.follow': input.follow,
    'rediacc.job.outcome': input.outcome,
    ...(input.startLatencyMs === undefined
      ? {}
      : { 'rediacc.job.start_latency_ms': input.startLatencyMs }),
    ...(input.polls === undefined ? {} : { 'rediacc.job.polls': input.polls }),
  };
}

/** Write the job's attributes onto the open command span. */
export function annotateJobSpan(input: JobSpanInput): void {
  telemetryService.annotateCommand(jobSpanAttributes(input));
}

/**
 * The follow kind of a direct run from how its start ended: a finished trailer is
 * `attached-finished`, a handle or a ticket handed back is `background`, and a
 * live tail (an interrupted follow, or a drop under an unlimited window that
 * reattached) is `tail`.
 */
export function followKindOf(
  startOutcome: string,
  finishedInside: boolean,
  finiteWindow: boolean
): JobFollowKind {
  if (startOutcome === 'trailer' && finishedInside) return 'attached-finished';
  if (startOutcome === 'handle' || startOutcome === 'trailer') return 'background';
  if (startOutcome === 'dropped' && finiteWindow) return 'background';
  return 'tail';
}
