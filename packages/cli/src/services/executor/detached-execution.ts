/**
 * Running a renet call as a machine job (agent/plans/PLAN-detached-jobs.md
 * sections 14-17): one `renet job start --request-id --attach` exec that starts
 * the job and streams its events, a reattach from the last line received when
 * that exec drops, and the ticket kept whenever the client stops watching.
 *
 * The attach window (`ExecuteOptions.attachWindowMs`, set by the entry point)
 * alone decides between a direct result and a ticket:
 *   - unlimited (a direct terminal run): attached until the job ends, through
 *     drops, for up to REATTACH_BUDGET_MS of lost transport;
 *   - finite (proxy, MCP): attached until the job ends or the window passes,
 *     whichever comes first; past it, the result is the ticket;
 *   - 0 (`--background`): the ticket the moment the job starts.
 *
 * A start whose handle never arrived is retried with the SAME request id, so
 * renet attaches the retry to the job the first start created instead of
 * running the work twice (section 17).
 */

import type { JobOverlap } from '@rediacc/shared/cli-contract/wire';
import type { SFTPClient } from '../../remote/sftp/index.js';
import { ERROR_CODES } from '../../types/errors.js';
import { EXIT_CODES } from '../../types/index.js';
import { CliExitError } from '../../utils/cli-exit-error.js';
import { getOutputFormat } from '../../utils/errors.js';
import { VERSION } from '../../version.js';
import { clusterKubeconfigRemotePath } from '../cluster/cluster-target.js';
import { getEffectiveConfigName } from '../config/config-name.js';
import type { configService } from '../config/config-resources.js';
import { outputService } from '../core/output.js';
import { currentRequestContext, writeStderr, writeStdout } from '../core/request-context.js';
import {
  attachFlagValue,
  clientKindFromEnv,
  invocationMinter,
  originJson,
  REATTACH_BUDGET_MS,
} from '../jobs/attach.js';
import { type TicketInput, type TicketKind, TicketStore } from '../jobs/ticket-store.js';
import { machineConnections } from '../machine/machine-connection.js';
import { fetchOtlpCredentials } from '../telemetry/otlp-credentials.js';
import { isTelemetryDisabled } from '../telemetry/telemetry.js';
import { type AttachState, type StartOutcome, startOnce } from './detached-attach.js';
import {
  backgroundEnvelope,
  backgroundStartedHint,
  buildJobStartCommand,
  createJobOutputCollector,
  followLostHint,
  isTerminalState,
  JobLogCursor,
  JobStartFailedError,
  type JobStatus,
  JobsUnsupportedError,
  jobStatusToExecuteResult,
  overlapWarningLines,
  type PreconditionRefusal,
  resumeHint,
} from './job-client.js';
import {
  FollowLostError,
  followJobLogs,
  logReconnectDelayMs,
  passthroughJobRenderer,
  readJobStatus,
  renderJobEvent,
} from './job-remote.js';
import {
  buildRenetEnv,
  detectEnvironment,
  resolveEnvSecrets,
  resolveRenetTimeoutMs,
} from './renet-command.js';
import type { ExecuteOptions, ExecuteResult, RenetEvent } from './types.js';

/**
 * The section 24 exemptions that stay on `renet execute`: an interactive exec
 * needs a live TTY, and a log follow never ends on its own. Named, so the rule
 * lives in one place and a test can pin it.
 */
export function runsOutsideJob(options: Pick<ExecuteOptions, 'functionName' | 'params'>): boolean {
  const params = options.params ?? {};
  if (params.tty === true) return true;
  if (options.functionName === 'container_logs' && params.follow === true) return true;
  return false;
}

/** The overlap refusal (section 19): exit 15, the other jobs as structured data. */
export class JobOverlapRefusedError extends CliExitError {
  constructor(
    readonly overlaps: JobOverlap[],
    machineName: string
  ) {
    const refusing = overlaps.filter((o) => o.action === 'refuse');
    const first = refusing[0];
    const holder = first ? `job ${first.jobId ?? first.unit ?? '?'}` : 'another job';
    super(
      ERROR_CODES.BUSY,
      `Refused to start the job on '${machineName}': ${holder} holds the same scope.`,
      {
        retryable: true,
        details: [
          ...refusing.flatMap(overlapWarningLines),
          ...(first?.jobId
            ? [`  Or stop it: rdc job cancel ${first.jobId} -m ${machineName}`]
            : []),
        ],
      }
    );
    this.name = 'JobOverlapRefusedError';
  }
}

/**
 * A start refused by its vault's `expect` (section 14): the machine's state is
 * not what the command was resolved against, and no unit was spawned. Exit 12,
 * the code the client-side presence probe this replaces refused with, and for
 * `repo_present` the same text, so the routing contradiction reads as before.
 */
export class JobPreconditionRefusedError extends CliExitError {
  constructor(
    readonly refusal: PreconditionRefusal,
    machineName: string
  ) {
    const machine = refusal.machine || machineName;
    super(
      ERROR_CODES.STATE_MISMATCH,
      refusal.expect === 'repo_present'
        ? `config places ${refusal.repository} on ${machine}, but ${machine} does not have its image. Run "rdc config reconcile", then retry.`
        : refusal.message
    );
    this.name = 'JobPreconditionRefusedError';
  }
}

/** The clock and pause of the start retry, seamed so a test runs the budget instantly. */
export interface JobExecutionTiming {
  now: () => number;
  sleep: (ms: number) => Promise<void>;
  budgetMs: number;
}

const realTiming: JobExecutionTiming = {
  now: Date.now,
  sleep: (ms) => new Promise<void>((resolve) => setTimeout(resolve, ms)),
  budgetMs: REATTACH_BUDGET_MS,
};

let timing: JobExecutionTiming = realTiming;

/** Test seam: replace the retry clock (pass nothing to restore real time). */
export function setJobExecutionTiming(next?: Partial<JobExecutionTiming>): void {
  timing = next ? { ...realTiming, ...next } : realTiming;
}

function repoOf(options: ExecuteOptions): string | undefined {
  return typeof options.params?.repository === 'string' ? options.params.repository : undefined;
}

/**
 * The ticket of one call. A store that cannot be written never fails the
 * command. With `owned` false the caller (`runJob`) writes the ticket, so this
 * one writes nothing.
 */
class CallTicket {
  private readonly store: TicketStore | undefined;

  constructor(
    readonly requestId: string,
    private readonly base: TicketInput,
    owned = true
  ) {
    this.store = owned ? openStore() : undefined;
  }

  append(kind: TicketKind, input: TicketInput = {}): void {
    try {
      this.store?.append(kind, this.requestId, { ...this.base, ...input });
    } catch (error) {
      outputService.warn(
        `Could not record job ticket ${this.requestId}: ${error instanceof Error ? error.message : String(error)}`
      );
    }
  }
}

function openStore(): TicketStore | undefined {
  try {
    return new TicketStore(getEffectiveConfigName());
  } catch {
    return undefined;
  }
}

type Lease = Awaited<ReturnType<typeof machineConnections.acquireFor>>;
type Launch = ReturnType<typeof buildJobStartCommand>;

/**
 * Run a renet call as a machine job and return what the window allows: the
 * job's result when it finished inside the window, else the ticket
 * (`state: 'running'`).
 */
export async function runJobExecution(
  remoteRenetPath: string,
  vault: string,
  options: ExecuteOptions,
  machine: Awaited<ReturnType<typeof configService.getLocalMachine>>,
  sshPrivateKey: string
): Promise<ExecuteResult> {
  const run = new JobRun(options);
  // Written BEFORE the start (section 16): a start whose answer is lost is still found later through its request id.
  run.ticket.append('starting', { startedAt: new Date(run.startedAt).toISOString() });

  const lease = await machineConnections.acquireFor(machine, sshPrivateKey);
  try {
    const launch = await buildLaunch(remoteRenetPath, options, run.requestId);
    const outcome = await run.start(lease, launch, vault);
    return await run.settle(outcome, lease, remoteRenetPath);
  } finally {
    lease.release();
  }
}

/** One call's job: its ticket, what the attach saw, and how the call ends. */
class JobRun {
  readonly startedAt = Date.now();
  readonly requestId: string;
  readonly window: number | undefined;
  readonly verb: string;
  readonly repo: string | undefined;
  readonly ticket: CallTicket;
  readonly state: AttachState = { lines: 0, overlaps: [], deduped: false };
  readonly collector = createJobOutputCollector();
  private readonly render: ((event: RenetEvent, line?: number) => void) | undefined;

  constructor(readonly options: ExecuteOptions) {
    this.window = options.attachWindowMs;
    this.requestId = options.requestId ?? invocationMinter().next(options.machineName);
    this.verb = options.verb ?? outputService.getCommandName() ?? options.functionName;
    this.repo = repoOf(options);
    this.render = options.onEvent ?? defaultRenderer(options);
    this.ticket = new CallTicket(
      this.requestId,
      {
        machine: options.machineName,
        via: { kind: 'ssh' },
        verb: this.verb,
        function: options.functionName,
        ...(this.repo ? { repo: this.repo } : {}),
      },
      !options.externalTicket
    );
  }

  onEvent(event: RenetEvent, line: number): void {
    this.collector.consume(event);
    this.render?.(event, line);
  }

  /** The handle arrived: the job exists. Announce it once, and warn about what it overlaps. */
  announce(jobId: string, overlaps: JobOverlap[], deduped: boolean, networkId?: number): void {
    this.state.overlaps = overlaps;
    this.state.deduped = deduped;
    if (networkId !== undefined) this.state.networkId = networkId;
    if (this.state.jobId) return;
    this.state.jobId = jobId;
    this.ticket.append('started', { jobId, state: 'running' });
    this.options.onJobStarted?.(jobId);
    for (const overlap of overlaps) {
      for (const line of overlapWarningLines(overlap)) writeStderr(`${line}\n`);
    }
  }

  /**
   * Run the start exec, retrying with the same request id while no handle has
   * arrived and the transport keeps dropping, for up to the reattach budget.
   */
  async start(lease: Lease, launch: Launch, vault: string): Promise<StartOutcome> {
    let firstDrop: number | undefined;
    for (let attempt = 0; ; attempt++) {
      const sftp = await safeEnsure(lease);
      const outcome = sftp
        ? await startOnce(sftp, launch, vault, this)
        : ({ kind: 'dropped', error: new Error('connection lost') } as const);
      if (outcome.kind !== 'dropped' || this.state.jobId) return outcome;
      firstDrop ??= timing.now();
      if (timing.now() - firstDrop >= timing.budgetMs) return outcome;
      await timing.sleep(logReconnectDelayMs(attempt));
    }
  }

  /** Turn the start's outcome into the call's result. */
  settle(
    outcome: StartOutcome,
    lease: Lease,
    remoteRenetPath: string
  ): ExecuteResult | Promise<ExecuteResult> {
    switch (outcome.kind) {
      case 'refused':
        this.ticket.append('acknowledged', { state: 'unknown' });
        throw new JobOverlapRefusedError(outcome.overlaps, this.options.machineName);
      case 'precondition':
        this.ticket.append('acknowledged', { state: 'unknown' });
        throw new JobPreconditionRefusedError(outcome.refusal, this.options.machineName);
      case 'unsupported':
        this.ticket.append('acknowledged', { state: 'unknown' });
        throw new JobsUnsupportedError(this.options.machineName, this.verb);
      case 'failed':
        throw new JobStartFailedError(this.options.machineName, outcome.detail);
      case 'interrupted':
        return this.detached();
      case 'handle':
        // `--background`: the ticket at once.
        return this.pending();
      case 'trailer':
        return this.fromTrailer();
      case 'dropped':
        // A finite window hands back the ticket; an unlimited one reattaches from the last line received.
        if (this.window !== undefined || !this.state.jobId) return this.pending();
        return this.reattach(lease, remoteRenetPath, this.state.jobId);
    }
  }

  private fromTrailer(): ExecuteResult {
    const status = this.state.status;
    // The window passed with the job still running.
    if (!status || !isTerminalState(status.state)) return this.pending();
    return this.finished(status);
  }

  private base(): Pick<ExecuteResult, 'jobId' | 'requestId' | 'overlaps' | 'networkId'> {
    return {
      ...(this.state.jobId ? { jobId: this.state.jobId } : {}),
      requestId: this.requestId,
      ...(this.state.networkId === undefined ? {} : { networkId: this.state.networkId }),
      ...(this.state.overlaps.length > 0 ? { overlaps: this.state.overlaps } : {}),
    };
  }

  private markSeen(): void {
    if (!this.state.jobId) return;
    this.ticket.append('seen', {
      jobId: this.state.jobId,
      lastSeenLine: this.state.lines,
      state: 'running',
    });
  }

  /** Follow a job again after its attach dropped, from the last line received. */
  private async reattach(
    lease: Lease,
    remoteRenetPath: string,
    jobId: string
  ): Promise<ExecuteResult> {
    const cursor = new JobLogCursor(this.state.lines);
    let interrupted: boolean;
    try {
      interrupted = await followJobLogs(
        lease,
        remoteRenetPath,
        jobId,
        {
          onEvent: (event, line) => this.onEvent(event, line ?? cursor.sinceLine),
          debug: this.options.debug,
          reconnect: { budgetMs: timing.budgetMs, now: timing.now, sleep: timing.sleep },
        },
        cursor,
        this.options.machineName
      );
    } catch (error) {
      if (!(error instanceof FollowLostError)) throw error;
      this.state.lines = error.sinceLine;
      return this.followLost(jobId);
    }
    this.state.lines = cursor.sinceLine;
    if (interrupted) return this.detached();

    const status = await readJobStatus(
      await lease.ensure(),
      remoteRenetPath,
      jobId,
      this.options.machineName
    );
    return this.finished(status);
  }

  /** The job ended while the client watched: its result, and nothing pending. */
  private finished(status: JobStatus): ExecuteResult {
    const result = jobStatusToExecuteResult(status, Date.now() - this.startedAt, this.collector);
    this.ticket.append('finished', {
      jobId: status.job_id,
      state: status.state,
      lastSeenLine: this.state.lines,
      exitCode: result.exitCode,
      ...(status.finished_at ? { finishedAt: status.finished_at } : {}),
    });
    this.ticket.append('acknowledged');
    return { ...result, ...this.base(), state: status.state, attached: true };
  }

  /** The ticket, for a job still running when the call returns (`-b`, or past the window). */
  private pending(): ExecuteResult {
    this.markSeen();
    if (this.state.jobId) {
      emitTicket(
        this.state.jobId,
        this.options.machineName,
        this.verb,
        this.repo,
        this.state.overlaps
      );
    }
    return {
      ...this.base(),
      success: true,
      exitCode: 0,
      durationMs: Date.now() - this.startedAt,
      state: 'running',
      attached: false,
    };
  }

  /** The transport stayed gone past the budget: the job runs on, the ticket is kept (section 16). */
  private followLost(jobId: string): ExecuteResult {
    this.markSeen();
    const hint = followLostHint(jobId, this.options.machineName);
    writeStderr(`\n${hint}\n`);
    return {
      ...this.base(),
      success: false,
      exitCode: EXIT_CODES.FOLLOW_LOST,
      error: hint,
      durationMs: Date.now() - this.startedAt,
      outputEchoed: true,
      state: 'running',
      attached: false,
    };
  }

  /** Ctrl-C: the operator stopped watching; the job keeps running and the ticket is kept. */
  private detached(): ExecuteResult {
    this.markSeen();
    const hint = resumeHint(this.state.jobId ?? this.requestId, this.options.machineName);
    writeStderr(`\n${hint}\n`);
    return {
      ...this.base(),
      success: false,
      exitCode: EXIT_CODES.DETACHED,
      error: hint,
      durationMs: Date.now() - this.startedAt,
      outputEchoed: true,
      state: 'running',
      attached: false,
    };
  }
}

/** How a call renders its job's events when the caller set no renderer. */
function defaultRenderer(options: ExecuteOptions): ((event: RenetEvent) => void) | undefined {
  if (options.captureOutput) return undefined;
  if (options.passthroughOutput) return passthroughJobRenderer(!options.quietSpinners);
  if (options.debug) return renderJobEvent;
  // Renet's own output lines are chatter for every verb that did not ask for them, as on the `renet execute` path: steps and problems render, output does not.
  return (event) => {
    if (event.type !== 'output') renderJobEvent(event);
  };
}

/** Build the `job start` launch: env (secrets on stdin), ceiling, request id, window, origin and steps. */
async function buildLaunch(
  remoteRenetPath: string,
  options: ExecuteOptions,
  requestId: string
): Promise<Launch> {
  const otlpCreds = isTelemetryDisabled() ? null : await fetchOtlpCredentials();
  const envSecrets = await resolveEnvSecrets(repoOf(options));
  const kubeconfig = options.kubeCluster
    ? clusterKubeconfigRemotePath(options.kubeCluster)
    : undefined;
  const window = options.attachWindowMs;
  const steps = options.jobSteps ?? [];
  return buildJobStartCommand({
    remoteRenetPath,
    env: buildRenetEnv({
      isDevelopment: detectEnvironment() === 'development',
      telemetryDisabled: isTelemetryDisabled(),
      otlpCreds,
      envSecrets,
      kubeconfig,
    }),
    timeoutMs: resolveRenetTimeoutMs(options.functionName, options.timeout),
    debug: options.debug,
    requestId,
    ...(window === 0 ? {} : { attach: attachFlagValue(window) }),
    origin: originJson({
      client: currentRequestContext() ? 'proxy' : clientKindFromEnv(),
      version: VERSION,
      config: { name: safeConfigName() },
    }),
    ...(steps.length > 0 ? { steps: JSON.stringify(steps) } : {}),
  });
}

function safeConfigName(): string | undefined {
  try {
    return getEffectiveConfigName();
  } catch {
    return undefined;
  }
}

async function safeEnsure(lease: Lease): Promise<SFTPClient | undefined> {
  try {
    return await lease.ensure();
  } catch {
    return undefined;
  }
}

/**
 * Hand the ticket to the operator. A served dispatch carries it on the wire
 * (the result's jobId and state), so nothing is printed there. Under `-o json`
 * stdout carries the one envelope; in text mode the hint goes to stderr, because
 * stdout belongs to the command (section 26).
 */
function emitTicket(
  jobId: string,
  machine: string,
  verb: string,
  repo: string | undefined,
  overlaps: JobOverlap[]
): void {
  if (currentRequestContext()) return;
  if (getOutputFormat() === 'json') {
    writeStdout(
      `${JSON.stringify(backgroundEnvelope({ jobId, machine, verb, repo, overlaps }))}\n`
    );
    return;
  }
  writeStderr(`${backgroundStartedHint(jobId, machine)}\n`);
}
