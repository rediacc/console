/**
 * The real, SSH-backed dependencies of `job wait` and the finished notice.
 * `job wait` follows a proxy ticket (`-b` through `--proxy`) with short polls
 * through `followProxy`; the notice cannot observe a proxy ticket yet.
 */

import { CLI_CONTRACT_VERSION } from '@rediacc/shared/cli-contract';
import { shellQuote } from '../../utils/shell-quote.js';
import { getSubscriptionTokenState } from '../account/subscription-auth.js';
import { getEffectiveConfigName } from '../config/config-name.js';
import { writeStderr } from '../core/request-context.js';
import { JobLogCursor, type JobStatus, parseJobList } from '../executor/job-client.js';
import {
  connectForJobs,
  followJobLogs,
  type JobConnection,
  readJobStatus,
  replayJobLogs,
  runJobCommand,
} from '../executor/job-remote.js';
import { ProxyClient } from '../executor/proxy-client.js';
import type { RenetEvent } from '../executor/types.js';
import { liveRepoExists, type NoticeDeps, type TicketObservation } from './finished-notice.js';
import type { JobWaitDeps } from './job-wait.js';
import { type Ticket, TicketStore } from './ticket-store.js';

export function openTicketStore(): TicketStore {
  return new TicketStore(getEffectiveConfigName());
}

async function withConnection<T>(
  machine: string,
  fn: (conn: JobConnection) => Promise<T>
): Promise<T> {
  const conn = await connectForJobs(machine, 'read-only');
  try {
    return await fn(conn);
  } finally {
    conn.lease.release();
  }
}

/** The proxy client a ticket's `via.url` names, signed in with this device's account login. */
function proxyClientFor(url: string): ProxyClient {
  return new ProxyClient({
    baseUrl: url,
    contractVersion: CLI_CONTRACT_VERSION,
    getToken: () => {
      const state = getSubscriptionTokenState();
      if (state.kind !== 'ready') {
        return Promise.reject(
          new Error(
            'Following a proxied job needs an account login. Run "rdc subscription login" first.'
          )
        );
      }
      return Promise.resolve(state.token.token);
    },
  });
}

/** Follow a proxy ticket by polls and give the terminal state in renet's status shape. */
export async function followProxyTicket(
  ticket: Ticket,
  signal: AbortSignal,
  onEvent: (event: RenetEvent, line?: number) => void,
  clientFor: (url: string) => Pick<ProxyClient, 'followJob'> = proxyClientFor
): Promise<JobStatus | undefined> {
  if (!(ticket.via?.url && ticket.machine && ticket.jobId)) return undefined;
  const status = await clientFor(ticket.via.url).followJob(
    ticket.machine,
    ticket.jobId,
    ticket.lastSeenLine,
    onEvent,
    signal
  );
  if (!status) return undefined;
  return {
    job_id: ticket.jobId,
    function: status.function,
    state: status.state,
    exit_code: status.exitCode ?? null,
    started_at: status.startedAt ?? '',
    ...(status.finishedAt ? { finished_at: status.finishedAt } : {}),
  };
}

/**
 * Ask the ticket's machine which job (if any) carries its request id, through
 * `renet job list --request-id`: the job id, null when renet answered with no
 * job, undefined when the machine could not be asked (unreachable, an older
 * renet without the flag, a proxy ticket).
 */
async function resolveStartingTicket(ticket: Ticket): Promise<string | null | undefined> {
  if (ticket.via?.kind === 'proxy' || !ticket.machine) return undefined;
  try {
    return await withConnection(ticket.machine, async (conn) => {
      const stdout = await runJobCommand(
        conn,
        `sudo ${shellQuote(conn.remoteRenetPath)} job list --request-id ${shellQuote(ticket.requestId)} --json`,
        'resolve a starting job'
      );
      const found = parseJobList(stdout);
      return found.length === 0 ? null : found[0].job_id;
    });
  } catch {
    return undefined;
  }
}

export function sshWaitDeps(onEvent?: (event: RenetEvent, line?: number) => void): JobWaitDeps {
  return {
    ...(onEvent
      ? {
          followProxy: (ticket: Ticket, signal: AbortSignal) =>
            followProxyTicket(ticket, signal, onEvent),
        }
      : {}),
    resolveStarting: resolveStartingTicket,
    withConnection: (machine, fn) => withConnection(machine, (conn) => fn(conn)),
    follow: (
      conn,
      jobId,
      cursor: JobLogCursor,
      onEvent: (e: RenetEvent, line?: number) => void,
      signal
    ) => {
      const c = conn as JobConnection;
      return followJobLogs(
        c.lease,
        c.remoteRenetPath,
        jobId,
        { onEvent, signal },
        cursor,
        c.machineName
      );
    },
    readStatus: (conn, jobId, machine) => {
      const c = conn as JobConnection;
      return readJobStatus(c.lease.sftp, c.remoteRenetPath, jobId, machine);
    },
    replay: (conn, jobId, onEvent) =>
      replayJobLogs(conn as JobConnection, jobId, { onEvent }, new JobLogCursor(0)),
  };
}

export function liveNoticeDeps(): NoticeDeps {
  return {
    store: openTicketStore(),
    write: (line) => writeStderr(`${line}\n`),
    repoExists: liveRepoExists,
    resolveStarting: resolveStartingTicket,
    observe: (ticket): Promise<TicketObservation | undefined> => {
      if (ticket.via?.kind === 'proxy' || !ticket.machine || !ticket.jobId) {
        return Promise.resolve(undefined);
      }
      const jobId = ticket.jobId;
      const machine = ticket.machine;
      return withConnection(machine, async (conn) => {
        const status = await readJobStatus(conn.lease.sftp, conn.remoteRenetPath, jobId, machine);
        return {
          state: status.state,
          exitCode: status.exit_code ?? undefined,
          finishedAt: status.finished_at,
        };
      });
    },
  };
}
