/**
 * The executor's own observation of a proxied job (PLAN-detached-jobs J6b, section 18 "Triggers").
 *
 * A served command runs the real command body, so the executor's ticket store holds the ticket and its step
 * plan for every job it started. A client that left the attach window follows by polls, and the poll that first
 * sees the terminal state is an observer like any other: it records the finish and runs the steps the job owes,
 * once, through the same claim as `rdc job wait`. A job the executor holds no ticket for (started by another
 * process) owes nothing here, bar one case: a failed or cancelled repository_create job is rolled back from the
 * machine's job record alone (rollbackFromJobRecord).
 */

import { repoNamesByGuid } from '@rediacc/shared/config-schema';
import { getEffectiveConfigName } from '../config/config-name.js';
import {
  outstandingSteps,
  runTicketSteps,
  type StepRunnerDeps,
  type StepRunReport,
} from './run-job.js';
import { liveStepRunnerDeps } from './run-job-live.js';
import { dueSteps, resolveStepHandler, type StepHandler } from './steps.js';
import { isTerminalTicketState, type TicketState, TicketStore } from './ticket-store.js';

export interface ObservedTerminal {
  state: TicketState;
  exitCode?: number;
  finishedAt?: string;
  /** The machine's own record of the job (renet's status file): what a lost ticket is rebuilt from. */
  function?: string;
  repoGuid?: string;
}

export interface ExecutorObservationDeps {
  store(): TicketStore;
  stepDeps(store: TicketStore): Promise<StepRunnerDeps>;
  /** The step handler lookup; the registry by default. */
  resolve?(name: string): Promise<StepHandler>;
  /** The registered name of the repository with this GUID in the request's config, if any. */
  repoRefForGuid?(guid: string): Promise<string | undefined>;
}

async function liveRepoRefForGuid(guid: string): Promise<string | undefined> {
  const { configService } = await import('../config/config-resources.js');
  const config = await configService.getCurrent();
  return config ? repoNamesByGuid(config).get(guid)?.ref : undefined;
}

const liveDeps: ExecutorObservationDeps = {
  store: () => new TicketStore(getEffectiveConfigName()),
  stepDeps: liveStepRunnerDeps,
  repoRefForGuid: liveRepoRefForGuid,
};

/**
 * A job the executor holds no ticket for is either another process's or one whose ticket died with the container's
 * disk (a sleep between dispatch and settle). The machine's status file still names a create job's repository, so a
 * create that did not succeed has its registration removed from that record alone. The step matches by GUID, so a
 * repo registered under the name since is left alone, and a rerun finds nothing to do.
 */
async function rollbackFromJobRecord(
  observed: ObservedTerminal,
  jobId: string,
  deps: ExecutorObservationDeps
): Promise<void> {
  if (observed.function !== 'repository_create' || !observed.repoGuid) return;
  if (observed.state !== 'failed' && observed.state !== 'cancelled') return;
  const repo = await (deps.repoRefForGuid ?? liveRepoRefForGuid)(observed.repoGuid);
  if (repo === undefined) return;
  const handler = await (deps.resolve ?? resolveStepHandler)('rollbackCreate');
  await handler({
    jobId,
    machine: '',
    params: { repo, guid: observed.repoGuid },
    state: observed.state,
  });
}

/**
 * Record a poll's terminal observation on the executor's ticket for `jobId` and run the steps it makes due.
 * Never throws: a poll must answer its client whatever the steps do. Returns undefined when there was nothing to run.
 */
export async function observeTerminalPoll(
  jobId: string,
  observed: ObservedTerminal,
  deps: ExecutorObservationDeps = liveDeps
): Promise<StepRunReport | undefined> {
  if (!isTerminalTicketState(observed.state)) return undefined;
  try {
    const store = deps.store();
    const ticket = store.tickets().find((t) => t.jobId === jobId);
    if (!ticket) {
      await rollbackFromJobRecord(observed, jobId, deps);
      return undefined;
    }
    if (ticket.acknowledged) return undefined;
    if (!isTerminalTicketState(ticket.state)) {
      store.append('finished', ticket.requestId, {
        state: observed.state,
        exitCode: observed.exitCode,
        finishedAt: observed.finishedAt,
      });
    }
    const owed = { ...ticket, state: observed.state };
    if (dueSteps(owed, observed.state).length === 0) {
      store.append('acknowledged', ticket.requestId);
      return undefined;
    }
    const report = await runTicketSteps(store, owed, observed, await deps.stepDeps(store));
    if (outstandingSteps(report).length === 0) store.append('acknowledged', ticket.requestId);
    return report;
  } catch {
    return undefined;
  }
}
