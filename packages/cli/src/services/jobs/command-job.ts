/**
 * A converted command's one job (PLAN-detached-jobs sections 14, 18 and 25).
 *
 * A command body that has client-side steps hands its main call and its step
 * plan to {@link runCommandJob}. The call runs through the executor as one
 * machine job with the entry point's attach window; `runJob` writes the ticket
 * around it and runs the steps a finished job owes, exactly once across
 * observers. A job still running when the window closes (`--background`, the
 * proxy window, a lost tail) returns `pending`: its steps stay on the ticket
 * and the spool, and `rdc job wait` or the finished-while-away notice runs them.
 *
 * The command never runs its follow-up code inline any more: the step plan is
 * the follow-up code, so a ticket handed back early cannot record a result that
 * has not happened (the reason each J0 verb sat in BACKGROUND_UNSAFE).
 */

import { randomUUID } from 'node:crypto';
import { getEffectiveConfigName } from '../config/config-name.js';
import { currentRequestContext } from '../core/request-context.js';
import { getExecutor } from '../executor/executor-factory.js';
import { observedJob } from '../executor/job-call.js';
import type { ExecuteOptions, ExecuteResult, Executor } from '../executor/types.js';
import {
  type JobCall,
  type JobStartOutcome,
  liveStepRunnerDeps,
  runJob,
  type StepRunnerDeps,
  type StepRunReport,
} from './run-job.js';
import type { PlannedStep } from './steps.js';
import { type Ticket, TicketStore } from './ticket-store.js';

export interface CommandJobDeps {
  executor(): Executor;
  store(): TicketStore;
  stepDeps(store: TicketStore): Promise<StepRunnerDeps>;
}

const liveDeps: CommandJobDeps = {
  executor: getExecutor,
  store: () => new TicketStore(getEffectiveConfigName()),
  stepDeps: liveStepRunnerDeps,
};

let deps: CommandJobDeps = liveDeps;

/** Test seam: replace any of the live dependencies; no argument restores them. */
export function setCommandJobDeps(next?: Partial<CommandJobDeps>): void {
  deps = next ? { ...liveDeps, ...next } : liveDeps;
}

export type CommandJobOutcome =
  | { kind: 'finished'; result: ExecuteResult; jobId: string; ticket: Ticket; steps: StepRunReport }
  | {
      kind: 'pending';
      /** The executor's answer: `state: 'running'`, and a non-zero exit code for a lost tail or a Ctrl-C detach. */
      result: ExecuteResult;
      ticket: Ticket;
      steps: StepRunReport;
    };

/**
 * The job was dispatched (the executor answered) and a later step of the command failed, a ticket-store write
 * for one. The job exists on the machine, so a caller must not undo what it registered for it. A rejection that is
 * not this error means the job never started.
 */
export class JobDispatchedError extends Error {
  constructor(
    readonly requestId: string | undefined,
    readonly jobId: string | undefined,
    readonly cause: unknown
  ) {
    super(
      `the job was dispatched${jobId ? ` (job ${jobId})` : ''}${requestId ? ` (ticket ${requestId})` : ''}, but recording it failed: ${cause instanceof Error ? cause.message : String(cause)}`
    );
    this.name = 'JobDispatchedError';
  }
}

/**
 * Run `options` as the command's one job, with `steps` on its ticket.
 *
 * A start the executor refuses (an overlap, a failed precondition, an old renet)
 * throws as before; the `starting` record runJob wrote is acknowledged first, so
 * the refusal leaves no ticket for the notice to chase. A failure after the executor answered
 * (the job exists) throws {@link JobDispatchedError} instead.
 */
export async function runCommandJob(
  verb: string,
  options: ExecuteOptions,
  steps: PlannedStep[]
): Promise<CommandJobOutcome> {
  const store = deps.store();
  const stepDeps = await deps.stepDeps(store);
  const inner = deps.executor();
  let last: ExecuteResult | undefined;
  let requestId: string | undefined;
  const mint = () => {
    requestId = randomUUID();
    return requestId;
  };
  const call = commandJobCall(verb, { ...options, verb }, inner, (result) => {
    last = result;
  });

  try {
    const outcome = await runJob(call, steps, {
      store,
      steps: stepDeps,
      mintRequestId: mint,
    });
    if (outcome.kind === 'finished') return outcome;
    return {
      kind: 'pending',
      result: last ?? { success: true, exitCode: 0, durationMs: 0, state: 'running' },
      ticket: outcome.ticket,
      steps: outcome.steps,
    };
  } catch (error) {
    if (last !== undefined) throw new JobDispatchedError(requestId, last.jobId, error);
    acknowledgeUnknown(store, requestId);
    throw error;
  }
}

/** A refused start leaves no ticket for the notice to chase; a store that cannot be written never fails the command. */
function acknowledgeUnknown(store: TicketStore, requestId: string | undefined): void {
  if (!requestId) return;
  try {
    store.append('acknowledged', requestId, { state: 'unknown' });
  } catch {
    // Left as is.
  }
}

/**
 * The executor's side of one converted command: one executor call carrying the
 * request id and the `--steps` plan, with the ticket left to `runJob`.
 *
 * The markers a step sees are the `step_done` names the executor collected from
 * the job's stream (`result.steps`). A call that returned here was followed from
 * its first event, so its marker list is defined even when empty: a failure step
 * such as rollbackFork can then tell "the image was never made" from "nobody saw".
 */
function commandJobCall(
  verb: string,
  options: ExecuteOptions,
  executor: Executor,
  onResult: (result: ExecuteResult) => void
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
      onResult(result);
      const markers = (result.steps ?? []).map((step) => step.name);
      const job = { ...observedJob(result), markers };
      if (result.state === 'running') {
        return { kind: 'pending', ...(result.jobId ? { jobId: result.jobId } : {}), job };
      }
      return { kind: 'finished', jobId: result.jobId ?? '', result, job };
    },
  };
}

/**
 * The exit code a pending outcome owes: zero when the ticket was handed back by
 * design (`--background`, the proxy window), the executor's code when the tail
 * was lost or the operator detached.
 */
export function pendingExitCode(outcome: CommandJobOutcome): number | undefined {
  if (outcome.kind !== 'pending' || outcome.result.success) return undefined;
  return outcome.result.exitCode;
}
