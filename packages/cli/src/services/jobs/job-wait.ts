/**
 * `rdc job wait`: resume following a ticketed job, then acknowledge it.
 *
 * Over SSH it resumes from the ticket's `lastSeenLine` through the same tail
 * `rdc job logs --follow` uses. The proxy path is J6's: `deps.followProxy` is
 * the seam, and until J6 supplies it a proxy ticket is refused with a message.
 *
 * Once the job is seen finished, the steps it owes run here (section 18),
 * exactly once across observers. The ticket is acknowledged only when no step
 * is left to another observer of this config.
 */

import { isTerminalState, JobLogCursor, type JobStatus } from '../executor/job-client.js';
import type { RenetEvent } from '../executor/types.js';
import {
  createStepObservationCollector,
  emptyStepReport,
  liveStepRunnerDeps,
  type ObservedJob,
  outstandingSteps,
  runTicketSteps,
  type StepRunnerDeps,
  type StepRunReport,
} from './run-job.js';
import { dueSteps, getStepDefinition } from './steps.js';
import { isTerminalTicketState, type Ticket, type TicketStore } from './ticket-store.js';

/** Opaque to this module: whatever `withConnection` hands to follow and readStatus. */
type WaitConnection = unknown;

export interface JobWaitDeps {
  /** Open a read-only connection, run `fn`, release. */
  withConnection<T>(machine: string, fn: (conn: WaitConnection) => Promise<T>): Promise<T>;
  /** Tail a job from the cursor. Resolves true when interrupted (abort), false at the end of the job. */
  follow(
    conn: WaitConnection,
    jobId: string,
    cursor: JobLogCursor,
    onEvent: (event: RenetEvent, line?: number) => void,
    signal: AbortSignal
  ): Promise<boolean>;
  readStatus(conn: WaitConnection, jobId: string, machine: string): Promise<JobStatus>;
  /** J6 seam: follow a proxy ticket with short polls. Absent until the proxy client lands. */
  followProxy?: (ticket: Ticket, signal: AbortSignal) => Promise<JobStatus | undefined>;
  /** Resolve a ticket stuck at `starting` through `job list --request-id`. Absent until renet supports it (J1b). */
  resolveStarting?: (ticket: Ticket) => Promise<string | undefined>;
  /**
   * Replay a finished job's whole log from line 0 into `onEvent`. Used when a step that reads the job's output is due
   * and this observer did not see the whole stream (a ticket finished while away, a follow resumed past line 0).
   */
  replay?: (
    conn: WaitConnection,
    jobId: string,
    onEvent: (event: RenetEvent, line?: number) => void
  ) => Promise<void>;
  /** The step runner. Built live (renet job claim over SSH) only when the ticket owes a step. */
  steps?: StepRunnerDeps;
}

export type WaitOutcome =
  | {
      kind: 'finished';
      status: Pick<JobStatus, 'state' | 'exit_code' | 'error'>;
      exitCode: number;
      steps: StepRunReport;
    }
  | { kind: 'timeout' }
  | { kind: 'interrupted' }
  | { kind: 'unresolved' }
  | { kind: 'proxy-unsupported' };

export interface WaitOptions {
  timeoutMs?: number;
  onEvent: (event: RenetEvent, line?: number) => void;
  /** Aborts the wait without touching the job (Ctrl-C). */
  signal?: AbortSignal;
}

/** The job's exit code: renet's own, else mirrored from the terminal state. */
function exitCodeFor(status: Pick<JobStatus, 'state' | 'exit_code'>): number {
  if (status.exit_code !== undefined && status.exit_code !== null) return status.exit_code;
  return status.state === 'succeeded' ? 0 : 1;
}

/** A ticket that never got its job id: resolve it through the request index, when renet has one. */
async function ensureJobId(
  store: TicketStore,
  ticket: Ticket,
  deps: JobWaitDeps
): Promise<Ticket | undefined> {
  if (ticket.jobId) return ticket;
  const resolved = await deps.resolveStarting?.(ticket);
  if (!resolved) return undefined;
  store.append('started', ticket.requestId, { jobId: resolved });
  return { ...ticket, jobId: resolved };
}

/** Run the follow under a signal that fires on timeout or on the caller's abort. */
async function withWaitSignal<T>(
  options: WaitOptions,
  run: (signal: AbortSignal) => Promise<T>
): Promise<{ result: T; timedOut: boolean }> {
  const controller = new AbortController();
  let timedOut = false;
  const timer =
    options.timeoutMs === undefined
      ? undefined
      : setTimeout(() => {
          timedOut = true;
          controller.abort();
        }, options.timeoutMs);
  const onOuterAbort = () => controller.abort();
  options.signal?.addEventListener('abort', onOuterAbort, { once: true });
  try {
    return { result: await run(controller.signal), timedOut };
  } finally {
    if (timer) clearTimeout(timer);
    options.signal?.removeEventListener('abort', onOuterAbort);
  }
}

export async function waitForJob(
  store: TicketStore,
  ticket: Ticket,
  deps: JobWaitDeps,
  options: WaitOptions
): Promise<WaitOutcome> {
  const current = await ensureJobId(store, ticket, deps);
  if (!current?.jobId) return { kind: 'unresolved' };
  const jobId = current.jobId;

  // Already known finished: nothing to follow; run what it owes and acknowledge.
  if (isTerminalTicketState(current.state)) {
    const status = { state: current.state as JobStatus['state'], exit_code: current.exitCode };
    const steps = await settleSteps(store, current, { state: current.state }, deps);
    return { kind: 'finished', status, exitCode: exitCodeFor(status), steps };
  }
  if (current.via?.kind === 'proxy' && !deps.followProxy) return { kind: 'proxy-unsupported' };

  const seen = createStepObservationCollector();
  const onEvent: WaitOptions['onEvent'] = (event, line) => {
    seen.consume(event);
    options.onEvent(event, line);
  };
  const { result: status, timedOut } = await withWaitSignal(options, (signal) =>
    current.via?.kind === 'proxy'
      ? (deps.followProxy as NonNullable<JobWaitDeps['followProxy']>)(current, signal)
      : followOverSsh(store, current, jobId, deps, onEvent, signal)
  );

  if (!status || !isTerminalState(status.state)) {
    return timedOut ? { kind: 'timeout' } : { kind: 'interrupted' };
  }

  return finishWait(store, current, status, seen, deps);
}

/** Record the terminal state, run the steps it makes due, and build the outcome. */
async function finishWait(
  store: TicketStore,
  current: Ticket,
  status: JobStatus,
  seen: ReturnType<typeof createStepObservationCollector>,
  deps: JobWaitDeps
): Promise<WaitOutcome> {
  const exitCode = exitCodeFor(status);
  store.append('finished', current.requestId, {
    state: status.state,
    exitCode,
    finishedAt: status.finished_at,
  });
  // A follow that resumed past line 0 missed the earlier events, so its markers are unknown: a marker step then falls back to the terminal state (stepIsDue).
  const sawWholeStream = current.via?.kind !== 'proxy' && current.lastSeenLine === 0;
  const steps = await settleSteps(
    store,
    { ...current, state: status.state },
    {
      state: status.state,
      exitCode,
      finishedAt: status.finished_at,
      ...(sawWholeStream ? { markers: seen.markers } : {}),
      output: seen.output || undefined,
    },
    deps
  );
  return { kind: 'finished', status, exitCode, steps };
}

/** Run the steps a finished ticket owes, then acknowledge it unless a step is left to another observer. */
async function settleSteps(
  store: TicketStore,
  ticket: Ticket,
  job: ObservedJob,
  deps: JobWaitDeps
): Promise<StepRunReport> {
  let report = emptyStepReport();
  const latest = store.find(ticket.requestId) ?? ticket;
  const owed = { ...latest, state: job.state };
  const due = dueSteps(owed, job.state, job.markers);
  if (due.length > 0) {
    const stepDeps = deps.steps ?? (await liveStepRunnerDeps(store));
    report = await runTicketSteps(store, owed, await withReplayedOutput(owed, job, deps), stepDeps);
  }
  if (outstandingSteps(report).length === 0) store.append('acknowledged', ticket.requestId);
  return report;
}

/**
 * The observation, completed with the job's log when a due step reads its output and this observer has none: the
 * results `repo migrate` prints per phase reach `rdc job wait` this way, long after the attach window closed. A log
 * that cannot be read leaves the observation as it was, and the step prints nothing rather than failing.
 */
async function withReplayedOutput(
  ticket: Ticket,
  job: ObservedJob,
  deps: JobWaitDeps
): Promise<ObservedJob> {
  const wantsOutput = dueSteps(ticket, job.state, job.markers).some(
    (s) => getStepDefinition(s.name)?.needsOutput === true
  );
  if (!wantsOutput || job.output || !deps.replay || !ticket.jobId || !ticket.machine) return job;
  const { replay, withConnection } = deps;
  const jobId = ticket.jobId;
  const seen = createStepObservationCollector();
  try {
    await withConnection(ticket.machine, (conn) =>
      replay(conn, jobId, (event) => seen.consume(event))
    );
  } catch {
    return job;
  }
  return {
    ...job,
    output: seen.output || undefined,
    markers: job.markers ?? seen.markers,
  };
}

function followOverSsh(
  store: TicketStore,
  ticket: Ticket,
  jobId: string,
  deps: JobWaitDeps,
  onEvent: WaitOptions['onEvent'],
  signal: AbortSignal
): Promise<JobStatus | undefined> {
  const machine = ticket.machine as string;
  const cursor = new JobLogCursor(ticket.lastSeenLine);
  return deps.withConnection(machine, async (conn) => {
    let interrupted: boolean;
    try {
      interrupted = await deps.follow(conn, jobId, cursor, onEvent, signal);
    } finally {
      // The cursor counts complete lines only, so resuming from it never skips or repeats one.
      store.append('seen', ticket.requestId, { lastSeenLine: cursor.sinceLine });
    }
    if (interrupted) return undefined;
    return deps.readStatus(conn, jobId, machine);
  });
}
