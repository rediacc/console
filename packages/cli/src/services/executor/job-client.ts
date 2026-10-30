/**
 * Client for renet's detached-job model.
 *
 * A normal execution rides the SSH channel that started it: the CLI runs
 * `renet execute`, streams its NDJSON events, and the operation dies with the
 * connection. A DETACHED execution breaks that coupling. `renet job start`
 * hands the work to a transient systemd unit on the machine and returns a job
 * ID immediately; the operation then runs with no relationship to the SSH
 * channel at all. The CLI re-attaches to it by tailing `renet job logs`, and if
 * the network drops mid-tail it simply reconnects and resumes.
 *
 * Two properties make the resume correct, and both are load-bearing:
 *
 *   - Offsets are counted in LINES, not bytes. The stream crosses SSH, where
 *     the transport is free to re-chunk the bytes however it likes, so a byte
 *     offset would only be meaningful if both ends agreed on framing. Counting
 *     complete lines is the one thing they can both agree on.
 *   - A partially delivered line is never counted. renet only advances its own
 *     cursor past complete lines, so a line cut in half by a dropped connection
 *     is re-sent in full on resume. Counting it here would silently skip it.
 *
 * This module holds the pure, dependency-free half: the remote command builders,
 * parsing, line accounting, version-skew detection, and the status-to-result
 * mapping. The I/O half (SSH, stream plumbing, the reconnect loop) lives in
 * job-remote.ts, which imports from here and never the other way around.
 */

import type { BackgroundEnvelope, JobOverlap } from '@rediacc/shared/cli-contract/wire';
import { z } from 'zod';
import { shellQuote } from '../../utils/shell-quote.js';
import { writeStdout } from '../core/request-context.js';
import { type RenetEnv, type RenetLaunch, sudoRenet } from './renet-launch.js';
import type { ExecuteResult, RenetEvent } from './types.js';

/**
 * The shape of a job ID as renet mints it (pkg/jobs: `j<unixnano-hex>-<4-byte-hex>`).
 *
 * This is validated, not trusted, before it is ever interpolated into a remote
 * shell command. The ID arrives as JSON from the machine, and a machine that
 * returned `j1-deadbeef; rm -rf /` would otherwise get exactly what it asked
 * for. renet validates its own IDs for the same reason on the receiving side.
 */
const JOB_ID_PATTERN = /^j[0-9a-f]{1,16}-[0-9a-f]{8}$/;

/** Raised when a job ID does not match what renet could have produced. */
export class InvalidJobIdError extends Error {
  constructor(readonly jobId: string) {
    super(
      `The machine returned a job id that renet could not have produced: ${JSON.stringify(jobId)}. ` +
        `Refusing to use it in a remote command.`
    );
    this.name = 'InvalidJobIdError';
  }
}

/** Validate a job ID before it reaches a shell. Returns it for chaining. */
export function assertJobId(jobId: string): string {
  if (!JOB_ID_PATTERN.test(jobId)) {
    throw new InvalidJobIdError(jobId);
  }
  return jobId;
}

/**
 * An overlap entry as renet prints it (private/renet/pkg/jobs/overlap.go
 * Overlap): another live job, or an active scheduled backup unit, that a start
 * met. Mapped to the wire's camelCase JobOverlap by toJobOverlap.
 */
const RenetOverlapSchema = z.object({
  started_at: z.string().optional(),
  origin: z
    .object({
      config: z.object({ name: z.string().optional(), id: z.string().optional() }).optional(),
      client: z.string().optional(),
      version: z.string().optional(),
      ssh_user: z.string().optional(),
      actor: z.string().optional(),
    })
    .optional(),
  job_id: z.string().optional(),
  function: z.string().optional(),
  command: z.string().optional(),
  repo_guid: z.string().optional(),
  machine: z.string().optional(),
  lock_class: z.string().optional(),
  state: z.string().optional(),
  unit: z.string().optional(),
  action: z.enum(['warn', 'refuse']),
  attach: z.string().default(''),
});

type RenetOverlap = z.infer<typeof RenetOverlapSchema>;

/** Drop the keys whose value is undefined or empty, so an absent renet field never becomes `""` on the wire. */
function compact<T extends Record<string, unknown>>(obj: T): T {
  return Object.fromEntries(
    Object.entries(obj).filter(([, value]) => value !== undefined && value !== '')
  ) as T;
}

/** Map renet's overlap entry onto the wire's JobOverlap (section 19). */
export function toJobOverlap(o: RenetOverlap): JobOverlap {
  const origin = o.origin
    ? compact({
        client: o.origin.client,
        version: o.origin.version,
        sshUser: o.origin.ssh_user,
        config: o.origin.config,
        actor: o.origin.actor,
      })
    : undefined;
  return compact({
    jobId: o.job_id,
    function: o.function,
    command: o.command,
    repoGuid: o.repo_guid,
    machine: o.machine,
    lockClass: o.lock_class,
    state: o.state,
    startedAt: o.started_at,
    origin,
    unit: o.unit,
    action: o.action,
    attach: o.attach,
  }) as JobOverlap;
}

/** What `renet job start --json` prints: everything needed to find the job again. */
const JobHandleSchema = z.object({
  job_id: z.string(),
  unit: z.string(),
  log_path: z.string(),
  /** Live jobs and scheduled units the start met and was allowed past. */
  overlaps: z.array(RenetOverlapSchema).nullable().optional(),
  /** True when the handle is an earlier start's with the same request id: nothing new started. */
  deduped: z.boolean().optional(),
  /** The network ID this start allocated for a vault with `network_id: "auto"` (section 14). */
  network_id: z.number().int().positive().optional(),
});

type JobHandle = z.infer<typeof JobHandleSchema>;

export type { JobHandle };

/** What `renet job status --json` prints (renet pkg/jobs Status). */
const JobStatusSchema = z.object({
  job_id: z.string(),
  function: z.string(),
  state: z.enum(['running', 'succeeded', 'failed', 'cancelled']),
  /** null while the job is still running. */
  exit_code: z.number().nullable().optional(),
  started_at: z.string(),
  /** Absent until the job finalizes. */
  finished_at: z.string().optional(),
  error: z.string().optional(),
  repo_guid: z.string().optional(),
  machine: z.string().optional(),
  unit: z.string().optional(),
  log_path: z.string().optional(),
  pid: z.number().optional(),
  request_id: z.string().optional(),
  command: z.string().optional(),
  lock_class: z.string().optional(),
});

type JobStatus = z.infer<typeof JobStatusSchema>;

export type { JobStatus };

/** renet's `job run` exit codes, which mirror the terminal state. */
const EXIT_SUCCESS = 0;
const EXIT_FAILURE = 1;

/**
 * Tracks how many complete NDJSON lines the renderer has been handed, which is
 * exactly what `renet job logs --since-line N` wants: "I already have N lines,
 * send me from N+1".
 *
 * Only newline bytes are counted, and deliberately so. A chunk that ends
 * mid-line contributes nothing until its newline arrives, which means a
 * connection that dies mid-line leaves the count pointing at the last COMPLETE
 * line. renet re-sends the half-delivered line on resume, the renderer sees it
 * exactly once, and nothing is lost or duplicated.
 *
 * Counting bytes rather than decoded characters is intentional: 0x0A cannot
 * appear inside a multi-byte UTF-8 sequence, so a chunk boundary that splits a
 * character can never corrupt the count.
 */
export class JobLogCursor {
  private delivered: number;

  constructor(startLine = 0) {
    this.delivered = startLine;
  }

  /** The value to pass as `--since-line` on the next (re)connect. */
  get sinceLine(): number {
    return this.delivered;
  }

  /** Count the complete lines in a chunk of the log stream. */
  consume(chunk: Buffer | string): void {
    const buf = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    for (const byte of buf) {
      if (byte === 0x0a) this.delivered += 1;
    }
  }
}

/**
 * Detect the version-skew case: the renet DEPLOYED on the machine predates the
 * detached-job model and has no `job` command at all.
 *
 * This matters because machines are upgraded independently of the CLI, so
 * during a rollout an older renet on the far end is the NORMAL state, not an
 * exceptional one. Cobra rejects an unknown command before running anything,
 * which is what makes it safe to fall back to a synchronous execution: no work
 * was started, so re-running cannot double-execute the operation.
 *
 * The match is deliberately narrow. Any OTHER `job start` failure must NOT be
 * treated as skew, because a failure after the unit was spawned would make a
 * fallback run the operation a second time.
 */
export function isJobCommandUnsupported(output: string): boolean {
  return /unknown command "job"/i.test(output);
}

/**
 * Detect the other version-skew case: the remote renet has the command but not a flag this CLI passes (cobra's own `Error: unknown flag: --since-line` or `Error: unknown shorthand flag: 'x' in -x` line, bare, after a `[step]` tag or after `: `; docker's own `unknown flag` text carries no `Error:` and does not count). Cobra rejects the invocation while parsing flags, before any command body runs, so the answer can name the skew without having changed anything on the machine.
 */
export function isRenetFlagUnsupported(output: string): boolean {
  return /(?:^|[:\]]\s)\s*Error: unknown (shorthand )?flag\b/m.test(output);
}

/** The answer to a renet that is older than the CLI talking to it. `machine` is the machine's name. */
export function renetOlderThanCliMessage(machine: string): string {
  return `renet on ${machine} is older than this CLI; run machine setup`;
}

/**
 * Whether a failed `job start` means the machine's renet is too old to run it
 * as a job: no `job` command at all, or no flag this CLI passes (`--request-id`,
 * `--attach`, `--origin` arrived with J1 and J1b). Cobra rejects both while
 * parsing, before any work, so nothing ran.
 */
export function isJobStartUnsupported(output: string): boolean {
  return isJobCommandUnsupported(output) || isRenetFlagUnsupported(output);
}

/**
 * The refusal for a renet older than the job model (Design 11). There is no
 * synchronous fallback: every renet call runs as a job, and `machine setup`
 * uploads the binary that can.
 */
export function jobsUnsupportedMessage(machineName: string, verb: string): string {
  return (
    `renet on '${machineName}' is older than this CLI and cannot run ${verb} as a job. ` +
    `Upgrade it: rdc machine setup ${machineName}`
  );
}

/** Raised when the machine's renet cannot run a job: nothing ran, exit 1. */
export class JobsUnsupportedError extends Error {
  constructor(
    readonly machineName: string,
    readonly verb: string
  ) {
    super(jobsUnsupportedMessage(machineName, verb));
    this.name = 'JobsUnsupportedError';
  }
}

/** Raised when `job start` fails for a reason that is NOT version skew. */
export class JobStartFailedError extends Error {
  constructor(
    readonly machineName: string,
    readonly detail: string
  ) {
    super(`Failed to start a detached job on '${machineName}': ${detail}`);
    this.name = 'JobStartFailedError';
  }
}

/**
 * The message shown when the operator interrupts a log tail (Ctrl-C).
 *
 * Interrupting the tail must NOT cancel the job. The whole point of a detached
 * job is that it outlives the connection watching it, and a user who hits
 * Ctrl-C on a scrolling log is stopping the log, not asking to destroy a
 * half-finished migration. So we say plainly that the job is still running and
 * hand back the commands to get back to it.
 */
export function resumeHint(jobId: string, machineName: string): string {
  return [
    `Detached from job ${jobId}. It is STILL RUNNING on '${machineName}' and was NOT cancelled.`,
    ``,
    `  Follow it again:  rdc job logs ${jobId} -m ${machineName} --follow`,
    `  Check the result: rdc job status ${jobId} -m ${machineName}`,
    `  Stop it:          rdc job cancel ${jobId} -m ${machineName}`,
  ].join('\n');
}

/**
 * The message shown when a job is started in the background (`--background`),
 * or outlives its attach window, in text mode. It goes to stderr: stdout
 * belongs to the command (section 26). Under `-o json` the envelope replaces it.
 */
export function backgroundStartedHint(jobId: string, machineName: string): string {
  return [
    `Started job ${jobId} on '${machineName}'. It keeps running in the background.`,
    ``,
    `  Wait for it:      rdc job wait ${jobId}`,
    `  Follow it:        rdc job logs ${jobId} -m ${machineName} --follow`,
    `  Check the result: rdc job status ${jobId} -m ${machineName}`,
  ].join('\n');
}

/**
 * The message shown when a direct attach lost its transport for longer than the
 * reattach budget (section 16). The job keeps running and the ticket is kept.
 */
export function followLostHint(jobId: string, machineName: string): string {
  return [
    `Lost the connection to job ${jobId} on '${machineName}'. The job is STILL RUNNING and its ticket is kept.`,
    ``,
    `  Resume following: rdc job wait ${jobId}`,
    `  Check the result: rdc job status ${jobId} -m ${machineName}`,
  ].join('\n');
}

/** The `-b` / attach-window envelope (Design 2, section 26), shared with MCP. */
export function backgroundEnvelope(params: {
  jobId: string;
  machine: string;
  verb: string;
  repo?: string;
  overlaps?: JobOverlap[];
}): BackgroundEnvelope {
  return {
    jobId: params.jobId,
    machine: params.machine,
    verb: params.verb,
    ...(params.repo ? { repo: params.repo } : {}),
    state: 'running',
    follow: `rdc job wait ${params.jobId}`,
    overlaps: params.overlaps ?? [],
  };
}

/** One overlap as a stderr warning line plus the command that shows the other job (section 19). */
export function overlapWarningLines(overlap: JobOverlap): string[] {
  const head = `${overlap.action === 'refuse' ? 'Refused' : 'Warning'}: ${overlapSubject(overlap)}, ${originLabel(overlap.origin)}.`;
  return overlap.attach ? [head, `  See it: ${overlap.attach}`] : [head];
}

/** "job <id> (<function> on <repo>) is running, started <ts>". */
function overlapSubject(overlap: JobOverlap): string {
  const what = overlap.unit ?? `job ${overlap.jobId ?? '?'}`;
  const doing = overlap.function ?? overlap.command ?? 'work';
  const scope = overlap.repo ?? overlap.repoGuid;
  const on = scope ? ` on ${scope}` : '';
  const started = overlap.startedAt ? `, started ${overlap.startedAt}` : '';
  return `${what} (${doing}${on}) is ${overlap.state ?? 'running'}${started}`;
}

/** "started by <user> via <client> (config <name>)", or the older-renet fallback. */
function originLabel(origin: JobOverlap['origin']): string {
  if (!origin) return 'started by: unknown (older renet)';
  const config = origin.config?.name ? ` (config ${origin.config.name})` : '';
  return `started by ${origin.sshUser ?? 'unknown'} via ${origin.client ?? 'unknown'}${config}`;
}

/** Parse `renet job start --json` output into a validated handle. */
export function parseJobHandle(stdout: string): JobHandle {
  const handle = JobHandleSchema.parse(JSON.parse(extractJsonObject(stdout)));
  assertJobId(handle.job_id);
  return handle;
}

/** Parse `renet job status --json` output into a validated status. */
export function parseJobStatus(stdout: string): JobStatus {
  return JobStatusSchema.parse(JSON.parse(extractJsonObject(stdout)));
}

/**
 * Parse `renet job list --json` output.
 *
 * renet prints `null` rather than `[]` when the spool is empty (Go marshals a
 * nil slice that way), so an empty spool is a legitimate answer, not a parse
 * failure.
 */
export function parseJobList(stdout: string): JobStatus[] {
  const parsed: unknown = JSON.parse(extractJsonValue(stdout));
  if (parsed === null) return [];
  return z.array(JobStatusSchema).parse(parsed);
}

/** What `renet job gc --json` prints. */
const JobGcResultSchema = z.object({
  removed: z.array(z.string()).nullable().default([]),
  count: z.number(),
});

export interface JobGcResult {
  removed: string[];
  count: number;
}

/** Parse `renet job gc --json` output. */
export function parseJobGcResult(stdout: string): JobGcResult {
  const parsed = JobGcResultSchema.parse(JSON.parse(extractJsonObject(stdout)));
  return { removed: parsed.removed ?? [], count: parsed.count };
}

/**
 * How long a job ran, as a short human string. A job that has not finished
 * reports how long it has been running so far, because "how long has this been
 * going" is the question an operator actually asks of a running job.
 */
export function formatJobDuration(status: JobStatus, now: number = Date.now()): string {
  const started = Date.parse(status.started_at);
  if (Number.isNaN(started)) return '-';

  const elapsed = jobDurationMs(status) ?? (isTerminalState(status.state) ? null : now - started);
  if (elapsed === null || elapsed < 0) return '-';

  if (elapsed < 1000) return `${elapsed}ms`;
  if (elapsed < 60_000) return `${(elapsed / 1000).toFixed(1)}s`;

  const minutes = Math.floor(elapsed / 60_000);
  const seconds = Math.round((elapsed % 60_000) / 1000);
  return `${minutes}m${seconds}s`;
}

/** Whether a job has reached a final state. */
export function isTerminalState(state: JobStatus['state']): boolean {
  return state === 'succeeded' || state === 'failed' || state === 'cancelled';
}

// --- remote command builders -------------------------------------------------
//
// Pure string builders for the `renet job ...` invocations. They live here, in the dependency-free half, so both callers can reach them without an import cycle: local-executor drives a detached execution, and the `rdc job` commands drive the operator-facing ones.
//
// Every builder that takes an id validates it first. A job id arrives as JSON FROM the machine and is then interpolated into a remote shell command, so an
// id the machine made up (`j1-deadbeef; rm -rf /`) must never reach a shell.

/**
 * Build the `renet job start` launch for a DETACHED execution.
 *
 * `env` is passed in rather than computed here, both to keep this module
 * free of the executor's environment plumbing and because it is load-bearing:
 * `job start` snapshots the environment it is handed into the job's spool so
 * that `job run` can re-inject it later, since systemd spawns the real body
 * with a clean environment. Drift between that environment and renet's capture
 * list would silently strip a repo's secrets from every detached deployment.
 *
 * Neither the vault nor a secret rides the argv: the secrets go over stdin
 * as the launch's `stdinPrefix`, followed by the vault, exactly as
 * `renet execute` takes them.
 */
export function buildJobStartCommand(params: {
  remoteRenetPath: string;
  /** From buildRenetEnv. */
  env: RenetEnv;
  /** Job ceiling in milliseconds. Rendered as a Go duration ("600000ms"). */
  timeoutMs?: number;
  debug?: boolean;
  /** The idempotency key (section 17): a retried start attaches to the first job. */
  requestId?: string;
  /** The `--attach` Go duration (`0s` is until terminal); absent prints the handle and returns. */
  attach?: string;
  /** The `--origin` JSON (section 19), at most 1 KiB. */
  origin?: string;
  /** The `--steps` JSON array (section 18): the client-side step plan renet keeps in the spool. */
  steps?: string;
}): RenetLaunch {
  const { remoteRenetPath, env, timeoutMs, debug, requestId, attach, origin, steps } = params;
  const timeoutFlag = timeoutMs ? ` --timeout ${timeoutMs}ms` : '';
  const debugFlag = debug ? ' --debug' : '';
  const requestFlag = requestId ? ` --request-id ${shellQuote(requestId)}` : '';
  const attachFlag = attach ? ` --attach ${shellQuote(attach)}` : '';
  const originFlag = origin ? ` --origin ${shellQuote(origin)}` : '';
  const stepsFlag = steps ? ` --steps ${shellQuote(steps)}` : '';
  return sudoRenet(
    env,
    `${shellQuote(remoteRenetPath)} job start --executor local --json${timeoutFlag}${debugFlag}${requestFlag}${attachFlag}${originFlag}${stepsFlag}`
  );
}

// --- the attach stream -------------------------------------------------------

/** The `{"type":"job_status",...}` trailer `job start --attach` and `job logs --with-status` print. */
const JobStatusTrailerSchema = JobStatusSchema.extend({
  type: z.literal('job_status'),
  deduped: z.boolean().optional(),
  overlaps: z.array(RenetOverlapSchema).nullable().optional(),
});

/** What a refused start prints on stdout before exiting 15. */
const OverlapRefusalSchema = z.object({
  refused: z.literal('overlap'),
  overlaps: z.array(RenetOverlapSchema),
});

/**
 * What a start refused by its vault's `expect` prints on stdout before exiting
 * 15 (private/renet/cmd/renet/job_precondition.go PreconditionRefusal).
 */
const PreconditionRefusalSchema = z.object({
  refused: z.literal('precondition'),
  expect: z.enum(['repo_present', 'repo_absent', 'repo_unmounted']),
  state: z.string(),
  repository: z.string(),
  repo_guid: z.string(),
  machine: z.string().optional(),
  message: z.string(),
});

type PreconditionRefusal = z.infer<typeof PreconditionRefusalSchema>;

export type { PreconditionRefusal };

/** One line of a `job start --attach` stream, classified. */
export type AttachLine =
  | {
      kind: 'handle';
      jobId: string;
      deduped: boolean;
      overlaps: JobOverlap[];
      networkId?: number;
    }
  | { kind: 'status'; status: JobStatus; deduped: boolean; overlaps: JobOverlap[] }
  | { kind: 'refusal'; overlaps: JobOverlap[] }
  | { kind: 'precondition'; refusal: PreconditionRefusal }
  | { kind: 'event'; event: RenetEvent }
  | { kind: 'raw'; text: string };

/**
 * Classify one complete line of an attach stream. The handle is the first
 * line, the status trailer the last; every line between is one spool line (an
 * event), which is what the line cursor counts.
 */
export function parseAttachLine(line: string): AttachLine {
  let parsed: unknown;
  try {
    parsed = JSON.parse(line);
  } catch {
    return { kind: 'raw', text: line };
  }
  if (!parsed || typeof parsed !== 'object') return { kind: 'event', event: parsed as RenetEvent };
  const obj = parsed as Record<string, unknown>;
  if (obj.type === 'job_handle') return handleLineOf(obj);
  if (obj.type === 'job_status') return statusLineOf(obj);
  if (obj.refused === 'overlap') {
    return {
      kind: 'refusal',
      overlaps: OverlapRefusalSchema.parse(obj).overlaps.map(toJobOverlap),
    };
  }
  if (obj.refused === 'precondition') {
    return { kind: 'precondition', refusal: PreconditionRefusalSchema.parse(obj) };
  }
  return { kind: 'event', event: obj as unknown as RenetEvent };
}

function handleLineOf(obj: Record<string, unknown>): AttachLine {
  const handle = JobHandleSchema.parse(obj);
  return {
    kind: 'handle',
    jobId: assertJobId(handle.job_id),
    deduped: handle.deduped === true,
    overlaps: (handle.overlaps ?? []).map(toJobOverlap),
    ...(handle.network_id === undefined ? {} : { networkId: handle.network_id }),
  };
}

function statusLineOf(obj: Record<string, unknown>): AttachLine {
  const { type: _type, deduped, overlaps, ...status } = JobStatusTrailerSchema.parse(obj);
  return {
    kind: 'status',
    status,
    deduped: deduped === true,
    overlaps: (overlaps ?? []).map(toJobOverlap),
  };
}

/** The overlaps, dedupe flag and allocated network ID of a plain (`-b`) handle. */
export function handleOverlaps(stdout: string): {
  deduped: boolean;
  overlaps: JobOverlap[];
  networkId?: number;
} {
  const handle = JobHandleSchema.parse(JSON.parse(extractJsonObject(stdout)));
  return {
    deduped: handle.deduped === true,
    overlaps: (handle.overlaps ?? []).map(toJobOverlap),
    ...(handle.network_id === undefined ? {} : { networkId: handle.network_id }),
  };
}

/** The overlaps of a refusal printed on stdout, or null when the output is no refusal. */
export function parseOverlapRefusal(stdout: string): JobOverlap[] | null {
  for (const line of stdout.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed.startsWith('{')) continue;
    const parsed = parseAttachLine(trimmed);
    if (parsed.kind === 'refusal') return parsed.overlaps;
  }
  return null;
}

/** The precondition refusal printed on stdout, or null when the output is none. */
export function parsePreconditionRefusal(stdout: string): PreconditionRefusal | null {
  for (const line of stdout.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed.startsWith('{')) continue;
    const parsed = parseAttachLine(trimmed);
    if (parsed.kind === 'precondition') return parsed.refusal;
  }
  return null;
}

/**
 * Build the `renet job logs` command used to attach to (or re-attach to) a
 * job's event stream.
 *
 * `sinceLine` is "how many lines I already have", so a fresh attach passes 0
 * and a resume after a dropped connection passes the count it received.
 *
 * No env prefix: reading the spool needs no secrets, no telemetry, and no
 * kubeconfig. Handing them to a log tail would be a gratuitous second exposure.
 */
export function buildJobLogsCommand(params: {
  remoteRenetPath: string;
  jobId: string;
  sinceLine: number;
  follow: boolean;
}): string {
  const jobId = assertJobId(params.jobId);
  const followFlag = params.follow ? ' --follow' : '';
  return `sudo ${shellQuote(params.remoteRenetPath)} job logs --id ${jobId} --since-line ${params.sinceLine}${followFlag}`;
}

/** Build the `renet job status` command. */
export function buildJobStatusCommand(params: { remoteRenetPath: string; jobId: string }): string {
  return `sudo ${shellQuote(params.remoteRenetPath)} job status --id ${assertJobId(params.jobId)} --json`;
}

/** Build the `renet job cancel` command. */
export function buildJobCancelCommand(params: { remoteRenetPath: string; jobId: string }): string {
  return `sudo ${shellQuote(params.remoteRenetPath)} job cancel --id ${assertJobId(params.jobId)} --json`;
}

/** Build the `renet job list` command. */
export function buildJobListCommand(params: { remoteRenetPath: string }): string {
  return `sudo ${shellQuote(params.remoteRenetPath)} job list --json`;
}

/**
 * Build the `renet job gc` command.
 *
 * The age is rendered as a Go duration in whole hours, which is the granularity
 * the flag exists for: nobody garbage-collects job logs to the minute.
 */
export function buildJobGcCommand(params: {
  remoteRenetPath: string;
  olderThanHours: number;
}): string {
  return `sudo ${shellQuote(params.remoteRenetPath)} job gc --older-than ${params.olderThanHours}h --json`;
}

// --- NDJSON stream reader ----------------------------------------------------

/**
 * Split a raw byte stream into NDJSON events.
 *
 * Identical in behaviour to the synchronous path's stdout handler: a line that
 * parses is an event, a line that does not is passed through as raw text (renet
 * subprocesses occasionally write unstructured output). A partial trailing line
 * is buffered until its newline arrives, so the reader never hands the renderer
 * half a JSON object.
 *
 * A fresh reader must be created per connection attempt: the buffered partial
 * line belongs to the attempt that died, and gluing it onto the first line of a
 * resumed stream would corrupt it.
 */
export function createEventLineReader(
  onEvent: (event: RenetEvent, line?: number) => void,
  startLine = 0
): (chunk: Buffer) => void {
  let buffered = '';
  let lineNumber = startLine;

  return (chunk: Buffer) => {
    buffered += chunk.toString();
    const lines = buffered.split('\n');
    buffered = lines.pop() ?? '';

    for (const line of lines) {
      // Advance for EVERY complete line, blank or not, so the ordinal tracks the same newline count JobLogCursor does. The two must stay in lockstep for a resume to dedupe against the right line.
      lineNumber += 1;
      const trimmed = line.trim();
      if (!trimmed) continue;

      try {
        onEvent(JSON.parse(trimmed) as RenetEvent, lineNumber);
      } catch {
        writeStdout(`${line}\n`);
      }
    }
  };
}

/**
 * Accumulates a detached job's event stream back into the stdout, stderr, and
 * step timings a synchronous run would have produced.
 *
 * This exists because a detached job's spool is ALWAYS NDJSON (`job run` forces
 * events mode, cmd/renet/job_commands.go), so a status-to-result mapping has no
 * captured text to hand back unless it is reconstructed here. The reconstruction
 * is byte-faithful: renet emits the exact same string either as an `output`
 * event or as a `Println` on the synchronous path
 * (cmd/renet/execute_command.go), so concatenating `output` messages
 * newline-terminated reproduces the non-events stdout, bridge relay prefixes and
 * all. That is precisely what `parseCapturedJson` expects.
 *
 * Kept dependency-free and separate from rendering on purpose: capturing the
 * output must not depend on whether, or how, the caller wants it drawn.
 */
export interface JobOutputCollector {
  /** Fold one decoded event into the accumulated output. */
  consume(event: RenetEvent): void;
  /** The reconstructed stdout, byte-faithful with a synchronous run. */
  readonly stdout: string;
  /** The reconstructed stderr (error and warning log lines). */
  readonly stderr: string;
  /** Step timings recovered from `step_done` events. */
  readonly steps: { name: string; duration_ms: number; detail?: string }[];
}

/**
 * The text an `output` event contributes to reconstructed stdout, or ''.
 *
 * renet's non-events path prints each line with Println, which always appends
 * exactly one newline; mirror that byte-for-byte so the reconstruction matches.
 */
function outputEventText(event: RenetEvent): string {
  return event.type === 'output' && event.msg != null ? `${event.msg}\n` : '';
}

/** The text an error/warning `log` event contributes to reconstructed stderr, or ''. */
function logEventText(event: RenetEvent): string {
  const isProblem = event.level === 'error' || event.level === 'warning';
  return event.type === 'log' && isProblem && event.msg != null ? `${event.msg}\n` : '';
}

/** The step timing a `step_done` event contributes, or null when incomplete. */
function stepDoneEntry(
  event: RenetEvent
): { name: string; duration_ms: number; detail?: string } | null {
  if (event.type !== 'step_done' || !event.name || typeof event.duration_ms !== 'number') {
    return null;
  }
  return {
    name: event.name,
    duration_ms: event.duration_ms,
    ...(event.detail ? { detail: event.detail } : {}),
  };
}

export function createJobOutputCollector(): JobOutputCollector {
  let stdout = '';
  let stderr = '';
  const steps: { name: string; duration_ms: number; detail?: string }[] = [];

  return {
    consume(event: RenetEvent): void {
      stdout += outputEventText(event);
      stderr += logEventText(event);
      const step = stepDoneEntry(event);
      if (step) steps.push(step);
    },
    get stdout() {
      return stdout;
    },
    get stderr() {
      return stderr;
    },
    get steps() {
      return steps;
    },
  };
}

/**
 * Pull the JSON object out of a captured stdout.
 *
 * `sudo` and the remote shell can prepend noise (a lecture banner, a warning)
 * before renet's own output, so we start at the first brace rather than
 * assuming the payload begins at byte zero.
 */
function extractJsonObject(stdout: string): string {
  const start = stdout.indexOf('{');
  const end = stdout.lastIndexOf('}');
  if (start < 0 || end < start) {
    throw new Error(`Expected JSON from renet, got: ${stdout.trim().slice(0, 200) || '(empty)'}`);
  }
  return stdout.slice(start, end + 1);
}

/**
 * Like extractJsonObject, but for a payload that may be an array or a bare
 * `null` (which is what Go prints for an empty slice, and what `job list`
 * returns for an empty spool).
 */
function extractJsonValue(stdout: string): string {
  const trimmed = stdout.trim();
  const start = trimmed.search(/[[{]|null/);
  if (start < 0) {
    throw new Error(`Expected JSON from renet, got: ${trimmed.slice(0, 200) || '(empty)'}`);
  }
  return trimmed.slice(start);
}

/**
 * Map a terminal job status onto the ExecuteResult the rest of the CLI expects,
 * so a detached run renders and exits exactly like a synchronous one.
 *
 * The duration comes from the job's own timestamps, not from how long the CLI
 * happened to be watching: with a detached job those are different numbers, and
 * the one the operator cares about is how long the WORK took. `wallMs` is only
 * a fallback for a malformed status.
 */
export function jobStatusToExecuteResult(
  status: JobStatus,
  wallMs: number,
  output?: Pick<JobOutputCollector, 'stdout' | 'stderr' | 'steps'>
): ExecuteResult {
  const success = status.state === 'succeeded';
  const operationDurationMs = jobDurationMs(status) ?? wallMs;

  return {
    success,
    exitCode: status.exit_code ?? (success ? EXIT_SUCCESS : EXIT_FAILURE),
    error: success ? undefined : (status.error ?? `job ${status.state}`),
    durationMs: wallMs,
    operationDurationMs,
    // A detached run reconstructs its output from the event stream (the spool is always NDJSON), so every parseCapturedJson caller sees the same stdout a synchronous run would have handed back.
    ...(output
      ? {
          stdout: output.stdout,
          stderr: output.stderr,
          ...(output.steps.length > 0 ? { steps: output.steps } : {}),
        }
      : {}),
  };
}

/** Duration between the job's own start and finish stamps, or null if unusable. */
export function jobDurationMs(status: JobStatus): number | null {
  if (!status.finished_at) return null;
  const started = Date.parse(status.started_at);
  const finished = Date.parse(status.finished_at);
  if (Number.isNaN(started) || Number.isNaN(finished) || finished < started) return null;
  return finished - started;
}
