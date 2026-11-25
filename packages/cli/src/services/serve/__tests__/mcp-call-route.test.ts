/**
 * `POST /v1/mcp/call` (agent/plans/PLAN-rmcp-agent-grants.md box AG-X, #749b6346): the container's handler for one hosted
 * MCP `tools/call`. The serve app is real, the account server is a fake with real ciphertext (agent-grant-harness.ts), and the
 * executor seam records what would have run on a machine. Each case is a call as the MCP Worker posts it.
 */

import { Hono } from 'hono';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ExecuteOptions, ExecuteResult } from '../../executor/types.js';
import { AgentGrantSessions } from '../agent-grant-session.js';
import { AuditUnavailableError } from '../audit.js';
import { routeAgentPrincipals } from '../container-config.js';
import { serveCrypto } from '../crypto.js';
import type { ExecutorAuditEvent, ServeDeps } from '../deps.js';
import { authorize } from '../policy.js';
import { createServeApp } from '../server.js';
import { SessionStore } from '../sessions.js';
import {
  EXECUTOR_TOKEN,
  type FakeAccount,
  type FakeGrant,
  fakeAccount,
  makeGrant,
  ORG_ID,
} from './agent-grant-harness.js';

// The dispatched command reads its config through the REAL configService, which must serve the config the grant session decrypted. The config dir points at an empty scratch directory, so a dispatch that fell through to the disk would find no machine.
await vi.hoisted(async () => {
  const { mkdtempSync } = await import('node:fs');
  const { tmpdir } = await import('node:os');
  const scratch = mkdtempSync(`${tmpdir()}/rdc-mcp-call-`);
  process.env.XDG_CONFIG_HOME = scratch;
  process.env.XDG_STATE_HOME = scratch;
  process.env.XDG_CACHE_HOME = scratch;
});
process.env.REDIACC_TELEMETRY_DISABLED = '1';
process.env.REDIACC_MCP_JOB_WAIT_INTERVAL_MS = '10';

// `job status` reads a machine over SSH; the job_wait cases script its answers instead, and every other dispatch is the real one.
const { dispatchStub } = vi.hoisted(() => ({
  dispatchStub: { run: undefined as undefined | (() => unknown) },
}));
vi.mock('../command-dispatch.js', async (original) => {
  const real = await original<typeof import('../command-dispatch.js')>();
  return {
    ...real,
    dispatchCommand: (args: Parameters<typeof real.dispatchCommand>[0]) =>
      dispatchStub.run ? Promise.resolve(dispatchStub.run()) : real.dispatchCommand(args),
  };
});

type Grant = Awaited<ReturnType<typeof makeGrant>>;

interface Booted {
  app: Hono;
  account: FakeAccount;
  sessions: AgentGrantSessions;
  executed: ExecuteOptions[];
  audited: ExecutorAuditEvent[];
  grants: Record<string, Grant>;
  setExecutor: (run: (options: ExecuteOptions) => Promise<ExecuteResult>) => void;
  setAudit: (audit: (event: ExecutorAuditEvent) => Promise<void>) => void;
}

/**
 * The authorizer these cases run under. The account's `agent-session` answer carries neither a policy nor the grant user's org
 * role yet, so the real `authorize` reads a grant principal as a policy-less `member` and refuses everything (the last case
 * pins that). This stands in for the missing role, so the cases below test the rest of the route: the checks
 * that are the route's own, and the `decide` rules that need no policy (grand repos, cluster ops).
 */
const asOwner: ServeDeps['authorize'] = (args) =>
  authorize({ ...args, principal: { ...args.principal, orgRole: 'owner' } });

async function boot(
  specs: Parameters<typeof makeGrant>[0][],
  mode: ServeDeps['mode'] = 'container',
  authorizer: ServeDeps['authorize'] = asOwner
): Promise<Booted> {
  const made = await Promise.all(specs.map((spec) => makeGrant(spec)));
  const account = fakeAccount(made);
  const sessions = new AgentGrantSessions({
    accountUrl: 'https://account.test',
    executorToken: EXECUTOR_TOKEN,
    orgId: ORG_ID,
    fetchImpl: account.fetch,
  });
  const executed: ExecuteOptions[] = [];
  const audited: ExecutorAuditEvent[] = [];
  let run: (options: ExecuteOptions) => Promise<ExecuteResult> = () =>
    Promise.resolve({ success: true, exitCode: 0, durationMs: 1, stdout: 'ok' });
  let audit: (event: ExecutorAuditEvent) => Promise<void> = (event) => {
    audited.push(event);
    return Promise.resolve();
  };
  const deps: ServeDeps = {
    mode,
    auth: {
      verify: () => Promise.reject(new Error('the call route takes no bearer')),
      canWriteAudit: () => Promise.resolve({ ok: true }),
    } as unknown as ServeDeps['auth'],
    sessions: new SessionStore(),
    crypto: serveCrypto,
    executor: {
      execute: (options: ExecuteOptions) => {
        executed.push(options);
        return run(options);
      },
    },
    loadConfig: routeAgentPrincipals(
      () => Promise.reject(new Error('a grant call never reaches the user loader')),
      sessions
    ),
    agentGrants: sessions,
    authorize: authorizer,
    audit: (event) => audit(event),
  };
  return {
    app: createServeApp(deps),
    account,
    sessions,
    executed,
    audited,
    grants: Object.fromEntries(made.map((grant) => [grant.grantId, grant])),
    setExecutor: (next) => {
      run = next;
    },
    setAudit: (next) => {
      audit = next;
    },
  };
}

interface CallBody {
  tool: string;
  args?: Record<string, unknown>;
  attachMs?: number;
  secret?: string;
}

function call(world: Booted, grant: FakeGrant, body: CallBody) {
  return world.app.request('/v1/mcp/call', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      grantId: grant.grantId,
      secret: body.secret ?? grant.secret,
      tool: body.tool,
      args: body.args ?? {},
      requestId: `req-${Math.random().toString(16).slice(2)}`,
      attachMs: body.attachMs ?? 45_000,
    }),
  });
}

interface Answer {
  result?: {
    isError?: boolean;
    content: { text: string }[];
    structuredContent?: { code?: string; message?: string };
  };
  job?: { jobId: string; machine?: string };
}

const answerOf = async (response: Response): Promise<Answer> => (await response.json()) as Answer;
const codeOf = (answer: Answer) => answer.result?.structuredContent?.code;

const GRAND = { ref: 'demo' };

beforeEach(() => {
  vi.spyOn(console, 'warn').mockImplementation(() => undefined);
});
afterEach(() => {
  vi.restoreAllMocks();
  dispatchStub.run = undefined;
});

describe('POST /v1/mcp/call', () => {
  it('runs the tool against the grant session config and answers the tool result', async () => {
    const world = await boot([
      { grantId: 'g_a', teamId: 'team-a', configId: 'cfg-a', machine: 'machine-a' },
    ]);
    const grant = world.grants.g_a as Grant;
    const resolved: { ip: string; key: string | undefined }[] = [];
    const { configService } = await import('../../config/config-resources.js');
    world.setExecutor(async (options) => {
      const machine = await configService.getLocalMachine(options.machineName);
      const local = await configService.getLocalConfig();
      resolved.push({ ip: machine.ip, key: local.sshPrivateKey });
      return { success: true, exitCode: 0, durationMs: 1, stdout: 'ok' };
    });

    const response = await call(world, grant, { tool: 'repo_status', args: GRAND });
    expect(response.status).toBe(200);
    const answer = await answerOf(response);

    expect(answer.result?.isError).toBe(false);
    expect(answer.job).toBeUndefined();
    expect(world.executed).toHaveLength(1);
    expect(world.executed[0]?.machineName).toBe('machine-a');
    // Execution ran against the DECRYPTED grant config, not the container's empty disk.
    expect(resolved).toEqual([{ ip: '10.9.9.9', key: 'KEY-cfg-a' }]);
    // The secret never rode into the executor seam or the audit.
    expect(JSON.stringify([world.executed, world.audited])).not.toContain(grant.secret);
  });

  it('keeps two grants of one user apart: each call runs on its own grant config', async () => {
    const world = await boot([
      { grantId: 'g_a', teamId: 'team-a', configId: 'cfg-a', machine: 'machine-a' },
      { grantId: 'g_b', teamId: 'team-b', configId: 'cfg-b', machine: 'machine-b' },
    ]);
    await call(world, world.grants.g_a as Grant, { tool: 'repo_status', args: GRAND });
    await call(world, world.grants.g_b as Grant, { tool: 'repo_status', args: GRAND });
    expect(world.executed.map((options) => options.machineName)).toEqual([
      'machine-a',
      'machine-b',
    ]);
  });

  it('answers an ended grant with its code and runs nothing, for a wrong secret and a refused grant', async () => {
    const world = await boot([
      { grantId: 'g_a', teamId: 'team-a', configId: 'cfg-a', machine: 'machine-a' },
      { grantId: 'g_b', teamId: 'team-b', configId: 'cfg-b', machine: 'machine-b' },
    ]);
    const a = world.grants.g_a as Grant;
    const b = world.grants.g_b as Grant;
    // First open succeeds; a wrong secret for the warm grant is refused without running anything.
    await call(world, a, { tool: 'repo_status', args: GRAND });
    world.executed.length = 0;

    const wrong = await answerOf(
      await call(world, a, { tool: 'repo_status', args: GRAND, secret: b.secret })
    );
    expect(codeOf(wrong)).toBe('REDIACC_GRANT_REVOKED');

    world.account.refused.add('g_b');
    const refused = await answerOf(await call(world, b, { tool: 'repo_status', args: GRAND }));
    expect(codeOf(refused)).toBe('REDIACC_GRANT_REVOKED');
    expect(world.executed).toEqual([]);
    expect(JSON.stringify([wrong, refused])).not.toContain(b.secret);
  });

  it('refuses a tool outside the grant scope: read-only flag, tool allowlist, unknown tool', async () => {
    const world = await boot([
      { grantId: 'g_ro', configId: 'cfg-ro', machine: 'machine-a', scope: { readOnly: true } },
      {
        grantId: 'g_list',
        configId: 'cfg-l',
        machine: 'machine-a',
        scope: { readOnly: false, tools: ['repo_list'] },
      },
    ]);
    const ro = world.grants.g_ro as Grant;
    const list = world.grants.g_list as Grant;

    const write = await answerOf(await call(world, ro, { tool: 'repo_delete', args: GRAND }));
    const other = await answerOf(await call(world, list, { tool: 'repo_status', args: GRAND }));
    const unknown = await answerOf(await call(world, ro, { tool: 'repo_nope' }));

    expect(codeOf(write)).toBe('POLICY_DENIED');
    expect(codeOf(other)).toBe('POLICY_DENIED');
    expect(codeOf(unknown)).toBe('INVALID_REQUEST');
    expect(world.executed).toEqual([]);
  });

  it('enforces the grant machine globs against the machine the repo resolves to', async () => {
    const world = await boot([
      {
        grantId: 'g_m',
        configId: 'cfg-m',
        machine: 'machine-a',
        scope: { readOnly: false, machines: ['other-*'] },
      },
      {
        grantId: 'g_ok',
        configId: 'cfg-ok',
        machine: 'machine-a',
        scope: { readOnly: false, machines: ['machine-*'] },
      },
    ]);
    const outside = await answerOf(
      await call(world, world.grants.g_m as Grant, { tool: 'repo_status', args: GRAND })
    );
    expect(codeOf(outside)).toBe('POLICY_DENIED');
    expect(outside.result?.structuredContent?.message).toContain('machine-a');
    expect(world.executed).toEqual([]);

    const inside = await answerOf(
      await call(world, world.grants.g_ok as Grant, { tool: 'repo_status', args: GRAND })
    );
    expect(inside.result?.isError).toBe(false);
    expect(world.executed).toHaveLength(1);
  });

  it('enforces the grant repo globs, and refuses a call that names no repo when repos are limited', async () => {
    const world = await boot([
      {
        grantId: 'g_r',
        configId: 'cfg-r',
        machine: 'machine-a',
        scope: { readOnly: false, repos: ['shop*'] },
      },
    ]);
    const grant = world.grants.g_r as Grant;
    const outside = await answerOf(await call(world, grant, { tool: 'repo_status', args: GRAND }));
    const unnamed = await answerOf(
      await call(world, grant, { tool: 'repo_list', args: { machine: 'machine-a' } })
    );
    expect(codeOf(outside)).toBe('POLICY_DENIED');
    expect(outside.result?.structuredContent?.message).toContain('demo');
    expect(codeOf(unnamed)).toBe('POLICY_DENIED');
    expect(world.executed).toEqual([]);
  });

  it('refuses a grand-repo change for an agent with no opt-in, before any host call', async () => {
    const world = await boot([{ grantId: 'g_a', configId: 'cfg-a', machine: 'machine-a' }]);
    const answer = await answerOf(
      await call(world, world.grants.g_a as Grant, { tool: 'repo_delete', args: GRAND })
    );
    expect(codeOf(answer)).toBe('POLICY_DENIED');
    expect(world.executed).toEqual([]);
    expect(world.audited).toEqual([]);
  });

  it('answers the job handle of a run that outlived the window, and keeps the dispatch counted', async () => {
    const world = await boot([{ grantId: 'g_a', configId: 'cfg-a', machine: 'machine-a' }]);
    world.setExecutor(() =>
      Promise.resolve({
        success: true,
        exitCode: 0,
        durationMs: 1,
        state: 'running',
        jobId: 'job-9',
      })
    );
    const answer = await answerOf(
      await call(world, world.grants.g_a as Grant, { tool: 'repo_status', args: GRAND })
    );
    expect(answer.job).toEqual({ jobId: 'job-9', machine: 'machine-a' });
    expect(answer.result).toBeUndefined();
  });

  it('answers the job handle when the window passes with a job started and the dispatch still running', async () => {
    const world = await boot([{ grantId: 'g_a', configId: 'cfg-a', machine: 'machine-a' }]);
    let release: (() => void) | undefined;
    world.setExecutor(
      (options) =>
        new Promise<ExecuteResult>((resolve) => {
          options.onJobStarted?.('job-slow', options.machineName);
          release = () => resolve({ success: true, exitCode: 0, durationMs: 1, stdout: 'late' });
        })
    );
    const answer = await answerOf(
      await call(world, world.grants.g_a as Grant, {
        tool: 'repo_status',
        args: GRAND,
        attachMs: 30,
      })
    );
    expect(answer.job).toEqual({ jobId: 'job-slow', machine: 'machine-a' });
    release?.();
  });

  it('answers TIMEOUT, not a job, when the window passes before any job started', async () => {
    const world = await boot([{ grantId: 'g_a', configId: 'cfg-a', machine: 'machine-a' }]);
    let release: (() => void) | undefined;
    world.setExecutor(
      () =>
        new Promise<ExecuteResult>((resolve) => {
          release = () => resolve({ success: true, exitCode: 0, durationMs: 1 });
        })
    );
    const answer = await answerOf(
      await call(world, world.grants.g_a as Grant, {
        tool: 'repo_status',
        args: GRAND,
        attachMs: 30,
      })
    );
    expect(codeOf(answer)).toBe('TIMEOUT');
    release?.();
  });

  it('answers a failed command as an isError result with its envelope', async () => {
    const world = await boot([{ grantId: 'g_a', configId: 'cfg-a', machine: 'machine-a' }]);
    world.setExecutor(() =>
      Promise.resolve({
        success: false,
        exitCode: 1,
        durationMs: 1,
        error: 'ssh refused',
        errorCode: 'SSH_REFUSED',
      })
    );
    const answer = await answerOf(
      await call(world, world.grants.g_a as Grant, { tool: 'repo_status', args: GRAND })
    );
    expect(answer.result?.isError).toBe(true);
    const envelope = JSON.parse(answer.result?.content[0]?.text ?? '{}') as {
      success: boolean;
      errors: { code: string }[];
    };
    expect(envelope.success).toBe(false);
    expect(envelope.errors[0]?.code).toBe('SSH_REFUSED');
  });

  it('is not registered in daemon mode, and refuses a malformed or smuggling body', async () => {
    const daemon = await boot(
      [{ grantId: 'g_a', configId: 'cfg-a', machine: 'machine-a' }],
      'daemon'
    );
    const absent = await call(daemon, daemon.grants.g_a as Grant, {
      tool: 'repo_status',
      args: GRAND,
    });
    expect(absent.status).toBe(404);

    const world = await boot([{ grantId: 'g_a', configId: 'cfg-a', machine: 'machine-a' }]);
    const bad = await world.app.request('/v1/mcp/call', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        grantId: 'g_a',
        secret: 's',
        tool: 'repo_status',
        args: {},
        requestId: 'r',
        attachMs: 10,
        extra: 1,
      }),
    });
    expect(bad.status).toBe(400);
  });

  it('refuses a mutating command whose started record cannot be delivered, and runs nothing', async () => {
    const world = await boot([{ grantId: 'g_a', configId: 'cfg-a', machine: 'machine-a' }]);
    world.setAudit(() => Promise.reject(new AuditUnavailableError('the account server is down')));
    const answer = await answerOf(
      await call(world, world.grants.g_a as Grant, {
        tool: 'machine_setup',
        args: { name: 'machine-a' },
      })
    );
    expect(codeOf(answer)).toBe('AUDIT_UNAVAILABLE');
    expect(world.executed).toEqual([]);
  });

  it('audits a mutating command as started before it runs and records its outcome, with no secret in either', async () => {
    const world = await boot([{ grantId: 'g_a', configId: 'cfg-a', machine: 'machine-a' }]);
    const grant = world.grants.g_a as Grant;
    const order: string[] = [];
    world.setAudit((event) => {
      order.push(`audit:${event.outcome ?? 'finished'}`);
      world.audited.push(event);
      return Promise.resolve();
    });
    world.setExecutor(() => {
      order.push('execute');
      return Promise.resolve({ success: true, exitCode: 0, durationMs: 1, stdout: 'ok' });
    });

    const answer = await answerOf(
      await call(world, grant, { tool: 'machine_restart-services', args: { name: 'machine-a' } })
    );

    expect(answer.result?.isError).toBe(false);
    expect(order[0]).toBe('audit:started');
    expect(order).toContain('execute');
    expect(order.indexOf('audit:started')).toBeLessThan(order.indexOf('execute'));
    expect(world.audited.at(-1)?.success).toBe(true);
    expect(JSON.stringify(world.audited)).not.toContain(grant.secret);
  });

  it('refuses every command under the real authorizer: a grant has no policy and no role yet (fail closed)', async () => {
    const world = await boot(
      [{ grantId: 'g_a', configId: 'cfg-a', machine: 'machine-a' }],
      'container',
      authorize
    );
    const answer = await answerOf(
      await call(world, world.grants.g_a as Grant, { tool: 'repo_status', args: GRAND })
    );
    expect(codeOf(answer)).toBe('POLICY_DENIED');
    expect(answer.result?.structuredContent?.message).toContain('No policy is configured');
    expect(world.executed).toEqual([]);
  });

  describe('job_wait', () => {
    const status = (state: string) => ({
      result: { success: true, exitCode: 0, durationMs: 1 },
      stdout: JSON.stringify({
        success: true,
        command: 'job status',
        data: { state },
        errors: null,
        warnings: [],
        metrics: { duration_ms: 1 },
      }),
      stderr: '',
    });
    const WAIT = { tool: 'job_wait', args: { 'job-id': 'job-1', machine: 'machine-a' } };

    it('repeats the status read until the job is terminal', async () => {
      const world = await boot([{ grantId: 'g_a', configId: 'cfg-a', machine: 'machine-a' }]);
      const states = ['running', 'running', 'succeeded'];
      let reads = 0;
      dispatchStub.run = () => status(states[reads++] ?? 'succeeded');
      const answer = await answerOf(await call(world, world.grants.g_a as Grant, WAIT));
      expect(reads).toBe(3);
      const envelope = JSON.parse(answer.result?.content[0]?.text ?? '{}') as {
        data: { state: string };
        next?: string;
      };
      expect(envelope.data.state).toBe('succeeded');
      expect(envelope.next).toBeUndefined();
    });

    it('answers the latest status with next=job_wait when the ceiling passes first', async () => {
      const world = await boot([{ grantId: 'g_a', configId: 'cfg-a', machine: 'machine-a' }]);
      dispatchStub.run = () => status('running');
      const answer = await answerOf(
        await call(world, world.grants.g_a as Grant, { ...WAIT, attachMs: 60 })
      );
      const envelope = JSON.parse(answer.result?.content[0]?.text ?? '{}') as {
        data: { state: string };
        next?: string;
        nextPollSeconds?: number;
      };
      expect(envelope.data.state).toBe('running');
      expect(envelope.next).toBe('job_wait');
      expect(envelope.nextPollSeconds).toBeGreaterThan(0);
    });
  });
});
