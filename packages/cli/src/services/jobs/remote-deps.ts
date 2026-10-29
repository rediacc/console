/**
 * The real, SSH-backed dependencies of `job wait` and the finished notice.
 * The proxy path is J6's seam: neither object supplies `followProxy`, and the
 * notice cannot observe a proxy ticket yet.
 */

import { getEffectiveConfigName } from '../config/config-name.js';
import { writeStderr } from '../core/request-context.js';
import type { JobLogCursor } from '../executor/job-client.js';
import {
  connectForJobs,
  followJobLogs,
  type JobConnection,
  readJobStatus,
} from '../executor/job-remote.js';
import type { RenetEvent } from '../executor/types.js';
import type { NoticeDeps, TicketObservation } from './finished-notice.js';
import type { JobWaitDeps } from './job-wait.js';
import { TicketStore } from './ticket-store.js';

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

export function sshWaitDeps(): JobWaitDeps {
  return {
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
  };
}

export function liveNoticeDeps(): NoticeDeps {
  return {
    store: openTicketStore(),
    write: (line) => writeStderr(`${line}\n`),
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
