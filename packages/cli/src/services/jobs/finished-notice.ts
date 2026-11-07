/**
 * The finished-while-away notice (Design 8).
 *
 * preAction starts a bounded check of this config's pending tickets: at most
 * NOTICE_MAX_TICKETS, in parallel, inside NOTICE_BUDGET_MS, one status read
 * each, and only tickets not checked in the last NOTICE_THROTTLE_MS. postAction
 * prints one stderr line per ticket that finished and acknowledges it, so each
 * ticket is announced once (a ticket still owing a step is marked announced and
 * gets only the pending line afterwards). With no tickets the check makes no machine call.
 *
 * Steps (section 18): in an interactive text run the notice runs the steps a
 * finished ticket owes, for up to NOTICE_STEPS_BUDGET_MS after the command's
 * own output. Under `-o json`, `-q` or MCP (which runs `rdc` with both) it
 * runs nothing and makes no machine call: it prints `steps pending: rdc job
 * wait <id>` on stderr for each finished ticket that still owes a step. A
 * ticket that owes a step stays unacknowledged, so `rdc job list` keeps
 * showing it until the steps ran.
 */

import { t } from '../../i18n/index.js';
import { getEffectiveConfigName } from '../config/config-name.js';
import { writeStderr } from '../core/request-context.js';
import { formatAge } from './duration.js';
import {
  abandonedLine,
  liveStepRunnerDeps,
  runTicketSteps,
  type StepRunnerDeps,
} from './run-job.js';
import { pendingStepNames } from './steps.js';
import {
  type ExpiredReason,
  isTerminalTicketState,
  type Ticket,
  TicketStore,
} from './ticket-store.js';

export const NOTICE_MAX_TICKETS = 5;
const NOTICE_BUDGET_MS = 2_000;
const NOTICE_THROTTLE_MS = 60_000;
/** How long the notice may spend starting steps after the command's own output. */
const NOTICE_STEPS_BUDGET_MS = 20_000;

/** A ticket still `starting` after this long is resolved through `job list --request-id`. */
const STARTING_CHECK_AFTER_MS = 10 * 60_000;
/** A ticket that owes something for this long is given up on: nothing resolved it in a week. */
export const TICKET_EXPIRE_AFTER_MS = 7 * 24 * 3_600_000;

/** What one status read learned about a ticket. */
export interface TicketObservation {
  state: Ticket['state'];
  exitCode?: number;
  finishedAt?: string;
  lastSeenLine?: number;
}

export interface NoticeDeps {
  store: TicketStore;
  /** Read one ticket's status: an SSH exec, or one proxy poll with maxLines=0. Undefined = could not tell. */
  observe(ticket: Ticket): Promise<TicketObservation | undefined>;
  /** stderr only. */
  write(line: string): void;
  now?: () => number;
  /** The step runner; built live only when a finished ticket owes a step. */
  steps?: StepRunnerDeps;
  /**
   * Resolve a ticket stuck at `starting` through `renet job list --request-id`: the job id,
   * null when renet answered that no job has that request id, undefined when it could not be asked.
   */
  resolveStarting?(ticket: Ticket): Promise<string | null | undefined>;
  /** Whether this is an interactive run (steps run only then). Defaults to stderr being a TTY. */
  interactive?: boolean;
  /** Whether a ticket's repository is still in the config: false drops the ticket, undefined (could not tell) keeps it. Absent, nothing is dropped. */
  repoExists?(repo: string): Promise<boolean | undefined>;
}

/**
 * - `full`: an ordinary text run. Check the tickets, announce, run owed steps.
 * - `pending-only`: `-o json` or `-q` (MCP runs both). No machine call, no step; print the pending line.
 * - `off`: `rdc job *` (which shows tickets itself) and a command served for an executor request.
 */
export type NoticeMode = 'full' | 'pending-only' | 'off';

interface NoticeParams {
  commandPath: string;
  quiet: boolean;
  format: string;
  inExecutorRequest: boolean;
}

export function noticeMode(params: NoticeParams): NoticeMode {
  if (params.inExecutorRequest) return 'off';
  if (params.commandPath === 'job' || params.commandPath.startsWith('job ')) return 'off';
  if (params.quiet || params.format === 'json') return 'pending-only';
  return 'full';
}

let recordedMode: NoticeMode = 'off';

/**
 * Whether the full notice (the machine check) should start for this invocation.
 * It also records the invocation's mode, so `finishNotice` prints the pending
 * line for a `pending-only` run that never started a check.
 */
export function shouldRunNotice(params: NoticeParams): boolean {
  recordedMode = noticeMode(params);
  return recordedMode === 'full';
}

function ageMs(ticket: Ticket, now: number): number | undefined {
  const from = Date.parse(ticket.finishedAt ?? ticket.startedAt ?? '');
  return Number.isNaN(from) ? undefined : now - from;
}

function startingTooLong(ticket: Ticket, now: number): boolean {
  return ticket.state === 'starting' && (ageMs(ticket, now) ?? 0) >= STARTING_CHECK_AFTER_MS;
}

function dueForCheck(ticket: Ticket, now: number): boolean {
  if (isTerminalTicketState(ticket.state)) return false;
  if (ticket.state === 'starting' && !startingTooLong(ticket, now)) return false;
  if (!ticket.jobId && ticket.state !== 'starting') return false;
  const last = ticket.lastCheckedAt ? Date.parse(ticket.lastCheckedAt) : 0;
  return now - last >= NOTICE_THROTTLE_MS;
}

function expire(
  deps: Pick<NoticeDeps, 'store' | 'write'>,
  ticket: Ticket,
  reason: ExpiredReason
): void {
  deps.store.append('expired', ticket.requestId, { reason });
  deps.write(abandonedLine(ticket.jobId ?? ticket.requestId, reason));
}

/** Resolve a ticket whose start was never confirmed. */
async function resolveStartingTicket(deps: NoticeDeps, ticket: Ticket, now: number): Promise<void> {
  const answer = await deps.resolveStarting?.(ticket).catch(() => undefined);
  if (typeof answer === 'string') {
    deps.store.append('started', ticket.requestId, { jobId: answer });
  } else if (answer === null) {
    expire(deps, ticket, 'never-started');
  } else if ((ageMs(ticket, now) ?? 0) >= TICKET_EXPIRE_AFTER_MS) {
    expire(deps, ticket, 'age');
  } else {
    // Could not tell: note the attempt so the next command does not retry within the throttle.
    deps.store.append('seen', ticket.requestId);
  }
}

/** The preAction half. Never rejects: a notice must not break the command it rides on. */
export async function checkPendingTickets(deps: NoticeDeps): Promise<void> {
  try {
    const now = (deps.now ?? Date.now)();
    const due = deps.store
      .pending()
      .filter((ticket) => dueForCheck(ticket, now))
      .slice(0, NOTICE_MAX_TICKETS);
    if (due.length === 0) return;

    const checks = due.map(async (ticket) => {
      if (!ticket.jobId) {
        await resolveStartingTicket(deps, ticket, now);
        return;
      }
      const seen = await deps.observe(ticket).catch(() => undefined);
      if (!seen) return;
      if (isTerminalTicketState(seen.state)) {
        deps.store.append('finished', ticket.requestId, { ...seen });
      } else {
        deps.store.append('seen', ticket.requestId, {
          state: seen.state,
          lastSeenLine: seen.lastSeenLine,
        });
      }
    });

    let timer: NodeJS.Timeout | undefined;
    const budget = new Promise<void>((resolve) => {
      timer = setTimeout(resolve, NOTICE_BUDGET_MS);
      timer.unref();
    });
    await Promise.race([Promise.all(checks), budget]);
    if (timer) clearTimeout(timer);
  } catch {
    // swallowed on purpose
  }
}

/**
 * Give up on finished tickets that owe something for over a week. No machine call, so it runs in
 * `pending-only` mode too. Never rejects.
 */
function expireOldTickets(deps: Pick<NoticeDeps, 'store' | 'write' | 'now'>): void {
  try {
    const now = (deps.now ?? Date.now)();
    for (const ticket of deps.store.pending()) {
      if (!(ticket.jobId && isTerminalTicketState(ticket.state))) continue;
      if ((ageMs(ticket, now) ?? 0) >= TICKET_EXPIRE_AFTER_MS) expire(deps, ticket, 'age');
    }
  } catch {
    // swallowed on purpose
  }
}

function finishedTickets(store: TicketStore): Ticket[] {
  return store
    .pending()
    .filter((ticket) => ticket.jobId && isTerminalTicketState(ticket.state))
    .slice(0, NOTICE_MAX_TICKETS);
}

function pendingLine(ticket: Ticket): string {
  return t('commands.job.steps.pending', { jobId: ticket.jobId ?? ticket.requestId });
}

/**
 * The postAction half: print once per newly finished ticket, then acknowledge
 * it. A ticket that still owes a step is not acknowledged: it gets the pending
 * line, and the next run (or `rdc job wait`) picks it up.
 */
export function printFinishedNotices(deps: Pick<NoticeDeps, 'store' | 'write' | 'now'>): void {
  try {
    const now = (deps.now ?? Date.now)();
    for (const ticket of finishedTickets(deps.store)) {
      if (!ticket.announced) deps.write(formatNotice(ticket, now));
      if (pendingStepNames(ticket).length > 0) {
        deps.write(pendingLine(ticket));
        if (!ticket.announced) deps.store.append('announced', ticket.requestId);
        continue;
      }
      deps.store.append('acknowledged', ticket.requestId);
    }
    deps.store.compactIfNeeded();
  } catch {
    // swallowed on purpose
  }
}

/**
 * Acknowledge the finished tickets whose repository left the config. Their steps have nothing left to act on, since each one works on the repository's config entry (settleRepoDelete refuses outright without one), so the ticket used to print `steps pending: rdc job wait <id>` on every later command forever (a deleted fork on bench, 2026-11-05). Never rejects.
 */
async function dropOrphanedTickets(deps: Pick<NoticeDeps, 'store' | 'repoExists'>): Promise<void> {
  const repoExists = deps.repoExists;
  if (!repoExists) return;
  try {
    const owing = deps.store
      .pending()
      .filter(
        (tk) => tk.repo && isTerminalTicketState(tk.state) && pendingStepNames(tk).length > 0
      );
    for (const ticket of owing) {
      const exists = await repoExists(ticket.repo as string).catch(() => undefined);
      if (exists === false) deps.store.append('acknowledged', ticket.requestId);
    }
  } catch {
    // swallowed on purpose
  }
}

/** The live repository check: a config that cannot be read answers undefined, so nothing is dropped on a guess. */
export async function liveRepoExists(repo: string): Promise<boolean | undefined> {
  try {
    const { configService } = await import('../config/config-resources.js');
    if (!(await configService.getCurrent())) return undefined;
    return (await configService.getRepository(repo)) !== undefined;
  } catch {
    return undefined;
  }
}

/** The `pending-only` half: no machine call and no step, only the pending line on stderr. */
function printPendingSteps(deps: Pick<NoticeDeps, 'store' | 'write'>): void {
  try {
    for (const ticket of finishedTickets(deps.store)) {
      if (pendingStepNames(ticket).length > 0) deps.write(pendingLine(ticket));
    }
  } catch {
    // swallowed on purpose
  }
}

/**
 * Run the steps finished tickets owe, starting none after the budget. A step
 * already started runs to its end. Never rejects.
 */
export async function runNoticeSteps(
  deps: NoticeDeps,
  budgetMs: number = NOTICE_STEPS_BUDGET_MS
): Promise<void> {
  try {
    const now = deps.now ?? Date.now;
    const owing = finishedTickets(deps.store).filter((tk) => pendingStepNames(tk).length > 0);
    if (owing.length === 0) return;
    const deadline = now() + budgetMs;
    const stepDeps = deps.steps ?? (await liveStepRunnerDeps(deps.store));
    for (const ticket of owing) {
      const report = await runTicketSteps(
        deps.store,
        ticket,
        { state: ticket.state, exitCode: ticket.exitCode, finishedAt: ticket.finishedAt },
        { ...stepDeps, now },
        { deadline }
      );
      if (report.gated.length > 0) {
        deps.write(
          t('commands.job.steps.pendingForConfig', {
            count: report.gated.length,
            config: ticket.config ?? '-',
          })
        );
      }
    }
  } catch {
    // swallowed on purpose
  }
}

function formatNotice(ticket: Ticket, now: number): string {
  const target = ticket.repo ? `${ticket.repo}@${ticket.machine}` : (ticket.machine ?? '-');
  const what = [ticket.verb ?? ticket.function ?? '-', target].join(' ');
  const params = {
    jobId: ticket.jobId,
    what,
    age: formatAge(ticket.finishedAt ?? ticket.lastCheckedAt, now),
    exitCode: ticket.exitCode ?? 1,
  };
  if (ticket.state === 'succeeded') return t('commands.job.notice.succeeded', params);
  if (ticket.state === 'cancelled') return t('commands.job.notice.cancelled', params);
  return t('commands.job.notice.failed', params);
}

// --- the cli.ts seam ---------------------------------------------------------

let active: { deps: NoticeDeps; check: Promise<void> } | undefined;

/** preAction: start the check without awaiting it. */
export function startNoticeCheck(deps: NoticeDeps): void {
  active = { deps, check: checkPendingTickets(deps) };
}

type PendingDeps = Pick<NoticeDeps, 'store' | 'write' | 'repoExists' | 'now'>;

function livePendingDeps(): PendingDeps {
  return {
    store: new TicketStore(getEffectiveConfigName()),
    write: (line) => writeStderr(`${line}\n`),
    repoExists: liveRepoExists,
  };
}

/**
 * postAction: let the check land, run owed steps in an interactive run, then
 * print. With no check started, a `pending-only` run prints the pending lines
 * from the store alone; any other run does nothing.
 */
export async function finishNotice(
  pendingDeps: () => PendingDeps = livePendingDeps
): Promise<void> {
  const current = active;
  const mode = recordedMode;
  active = undefined;
  recordedMode = 'off';
  if (!current) {
    if (mode !== 'pending-only') return;
    try {
      const deps = pendingDeps();
      await dropOrphanedTickets(deps);
      expireOldTickets(deps);
      printPendingSteps(deps);
    } catch {
      // a config name the store rejects never breaks the command
    }
    return;
  }
  await current.check;
  await dropOrphanedTickets(current.deps);
  expireOldTickets(current.deps);
  if (current.deps.interactive ?? Boolean(process.stderr.isTTY)) {
    await runNoticeSteps(current.deps);
  }
  printFinishedNotices(current.deps);
}
