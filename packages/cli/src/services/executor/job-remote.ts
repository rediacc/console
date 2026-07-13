/**
 * The SSH half of the detached-job client.
 *
 * Everything here drives `renet job ...` on a machine over the shared SSH pool.
 * It is the SINGLE implementation of those operations, used by both callers:
 *
 *   - local-executor's detached execution, which starts a job and then watches
 *     it as if it had been running synchronously all along;
 *   - the `rdc job` commands, which re-attach to a job someone else started.
 *
 * That sharing is the point. Log following in particular has to reconnect and
 * resume from the last complete line, and having two copies of that logic is
 * how you end up with one of them silently dropping a line.
 *
 * Dependency direction is deliberately one-way: this module imports from
 * job-client (pure: builders, parsers, line accounting) and never from
 * local-executor, so local-executor can import from here without a cycle.
 */

import type { SFTPClient } from '../../remote/sftp/index.js';
import { formatStepDuration, getActiveLabel, getDoneLabel } from '../../utils/timeline.js';
import { configService } from '../config/config-resources.js';
import { outputService } from '../core/output.js';
import { writeStderr, writeStdout } from '../core/request-context.js';
import { type MachineConnectionLease, machineConnections } from '../machine/machine-connection.js';
import { provisionRenetToRemote } from '../renet/renet-execution.js';
import {
  buildJobCancelCommand,
  buildJobGcCommand,
  buildJobListCommand,
  buildJobLogsCommand,
  buildJobStatusCommand,
  createEventLineReader,
  type JobGcResult,
  JobLogCursor,
  type JobStatus,
  parseJobGcResult,
  parseJobList,
  parseJobStatus,
} from './job-client.js';
import type { RenetEvent } from './types.js';

/**
 * How many times a dropped log tail is reconnected before giving up.
 *
 * Reconnecting is cheap and safe: the job runs on the machine either way, so
 * resuming only changes what we can SEE of it. The ceiling exists to stop an
 * unreachable machine from spinning forever, not to ration attempts.
 */
const MAX_LOG_RECONNECTS = 5;

/** Backoff before reconnecting a dropped log tail, capped so it stays responsive. */
function logReconnectDelayMs(attempt: number): number {
  return Math.min(500 * 2 ** attempt, 5000);
}

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** How a caller wants a job's log stream rendered and reported. */
export interface JobFollowOptions {
  /** Where events go. The optional second arg is the event's spool-line ordinal. */
  onEvent: (event: RenetEvent, line?: number) => void;
  debug?: boolean;
  /**
   * Aborts the follow WITHOUT cancelling the job (detach, not cancel). The serve
   * layer passes the request's signal, so a client disconnect detaches with one
   * listener for the whole follow. When omitted, a CLI follow falls back to
   * detaching on SIGINT, unchanged from before.
   */
  signal?: AbortSignal;
}

/** One attempt at tailing a job's logs. */
type FollowOutcome =
  | { kind: 'done' }
  | { kind: 'interrupted' }
  /** The connection died. The job is unaffected; reconnect and resume. */
  | { kind: 'transport'; error: Error }
  /** `job logs` itself refused (e.g. unknown job). Retrying will not help. */
  | { kind: 'failed'; error: Error };

/**
 * A live connection to a machine, with renet provisioned and ready to run
 * `job` subcommands.
 */
export interface JobConnection {
  lease: MachineConnectionLease;
  remoteRenetPath: string;
}

/**
 * Connect to a machine and make sure it has a renet binary to run.
 *
 * The caller MUST release the lease when done. Provisioning is the same step
 * every other machine-plane path takes, so a machine that has never been
 * touched still answers `rdc job list`.
 */
export async function connectForJobs(machineName: string): Promise<JobConnection> {
  const config = await configService.getLocalConfig();
  const machine = await configService.getLocalMachine(machineName);

  const lease = await machineConnections.acquire(machineName);
  try {
    const { remotePath } = await provisionRenetToRemote(
      { renetPath: config.renetPath },
      machine,
      lease.sshPrivateKey,
      {}
    );
    return { lease, remoteRenetPath: remotePath };
  } catch (error) {
    lease.release();
    throw error;
  }
}

// --- read operations ---------------------------------------------------------

/** List every job in a machine's spool, newest first. */
export async function listJobs(conn: JobConnection): Promise<JobStatus[]> {
  const stdout = await runJobCommand(
    conn,
    buildJobListCommand({ remoteRenetPath: conn.remoteRenetPath }),
    'list jobs'
  );
  return parseJobList(stdout);
}

/** Read one job's status. Reconciles a dead unit machine-side (see renet). */
export async function readJobStatus(
  sftp: SFTPClient,
  remoteRenetPath: string,
  jobId: string
): Promise<JobStatus> {
  const { exitCode, stdout, stderr } = await execCapture(
    sftp,
    buildJobStatusCommand({ remoteRenetPath, jobId })
  );

  if (exitCode !== 0) {
    throw new Error(failureDetail(`read the status of job ${jobId}`, stdout, stderr, exitCode));
  }

  return parseJobStatus(stdout);
}

// --- write operations --------------------------------------------------------

/**
 * Cancel a job.
 *
 * renet writes the cancel marker BEFORE stopping the unit, so the job sees
 * SIGTERM with the reason already on disk and finalizes as "cancelled" rather
 * than "failed". Cancelling an already-finished job is not an error.
 */
export async function cancelJob(conn: JobConnection, jobId: string): Promise<JobStatus> {
  const stdout = await runJobCommand(
    conn,
    buildJobCancelCommand({ remoteRenetPath: conn.remoteRenetPath, jobId }),
    `cancel job ${jobId}`
  );
  return parseJobStatus(stdout);
}

/** Remove finished jobs and their logs. Running jobs are never collected. */
export async function gcJobs(conn: JobConnection, olderThanHours: number): Promise<JobGcResult> {
  const stdout = await runJobCommand(
    conn,
    buildJobGcCommand({ remoteRenetPath: conn.remoteRenetPath, olderThanHours }),
    'garbage-collect jobs'
  );
  return parseJobGcResult(stdout);
}

// --- log following -----------------------------------------------------------

/**
 * Tail a job's event stream until it finishes, reconnecting and resuming from
 * the last complete line whenever the connection drops.
 *
 * Returns true if the operator interrupted the tail (Ctrl-C). Interrupting
 * DETACHES; it never cancels. A user hitting Ctrl-C on a scrolling log is
 * stopping the log, not asking to destroy a half-finished migration.
 *
 * `cursor` is owned by the caller so it survives across reconnects, and so a
 * caller that already received N lines can resume from there.
 */
export async function followJobLogs(
  lease: MachineConnectionLease,
  remoteRenetPath: string,
  jobId: string,
  options: JobFollowOptions,
  cursor: JobLogCursor
): Promise<boolean> {
  for (let attempt = 0; ; attempt++) {
    const outcome = await followJobLogsOnce(lease, remoteRenetPath, jobId, options, cursor);

    switch (outcome.kind) {
      case 'done':
        return false;
      case 'interrupted':
        return true;
      case 'failed':
        throw outcome.error;
    }

    // Transport died. The JOB is untouched (it runs under systemd, not under
    // this connection), so all that is lost is our view of it. Resume from the
    // last COMPLETE line: renet re-sends anything it only half-delivered.
    if (attempt >= MAX_LOG_RECONNECTS) throw outcome.error;

    if (options.debug) {
      outputService.info(
        `Log stream dropped (${outcome.error.message}); resuming job ${jobId} from line ${cursor.sinceLine}`
      );
    }

    await delay(logReconnectDelayMs(attempt));
  }
}

/** One attempt at tailing the log stream. */
async function followJobLogsOnce(
  lease: MachineConnectionLease,
  remoteRenetPath: string,
  jobId: string,
  options: JobFollowOptions,
  cursor: JobLogCursor
): Promise<FollowOutcome> {
  const command = buildJobLogsCommand({
    remoteRenetPath,
    jobId,
    sinceLine: cursor.sinceLine,
    follow: true,
  });

  // A fresh reader per attempt: it buffers a partial line internally, and
  // carrying that stale fragment across a reconnect would glue it onto the
  // first line of the resumed stream and corrupt it. Seed its ordinal from the
  // cursor so a resumed line keeps the spool-line number it had before the drop.
  const read = createEventLineReader(options.onEvent, cursor.sinceLine);

  let stopped = false;
  const interrupt = watchForInterrupt(options.signal, () => {
    // Stop rendering immediately: the remote tail keeps streaming until this
    // process exits, and events arriving after the resume hint would bury it.
    stopped = true;
  });

  const streaming = (async (): Promise<FollowOutcome> => {
    try {
      const sftp = await lease.ensure();
      const exitCode = await sftp.execStreaming(command, {
        onStdout: (data) => {
          if (stopped) return;
          read(data);
          cursor.consume(data);
        },
        onStderr: (data) => {
          if (options.debug && !stopped) process.stderr.write(data);
        },
      });

      // A dropped connection surfaces as a channel close with no exit status.
      if (typeof exitCode !== 'number') {
        return { kind: 'transport', error: new Error('log stream closed without an exit status') };
      }
      if (exitCode === 0) return { kind: 'done' };

      return {
        kind: 'failed',
        error: new Error(`renet job logs exited ${exitCode} for job ${jobId}`),
      };
    } catch (error) {
      // execStreaming rejects on a channel error or a dead session: transport.
      return {
        kind: 'transport',
        error: error instanceof Error ? error : new Error(String(error)),
      };
    }
  })();

  try {
    return await Promise.race([streaming, interrupt.promise]);
  } finally {
    interrupt.dispose();
  }
}

/**
 * A promise that resolves `interrupted` when the caller asks to detach.
 *
 * The signal is preferred so a server can hang the follow off the request
 * lifetime (client disconnect = detach) with ONE listener for the whole follow,
 * not one per reconnect attempt. With no signal, a CLI follow keeps the historical
 * behaviour: Ctrl-C (SIGINT) detaches. Either way `dispose` removes the listener
 * so a completed attempt leaks nothing.
 */
function watchForInterrupt(
  signal: AbortSignal | undefined,
  onInterrupt: () => void
): { promise: Promise<FollowOutcome>; dispose: () => void } {
  let dispose = () => {};
  const promise = new Promise<FollowOutcome>((resolve) => {
    const fire = () => {
      onInterrupt();
      resolve({ kind: 'interrupted' });
    };
    if (signal) {
      if (signal.aborted) {
        fire();
        return;
      }
      signal.addEventListener('abort', fire, { once: true });
      dispose = () => signal.removeEventListener('abort', fire);
    } else {
      process.once('SIGINT', fire);
      dispose = () => process.removeListener('SIGINT', fire);
    }
  });
  return { promise, dispose };
}

/** Replay a job's logs without following. Returns the lines delivered. */
export async function replayJobLogs(
  conn: JobConnection,
  jobId: string,
  options: JobFollowOptions,
  cursor: JobLogCursor
): Promise<void> {
  const command = buildJobLogsCommand({
    remoteRenetPath: conn.remoteRenetPath,
    jobId,
    sinceLine: cursor.sinceLine,
    follow: false,
  });

  const read = createEventLineReader(options.onEvent, cursor.sinceLine);
  const sftp = await conn.lease.ensure();

  let stderr = '';
  const exitCode = await sftp.execStreaming(command, {
    onStdout: (data) => {
      read(data);
      cursor.consume(data);
    },
    onStderr: (data) => {
      stderr += data.toString();
    },
  });

  if (exitCode !== 0) {
    throw new Error(failureDetail(`read the logs of job ${jobId}`, '', stderr, exitCode));
  }
}

// --- rendering ---------------------------------------------------------------

/**
 * The default renderer for a job's event stream.
 *
 * This is what makes re-attaching to a running job look exactly like having
 * watched it from the start: the same step lines, the same durations, drawn
 * from the same events the synchronous path renders. That is the whole payoff
 * of the line-based offsets.
 */
export function renderJobEvent(event: RenetEvent): void {
  const line = jobEventLine(event);
  if (!line) return;

  // Route through the request context so a served follow writes into the
  // request's buffer, not the container's terminal. On a laptop this is stdout.
  if (line.stream === 'err') {
    writeStderr(line.text);
    return;
  }

  writeStdout(line.text);
}

/** What one event renders to, or null if it renders to nothing. */
interface EventLine {
  stream: 'out' | 'err';
  text: string;
}

function jobEventLine(event: RenetEvent): EventLine | null {
  switch (event.type) {
    case 'step_start':
      return stepStartLine(event);
    case 'step_done':
      return stepDoneLine(event);
    case 'log':
      return logLine(event);
    case 'output':
      return outputLine(event);
    default:
      return null;
  }
}

function stepStartLine(event: RenetEvent): EventLine | null {
  if (!event.name) return null;
  return { stream: 'out', text: `⠋ ${getActiveLabel(event.name)}...` };
}

function stepDoneLine(event: RenetEvent): EventLine | null {
  if (!event.name || event.duration_ms == null) return null;
  return {
    stream: 'out',
    text: `\r✔ ${getDoneLabel(event.name)} (${formatStepDuration(event.duration_ms)})\n`,
  };
}

/** Only errors and warnings: the rest is noise in a log replay. */
function logLine(event: RenetEvent): EventLine | null {
  if (event.level !== 'error' && event.level !== 'warning') return null;
  return { stream: 'err', text: `  ${event.msg ?? ''}\n` };
}

function outputLine(event: RenetEvent): EventLine | null {
  if (!event.msg) return null;
  return { stream: 'out', text: event.msg.endsWith('\n') ? event.msg : `${event.msg}\n` };
}

// --- plumbing ----------------------------------------------------------------

/** Run a one-shot `renet job` subcommand and return its stdout. */
async function runJobCommand(conn: JobConnection, command: string, what: string): Promise<string> {
  const sftp = await conn.lease.ensure();
  const { exitCode, stdout, stderr } = await execCapture(sftp, command);

  if (exitCode !== 0) {
    throw new Error(failureDetail(what, stdout, stderr, exitCode));
  }

  return stdout;
}

async function execCapture(
  sftp: SFTPClient,
  command: string
): Promise<{ exitCode: number; stdout: string; stderr: string }> {
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

  return { exitCode, stdout, stderr };
}

/**
 * Turn a failed `renet job` invocation into something an operator can act on.
 *
 * renet writes the useful part to stderr ("unknown job", "invalid job id"), so
 * that is preferred over stdout, and the exit code alone is never enough.
 */
function failureDetail(what: string, stdout: string, stderr: string, exitCode: number): string {
  const detail = (stderr || stdout).trim().split('\n')[0] ?? '';
  return detail
    ? `Failed to ${what}: ${detail}`
    : `Failed to ${what}: renet exited ${exitCode} with no output`;
}
