/**
 * `runJob(call, steps)` and the exactly-once step runner (PLAN-detached-jobs
 * sections 16 and 18).
 *
 * A command body hands `runJob` a {@link JobCall}: something that starts the
 * job with a request id and a step plan, attaches for the attach window, and
 * answers either "finished, here is the result" or "still running". `runJob`
 * writes the ticket around it (a `starting` record before the start, `started`
 * once the job id is known), runs the steps a finished job owes, and returns
 * `finished(result)` or `pending(ticket)`. The executor wires the real start;
 * this module never touches SSH or the proxy for the start itself.
 *
 * Steps run once, whoever observes the terminal state first: `runJob` inside
 * the attach, `rdc job wait`, or the finished-while-away notice. Each observer
 * claims the steps through `renet job claim` (the {@link ClaimExec} seam), runs
 * only what it claimed, marks it done on the machine, and records `step-done`
 * on the local ticket. The config gate keeps an observer of another config
 * from running a plan that belongs to the config that started the job.
 */

import { randomUUID } from 'node:crypto';
import { hostname } from 'node:os';
import { shellQuote } from '../../utils/shell-quote.js';
import { assertJobId } from '../executor/job-client.js';
import type { RenetEvent } from '../executor/types.js';
import {
  dueSteps,
  type PlannedStep,
  resolveStepHandler,
  type SpoolStep,
  type StepHandler,
  toSpoolSteps,
  toTicketSteps,
} from './steps.js';
import type { Ticket, TicketState, TicketStep, TicketStore, TicketVia } from './ticket-store.js';

// --- the observation ---------------------------------------------------------

/** The config a job was started from, or the config observing it. */
export interface ConfigIdentity {
  configName?: string;
  configId?: string;
}

/** What an observer learned about a job. */
export interface ObservedJob {
  state: TicketState;
  exitCode?: number;
  finishedAt?: string;
  /** Names of marker events seen in the job's stream (renet `step_done` names). Undefined when the observer saw no stream. */
  markers?: string[];
  /** The job's reconstructed stdout, for steps that need it. */
  output?: string;
  /** The job's recorded origin (renet `job status` origin.config), when the observer read it. */
  origin?: ConfigIdentity;
}

/**
 * Steps run only for the config that started the job. Ids decide when both
 * sides carry one; otherwise names do. An origin that names no config at all
 * (a job started before origins were recorded) is not gated.
 */
export function configMatches(origin: ConfigIdentity, observer: ConfigIdentity): boolean {
  if (origin.configId && observer.configId) return origin.configId === observer.configId;
  if (origin.configName && observer.configName) return origin.configName === observer.configName;
  return !origin.configId && !origin.configName;
}

// --- the claim seam ----------------------------------------------------------

export type ClaimResultKind = 'claimed' | 'reclaimed' | 'already-claimed' | 'done';

export interface ClaimAnswer {
  name: string;
  result: ClaimResultKind;
}

export interface ClaimRequest {
  machine: string;
  jobId: string;
  steps: string[];
  /** Record the steps as done instead of claiming them. */
  done?: boolean;
}

/** `renet job claim --id <jobId> --steps a,b [--done]`, run on the job's machine. */
export type ClaimExec = (request: ClaimRequest) => Promise<ClaimAnswer[]>;

export interface StepRunnerDeps {
  claim: ClaimExec;
  /** The observing config. */
  observer: ConfigIdentity;
  /** stderr only. */
  warn(line: string): void;
  /** Handler lookup; the registry by default. */
  resolve?: (name: string) => Promise<StepHandler>;
  now?: () => number;
}

export interface StepRunReport {
  /** Ran here and recorded done. */
  ran: string[];
  /** Another observer already finished them; mirrored as done here. */
  doneElsewhere: string[];
  /** Another live observer holds the claim. */
  heldElsewhere: string[];
  /** Claimed here, but the handler or the claim failed. The claim goes stale and is retaken later. */
  failed: string[];
  /** Due, but owned by another config. */
  gated: string[];
  /** Due, but not started before the budget ran out. */
  deferred: string[];
}

export function emptyStepReport(): StepRunReport {
  return { ran: [], doneElsewhere: [], heldElsewhere: [], failed: [], gated: [], deferred: [] };
}

/** Steps still owed after a run: whatever another observer of this config may pick up. */
export function outstandingSteps(report: StepRunReport): string[] {
  return [...report.heldElsewhere, ...report.failed, ...report.deferred];
}

export interface StepRunOptions {
  /** Absolute deadline (ms since epoch). Steps not claimed by then are deferred, never abandoned mid-run. */
  deadline?: number;
}

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

interface StepSession {
  /** Claim steps; undefined when the claim exec failed (the steps are reported failed). */
  claim(names: string[]): Promise<ClaimAnswer[] | undefined>;
  /** Act on one claim answer: run what was claimed, mirror what is done, skip what is held. */
  settle(step: TicketStep, answer: ClaimAnswer | undefined): Promise<void>;
}

function openStepSession(
  store: TicketStore,
  ticket: Ticket & { jobId: string; machine: string },
  job: ObservedJob,
  deps: StepRunnerDeps,
  report: StepRunReport
): StepSession {
  const { jobId, machine } = ticket;
  const resolve = deps.resolve ?? resolveStepHandler;
  const recordDone = (name: string) => store.append('step-done', ticket.requestId, { step: name });

  const run = async (step: TicketStep): Promise<boolean> => {
    try {
      const handler = await resolve(step.name);
      await handler({
        jobId,
        machine,
        params: step.params ?? {},
        state: job.state,
        output: job.output,
        finishedAt: job.finishedAt,
        ...(job.exitCode === undefined ? {} : { exitCode: job.exitCode }),
        ...(job.markers === undefined ? {} : { markers: job.markers }),
      });
      return true;
    } catch (error) {
      deps.warn(errorText(error));
      report.failed.push(step.name);
      return false;
    }
  };

  return {
    async claim(names) {
      try {
        return await deps.claim({ machine, jobId, steps: names });
      } catch (error) {
        deps.warn(errorText(error));
        report.failed.push(...names);
        return undefined;
      }
    },
    async settle(step, answer) {
      if (!answer) return;
      if (answer.result === 'done') {
        recordDone(step.name);
        report.doneElsewhere.push(step.name);
        return;
      }
      if (answer.result === 'already-claimed') {
        report.heldElsewhere.push(step.name);
        return;
      }
      if (!(await run(step))) return;
      // The step ran: record it here even if the machine-side done marker fails, since every step is idempotent or keyed by job id and a stale-claim rerun changes nothing.
      try {
        await deps.claim({ machine, jobId, steps: [step.name], done: true });
      } catch (error) {
        deps.warn(errorText(error));
      }
      recordDone(step.name);
      report.ran.push(step.name);
    },
  };
}

/**
 * Run the steps a ticket owes for an observed state, exactly once across
 * observers. Never throws: a step failure is reported and leaves the step
 * pending, so the next observer retakes the claim once it goes stale.
 */
export async function runTicketSteps(
  store: TicketStore,
  ticket: Ticket,
  job: ObservedJob,
  deps: StepRunnerDeps,
  options: StepRunOptions = {}
): Promise<StepRunReport> {
  const report = emptyStepReport();
  const due = dueSteps(ticket, job.state, job.markers);
  const { jobId, machine } = ticket;
  if (due.length === 0 || !jobId || !machine) return report;

  if (!configMatches(job.origin ?? { configName: ticket.config }, deps.observer)) {
    report.gated = due.map((s) => s.name);
    return report;
  }

  const session = openStepSession(store, { ...ticket, jobId, machine }, job, deps, report);
  if (options.deadline === undefined) await settleAll(session, due);
  else await settleWithin(session, due, options.deadline, deps.now ?? Date.now, report);
  return report;
}

/** Claim every due step in one exec, then settle each. */
async function settleAll(session: StepSession, due: TicketStep[]): Promise<void> {
  const answers = await session.claim(due.map((s) => s.name));
  if (!answers) return;
  for (const step of due) {
    await session.settle(
      step,
      answers.find((a) => a.name === step.name)
    );
  }
}

/** Under a budget, claim one step at a time, so nothing is claimed that will not be run. */
async function settleWithin(
  session: StepSession,
  due: TicketStep[],
  deadline: number,
  now: () => number,
  report: StepRunReport
): Promise<void> {
  for (const step of due) {
    if (now() >= deadline) {
      report.deferred.push(step.name);
      continue;
    }
    const answers = await session.claim([step.name]);
    await session.settle(
      step,
      answers?.find((a) => a.name === step.name)
    );
  }
}

// --- markers and output from an event stream ---------------------------------

/** Folds a job's events into the markers and output a step may need. */
export function createStepObservationCollector(): {
  consume(event: RenetEvent): void;
  readonly markers: string[];
  readonly output: string;
} {
  const markers: string[] = [];
  let output = '';
  return {
    consume(event) {
      if (event.type === 'step_done' && event.name && !markers.includes(event.name)) {
        markers.push(event.name);
      }
      if (event.type === 'output' && event.msg != null) output += `${event.msg}\n`;
    },
    get markers() {
      return markers;
    },
    get output() {
      return output;
    },
  };
}

// --- runJob ------------------------------------------------------------------

/** What the call's start receives: the request id to dedupe on and the `--steps` plan. */
export interface JobStartRequest {
  requestId: string;
  /** Empty when the command plans no steps; then `--steps` is omitted. */
  steps: SpoolStep[];
}

export type JobStartOutcome<R> =
  | { kind: 'finished'; jobId: string; result: R; job: ObservedJob; lastSeenLine?: number }
  | {
      kind: 'pending';
      /** Absent when the start's answer was lost; `rdc job wait` resolves it through the request id. */
      jobId?: string;
      /** What the attach saw before the window closed (markers fire their steps now). */
      job?: ObservedJob;
      lastSeenLine?: number;
    };

/** "Start a job and observe it", supplied by the executor. */
export interface JobCall<R> {
  verb: string;
  function: string;
  machine: string;
  repo?: string;
  via?: TicketVia;
  start(request: JobStartRequest): Promise<JobStartOutcome<R>>;
}

export type RunJobResult<R> =
  | { kind: 'finished'; result: R; jobId: string; ticket: Ticket; steps: StepRunReport }
  | { kind: 'pending'; ticket: Ticket; steps: StepRunReport };

export interface RunJobDeps {
  store: TicketStore;
  steps: StepRunnerDeps;
  mintRequestId?: () => string;
  now?: () => Date;
}

function requireTicket(store: TicketStore, requestId: string): Ticket {
  const ticket = store.tickets().find((t) => t.requestId === requestId);
  if (!ticket) throw new Error(`The job ticket ${requestId} vanished from the store.`);
  return ticket;
}

/** Run the due steps of a finished call that never became a job: no claim, since no other observer can see it. */
async function runUnspooledSteps(
  store: TicketStore,
  ticket: Ticket,
  job: ObservedJob,
  deps: RunJobDeps
): Promise<StepRunReport> {
  const report = emptyStepReport();
  const resolve = deps.steps.resolve ?? resolveStepHandler;
  for (const step of dueSteps(ticket, job.state, job.markers)) {
    try {
      const handler = await resolve(step.name);
      await handler({
        jobId: '',
        machine: ticket.machine ?? '',
        params: step.params ?? {},
        state: job.state,
        output: job.output,
        finishedAt: job.finishedAt,
        ...(job.exitCode === undefined ? {} : { exitCode: job.exitCode }),
        ...(job.markers === undefined ? {} : { markers: job.markers }),
      });
      store.append('step-done', ticket.requestId, { step: step.name });
      report.ran.push(step.name);
    } catch (error) {
      deps.steps.warn(errorText(error));
      report.failed.push(step.name);
    }
  }
  return report;
}

export async function runJob<R>(
  call: JobCall<R>,
  steps: PlannedStep[],
  deps: RunJobDeps
): Promise<RunJobResult<R>> {
  const { store } = deps;
  const requestId = (deps.mintRequestId ?? randomUUID)();
  const startedAt = (deps.now ?? (() => new Date()))().toISOString();

  store.append('starting', requestId, {
    verb: call.verb,
    function: call.function,
    machine: call.machine,
    repo: call.repo,
    via: call.via ?? { kind: 'ssh' },
    startedAt,
    steps: toTicketSteps(steps),
  });

  const outcome = await call.start({ requestId, steps: toSpoolSteps(steps) });
  if (outcome.jobId) {
    store.append('started', requestId, {
      jobId: outcome.jobId,
      lastSeenLine: outcome.lastSeenLine,
    });
  }

  if (outcome.kind === 'pending') {
    let report = emptyStepReport();
    if (outcome.job) {
      // A marker seen inside the window fires its step now; the terminal steps wait for whoever sees the end.
      report = await runTicketSteps(
        store,
        requireTicket(store, requestId),
        outcome.job,
        deps.steps
      );
    }
    return { kind: 'pending', ticket: requireTicket(store, requestId), steps: report };
  }

  store.append('finished', requestId, {
    state: outcome.job.state,
    exitCode: outcome.job.exitCode,
    finishedAt: outcome.job.finishedAt,
  });
  const finishedTicket = requireTicket(store, requestId);
  // A call that ran outside a job (a section 24 exemption) has no spool to claim against and no other observer: its steps run here, once.
  const report = outcome.jobId
    ? await runTicketSteps(store, finishedTicket, outcome.job, deps.steps)
    : await runUnspooledSteps(store, finishedTicket, outcome.job, deps);
  // The command reports its own result, so the notice has nothing to announce; a step another observer still holds keeps the ticket visible.
  if (outstandingSteps(report).length === 0) store.append('acknowledged', requestId);
  return {
    kind: 'finished',
    result: outcome.result,
    jobId: outcome.jobId,
    ticket: requireTicket(store, requestId),
    steps: report,
  };
}

// --- the live claim ----------------------------------------------------------

/** The claim command. Step names are validated by the registry pattern before they reach a shell. */
export function buildJobClaimCommand(params: {
  remoteRenetPath: string;
  jobId: string;
  steps: string[];
  done?: boolean;
  origin: ConfigIdentity;
  host: string;
  pid: number;
}): string {
  for (const name of params.steps) {
    if (!/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(name)) throw new Error(`Invalid step name: ${name}`);
  }
  const origin = JSON.stringify({
    client: 'rdc',
    ...(params.origin.configName || params.origin.configId
      ? {
          config: {
            ...(params.origin.configName ? { name: params.origin.configName } : {}),
            ...(params.origin.configId ? { id: params.origin.configId } : {}),
          },
        }
      : {}),
  });
  return [
    'sudo',
    shellQuote(params.remoteRenetPath),
    'job claim',
    `--id ${assertJobId(params.jobId)}`,
    `--steps ${params.steps.join(',')}`,
    params.done ? '--done' : '',
    `--origin ${shellQuote(origin)}`,
    `--host ${shellQuote(params.host)}`,
    `--pid ${Math.trunc(params.pid)}`,
  ]
    .filter(Boolean)
    .join(' ');
}

/** Parse `renet job claim` JSON: `{ job_id, steps: [{ name, result }] }`. */
export function parseClaimOutput(stdout: string): ClaimAnswer[] {
  const start = stdout.indexOf('{');
  const parsed = JSON.parse(start >= 0 ? stdout.slice(start) : stdout) as {
    steps?: { name?: unknown; result?: unknown }[];
  };
  const kinds: ClaimResultKind[] = ['claimed', 'reclaimed', 'already-claimed', 'done'];
  return (parsed.steps ?? [])
    .filter(
      (s): s is { name: string; result: ClaimResultKind } =>
        typeof s.name === 'string' && kinds.includes(s.result as ClaimResultKind)
    )
    .map((s) => ({ name: s.name, result: s.result }));
}

/** The real claim: one SSH exec of `renet job claim` per call, on a pooled connection. */
export function liveClaimExec(observer: ConfigIdentity): ClaimExec {
  return async (request) => {
    const { connectForJobs } = await import('../executor/job-remote.js');
    const conn = await connectForJobs(request.machine, 'read-only');
    try {
      const sftp = await conn.lease.ensure();
      const command = buildJobClaimCommand({
        remoteRenetPath: conn.remoteRenetPath,
        jobId: request.jobId,
        steps: request.steps,
        done: request.done,
        origin: observer,
        host: hostname(),
        pid: process.pid,
      });
      let stdout = '';
      let stderr = '';
      const exitCode = await sftp.execStreaming(command, {
        onStdout: (data) => {
          stdout += data.toString();
        },
        onStderr: (data) => {
          stderr += data.toString();
        },
      });
      if (exitCode !== 0) {
        const detail = (stderr || stdout).trim().split('\n')[0] ?? '';
        throw new Error(
          `Failed to claim steps ${request.steps.join(',')} of job ${request.jobId}: ${detail || `renet exited ${exitCode}`}`
        );
      }
      return parseClaimOutput(stdout);
    } finally {
      conn.lease.release();
    }
  };
}

/** The live step-runner deps for this process's config. */
export async function liveStepRunnerDeps(store: TicketStore): Promise<StepRunnerDeps> {
  const [{ configService }, { writeStderr }] = await Promise.all([
    import('../config/config-resources.js'),
    import('../core/request-context.js'),
  ]);
  let configId: string | undefined;
  try {
    configId = (await configService.getCurrent())?.id;
  } catch {
    configId = undefined;
  }
  const observer: ConfigIdentity = { configName: store.config, configId };
  return {
    claim: liveClaimExec(observer),
    observer,
    warn: (line) => writeStderr(`${line}\n`),
  };
}
