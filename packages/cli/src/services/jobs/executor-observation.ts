/**
 * The executor's own observation of a proxied job (PLAN-detached-jobs J6b, section 18 "Triggers").
 *
 * A served command runs the real command body, so the executor's ticket store holds the ticket and its step
 * plan for every job it started. A client that left the attach window follows by polls, and the poll that first
 * sees the terminal state is an observer like any other: it records the finish and runs the steps the job owes,
 * once, through the same claim as `rdc job wait`. A job the executor holds no ticket for (started by another
 * process) owes nothing here.
 */

import { getEffectiveConfigName } from '../config/config-name.js';
import {
  liveStepRunnerDeps,
  outstandingSteps,
  runTicketSteps,
  type StepRunnerDeps,
  type StepRunReport,
} from './run-job.js';
import { dueSteps } from './steps.js';
import { isTerminalTicketState, type TicketState, TicketStore } from './ticket-store.js';

export interface ObservedTerminal {
  state: TicketState;
  exitCode?: number;
  finishedAt?: string;
}

export interface ExecutorObservationDeps {
  store(): TicketStore;
  stepDeps(store: TicketStore): Promise<StepRunnerDeps>;
}

const liveDeps: ExecutorObservationDeps = {
  store: () => new TicketStore(getEffectiveConfigName()),
  stepDeps: liveStepRunnerDeps,
};

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
    if (!ticket || ticket.acknowledged) return undefined;
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
