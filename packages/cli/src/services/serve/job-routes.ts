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
import type { AuthVerifier } from './auth.js';
import type { ServeDeps } from './deps.js';
import {
  buildJobPollArgv,
  createTerminalLedger,
  DEFAULT_MAX_LINES,
  JobPollParseError,
  parseJobPollOutput,
} from './job-poll.js';

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
    try {
      const checked = await helpers.withRequestConfig(config, async () => {
        const polled = await pollAndParse(machine, jobId, sinceLine, maxLines);
        await observeTerminalPoll(jobId, {
          state: polled.status.state as TicketState,
          exitCode: polled.status.exitCode,
          finishedAt: polled.status.finishedAt,
        });
        return polled;
      });
      await auditFirstTerminal(ledger, deps, principal, machine, jobId, checked);
      return c.json(checked.body);
    } catch (error) {
      return pollFailure(c, error);
    }
  });

  app.post(PROXY_ROUTES.jobCancelPattern, async (c) => {
    const admitted = await admitOrRefuse(c, 'job cancel');
    if (admitted instanceof Response) return admitted;
    const { principal, jobId, machine, config } = admitted;
    const started = Date.now();
    const destructive = getCommand('job cancel')?.destructive ?? true;
    try {
      const status = await helpers.withRequestConfig(config, async () => {
        const conn = await connectForJobs(machine, 'read-only');
        try {
          return await cancelJob(conn, jobId);
        } finally {
          conn.lease.release();
        }
      });
      await deps.audit?.({
        principal,
        commandPath: 'job cancel',
        machineName: machine,
        params: { id: jobId },
        success: true,
        exitCode: 0,
        durationMs: Date.now() - started,
        destructive,
      });
      return c.json({
        state: status.state,
        ...(status.exit_code == null ? {} : { exitCode: status.exit_code }),
      });
    } catch (error) {
      await deps.audit?.({
        principal,
        commandPath: 'job cancel',
        machineName: machine,
        params: { id: jobId },
        success: false,
        exitCode: 1,
        durationMs: Date.now() - started,
        destructive,
      });
      return c.json({ error: error instanceof Error ? error.message : 'The cancel failed.' }, 500);
    }
  });
}

class BadJobRequest extends Error {}

/** The poll body, checked against the wire schema, with how long the exec took. */
async function pollAndParse(machine: string, jobId: string, sinceLine: number, maxLines: number) {
  const started = Date.now();
  const body = JobPollResponseSchema.parse(await pollOnce(machine, jobId, sinceLine, maxLines));
  return { body, status: body.status, durationMs: Date.now() - started };
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

/** Ship the terminal audit event the first time a poll sees the job finished, and never again. */
async function auditFirstTerminal(
  ledger: ReturnType<typeof createTerminalLedger>,
  deps: ServeDeps,
  principal: Principal,
  machine: string,
  jobId: string,
  checked: { status: { state: string; exitCode?: number; function: string }; durationMs: number }
): Promise<void> {
  if (!ledger.firstTerminal(jobId, checked.status.state)) return;
  await auditTerminal(deps, principal, machine, jobId, checked.status, checked.durationMs);
}

/** The terminal audit event, shipped by the poll that first sees the job finished. */
async function auditTerminal(
  deps: ServeDeps,
  principal: Principal,
  machine: string,
  jobId: string,
  status: { state: string; exitCode?: number; function: string },
  durationMs: number
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
    durationMs,
    destructive: false,
  });
}

function refuse(c: Context, error: unknown, helpers: JobRouteHelpers): Response {
  if (error instanceof BadJobRequest) return c.json({ error: error.message }, 400);
  const { status, message, code } = helpers.statusFor(error);
  return c.json({ error: message, ...(code ? { code } : {}) }, status);
}
