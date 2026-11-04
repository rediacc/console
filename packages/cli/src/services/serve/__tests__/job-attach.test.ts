/**
 * The attach window of a proxied command (PLAN-detached-jobs J6, J6b).
 *
 * `/v1/command` answers with the job line the instant a job starts (machine, overlaps), a heartbeat every
 * quiet period, and one result line: `state: 'running'` when the job outlived the executor seam's attach
 * window. A request id from the body is the invocation id, minted per call as `<id>:<machine>:<seq>`; a
 * client that leaves mid-window never fails the dispatch. The executor is faked (the attach decision itself
 * is the seam's, pinned in the executor tests); everything between HTTP and the dispatch is production code.
 */

import type { AddressInfo } from 'node:net';
import { serve } from '@hono/node-server';
import { CLI_CONTRACT_VERSION } from '@rediacc/shared/cli-contract';
import { type StreamLine, StreamLineSchema } from '@rediacc/shared/cli-contract/wire';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import { afterEach, describe, expect, it, vi } from 'vitest';

// The dispatched command runs the real CLI, which would otherwise read the developer's own config from disk. This is the config the EXECUTOR holds.
vi.mock('../../config/network-id-discovery.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../config/network-id-discovery.js')>()),
  ensureRepositoryNetworkId: vi.fn(() => Promise.resolve(7)),
}));
vi.mock('../../config/config-resources.js', () => ({
  configService: {
    resetResourceView: vi.fn(),
    getRepository: vi.fn((name: string) =>
      Promise.resolve({ repositoryGuid: `guid-${name}`, credential: 'set', networkId: 7 })
    ),
    getLanguage: vi.fn(() => Promise.resolve('en')),
    applyDefaults: vi.fn((options: Record<string, unknown>) => Promise.resolve(options)),
    setRuntimeConfig: vi.fn(),
    getLocalConfig: vi.fn(() => Promise.resolve({ machines: {}, repositories: {} })),
    getLocalMachine: vi.fn((name: string) =>
      Promise.resolve({ ip: '10.0.0.1', user: 'root', name })
    ),
    // `shop` is placed on `hostinger` so a derived-machine repo verb (`repo cat`, the positional-ref acceptance vehicle after `_refprobe` retired) resolves its execution machine from placement (spec/03 §2.3), not from a dead `-m`.
    getCurrent: vi.fn(() =>
      Promise.resolve({
        state: {},
        resources: {
          repositories: {
            shop: { grand: 'base', tags: { base: {} }, placement: { machine: 'hostinger' } },
            demo: { grand: 'base', tags: { base: {} }, placement: { machine: 'hostinger' } },
            // Distinct placements so the concurrency test derives distinct machines.
            alpha: { grand: 'base', tags: { base: {} }, placement: { machine: 'm1' } },
            beta: { grand: 'base', tags: { base: {} }, placement: { machine: 'm2' } },
          },
        },
      })
    ),
  },
}));

// The CLI reads its proxy bearer token from the account login. This is the only thing the client half needs that a test cannot supply through argv.
const { proxyToken } = vi.hoisted(() => ({ proxyToken: { value: 'rdt_owner' } }));
vi.mock('../../account/subscription-auth.js', async (original) => ({
  ...(await original<Record<string, unknown>>()),
  getSubscriptionTokenState: () => ({ kind: 'ready', token: { token: proxyToken.value } }),
}));

// Telemetry would otherwise try the network on every dispatched command.
process.env.REDIACC_TELEMETRY_DISABLED = '1';

import type { ExecuteOptions, ExecuteResult } from '../../executor/types.js';
import { AuthVerifier } from '../auth.js';
import { serveCrypto } from '../crypto.js';
import type { ServeDeps } from '../deps.js';
import { authorize } from '../policy.js';
import { createServeApp } from '../server.js';
import { SessionStore } from '../sessions.js';

const TOKEN = 'rdt_owner';
const REQUEST_ID = 'inv-0123-abcd';

const config = {
  schemaVersion: 3,
  id: '00000000-0000-0000-0000-000000000001',
  version: 1,
  defaults: { language: 'en', datastoreSize: '95%' },
  encryption: { mode: 'plaintext' },
} as RdcConfig;

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

describe('attach window over /v1/command', () => {
  let server: ReturnType<typeof serve>;
  let baseUrl: string;

  function boot(execute: (options: ExecuteOptions) => Promise<ExecuteResult>) {
    const deps: ServeDeps = {
      mode: 'daemon',
      auth: new AuthVerifier({
        accountUrl: 'https://account.test',
        executorToken: 'rdt_executor',
        fetchImpl: (() =>
          Promise.resolve(
            Response.json({
              active: true,
              scopes: ['proxy:exec'],
              orgId: 'org-1',
              teamId: 'team-1',
              createdByUserId: 'user-owner',
              userEmail: 'owner@example.com',
              orgRole: 'owner',
            })
          )) as unknown as typeof fetch,
      }),
      sessions: new SessionStore(),
      crypto: serveCrypto,
      loadConfig: () => Promise.resolve(config),
      authorize,
      audit: () => Promise.resolve(),
      executor: { execute },
    };
    server = serve({ fetch: createServeApp(deps).fetch, port: 0 });
    baseUrl = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  }

  function post(extra: Record<string, unknown> = {}, signal?: AbortSignal): Promise<Response> {
    return fetch(`${baseUrl}/v1/command`, {
      method: 'POST',
      signal,
      headers: { authorization: `Bearer ${TOKEN}`, 'content-type': 'application/json' },
      body: JSON.stringify({
        contractVersion: CLI_CONTRACT_VERSION,
        pathKey: 'repo status',
        params: {},
        positionals: { ref: 'demo' },
        ...extra,
      }),
    });
  }

  async function lines(response: Response): Promise<StreamLine[]> {
    const text = await response.text();
    return text
      .split('\n')
      .filter((l) => l.trim() !== '')
      .map((l) => StreamLineSchema.parse(JSON.parse(l)));
  }

  afterEach(async () => {
    delete process.env.REDIACC_PROXY_HEARTBEAT_MS;
    await new Promise<void>((resolve) => server.close(() => resolve()));
  });

  it('writes the job line with the machine and the overlaps, then a running result', async () => {
    const overlap = {
      jobId: 'j1-other',
      function: 'repository_up',
      action: 'warn',
      attach: 'rdc job logs j1-other -m hostinger --follow',
    };
    boot((options) => {
      options.onJobStarted?.('j18c1c04dd251ce26-0ccf9fe5', 'hostinger', [overlap] as never);
      return Promise.resolve({
        success: true,
        exitCode: 0,
        durationMs: 20_000,
        jobId: 'j18c1c04dd251ce26-0ccf9fe5',
        state: 'running',
        attached: false,
      });
    });

    const all = await lines(await post());
    expect(all[0]).toMatchObject({
      kind: 'job',
      jobId: 'j18c1c04dd251ce26-0ccf9fe5',
      machine: 'hostinger',
    });
    expect(all[0]).toHaveProperty('overlaps');
    const result = all.at(-1);
    expect(result).toMatchObject({ kind: 'result', result: { state: 'running', attached: false } });
    expect(all.filter((l) => l.kind === 'result')).toHaveLength(1);
  });

  it('returns a job that finished inside the window as one result, with no job line needed', async () => {
    boot(() =>
      Promise.resolve({
        success: true,
        exitCode: 0,
        durationMs: 2000,
        state: 'succeeded',
        attached: true,
      })
    );
    const all = await lines(await post());
    expect(all.filter((l) => l.kind === 'job')).toHaveLength(0);
    expect(all.at(-1)).toMatchObject({
      kind: 'result',
      result: { attached: true, state: 'succeeded' },
    });
  });

  it('mints each call request id from the body id as <id>:<machine>:<seq>', async () => {
    const seen: (string | undefined)[] = [];
    boot((options) => {
      seen.push(options.requestId);
      return Promise.resolve({ success: true, exitCode: 0, durationMs: 1 });
    });
    await (await post({ requestId: REQUEST_ID })).text();
    await (await post()).text();
    expect(seen[0]).toBe(`${REQUEST_ID}:hostinger:1`);
    // Without a body id the executor seam's own id stands.
    expect(seen[1]).not.toContain(REQUEST_ID);
  });

  it('keeps a quiet window alive with heartbeats', async () => {
    process.env.REDIACC_PROXY_HEARTBEAT_MS = '25';
    boot(async () => {
      await wait(200);
      return { success: true, exitCode: 0, durationMs: 200 };
    });
    const all = await lines(await post());
    expect(all.filter((l) => l.kind === 'heartbeat').length).toBeGreaterThanOrEqual(2);
    expect(all.at(-1)?.kind).toBe('result');
  });

  it('keeps the dispatch running when the client leaves mid-window', async () => {
    let finished = false;
    boot(async (options) => {
      options.onJobStarted?.('j18c1c04dd251ce26-0ccf9fe5', 'hostinger');
      await wait(150);
      finished = true;
      return { success: true, exitCode: 0, durationMs: 150 };
    });
    const controller = new AbortController();
    const response = await post({}, controller.signal);
    // The job line has been written; the client drops before the job finishes.
    const reader = response.body?.getReader();
    await reader?.read();
    controller.abort();
    await wait(400);
    expect(finished).toBe(true);
  });

  it('is unchanged for a refused command: a 400 before any stream opens', async () => {
    boot(() => Promise.resolve({ success: true, exitCode: 0, durationMs: 1 }));
    const res = await post({ pathKey: 'repo sync upload' });
    expect(res.status).toBe(400);
  });
});
