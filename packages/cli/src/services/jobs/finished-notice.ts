/**
 * The finished-while-away notice (Design 8).
 *
 * preAction starts a bounded check of this config's pending tickets: at most
 * NOTICE_MAX_TICKETS, in parallel, inside NOTICE_BUDGET_MS, one status read
 * each, and only tickets not checked in the last NOTICE_THROTTLE_MS. postAction
 * prints one stderr line per ticket that finished and acknowledges it, so each
 * ticket is announced once. With no tickets the check makes no machine call.
 */

import { t } from '../../i18n/index.js';
import { formatAge } from './duration.js';
import { isTerminalTicketState, type Ticket, type TicketStore } from './ticket-store.js';

export const NOTICE_MAX_TICKETS = 5;
export const NOTICE_BUDGET_MS = 2_000;
export const NOTICE_THROTTLE_MS = 60_000;

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
}

/** Whether the notice should run for this invocation. */
export function shouldRunNotice(params: {
  commandPath: string;
  quiet: boolean;
  format: string;
  inExecutorRequest: boolean;
}): boolean {
  if (params.quiet || params.format === 'json' || params.inExecutorRequest) return false;
  return params.commandPath !== 'job' && !params.commandPath.startsWith('job ');
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

/** The postAction half: print once per newly finished ticket, then acknowledge it. */
export function printFinishedNotices(deps: Pick<NoticeDeps, 'store' | 'write' | 'now'>): void {
  try {
    const now = (deps.now ?? Date.now)();
    const finished = deps.store
      .pending()
      .filter((ticket) => ticket.jobId && isTerminalTicketState(ticket.state))
      .slice(0, NOTICE_MAX_TICKETS);
    for (const ticket of finished) {
      deps.write(formatNotice(ticket, now));
      deps.store.append('acknowledged', ticket.requestId);
    }
    deps.store.compactIfNeeded();
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

/** postAction: let the check land, then print. A no-op when no check was started. */
export async function finishNotice(): Promise<void> {
  const current = active;
  active = undefined;
  if (!current) return;
  await current.check;
  printFinishedNotices(current.deps);
}
