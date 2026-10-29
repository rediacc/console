/**
 * `rdc job`, manage detached machine operations.
 *
 * A detached job survives the connection that started it: the work runs under a
 * transient systemd unit on the machine, so a dropped SSH channel, a closed
 * laptop, or a Ctrl-C on the log tail leaves it running. These commands are how
 * an operator gets back to one afterwards.
 *
 * `logs --follow` re-attaches to a running job and renders it through the SAME
 * event path a live command uses, so watching a job you re-attached to looks
 * exactly like watching one you started. That is the payoff of the line-based
 * offsets: the CLI can leave and come back without losing or repeating a line.
 */

import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { outputService } from '../services/core/output.js';
import { setExitCode } from '../services/core/request-context.js';
import {
  formatJobDuration,
  isTerminalState,
  JobLogCursor,
  type JobStatus,
} from '../services/executor/job-client.js';
import {
  cancelJob,
  connectForJobs,
  followJobLogs,
  gcJobs,
  type JobConnection,
  listJobs,
  readJobStatus,
  renderJobEvent,
  replayJobLogs,
} from '../services/executor/job-remote.js';
import { formatAge, parseWaitTimeoutMs } from '../services/jobs/duration.js';
import { type WaitOutcome, waitForJob } from '../services/jobs/job-wait.js';
import { openTicketStore, sshWaitDeps } from '../services/jobs/remote-deps.js';
import type { Ticket } from '../services/jobs/ticket-store.js';
import type { RenetAccess } from '../services/renet/renet-execution.js';
import { EXIT_CODES, type OutputFormat } from '../types/index.js';
import { getOutputFormat, handleError } from '../utils/errors.js';

/** Default GC horizon: one week, matching renet's own default. */
const DEFAULT_GC_HOURS = 168;

interface JobCommandOptions {
  machine?: string;
  timeout?: string;
  id?: string;
  follow?: boolean;
  sinceLine?: string;
  olderThan?: string;
  yes?: boolean;
  debug?: boolean;
}

/** Options once the target machine is known: required for gc, resolved from `-m` or the ticket elsewhere. */
type MachineJobOptions = JobCommandOptions & { machine: string };

/** Run a job command against a machine, always releasing the connection. */
async function withJobConnection<T>(
  machineName: string,
  access: RenetAccess,
  fn: (conn: JobConnection) => Promise<T>
): Promise<T> {
  const conn = await connectForJobs(machineName, access);
  try {
    return await fn(conn);
  } finally {
    conn.lease.release();
  }
}

/**
 * The machine and job id a command acts on: `-m` wins, otherwise the local ticket
 * for that id supplies the machine. With neither the command cannot know whose
 * spool to read, and says so.
 */
function resolveJobTarget(
  jobId: string,
  machineOption: string | undefined
): { machine: string; jobId: string } {
  const ticket = openTicketStore().find(jobId);
  const machine = machineOption ?? ticket?.machine;
  if (!machine) throw new Error(t('commands.job.machineRequired', { jobId }));
  return { machine, jobId: ticket?.jobId ?? jobId };
}

/** The rows `rdc job list` prints without `-m`: this config's tickets. */
function toTicketRow(ticket: Ticket) {
  return {
    id: ticket.jobId ?? ticket.requestId,
    state: ticket.state,
    verb: ticket.verb ?? ticket.function ?? '-',
    repo: ticket.repo ?? '-',
    machine: ticket.machine ?? '-',
    age: formatAge(ticket.startedAt),
  };
}

/** `rdc job list` without -m: this config's pending and unacknowledged tickets. */
function listTickets(format: OutputFormat): void {
  const store = openTicketStore();
  const tickets = store.pending();
  store.compactIfNeeded();
  if (tickets.length === 0 && format === 'table') {
    outputService.info(t('commands.job.list.emptyTickets'));
    return;
  }
  outputService.print(tickets.map(toTicketRow), format);
}

/** The rows `rdc job list -m` prints. */
function toListRow(status: JobStatus) {
  return {
    id: status.job_id,
    state: status.state,
    function: status.function,
    repo: status.repo_guid ?? '-',
    started: status.started_at,
    duration: formatJobDuration(status),
  };
}

/**
 * Parse `--older-than`. Accepts a Go-ish duration in hours ("168h") or a bare
 * number of hours, because an operator who types `--older-than 24` means 24
 * hours and should not have to discover that the `h` was mandatory.
 */
function parseOlderThanHours(raw: string | undefined): number {
  if (!raw) return DEFAULT_GC_HOURS;

  const match = /^(\d+)\s*h?$/.exec(raw.trim());
  if (!match) {
    throw new Error(t('commands.job.gc.invalidOlderThan', { value: raw }));
  }

  return Number.parseInt(match[1], 10);
}

/** Parse `--since-line`, rejecting anything that is not a line count. */
function parseSinceLine(raw: string | undefined): number {
  if (!raw) return 0;

  const parsed = Number.parseInt(raw, 10);
  if (Number.isNaN(parsed) || parsed < 0) {
    throw new Error(t('commands.job.logs.invalidSinceLine', { value: raw }));
  }

  return parsed;
}

export function registerJobCommands(program: Command): void {
  const job = program
    .command('job')
    .summary(t('commands.job.summary'))
    .description(t('commands.job.description'));

  job
    .command('list')
    .description(t('commands.job.list.description'))
    .option('-m, --machine <name>', t('commands.job.list.machineOption'))
    .action(async (options: JobCommandOptions) => {
      try {
        const format = getOutputFormat();

        if (!options.machine) {
          listTickets(format);
          return;
        }

        const jobs = await withJobConnection(options.machine, 'read-only', listJobs);

        if (jobs.length === 0 && format === 'table') {
          outputService.info(t('commands.job.list.empty', { machine: options.machine }));
          return;
        }

        outputService.print(jobs.map(toListRow), format);
      } catch (error) {
        handleError(error);
      }
    });

  job
    .command('status')
    .description(t('commands.job.status.description'))
    .argument('<job-id>', t('commands.job.idOption'))
    .option('-m, --machine <name>', t('commands.job.ticketMachineOption'))
    .action(async (requested: string, options: JobCommandOptions) => {
      try {
        const { machine, jobId } = resolveJobTarget(requested, options.machine);
        const status = await withJobConnection(machine, 'read-only', (conn) =>
          readJobStatus(conn.lease.sftp, conn.remoteRenetPath, jobId, machine)
        );

        outputService.print(status, getOutputFormat());
      } catch (error) {
        handleError(error);
      }
    });

  job
    .command('logs')
    .description(t('commands.job.logs.description'))
    .argument('<job-id>', t('commands.job.idOption'))
    .option('-m, --machine <name>', t('commands.job.ticketMachineOption'))
    .option('-f, --follow', t('commands.job.logs.followOption'))
    .option('--since-line <n>', t('commands.job.logs.sinceLineOption'))
    .option('--debug', t('options.debug'))
    .action(async (requested: string, options: JobCommandOptions) => {
      try {
        const { machine, jobId } = resolveJobTarget(requested, options.machine);
        await runJobLogs(jobId, { ...options, machine });
      } catch (error) {
        handleError(error);
      }
    });

  job
    .command('cancel')
    .description(t('commands.job.cancel.description'))
    .argument('<job-id>', t('commands.job.idOption'))
    .option('-m, --machine <name>', t('commands.job.ticketMachineOption'))
    .option('-y, --yes', t('options.yes'))
    .action(async (requested: string, options: JobCommandOptions) => {
      try {
        const { machine, jobId } = resolveJobTarget(requested, options.machine);
        await runJobCancel({ ...options, machine, id: jobId }, getOutputFormat());
      } catch (error) {
        handleError(error);
      }
    });

  job
    .command('wait')
    .description(t('commands.job.wait.description'))
    .argument('<job-id>', t('commands.job.idOption'))
    .option('-m, --machine <name>', t('commands.job.ticketMachineOption'))
    .option('--timeout <duration>', t('commands.job.wait.timeoutOption'))
    .action(async (requested: string, options: JobCommandOptions) => {
      try {
        await runJobWait(requested, options);
      } catch (error) {
        handleError(error);
      }
    });

  job
    .command('gc')
    .description(t('commands.job.gc.description'))
    .requiredOption('-m, --machine <name>', t('commands.job.machineOption'))
    .option('--older-than <duration>', t('commands.job.gc.olderThanOption'))
    .option('-y, --yes', t('options.yes'))
    .action(async (options: JobCommandOptions) => {
      try {
        await runJobGc(options as MachineJobOptions, getOutputFormat());
      } catch (error) {
        handleError(error);
      }
    });
}

/**
 * Replay, and optionally follow, a job's event stream.
 *
 * Ctrl-C during a follow DETACHES. It does not cancel: the job is running under
 * systemd, not under this terminal, and a user stopping a scrolling log is not
 * asking to destroy a half-finished migration.
 */
async function runJobLogs(jobId: string, options: MachineJobOptions): Promise<void> {
  const cursor = new JobLogCursor(parseSinceLine(options.sinceLine));

  await withJobConnection(options.machine, 'read-only', async (conn) => {
    const followOptions = { onEvent: renderJobEvent, debug: options.debug };

    if (!options.follow) {
      await replayJobLogs(conn, jobId, followOptions, cursor);
      return;
    }

    const interrupted = await followJobLogs(
      conn.lease,
      conn.remoteRenetPath,
      jobId,
      followOptions,
      cursor,
      options.machine
    );

    if (interrupted) {
      outputService.warn(t('commands.job.logs.detached', { jobId, machine: options.machine }));
      setExitCode(EXIT_CODES.DETACHED);
      return;
    }

    // The stream ended because the job did. Report how it went, so a follow leaves the operator knowing the outcome rather than just a stopped log.
    const status = await readJobStatus(
      conn.lease.sftp,
      conn.remoteRenetPath,
      jobId,
      options.machine
    );
    reportTerminalState(status);
  });
}

/**
 * Resume following a ticketed job from its last seen line, then acknowledge it
 * and exit with the job's own exit code. `--timeout` stops the WAIT, not the job.
 */
async function runJobWait(requested: string, options: JobCommandOptions): Promise<void> {
  const timeoutMs = options.timeout === undefined ? undefined : parseWaitTimeoutMs(options.timeout);
  if (options.timeout !== undefined && timeoutMs === undefined) {
    throw new Error(t('commands.job.wait.invalidTimeout', { value: options.timeout }));
  }

  const store = openTicketStore();
  let ticket = store.find(requested);
  if (!ticket) {
    if (!options.machine) throw new Error(t('commands.job.machineRequired', { jobId: requested }));
    // No ticket (a job started elsewhere): adopt it so the wait leaves a resumable record.
    store.append('started', `adopted-${requested}`, {
      jobId: requested,
      machine: options.machine,
      via: { kind: 'ssh' },
      startedAt: new Date().toISOString(),
    });
    ticket = store.find(requested);
  }
  if (!ticket) throw new Error(t('commands.job.machineRequired', { jobId: requested }));

  const target = ticket.jobId ?? ticket.requestId;
  const outcome = await waitForJob(store, ticket, sshWaitDeps(), {
    timeoutMs,
    onEvent: renderJobEvent,
  });
  reportWaitOutcome(outcome, target, ticket.machine ?? options.machine ?? '');
  store.compactIfNeeded();
}

function reportWaitOutcome(outcome: WaitOutcome, jobId: string, machine: string): void {
  switch (outcome.kind) {
    case 'finished':
      if (outcome.status.state === 'succeeded') {
        outputService.success(t('commands.job.finished.succeeded', { jobId }));
      } else {
        outputService.warn(
          t('commands.job.finished.other', { jobId, state: outcome.status.state, error: '' })
        );
      }
      setExitCode(outcome.exitCode);
      return;
    case 'timeout':
      outputService.warn(t('commands.job.wait.timedOut', { jobId, machine }));
      setExitCode(EXIT_CODES.FOLLOW_LOST);
      return;
    case 'interrupted':
      outputService.warn(t('commands.job.wait.detached', { jobId, machine }));
      setExitCode(EXIT_CODES.DETACHED);
      return;
    case 'unresolved':
      throw new Error(t('commands.job.wait.startingUnresolved', { jobId }));
    case 'proxy-unsupported':
      throw new Error(t('commands.job.wait.proxyUnsupported', { jobId }));
  }
}

/** Print (and exit-code) a job's final outcome after a follow. */
function reportTerminalState(status: JobStatus): void {
  if (status.state === 'succeeded') {
    outputService.success(t('commands.job.finished.succeeded', { jobId: status.job_id }));
    return;
  }

  outputService.warn(
    t('commands.job.finished.other', {
      jobId: status.job_id,
      state: status.state,
      error: status.error ?? '',
    })
  );
  setExitCode(status.exit_code ?? 1);
}

/** Cancel a running job, confirming first: it stops real work. */
async function runJobCancel(options: MachineJobOptions, format: OutputFormat): Promise<void> {
  const jobId = options.id as string;

  await withJobConnection(options.machine, 'provision', async (conn) => {
    const current = await readJobStatus(
      conn.lease.sftp,
      conn.remoteRenetPath,
      jobId,
      options.machine
    );

    // Cancelling a finished job is a no-op machine-side, so do not make the operator confirm something that will not happen.
    if (isTerminalState(current.state)) {
      outputService.info(t('commands.job.cancel.alreadyFinished', { jobId, state: current.state }));
      return;
    }

    if (!options.yes) {
      const { askConfirm } = await import('../utils/prompt.js');
      const confirmed = await askConfirm(
        t('commands.job.cancel.confirm', {
          jobId,
          function: current.function,
          machine: options.machine,
        })
      );
      if (!confirmed) {
        outputService.info(t('status.cancelled'));
        return;
      }
    }

    const status = await cancelJob(conn, jobId);
    outputService.success(t('commands.job.cancel.requested', { jobId }));
    outputService.print(status, format);
  });
}

/** Remove finished jobs and their logs. Running jobs are never collected. */
async function runJobGc(options: MachineJobOptions, format: OutputFormat): Promise<void> {
  const hours = parseOlderThanHours(options.olderThan);

  await withJobConnection(options.machine, 'provision', async (conn) => {
    if (!options.yes) {
      const { askConfirm } = await import('../utils/prompt.js');
      const confirmed = await askConfirm(
        t('commands.job.gc.confirm', { hours, machine: options.machine })
      );
      if (!confirmed) {
        outputService.info(t('status.cancelled'));
        return;
      }
    }

    const result = await gcJobs(conn, hours);
    outputService.success(t('commands.job.gc.removed', { count: result.count }));

    if (result.count > 0) {
      outputService.print(
        result.removed.map((id) => ({ id })),
        format
      );
    }
  });
}
