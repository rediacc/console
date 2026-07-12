/**
 * Loopback: a real `rdc --proxy` invocation driving a real serve app over real HTTP.
 *
 * This is the test that proves the two halves of the proxy actually fit, and the
 * client half is the ACTUAL CLI: argv goes through the real Commander tree, the
 * real preAction hook decides to proxy, and the real client serializes the
 * request. That matters, because the flaw this replaced was invisible to a test
 * that hand-built requests: `--proxy` used to intercept inside the action body,
 * downstream of config reads a proxy client cannot do, so it died before the wire.
 * A hand-built request skips exactly the code that was broken.
 *
 * It boots the Hono app on an ephemeral port with a fake executor and throwaway
 * keys. Everything between the two ends is production code: the wire schema, the
 * NDJSON framing, the streaming reader, auth, policy, and the CEK grant.
 *
 * What it deliberately does NOT stub: the crypto. The CEK handoff runs real
 * X25519 through Web Crypto, because a grant that only works against a mock is
 * worth nothing.
 *
 * The /v1/command half does not stub the CLI either. It drives the REAL Commander
 * tree in-process, so the command-to-function mapping under test is the one that
 * actually ships: "repo status" reaches repository_status because the real action
 * body said so, not because the test said so. The executor is faked (nothing here
 * touches a machine) and the config is faked (nothing here reads the developer's
 * ~/.config), and those are the only two seams.
 */

import type { AddressInfo } from 'node:net';
import { serve } from '@hono/node-server';
import { CLI_CONTRACT_VERSION } from '@rediacc/shared/cli-contract';
import {
  cekHandoffEncrypt,
  exportAesKey,
  fromBase64,
  generateCek,
} from '@rediacc/shared/config-crypto';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import { afterEach, describe, expect, it, vi } from 'vitest';

// The dispatched command runs the real CLI, which would otherwise read the
// developer's own config from disk. This is the config the EXECUTOR holds.
vi.mock('../../config/config-resources.js', () => ({
  configService: {
    getRepository: vi.fn((name: string) =>
      Promise.resolve({ repositoryGuid: `guid-${name}`, credential: 'set', networkId: 7 })
    ),
    ensureRepositoryNetworkId: vi.fn(() => Promise.resolve(7)),
    getLanguage: vi.fn(() => Promise.resolve('en')),
    applyDefaults: vi.fn((options: Record<string, unknown>) => Promise.resolve(options)),
    setRuntimeConfig: vi.fn(),
    getLocalConfig: vi.fn(() => Promise.resolve({ machines: {}, repositories: {} })),
    getLocalMachine: vi.fn((name: string) =>
      Promise.resolve({ ip: '10.0.0.1', user: 'root', name })
    ),
    getCurrent: vi.fn(() => Promise.resolve({ state: {} })),
  },
}));

// The CLI reads its proxy bearer token from the account login. This is the only
// thing the client half needs that a test cannot supply through argv.
const { proxyToken } = vi.hoisted(() => ({ proxyToken: { value: 'rdt_owner' } }));
vi.mock('../../account/subscription-auth.js', async (original) => ({
  ...(await original<Record<string, unknown>>()),
  getSubscriptionTokenState: () => ({ kind: 'ready', token: { token: proxyToken.value } }),
}));

// Telemetry would otherwise try the network on every dispatched command.
process.env.REDIACC_TELEMETRY_DISABLED = '1';

import { createCli } from '../../../cli.js';
import {
  createOutputState,
  DispatchExit,
  runInRequestContext,
} from '../../core/request-context.js';
import { ProxyClient } from '../../executor/proxy-client.js';
import type { ExecuteOptions, ExecuteResult, RenetEvent } from '../../executor/types.js';
import { AuthVerifier } from '../auth.js';
import { serveCrypto } from '../crypto.js';
import type { ServeDeps } from '../deps.js';
import { authorize } from '../policy.js';
import { createServeApp } from '../server.js';
import { SessionStore } from '../sessions.js';

/** A config with no policy document: owners are allowed, members are not. */
function baseConfig(policy?: unknown): RdcConfig {
  const config = {
    schemaVersion: 3,
    id: '00000000-0000-0000-0000-000000000001',
    version: 1,
    defaults: { language: 'en', datastoreSize: '95%' },
    encryption: { mode: 'plaintext' },
    ...(policy ? { policy } : {}),
  };
  return config as RdcConfig;
}

/** An executor that records what it was asked to do and replays scripted events. */
function fakeExecutor(events: RenetEvent[], result: Partial<ExecuteResult> = {}) {
  const calls: ExecuteOptions[] = [];
  return {
    calls,
    executor: {
      execute(options: ExecuteOptions): Promise<ExecuteResult> {
        calls.push(options);
        for (const event of events) options.onEvent?.(event);
        return Promise.resolve({
          success: true,
          exitCode: 0,
          durationMs: 7,
          stdout: 'done',
          ...result,
        });
      },
    },
  };
}

/** An account server that introspects tokens. */
function fakeAccount(principals: Record<string, unknown>) {
  return vi.fn((_url: string, init?: RequestInit) => {
    const body = JSON.parse(String(init?.body ?? '{}')) as { token: string };
    const found = principals[body.token];
    return Promise.resolve(
      new Response(JSON.stringify(found ?? { active: false }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );
  }) as unknown as typeof fetch;
}

const OWNER_TOKEN = 'rdt_owner';
const MEMBER_TOKEN = 'rdt_member';

const ACCOUNT_PRINCIPALS = {
  [OWNER_TOKEN]: {
    active: true,
    scopes: ['proxy:exec'],
    orgId: 'org-1',
    teamId: 'team-1',
    createdByUserId: 'user-owner',
    userEmail: 'owner@example.com',
    orgRole: 'owner',
  },
  [MEMBER_TOKEN]: {
    active: true,
    scopes: ['proxy:exec'],
    orgId: 'org-1',
    teamId: 'team-1',
    createdByUserId: 'user-member',
    userEmail: 'member@example.com',
    orgRole: 'member',
  },
};

describe('proxy loopback', () => {
  let server: ReturnType<typeof serve>;
  let baseUrl: string;
  let sessions: SessionStore;
  let audited: unknown[];

  function boot(deps: Partial<ServeDeps> & Pick<ServeDeps, 'executor'>) {
    sessions = new SessionStore();
    audited = [];

    const full: ServeDeps = {
      mode: 'daemon',
      auth: new AuthVerifier({
        accountUrl: 'https://account.test',
        executorToken: 'rdt_executor',
        fetchImpl: fakeAccount(ACCOUNT_PRINCIPALS),
      }),
      sessions,
      crypto: serveCrypto,
      loadConfig: () => Promise.resolve(baseConfig()),
      authorize,
      audit: (event) => {
        audited.push(event);
        return Promise.resolve();
      },
      ...deps,
    };

    const app = createServeApp(full);
    server = serve({ fetch: app.fetch, port: 0 });
    const address = server.address() as AddressInfo;
    baseUrl = `http://127.0.0.1:${address.port}`;
  }

  /**
   * Run a REAL `rdc --proxy <url> <command>` against the booted executor.
   *
   * The CLI would end the process with the command's exit code, which a test
   * cannot allow, so the parse runs inside a request context: exitProcess then
   * unwinds this call instead of killing vitest, and the same context captures
   * what the CLI rendered. Both behaviours are production code paths, not test
   * scaffolding, and asserting on the captured output is asserting on exactly
   * what an operator's terminal would have shown.
   */
  async function runCli(
    argv: string[],
    token = OWNER_TOKEN
  ): Promise<{ exitCode: number; stdout: string; stderr: string }> {
    proxyToken.value = token;
    const context = {
      output: createOutputState(),
      stdout: [] as string[],
      stderr: [] as string[],
    };

    const exitCode = await runInRequestContext(context, async () => {
      const program = createCli();
      try {
        await program.parseAsync(['--proxy', baseUrl, ...argv], { from: 'user' });
        return 0;
      } catch (error) {
        if (error instanceof DispatchExit) return error.code;
        throw error;
      }
    });

    return {
      exitCode,
      stdout: context.stdout.join('\n'),
      stderr: context.stderr.join('\n'),
    };
  }

  afterEach(async () => {
    await new Promise<void>((resolve) => server.close(() => resolve()));
  });

  // ─── The client half: a real `rdc --proxy` invocation ──────────────────────

  it('runs a whole command through the real CLI: argv in, rendered events out', async () => {
    const { executor, calls } = fakeExecutor([
      { type: 'step_start', name: 'snapshot' },
      { type: 'step_done', name: 'snapshot', duration_ms: 31 },
      // Renet's own output arrives as events in events mode, which is how it
      // reaches a terminal on a laptop too.
      { type: 'output', msg: 'STATUS: running\n' },
    ]);
    boot({ executor });

    const { exitCode, stdout } = await runCli([
      'repo',
      'status',
      '--name',
      'demo',
      '-m',
      'hostinger',
    ]);

    expect(exitCode).toBe(0);

    // The CLI never touched a machine, never read a repo out of local config,
    // and never resolved a function. The EXECUTOR did all of that by running the
    // command, which is why the fake executor saw repository_status at all.
    expect(calls).toHaveLength(1);
    expect(calls[0].functionName).toBe('repository_status');
    expect(calls[0].machineName).toBe('hostinger');
    expect(calls[0].params).toMatchObject({ repository: 'demo' });
    expect(calls[0].extraMachines).toBeUndefined();

    // The operator sees the same timeline they would have seen locally, because
    // these are renet's own events rendered through the same helpers.
    expect(stdout).toContain('Snapshot');
    // ...and renet's output, rendered live as it streamed.
    expect(stdout).toContain('STATUS: running');
  });

  it('prints the captured output when a run streamed none of it live', async () => {
    // A run that emits no output events must still show what renet said, rather
    // than ending in silence. It is printed once, never twice.
    const { executor } = fakeExecutor([], { stdout: 'the whole answer' });
    boot({ executor });

    const { stdout } = await runCli(['repo', 'status', '--name', 'demo', '-m', 'hostinger']);

    expect(stdout).toContain('the whole answer');
    expect(stdout.match(/the whole answer/g)).toHaveLength(1);
  });

  it('exits non-zero when the command fails at the executor', async () => {
    const { executor } = fakeExecutor([], {
      success: false,
      exitCode: 7,
      error: 'the machine said no',
    });
    boot({ executor });

    const { exitCode, stdout, stderr } = await runCli([
      'repo',
      'status',
      '--name',
      'demo',
      '-m',
      'hostinger',
    ]);

    // The exit code an operator scripts against is the one the command chose,
    // carried back across the wire rather than invented by the client.
    expect(exitCode).toBe(7);
    expect(`${stdout}${stderr}`).toContain('the machine said no');
  });

  it('sends only the options the command declares, keyed by long flag', async () => {
    const { executor, calls } = fakeExecutor([]);
    boot({ executor });

    // --skip-router-restart is stored by Commander as `skipRouterRestart`; the
    // wire speaks the contract's long flags, so it has to be turned back.
    await runCli(['repo', 'status', '--name', 'demo', '-m', 'hostinger', '--skip-router-restart']);

    expect(calls).toHaveLength(1);
    // The executor received it as a real flag: the command it ran had it set.
    expect(calls[0].skipRouterRestart).toBe(true);
    // The client's own options never travel: --proxy is the client's business.
    expect(audited[0]).toMatchObject({ commandPath: 'repo status' });
    expect(JSON.stringify(audited[0])).not.toContain('proxy');
  });

  it('ships exactly one audit event per command, attributed to the verified user', async () => {
    const { executor } = fakeExecutor([]);
    boot({ executor });

    await runCli(['repo', 'status', '--name', 'demo', '-m', 'hostinger']);

    expect(audited).toHaveLength(1);
    expect(audited[0]).toMatchObject({
      commandPath: 'repo status',
      functionName: 'repository_status',
      success: true,
      principal: { userEmail: 'owner@example.com', orgId: 'org-1' },
    });
  });

  it('refuses up front a command the proxy cannot serve, without calling the executor', async () => {
    const { executor, calls } = fakeExecutor([]);
    boot({ executor });

    // `term connect` needs the operator's terminal. The contract says so, and the
    // CLI refuses before a request is ever made.
    await expect(runCli(['term', 'connect', '-m', 'hostinger'])).rejects.toThrow(
      /terminal|--proxy/i
    );
    expect(calls).toHaveLength(0);
  });

  it('rejects an unknown token', async () => {
    const { executor } = fakeExecutor([]);
    boot({ executor });

    await expect(
      runCli(['repo', 'status', '--name', 'demo', '-m', 'hostinger'], 'rdt_nope')
    ).rejects.toThrow(/not valid for the executor|401/i);
  });

  it('denies a member when the org has no policy document, and never runs the command', async () => {
    const { executor, calls } = fakeExecutor([]);
    boot({ executor });

    await expect(
      runCli(['repo', 'status', '--name', 'demo', '-m', 'hostinger'], MEMBER_TOKEN)
    ).rejects.toThrow(/only owners and admins/i);

    // Policy is enforced BEFORE execution, not after.
    expect(calls).toHaveLength(0);
  });

  it('enforces a policy document that denies a specific command', async () => {
    const { executor, calls } = fakeExecutor([]);
    boot({
      executor,
      loadConfig: () =>
        Promise.resolve(
          baseConfig({
            version: 1,
            defaults: { commands: { allow: ['repo *'], deny: ['repo status'] } },
          })
        ),
    });

    await expect(runCli(['repo', 'status', '--name', 'demo', '-m', 'hostinger'])).rejects.toThrow();
    expect(calls).toHaveLength(0);
  });

  it('refuses a client whose contract version disagrees with the executor', async () => {
    const { executor } = fakeExecutor([]);
    boot({ executor });

    const stale = new ProxyClient({
      baseUrl,
      getToken: () => Promise.resolve(OWNER_TOKEN),
      contractVersion: 'contract-from-last-year',
    });

    await expect(stale.run('repo status', { name: 'demo' }, () => {})).rejects.toThrow(/contract/i);
  });

  it('grants a CEK over real X25519 and holds it in memory only', async () => {
    const { executor } = fakeExecutor([]);
    boot({ executor });

    // 1. Client opens a session; the executor mints an ephemeral keypair.
    const open = await fetch(`${baseUrl}/v1/session`, {
      method: 'POST',
      headers: { authorization: `Bearer ${OWNER_TOKEN}` },
    });
    expect(open.status).toBe(200);
    const { sessionId, publicKey } = (await open.json()) as {
      sessionId: string;
      publicKey: string;
    };

    // 2. Client seals its real CEK to that public key.
    const cek = await generateCek();
    const rawCek = await exportAesKey(cek);
    const executorPublic = await crypto.subtle.importKey(
      'spki',
      fromBase64(publicKey) as unknown as ArrayBuffer,
      { name: 'X25519' },
      true,
      []
    );
    const blob = await cekHandoffEncrypt(rawCek, executorPublic);

    // 3. Executor opens it and holds the key for the session.
    const grant = await fetch(`${baseUrl}/v1/session/${sessionId}/cek`, {
      method: 'POST',
      headers: { authorization: `Bearer ${OWNER_TOKEN}`, 'content-type': 'application/json' },
      body: JSON.stringify(blob),
    });
    expect(grant.status).toBe(200);

    const held = await exportAesKey(sessions.requireCek(sessionId));
    expect(Buffer.from(held)).toEqual(Buffer.from(rawCek));

    // Closing the session is the only thing that removes the key.
    sessions.close(sessionId);
    expect(() => sessions.requireCek(sessionId)).toThrow(/unknown or expired/i);
  });

  it('refuses a CEK grant from a principal who did not open the session (SEC-3)', async () => {
    const { executor } = fakeExecutor([]);
    boot({ executor });

    // The OWNER opens the session and gets the public key to seal to.
    const open = await fetch(`${baseUrl}/v1/session`, {
      method: 'POST',
      headers: { authorization: `Bearer ${OWNER_TOKEN}` },
    });
    const { sessionId, publicKey } = (await open.json()) as {
      sessionId: string;
      publicKey: string;
    };

    const cek = await generateCek();
    const executorPublic = await crypto.subtle.importKey(
      'spki',
      fromBase64(publicKey) as unknown as ArrayBuffer,
      { name: 'X25519' },
      true,
      []
    );
    const blob = await cekHandoffEncrypt(await exportAesKey(cek), executorPublic);

    // A DIFFERENT real user, with a perfectly valid token, tries to complete the
    // owner's grant. The executor refuses, and the session gets no key.
    const grant = await fetch(`${baseUrl}/v1/session/${sessionId}/cek`, {
      method: 'POST',
      headers: { authorization: `Bearer ${MEMBER_TOKEN}`, 'content-type': 'application/json' },
      body: JSON.stringify(blob),
    });

    expect(grant.status).toBe(404);
    expect(() => sessions.requireCek(sessionId)).toThrow(/no config key yet/i);
  });

  it('reports its identity through server-info', async () => {
    const { executor } = fakeExecutor([]);
    boot({ executor, mode: 'container', scope: { orgId: 'org-1', teamId: 'team-1' } });

    const info = await new ProxyClient({
      baseUrl,
      getToken: () => Promise.resolve(OWNER_TOKEN),
      contractVersion: CLI_CONTRACT_VERSION,
    }).serverInfo();
    expect(info.mode).toBe('container');
    expect(info.contractVersion).toBe(CLI_CONTRACT_VERSION);
    expect(info.scope).toEqual({ orgId: 'org-1', teamId: 'team-1' });
  });
  // ─── /v1/command: the executor runs the CLI ────────────────────────────────
  //
  // The console has no CLI, so it names a COMMAND and the executor works out the
  // function. Everything below drives the real Commander tree in-process.

  /** POST a command-level request and read the NDJSON stream back. */
  async function postCommand(
    body: Record<string, unknown>,
    token = OWNER_TOKEN
  ): Promise<{ status: number; events: RenetEvent[]; results: unknown[]; error?: string }> {
    const response = await fetch(`${baseUrl}/v1/command`, {
      method: 'POST',
      headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json' },
      body: JSON.stringify({ contractVersion: CLI_CONTRACT_VERSION, ...body }),
    });

    if (!response.ok) {
      const failure = (await response.json()) as { error?: string };
      return { status: response.status, events: [], results: [], error: failure.error };
    }

    const text = await response.text();
    const lines = text
      .split('\n')
      .filter(Boolean)
      .map((line) => JSON.parse(line));
    return {
      status: response.status,
      events: lines.filter((l) => l.kind === 'event').map((l) => l.event as RenetEvent),
      results: lines.filter((l) => l.kind === 'result').map((l) => l.result),
    };
  }

  it('resolves a command to its renet function by running the real CLI', async () => {
    const { executor, calls } = fakeExecutor([]);
    boot({ executor });

    const { status, results } = await postCommand({
      pathKey: 'repo status',
      params: { name: 'demo', machine: 'hostinger' },
    });

    expect(status).toBe(200);
    expect(results).toHaveLength(1);

    // Nothing in this test said "repository_status". The command's own action
    // body did, which is the whole point: the console never needs to know it.
    expect(calls).toHaveLength(1);
    expect(calls[0].functionName).toBe('repository_status');
    expect(calls[0].machineName).toBe('hostinger');
    expect(calls[0].params).toMatchObject({ repository: 'demo' });
  });

  it('streams events and terminates with exactly one result line', async () => {
    const { executor } = fakeExecutor([
      { type: 'step_start', name: 'inspect' },
      { type: 'step_done', name: 'inspect', duration_ms: 12 },
    ]);
    boot({ executor });

    const { events, results } = await postCommand({
      pathKey: 'repo status',
      params: { name: 'demo', machine: 'hostinger' },
    });

    expect(events.map((e) => e.type)).toEqual(['step_start', 'step_done']);
    expect(events[1].duration_ms).toBe(12);
    expect(results).toHaveLength(1);
    expect((results[0] as ExecuteResult).success).toBe(true);
  });

  it('audits the function the command actually ran, not the path it was asked for', async () => {
    const { executor } = fakeExecutor([]);
    boot({ executor });

    await postCommand({ pathKey: 'repo status', params: { name: 'demo', machine: 'hostinger' } });

    expect(audited).toHaveLength(1);
    expect(audited[0]).toMatchObject({
      commandPath: 'repo status',
      functionName: 'repository_status',
      machineName: 'hostinger',
      success: true,
      principal: { userEmail: 'owner@example.com' },
    });
  });

  it('denies on the command path BEFORE the CLI runs at all', async () => {
    const { executor, calls } = fakeExecutor([]);
    boot({
      executor,
      loadConfig: () =>
        Promise.resolve(
          baseConfig({
            version: 1,
            defaults: { commands: { allow: ['repo *'], deny: ['repo status'] } },
          })
        ),
    });

    const { status } = await postCommand({
      pathKey: 'repo status',
      params: { name: 'demo', machine: 'hostinger' },
    });

    expect(status).toBe(403);
    expect(calls).toHaveLength(0);
  });

  it('refuses a param that is not a declared option, so argv cannot be smuggled', async () => {
    const { executor, calls } = fakeExecutor([]);
    boot({ executor });

    const { status, error } = await postCommand({
      pathKey: 'repo status',
      params: { name: 'demo', machine: 'hostinger', 'not-an-option': 'x' },
    });

    expect(status).toBe(400);
    expect(error).toMatch(/no --not-an-option option/i);
    expect(calls).toHaveLength(0);
  });

  it('refuses an unknown command path', async () => {
    const { executor } = fakeExecutor([]);
    boot({ executor });

    const { status, error } = await postCommand({ pathKey: 'repo nonsense', params: {} });
    expect(status).toBe(400);
    expect(error).toMatch(/no "rdc repo nonsense" command/i);
  });

  it('refuses a command that needs a terminal', async () => {
    const { executor } = fakeExecutor([]);
    boot({ executor });

    const { status, error } = await postCommand({
      pathKey: 'term connect',
      params: { machine: 'hostinger' },
    });

    expect(status).toBe(400);
    expect(error).toMatch(/needs a terminal/i);
  });

  it('keeps two concurrent commands from contaminating each other', async () => {
    // Both requests run the same command at the same time, each with its own
    // params and its own scripted events. A module-global output buffer or a
    // shared event subscriber would cross the wires here; AsyncLocalStorage is
    // what keeps them apart, and this is the test that proves it.
    const calls: ExecuteOptions[] = [];
    const executor = {
      async execute(options: ExecuteOptions): Promise<ExecuteResult> {
        calls.push(options);
        const repo = String(options.params?.repository);
        // Yield, so the two dispatches genuinely interleave rather than running
        // one after the other.
        await new Promise((resolve) => setTimeout(resolve, 20));
        options.onEvent?.({ type: 'log', msg: `event-for-${repo}` });
        await new Promise((resolve) => setTimeout(resolve, 20));
        options.onEvent?.({ type: 'step_done', name: repo, duration_ms: 1 });
        return { success: true, exitCode: 0, durationMs: 5, stdout: `stdout-for-${repo}` };
      },
    };
    boot({ executor });

    const [alpha, beta] = await Promise.all([
      postCommand({ pathKey: 'repo status', params: { name: 'alpha', machine: 'm1' } }),
      postCommand({ pathKey: 'repo status', params: { name: 'beta', machine: 'm2' } }),
    ]);

    // Each command reached the executor with its OWN params.
    expect(calls).toHaveLength(2);
    expect(
      calls.map((c) => String(c.params?.repository)).sort((a, b) => a.localeCompare(b))
    ).toEqual(['alpha', 'beta']);

    // And each response carries only its OWN events. This is the assertion a
    // global buffer fails: alpha would see beta's events too.
    const alphaEvents = alpha.events.map((e) => e.msg ?? e.name);
    const betaEvents = beta.events.map((e) => e.msg ?? e.name);
    expect(alphaEvents).toEqual(['event-for-alpha', 'alpha']);
    expect(betaEvents).toEqual(['event-for-beta', 'beta']);

    expect(alpha.results).toHaveLength(1);
    expect(beta.results).toHaveLength(1);
    expect((alpha.results[0] as ExecuteResult).stdout).toBe('stdout-for-alpha');
    expect((beta.results[0] as ExecuteResult).stdout).toBe('stdout-for-beta');
  });
});
