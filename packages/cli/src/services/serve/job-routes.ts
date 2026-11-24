/**
 * The poll and cancel routes of a proxied machine job (PLAN-detached-jobs Design 4).
 *
 * `/v1/command` returns once the job outlives its attach window; the client then follows with short
 * polls, each one an SSH exec of `renet job logs --since-line N --max-lines K --with-status`, so no HTTP
 * request outlives the Durable Object's idle window. Policy is anchored on the contract commands
 * `job logs` (poll) and `job cancel` (cancel), scoped to the machine. A poll that first observes a
 * terminal state ships the terminal audit event, once per job.
 */

import { getCommand } from '@rediacc/shared/cli-contract';
import { JobPollResponseSchema, PROXY_ROUTES } from '@rediacc/shared/cli-contract/wire';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import type { Context, Hono } from 'hono';
import { shellQuote } from '../../utils/shell-quote.js';
import { assertJobId } from '../executor/job-client.js';
import { cancelJob, connectForJobs, runJobCommand } from '../executor/job-remote.js';
import { observeTerminalPoll } from '../jobs/executor-observation.js';
import type { TicketState } from '../jobs/ticket-store.js';
import { AUDIT_UNAVAILABLE, AuditUnavailableError } from './audit.js';
import type { AuthVerifier } from './auth.js';
import type { ExecutorAuditEvent, ServeDeps } from './deps.js';
import {
  buildJobPollArgv,
  createTerminalLedger,
  DEFAULT_MAX_LINES,
  JobPollParseError,
  parseJobPollOutput,
} from './job-poll.js';
import { withRouteSpan } from './route-span.js';

type Principal = Awaited<ReturnType<AuthVerifier['verify']>>;

interface Admitted {
  principal: Principal;
  jobId: string;
  machine: string;
  config: RdcConfig | undefined;
}

/** What server.ts lends this module, so the two cannot disagree on authentication, status mapping or config scope. */
export interface JobRouteHelpers {
  authenticate: (header: string | undefined) => Promise<Principal>;
  statusFor: (error: unknown) => {
    status: 400 | 401 | 403 | 404 | 500;
    message: string;
    code?: string;
  };
  requestScopedConfig: (config: RdcConfig) => RdcConfig | undefined;
  withRequestConfig: <T>(config: RdcConfig | undefined, fn: () => Promise<T>) => Promise<T>;
  configSession: (header: string | undefined) => string | undefined;
}

function intParam(raw: string | undefined, fallback: number): number {
  if (!raw) return fallback;
  const parsed = Number.parseInt(raw, 10);
  return Number.isNaN(parsed) || parsed < 0 ? fallback : parsed;
}

export function registerJobRoutes(app: Hono, deps: ServeDeps, helpers: JobRouteHelpers): void {
  const ledger = createTerminalLedger();

  /** Authenticate, validate the id and machine, and authorize the contract command; the config comes back for the exec. */
  async function admit(
    header: string | undefined,
    sessionHeader: string | undefined,
    rawId: string,
    machine: string | undefined,
    commandPath: 'job logs' | 'job cancel'
  ): Promise<Admitted> {
    const principal = await helpers.authenticate(header);
    const jobId = assertJobId(rawId);
    if (!machine) throw new BadJobRequest('The "machine" query parameter is required.');
    const session = helpers.configSession(sessionHeader);
    if (session) deps.sessions.sessionForExec(principal, session);
    const config = await deps.loadConfig(principal, session);
    deps.authorize({ principal, commandPath, config, machineName: machine });
    return { principal, jobId, machine, config: helpers.requestScopedConfig(config) };
  }

  async function admitOrRefuse(
    c: Context,
    commandPath: 'job logs' | 'job cancel'
  ): Promise<Admitted | Response> {
    try {
      return await admit(
        c.req.header('authorization'),
        c.req.header('x-config-session'),
        c.req.param('id') ?? '',
        c.req.query('machine'),
        commandPath
      );
    } catch (error) {
      return refuse(c, error, helpers);
    }
  }

  app.get(PROXY_ROUTES.jobPollPattern, async (c) => {
    const admitted = await admitOrRefuse(c, 'job logs');
    if (admitted instanceof Response) return admitted;
    const { principal, jobId, machine, config } = admitted;
    const sinceLine = intParam(c.req.query('sinceLine'), 0);
    const maxLines = intParam(c.req.query('maxLines'), DEFAULT_MAX_LINES);
    return withRouteSpan('job-poll', principal, async () => {
      try {
        const checked = await helpers.withRequestConfig(config, async () => {
          const polled = await pollAndParse(machine, jobId, sinceLine, maxLines);
          await observeTerminalPoll(jobId, {
            state: polled.status.state as TicketState,
            exitCode: polled.status.exitCode,
            finishedAt: polled.status.finishedAt,
            function: polled.status.function,
            repoGuid: polled.repoGuid,
          });
          return polled;
        });
        await auditFirstTerminal(ledger, deps, principal, machine, jobId, checked);
        await recordJobEnd(deps, jobId, checked.status);
        return c.json(checked.body);
      } catch (error) {
        return pollFailure(c, error);
      }
    });
  });

  app.post(PROXY_ROUTES.jobCancelPattern, async (c) => {
    const admitted = await admitOrRefuse(c, 'job cancel');
    if (admitted instanceof Response) return admitted;
    const { principal, jobId, machine, config } = admitted;
    const started = Date.now();
    const destructive = getCommand('job cancel')?.destructive ?? true;
    const cancelEvent = (success: boolean, outcome?: 'started'): ExecutorAuditEvent => ({
      principal,
      commandPath: 'job cancel',
      machineName: machine,
      params: { id: jobId },
      success,
      exitCode: success ? 0 : 1,
      durationMs: outcome ? 0 : Date.now() - started,
      destructive,
      ...(outcome ? { outcome } : {}),
    });
    // A cancel changes a machine: it is recorded before it runs, and refused when that record cannot be delivered (PLAN-rmcp-writeback.md Design 8).
    const unrecorded = await undeliveredAudit(deps, cancelEvent(true, 'started'));
    if (unrecorded) {
      return c.json(
        {
          error: `The executor refuses "rdc job cancel": its audit record could not be delivered (${unrecorded}), and a change it cannot record is not made.`,
          code: AUDIT_UNAVAILABLE,
        },
        503
      );
    }
    return withRouteSpan('job-cancel', principal, async () => {
      const outcome = await helpers
        .withRequestConfig(config, () => cancelOnMachine(machine, jobId))
        .then(
          (status) => ({ status }),
          (error: unknown) => ({ error })
        );
      const auditFailed = await undeliveredAudit(deps, cancelEvent(!('error' in outcome)));
      const answer = cancelAnswer(outcome, auditFailed);
      return c.json(answer.body, answer.status);
    });
  });
}

type CancelStatus = Awaited<ReturnType<typeof cancelJob>>;

/** The cancel route's answer: the job's state, or the failure; `audit_failed` when its record was not delivered. */
function cancelAnswer(
  outcome: { status: CancelStatus } | { error: unknown },
  auditFailed: string | undefined
): { body: Record<string, unknown>; status: 200 | 500 } {
  const audit = auditFailed ? { audit_failed: auditFailed } : {};
  if ('error' in outcome) {
    const message = outcome.error instanceof Error ? outcome.error.message : 'The cancel failed.';
    return { body: { error: message, ...audit }, status: 500 };
  }
  const { state, exit_code: exitCode } = outcome.status;
  return { body: { state, ...(exitCode == null ? {} : { exitCode }), ...audit }, status: 200 };
}

/** `renet job cancel` on the job's machine, over a pooled connection. */
async function cancelOnMachine(machine: string, jobId: string) {
  const conn = await connectForJobs(machine, 'read-only');
  try {
    return await cancelJob(conn, jobId);
  } finally {
    conn.lease.release();
  }
}

/**
 * Ship one audit event. Undefined when it was delivered, otherwise why not: the
 * caller refuses a change whose record it could not ship before, and reports
 * `audit_failed` for one already made.
 */
async function undeliveredAudit(
  deps: ServeDeps,
  event: ExecutorAuditEvent
): Promise<string | undefined> {
  try {
    await deps.audit?.(event);
    return undefined;
  } catch (error) {
    if (!(error instanceof AuditUnavailableError)) throw error;
    return error.message;
  }
}

class BadJobRequest extends Error {}

/** The poll body, checked against the wire schema, with how long the exec took. */
async function pollAndParse(machine: string, jobId: string, sinceLine: number, maxLines: number) {
  const started = Date.now();
  const polled = await pollOnce(machine, jobId, sinceLine, maxLines);
  const body = JobPollResponseSchema.parse(polled);
  // The wire body does not carry the repo GUID; it stays server side, for rebuilding a ticket the executor lost.
  return {
    body,
    status: body.status,
    repoGuid: polled.status.repoGuid,
    durationMs: Date.now() - started,
  };
}

/** One `renet job logs --with-status` exec, parsed into a poll body. */
async function pollOnce(machine: string, jobId: string, sinceLine: number, maxLines: number) {
  const conn = await connectForJobs(machine, 'read-only');
  try {
    const argv = buildJobPollArgv(jobId, sinceLine, maxLines).map(shellQuote).join(' ');
    const stdout = await runJobCommand(
      conn,
      `sudo ${shellQuote(conn.remoteRenetPath)} ${argv}`,
      `poll job ${jobId}`
    );
    return parseJobPollOutput(stdout, { sinceLine, maxLines });
  } finally {
    conn.lease.release();
  }
}

/** A failed poll: a body renet's output could not be parsed into is a bad gateway, anything else a server fault. */
function pollFailure(c: Context, error: unknown): Response {
  const message = error instanceof Error ? error.message : 'The poll failed.';
  return c.json({ error: message }, error instanceof JobPollParseError ? 502 : 500);
}

/**
 * Ship the terminal audit event the first time a poll sees the job finished. An
 * event the sink could not deliver is forgotten by the ledger, so the next poll
 * of the job tries again; the poll itself still answers, since the job's end is
 * a fact whether or not its record arrived.
 */
async function auditFirstTerminal(
  ledger: ReturnType<typeof createTerminalLedger>,
  deps: ServeDeps,
  principal: Principal,
  machine: string,
  jobId: string,
  checked: { status: JobStatusForAudit; durationMs: number }
): Promise<void> {
  if (!ledger.firstTerminal(jobId, checked.status.state)) return;
  try {
    await auditTerminal(deps, principal, machine, jobId, checked.status, checked.durationMs);
  } catch (error) {
    if (!(error instanceof AuditUnavailableError)) throw error;
    ledger.forget(jobId);
  }
}

/** A poll that sees a terminal state closes the run index row of a detached run this process remembers. */
async function recordJobEnd(
  deps: ServeDeps,
  jobId: string,
  status: { state: string; exitCode?: number }
): Promise<void> {
  const { state } = status;
  if (state !== 'succeeded' && state !== 'failed' && state !== 'cancelled') return;
  await deps.runIndex?.endJob(jobId, {
    state,
    ...(status.exitCode === undefined ? {} : { exitCode: status.exitCode }),
  });
}

interface JobStatusForAudit {
  state: string;
  exitCode?: number;
  function: string;
  startedAt?: string;
  finishedAt?: string;
}

/** How long the JOB ran, from its own status file; the poll's exec time is the fallback for a status that carries no usable pair. */
function jobDurationMs(status: JobStatusForAudit, pollMs: number): number {
  const started = status.startedAt ? Date.parse(status.startedAt) : Number.NaN;
  const finished = status.finishedAt ? Date.parse(status.finishedAt) : Number.NaN;
  return Number.isNaN(started) || Number.isNaN(finished) || finished < started
    ? pollMs
    : finished - started;
}

/** The terminal audit event, shipped by the poll that first sees the job finished. */
async function auditTerminal(
  deps: ServeDeps,
  principal: Principal,
  machine: string,
  jobId: string,
  status: JobStatusForAudit,
  pollMs: number
): Promise<void> {
  const succeeded = status.state === 'succeeded';
  await deps.audit?.({
    principal,
    commandPath: 'job logs',
    functionName: status.function,
    machineName: machine,
    params: { id: jobId, terminal: status.state },
    success: succeeded,
    exitCode: status.exitCode ?? (succeeded ? 0 : 1),
    durationMs: jobDurationMs(status, pollMs),
    destructive: false,
    jobId,
    outcome: terminalOutcomeOf(status.state),
  });
}

function terminalOutcomeOf(state: string): 'succeeded' | 'failed' | 'cancelled' {
  return state === 'succeeded' || state === 'cancelled' ? state : 'failed';
}

function refuse(c: Context, error: unknown, helpers: JobRouteHelpers): Response {
  if (error instanceof BadJobRequest) return c.json({ error: error.message }, 400);
  const { status, message, code } = helpers.statusFor(error);
  return c.json({ error: message, ...(code ? { code } : {}) }, status);
}
