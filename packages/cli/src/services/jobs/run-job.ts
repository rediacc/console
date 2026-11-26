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
import { t } from '../../i18n/index.js';
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
import type {
  ExpiredReason,
  Ticket,
  TicketState,
  TicketStep,
  TicketStore,
  TicketVia,
} from './ticket-store.js';

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

interface ClaimRequest {
  machine: string;
  jobId: string;
  steps: string[];
  /** Record the steps as done instead of claiming them. */
  done?: boolean;
}

/** `renet job claim` exits with this when the job is not in the spool: the steps it owes can never run. */
export const JOB_NOT_FOUND_EXIT = 16;

/** Each expiry reason's text, spelled as literal keys so the orphan check sees every one of them. */
const REASON_TEXT: Record<ExpiredReason, () => string> = {
  gone: () => t('commands.job.steps.reason.gone'),
  'never-started': () => t('commands.job.steps.reason.never-started'),
  age: () => t('commands.job.steps.reason.age'),
  dismissed: () => t('commands.job.steps.reason.dismissed'),
};

/** The one line printed when a ticket is given up on: `job X: steps abandoned (reason)`. */
export function abandonedLine(jobId: string, reason: ExpiredReason): string {
  return t('commands.job.steps.abandoned', { jobId, reason: REASON_TEXT[reason]() });
}

/** The claim reached the machine and the job is gone from it. */
export class JobGoneError extends Error {
  constructor(jobId: string) {
    super(`Job ${jobId} is gone from the machine`);
    this.name = 'JobGoneError';
  }
}

/** `renet job claim --id <jobId> --steps a,b [--done]`, run on the job's machine. */
export type ClaimExec = (request: ClaimRequest) => Promise<ClaimAnswer[]>;

export interface StepRunnerDeps {
  claim: ClaimExec;
  /** The observing config. */
  observer: ConfigIdentity;
  /** stderr only. */
  warn(line: string): void;
  /**
   * Keep the machine's pooled SSH session open until the returned release is called, so claims and the job's own
   * session share one connection instead of each reopening it (about 3 s apiece). Optional: without it each claim
   * connects on its own. A hold never replaces a claim.
   */
  hold?: (machine: string) => Promise<() => void>;
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
  /**
   * Wall time of the work done here, in run order: `claim` for each claim exec, then each step that ran (its handler
   * and its machine-side done marker), so a command can account for the time its steps took.
   */
  timings?: StepTiming[];
}

/** One timed piece of step work: a step's name, or `claim` for a claim exec. */
interface StepTiming {
  name: string;
  duration_ms: number;
  startedAtMs: number;
}

/** The name a claim exec is timed under in {@link StepRunReport.timings}. */
export const CLAIM_TIMING = 'claim';

export function emptyStepReport(): StepRunReport {
  return {
    ran: [],
    doneElsewhere: [],
    heldElsewhere: [],
    failed: [],
    gated: [],
    deferred: [],
    timings: [],
  };
}

/** Run `fn`, recording its wall time under `name` in the report, even when it throws. */
async function timed<T>(report: StepRunReport, name: string, fn: () => Promise<T>): Promise<T> {
  const startedAtMs = Date.now();
  try {
    return await fn();
  } finally {
    (report.timings ??= []).push({ name, duration_ms: Date.now() - startedAtMs, startedAtMs });
  }
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
  let gone = false;
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
      if (gone) return undefined;
      try {
        return await timed(report, CLAIM_TIMING, () =>
          deps.claim({ machine, jobId, steps: names })
        );
      } catch (error) {
        if (error instanceof JobGoneError) {
          // The job left the spool, so no observer can ever claim its steps: close the ticket instead of retrying forever.
          gone = true;
          store.append('expired', ticket.requestId, { reason: 'gone' });
          deps.warn(abandonedLine(jobId, 'gone'));
          return undefined;
        }
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
      const ran = await timed(report, step.name, async () => {
        if (!(await run(step))) return false;
        // The step ran: record it here even if the machine-side done marker fails, since every step is idempotent or keyed by job id and a stale-claim rerun changes nothing.
        try {
          await deps.claim({ machine, jobId, steps: [step.name], done: true });
        } catch (error) {
          deps.warn(errorText(error));
        }
        return true;
      });
      if (!ran) return;
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
  const held = holdSession(deps, ticket.via?.kind === 'proxy' ? undefined : machine);
  try {
    if (options.deadline === undefined) await settleAll(session, due);
    else await settleWithin(session, due, options.deadline, deps.now ?? Date.now, report);
  } finally {
    (await held)();
  }
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
interface JobStartRequest {
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
      await timed(report, step.name, () =>
        handler({
          jobId: '',
          machine: ticket.machine ?? '',
          params: step.params ?? {},
          state: job.state,
          output: job.output,
          finishedAt: job.finishedAt,
          ...(job.exitCode === undefined ? {} : { exitCode: job.exitCode }),
          ...(job.markers === undefined ? {} : { markers: job.markers }),
        })
      );
      store.append('step-done', ticket.requestId, { step: step.name });
      report.ran.push(step.name);
    } catch (error) {
      deps.steps.warn(errorText(error));
      report.failed.push(step.name);
    }
  }
  return report;
}

/**
 * A retried start attaches to the job the first start made and renet keeps that start's params and steps, so the ticket
 * keeps its plan too: the retry's own may carry ids minted afresh (a commit guid). A start that was refused made no
 * job, so the retry's plan stands.
 */
function keepsFirstPlan(store: TicketStore, requestId: string): boolean {
  const prior = store.tickets().find((t) => t.requestId === requestId);
  return prior !== undefined && (prior.jobId !== undefined || !prior.acknowledged);
}

const NO_RELEASE = (): void => undefined;

/**
 * Start holding the machine's pooled session. Not awaited by the caller, so the connect overlaps the call's own and
 * shares its pool entry. A failed hold is no hold: the call and each claim connect and report for themselves.
 */
function holdSession(deps: StepRunnerDeps, machine: string | undefined): Promise<() => void> {
  if (!(deps.hold && machine)) return Promise.resolve(NO_RELEASE);
  return deps.hold(machine).catch(() => NO_RELEASE);
}

/**
 * Run a job and its due steps. The machine's SSH session is held from before the start until the steps are settled,
 * so the claims that follow a finished job reuse it. Only an SSH-reached job holds one: a proxied job's machine is
 * not ours to connect to.
 */
export async function runJob<R>(
  call: JobCall<R>,
  steps: PlannedStep[],
  deps: RunJobDeps
): Promise<RunJobResult<R>> {
  const held = holdSession(deps.steps, call.via?.kind === 'proxy' ? undefined : call.machine);
  try {
    return await runJobHeld(call, steps, deps);
  } finally {
    (await held)();
  }
}

async function runJobHeld<R>(
  call: JobCall<R>,
  steps: PlannedStep[],
  deps: RunJobDeps
): Promise<RunJobResult<R>> {
  const { store } = deps;
  const requestId = (deps.mintRequestId ?? randomUUID)();
  const startedAt = (deps.now ?? (() => new Date()))().toISOString();

  const plan = keepsFirstPlan(store, requestId) ? {} : { steps: toTicketSteps(steps) };

  store.append('starting', requestId, {
    verb: call.verb,
    function: call.function,
    machine: call.machine,
    repo: call.repo,
    via: call.via ?? { kind: 'ssh' },
    startedAt,
    ...plan,
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
