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
import { liveStepRunnerDeps, runTicketSteps, type StepRunnerDeps } from './run-job.js';
import { pendingStepNames } from './steps.js';
import { isTerminalTicketState, type Ticket, TicketStore } from './ticket-store.js';

export const NOTICE_MAX_TICKETS = 5;
export const NOTICE_BUDGET_MS = 2_000;
export const NOTICE_THROTTLE_MS = 60_000;
/** How long the notice may spend starting steps after the command's own output. */
export const NOTICE_STEPS_BUDGET_MS = 20_000;

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
  /** Whether this is an interactive run (steps run only then). Defaults to stderr being a TTY. */
  interactive?: boolean;
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

function dueForCheck(ticket: Ticket, now: number): boolean {
  if (!ticket.jobId || isTerminalTicketState(ticket.state) || ticket.state === 'starting') {
    return false;
  }
  const last = ticket.lastCheckedAt ? Date.parse(ticket.lastCheckedAt) : 0;
  return now - last >= NOTICE_THROTTLE_MS;
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
      const seen = await deps.observe(ticket).catch(() => undefined);
      if (!seen || !ticket.jobId) return;
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

/** The `pending-only` half: no machine call and no step, only the pending line on stderr. */
export function printPendingSteps(deps: Pick<NoticeDeps, 'store' | 'write'>): void {
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

export function formatNotice(ticket: Ticket, now: number): string {
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

function livePendingDeps(): Pick<NoticeDeps, 'store' | 'write'> {
  return {
    store: new TicketStore(getEffectiveConfigName()),
    write: (line) => writeStderr(`${line}\n`),
  };
}

/**
 * postAction: let the check land, run owed steps in an interactive run, then
 * print. With no check started, a `pending-only` run prints the pending lines
 * from the store alone; any other run does nothing.
 */
export async function finishNotice(
  pendingDeps: () => Pick<NoticeDeps, 'store' | 'write'> = livePendingDeps
): Promise<void> {
  const current = active;
  const mode = recordedMode;
  active = undefined;
  recordedMode = 'off';
  if (!current) {
    if (mode !== 'pending-only') return;
    try {
      printPendingSteps(pendingDeps());
    } catch {
      // a config name the store rejects never breaks the command
    }
    return;
  }
  await current.check;
  if (current.deps.interactive ?? Boolean(process.stderr.isTTY)) {
    await runNoticeSteps(current.deps);
  }
  printFinishedNotices(current.deps);
}
