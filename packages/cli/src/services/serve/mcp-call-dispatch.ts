/**
 * The dispatch of one hosted MCP call, with its audit and its answer window (agent/plans/PLAN-rmcp-agent-grants.md Design 4).
 *
 * A mutating command is audited as `started` first and is refused (AUDIT_UNAVAILABLE) when that record cannot be delivered,
 * as `/v1/command` does: a change the executor cannot record is not made. The command then runs against the grant session's
 * config, counted as one running dispatch until it settles, and its outcome is audited whenever it ends, also after the call
 * has answered a job handle. The call waits at most `windowMs`: a run that has started a job by then is {@link HandedBack}, one
 * that has not is {@link WindowPassed}, and either way the dispatch keeps running.
 */

import type { AiToolRun, requestOf } from '../ai/tools.js';
import type { ForensicsTicket } from '../forensics/client.js';
import type { AgentGrantHandle } from './agent-grant-session.js';
import { AuditUnavailableError } from './audit.js';
import type { BusyCounter } from './busy.js';
import { type DispatchOutcome, dispatchCommand } from './command-dispatch.js';
import type { ExecutorAuditEvent, ServeDeps } from './deps.js';
import { targetFrom } from './mcp-call-scope.js';
import { isReadOnlyCommand } from './policy.js';

/** A run that started a job and passed the answer window: the job keeps running, the call answers its handle. */
export class HandedBack extends Error {
  constructor(
    readonly jobId: string,
    readonly machine: string | undefined
  ) {
    super('handed back');
  }
}

/** A run that passed the answer window before it started a job. */
export class WindowPassed extends Error {}

export interface DispatchCall {
  deps: ServeDeps;
  busy: BusyCounter;
  handle: AgentGrantHandle;
  requestId: string;
  /** How long the call waits for the dispatch, in milliseconds. */
  windowMs: number;
  /** Told of every machine job the dispatch starts, also after the call answered (an AI chat cancels them on abort). */
  onJobStarted?: (jobId: string, machine: string | undefined) => void;
  /** The request's single-use forensics read ticket, handed to the dispatch (PLAN-forensics-investigation D8). */
  forensicsTicket?: ForensicsTicket;
}

/** `{[key]: value}` when `value` is present, else nothing: keeps the optional audit fields out of the branch count. */
function present<K extends string, V>(
  key: K,
  value: V | undefined | null | ''
): Partial<Record<K, V>> {
  if (value === undefined || value === null || value === '') return {};
  return { [key]: value } as Record<K, V>;
}

/** The audit fields a finished dispatch adds to the event: the function it ran, where, and how it ended. */
function outcomeFields(
  outcome: DispatchOutcome,
  requestedMachine: string | undefined
): Partial<ExecutorAuditEvent> {
  const { result } = outcome;
  return {
    ...present('functionName', outcome.functionName),
    ...present('functionParams', outcome.functionParams),
    ...present('machineName', outcome.machineName ?? requestedMachine),
    ...present('jobId', result.jobId),
    ...present('outcome', result.state === 'running' ? 'started' : result.state),
    success: result.success,
    exitCode: result.exitCode,
    durationMs: result.durationMs,
  };
}

/** The `started` record of a mutating command, after checking the executor can record at all. */
async function recordStarted(deps: ServeDeps, event: ExecutorAuditEvent): Promise<void> {
  const capability = await deps.auth.canWriteAudit();
  if (!capability.ok) {
    throw new AuditUnavailableError(`the executor cannot record it: ${capability.reason}`);
  }
  await deps.audit?.(event);
}

/** Wait for `settled`, or answer by throwing at the window: {@link HandedBack} with a job started, else {@link WindowPassed}. */
async function withinWindow(
  settled: Promise<DispatchOutcome>,
  windowMs: number,
  job: () => { jobId: string; machine: string | undefined } | undefined
): Promise<DispatchOutcome> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const passed = new Promise<'passed'>((resolve) => {
    timer = setTimeout(() => resolve('passed'), windowMs);
  });
  try {
    const raced = await Promise.race([settled, passed]);
    if (raced !== 'passed') return raced;
    const started = job();
    if (started) throw new HandedBack(started.jobId, started.machine);
    throw new WindowPassed();
  } finally {
    clearTimeout(timer);
  }
}

/** The `dispatch` step of `runAiTool` for one call: audit, run against the grant's config, audit the outcome, answer within the window. */
export function dispatcher(call: DispatchCall, request: ReturnType<typeof requestOf>) {
  const { deps, handle, requestId } = call;
  const { principal } = handle;
  return async (run: AiToolRun): Promise<DispatchOutcome> => {
    const { entry } = run.prepared;
    const machineName = targetFrom(
      entry.machineOption,
      entry.machinePositional,
      request.params,
      request.positionals
    );
    const event = (extra: Partial<ExecutorAuditEvent>): ExecutorAuditEvent => ({
      principal,
      commandPath: entry.pathKey,
      requestId,
      ...present('machineName', machineName),
      params: request.params,
      success: true,
      exitCode: 0,
      durationMs: 0,
      destructive: entry.destructive ?? false,
      ...extra,
    });
    const recordsIntent = !!deps.audit && !isReadOnlyCommand(entry);
    if (recordsIntent) await recordStarted(deps, event({ outcome: 'started' }));

    let job: { jobId: string; machine: string | undefined } | undefined;
    const dispatched = call.busy.track(() =>
      dispatchCommand({
        prepared: run.prepared,
        executor: deps.executor,
        config: handle.config,
        ...(principal.tokenId ? { principalTokenId: principal.tokenId } : {}),
        caller: {
          userId: principal.userId,
          orgId: principal.orgId,
          userEmail: principal.userEmail,
        },
        requestId,
        ...(call.forensicsTicket ? { forensicsTicket: call.forensicsTicket } : {}),
        ...(run.background ? { background: true } : {}),
        onJobStarted: (jobId, machine) => {
          job = { jobId, machine };
          call.onJobStarted?.(jobId, machine);
        },
        onEvent: run.onEvent,
      })
    );
    // The outcome is audited whenever the dispatch ends, also after the call answered a job handle; a job handed back after a `started` record is recorded by the poll that ends it.
    const audited = dispatched.then(async (outcome) => {
      if (outcome.result.state === 'running' && recordsIntent) return outcome;
      await Promise.resolve(deps.audit?.(event(outcomeFields(outcome, machineName)))).catch(
        () => undefined
      );
      return outcome;
    });
    // A rejection after the call answered early is not an unhandled one.
    audited.catch(() => undefined);
    return await withinWindow(audited, call.windowMs, () => job);
  };
}
