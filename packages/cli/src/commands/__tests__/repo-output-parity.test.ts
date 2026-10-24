/**
 * `rdc repo up|down|status` print the same stdout locally and through `--proxy`.
 *
 * The B4 e2e probe found two divergences. Through the proxy, `repo up` and
 * `repo down` printed renet's own repository-list JSON on stdout where a local run
 * printed nothing (the local step detector drops every renet line that is not a
 * step; the executor forwarded them as `output` events and as the raw result
 * capture, and the client printed both). And `repo status` printed the repo
 * record through the proxy while the local run printed nothing, even with
 * `-o json`: the answer was dropped by the same detector.
 *
 * Each case runs one command BOTH ways against the same scripted machine answer
 * (real Commander tree, real serve app over HTTP, real ProxyClient; only the
 * account server and the machine are faked) and compares the bytes.
 */

import type { AddressInfo } from 'node:net';
import { serve } from '@hono/node-server';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../utils/agent-guard.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../utils/agent-guard.js')>()),
  isAgentEnvironment: () => false,
}));

await vi.hoisted(async () => {
  const { mkdtempSync } = await import('node:fs');
  const os = await import('node:os');
  const scratch = mkdtempSync(`${os.tmpdir()}/rdc-repo-output-parity-`);
  process.env.XDG_CONFIG_HOME = scratch;
  process.env.XDG_STATE_HOME = scratch;
  process.env.XDG_CACHE_HOME = scratch;
  process.env.REDIACC_TELEMETRY_DISABLED = '1';
});

// The proxy client reads its bearer token from the account login.
vi.mock('../../services/account/subscription-auth.js', async (original) => ({
  ...(await original<Record<string, unknown>>()),
  getSubscriptionTokenState: () => ({ kind: 'ready', token: { token: 'rdt_owner' } }),
}));

import { configFileStorage } from '../../adapters/config-file-storage.js';
import { createCli } from '../../cli.js';
import {
  type CommandRequestContext,
  createOutputState,
  createRequestConfigScope,
  DispatchExit,
  runInRequestContext,
} from '../../services/core/request-context.js';
import type { ExecuteOptions, ExecuteResult, Executor } from '../../services/executor/types.js';
import { AuthVerifier } from '../../services/serve/auth.js';
import { serveCrypto } from '../../services/serve/crypto.js';
import type { ServeDeps } from '../../services/serve/deps.js';
import { authorize } from '../../services/serve/policy.js';
import { createServeApp } from '../../services/serve/server.js';
import { SessionStore } from '../../services/serve/sessions.js';

const IDENTITY = {
  active: true,
  scopes: ['proxy:exec', 'audit:write'],
  orgId: 'org-1',
  teamId: null,
  createdByUserId: 'user-owner',
  userEmail: 'owner@example.com',
  orgRole: 'owner',
};

const CONFIG = {
  schemaVersion: 3,
  id: '00000000-0000-4000-8000-0000000000f0',
  version: 1,
  credentials: { ssh: { privateKey: 'KEY' } },
  resources: {
    machines: { m1: { ip: '10.1.1.1', user: 'root', port: 22 } },
    repositories: {
      shop: {
        grand: 'latest',
        placement: { machine: 'm1' },
        tags: {
          latest: {
            repositoryGuid: '11111111-1111-4111-8111-111111111111',
            networkId: 2816,
            credential: 'set',
          },
          px: {
            repositoryGuid: '22222222-2222-4222-8222-222222222222',
            grandGuid: '11111111-1111-4111-8111-111111111111',
            parentGuid: '11111111-1111-4111-8111-111111111111',
            networkId: 2832,
            credential: 'set',
          },
        },
      },
    },
    storages: {},
  },
  encryption: { mode: 'plaintext' },
} as unknown as RdcConfig;

const REPO_LIST = '{"repositories":[{"name":"shop","guid":"11111111"}]}';
const STATUS_RECORD = '{"guid":"22222222-2222-4222-8222-222222222222","mounted":true}';

/** A machine that answers with `stdout`, and says the same thing as `output` events the way renet's events mode does. */
function machine(stdout: string): { executor: Executor; calls: ExecuteOptions[] } {
  const calls: ExecuteOptions[] = [];
  return {
    calls,
    executor: {
      execute(options): Promise<ExecuteResult> {
        calls.push(options);
        for (const line of stdout.split('\n')) options.onEvent?.({ type: 'output', msg: line });
        return Promise.resolve({
          success: true,
          exitCode: 0,
          durationMs: 3,
          stdout: `${stdout}\n`,
        });
      },
    },
  };
}

/** Keep the one field that is a clock reading, so two runs of the same command compare equal. */
function normalize(stdout: string): string {
  // A request context stores one entry per write without its newline, and the client writes its whole capture as one entry with one, so only the trailing newline differs between the two captures.
  return stdout.trimEnd().replaceAll(/"duration_ms": \d+/g, '"duration_ms": 0');
}

describe('repo up|down|status stdout parity between a local run and --proxy', () => {
  let server: ReturnType<typeof serve> | undefined;

  afterEach(async () => {
    const running = server;
    server = undefined;
    if (running) await new Promise<void>((resolve) => running.close(() => resolve()));
  });

  async function runBothWays(argv: string[], stdout: string) {
    // A daemon-mode executor runs against its own enrolled config file.
    await configFileStorage.save(CONFIG, 'rediacc');
    const { executor } = machine(stdout);

    // Local: the real tree against the same config and machine, no proxy.
    const local: CommandRequestContext = {
      output: createOutputState(),
      stdout: [],
      stderr: [],
      executor,
      config: createRequestConfigScope(CONFIG),
    };
    const localExit = await runInRequestContext(local, async () => {
      try {
        await createCli().parseAsync(['--output', 'json', '--yes', ...argv], { from: 'user' });
        return 0;
      } catch (error) {
        if (error instanceof DispatchExit) return error.code;
        throw error;
      }
    });

    // Proxied: the same words, through a real serve app.
    const deps: ServeDeps = {
      mode: 'daemon',
      auth: new AuthVerifier({
        accountUrl: 'https://account.test',
        executorToken: 'rdt_executor',
        fetchImpl: () => Promise.resolve(Response.json(IDENTITY)),
      }),
      sessions: new SessionStore(),
      crypto: serveCrypto,
      executor: machine(stdout).executor,
      loadConfig: () => Promise.resolve(CONFIG),
      authorize,
      audit: () => Promise.resolve(),
    };
    server = serve({ fetch: createServeApp(deps).fetch, port: 0 });
    const baseUrl = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
    const proxied: CommandRequestContext = { output: createOutputState(), stdout: [], stderr: [] };
    const proxiedExit = await runInRequestContext(proxied, async () => {
      try {
        await createCli().parseAsync(['--proxy', baseUrl, '--output', 'json', ...argv], {
          from: 'user',
        });
        return 0;
      } catch (error) {
        if (error instanceof DispatchExit) return error.code;
        throw error;
      }
    });

    return {
      localExit,
      proxiedExit,
      localOut: normalize(local.stdout.join('\n')),
      proxiedOut: normalize(proxied.stdout.join('\n')),
    };
  }

  it('repo down prints nothing on stdout either way, not the renet repository list', async () => {
    const run = await runBothWays(['repo', 'down', 'shop:px'], REPO_LIST);

    expect(run.localExit).toBe(0);
    expect(run.proxiedExit).toBe(0);
    expect(run.proxiedOut).not.toContain('repositories');
    expect(run.proxiedOut).toBe(run.localOut);
  });

  it('repo up prints nothing on stdout either way, not the renet repository list', async () => {
    const run = await runBothWays(['repo', 'up', 'shop:px', '--no-start'], REPO_LIST);

    expect(run.localExit).toBe(0);
    expect(run.proxiedExit).toBe(0);
    expect(run.proxiedOut).not.toContain('repositories');
    expect(run.proxiedOut).toBe(run.localOut);
  });

  it('repo status prints the record on stdout either way, as a single JSON document', async () => {
    const run = await runBothWays(['repo', 'status', 'shop:px'], STATUS_RECORD);

    expect(run.localExit).toBe(0);
    expect(run.proxiedExit).toBe(0);
    expect(run.localOut).toContain('22222222-2222-4222-8222-222222222222');
    expect(run.proxiedOut).toBe(run.localOut);
    expect(run.proxiedOut.match(/22222222-2222-4222-8222-222222222222/g)).toHaveLength(1);
    expect(() => JSON.parse(run.localOut)).not.toThrow();
  });
});
