/**
 * `-b` through the proxy (PLAN-detached-jobs, finding #d31b4054).
 *
 * The client sends `background: true` in the command request and the served dispatch gives every machine
 * job of THAT request a zero attach window, so the job id comes back at once and nothing follows it. A
 * request without the flag keeps the served window. The executor is faked; everything between HTTP and the
 * dispatch is production code, and the window the fake sees is the one the executor seam stamped.
 */

import { mkdtempSync, rmSync } from 'node:fs';
import type { AddressInfo } from 'node:net';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { serve } from '@hono/node-server';
import { CLI_CONTRACT_VERSION } from '@rediacc/shared/cli-contract';
import { type StreamLine, StreamLineSchema } from '@rediacc/shared/cli-contract/wire';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../config/network-id-discovery.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../config/network-id-discovery.js')>()),
  ensureRepositoryNetworkId: vi.fn(() => Promise.resolve(7)),
}));
vi.mock('../../config/config-resources.js', () => ({
  configService: {
    resetResourceView: vi.fn(),
    getRepository: vi.fn((name: string) =>
      Promise.resolve({
        repositoryGuid: `guid-${name}`,
        credential: 'set',
        networkId: 7,
        ...(name.includes(':') ? { grandGuid: 'guid-grand' } : {}),
      })
    ),
    getLanguage: vi.fn(() => Promise.resolve('en')),
    applyDefaults: vi.fn((options: Record<string, unknown>) => Promise.resolve(options)),
    setRuntimeConfig: vi.fn(),
    getLocalConfig: vi.fn(() => Promise.resolve({ machines: {}, repositories: {} })),
    getLocalMachine: vi.fn((name: string) =>
      Promise.resolve({ ip: '10.0.0.1', user: 'root', name })
    ),
    getCurrent: vi.fn(() =>
      Promise.resolve({
        state: {},
        resources: {
          repositories: {
            demo: {
              grand: 'base',
              tags: { base: {}, trial: {} },
              placement: { machine: 'hostinger' },
            },
          },
        },
      })
    ),
  },
}));

process.env.REDIACC_TELEMETRY_DISABLED = '1';

import type { ExecuteOptions, ExecuteResult } from '../../executor/types.js';
import { JOB_ATTACH_WINDOW_MS } from '../../jobs/attach.js';
import { setCommandJobDeps } from '../../jobs/command-job.js';
import { TicketStore } from '../../jobs/ticket-store.js';
import { AuthVerifier } from '../auth.js';
import { serveCrypto } from '../crypto.js';
import type { ServeDeps } from '../deps.js';
import { authorize } from '../policy.js';
import { createServeApp } from '../server.js';
import { SessionStore } from '../sessions.js';

const TOKEN = 'rdt_owner';
const JOB = 'j18c1c04dd251ce26-0ccf9fe5';

const config = {
  schemaVersion: 3,
  id: '00000000-0000-0000-0000-000000000001',
  version: 1,
  defaults: { language: 'en', datastoreSize: '95%' },
  encryption: { mode: 'plaintext' },
} as RdcConfig;

describe('background flag over /v1/command', () => {
  let server: ReturnType<typeof serve>;
  let baseUrl: string;
  let dir: string;
  let windows: (number | undefined)[];
  let followed: number;

  function boot(): void {
    const deps: ServeDeps = {
      mode: 'daemon',
      auth: new AuthVerifier({
        accountUrl: 'https://account.test',
        executorToken: 'rdt_executor',
        fetchImpl: (() =>
          Promise.resolve(
            Response.json({
              active: true,
              scopes: ['proxy:exec', 'audit:write'],
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
      executor: {
        execute(options: ExecuteOptions): Promise<ExecuteResult> {
          if (options.functionName !== 'repository_up') {
            return Promise.resolve({ success: true, exitCode: 0, durationMs: 1 });
          }
          windows.push(options.attachWindowMs);
          options.onJobStarted?.(JOB, options.machineName);
          // A zero window returns the ticket at once; any other window would hold the call and follow the job.
          if (options.attachWindowMs !== 0) followed += 1;
          return Promise.resolve({
            success: true,
            exitCode: 0,
            durationMs: 1,
            jobId: JOB,
            state: 'running',
            attached: false,
          });
        },
      },
    };
    server = serve({ fetch: createServeApp(deps).fetch, port: 0 });
    baseUrl = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  }

  const up = (extra: Record<string, unknown> = {}) =>
    fetch(`${baseUrl}/v1/command`, {
      method: 'POST',
      headers: { authorization: `Bearer ${TOKEN}`, 'content-type': 'application/json' },
      body: JSON.stringify({
        contractVersion: CLI_CONTRACT_VERSION,
        pathKey: 'repo up',
        params: {},
        positionals: { ref: 'demo:trial' },
        ...extra,
      }),
    });

  async function lines(response: Response): Promise<StreamLine[]> {
    const text = await response.text();
    return text
      .split('\n')
      .filter((l) => l.trim() !== '')
      .map((l) => StreamLineSchema.parse(JSON.parse(l)));
  }

  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), 'job-background-'));
    const store = new TicketStore('test', dir);
    windows = [];
    followed = 0;
    setCommandJobDeps({
      store: () => store,
      stepDeps: () =>
        Promise.resolve({
          observer: { configName: 'test' },
          warn: () => undefined,
          claim: ({ steps }) =>
            Promise.resolve(steps.map((name) => ({ name, result: 'claimed' as const }))),
        }),
    });
    boot();
  });

  afterEach(async () => {
    setCommandJobDeps();
    rmSync(dir, { recursive: true, force: true });
    await new Promise<void>((resolve) => server.close(() => resolve()));
  });

  it('C: background starts the job with a zero window, announces its id and follows nothing', async () => {
    const all = await lines(await up({ background: true }));
    expect(windows).toEqual([0]);
    expect(followed).toBe(0);
    expect(all.find((l) => l.kind === 'job')).toMatchObject({ jobId: JOB, machine: 'hostinger' });
    expect(all.at(-1)).toMatchObject({ kind: 'result', result: { jobId: JOB, state: 'running' } });
  });

  it('D: without the flag the served window stands, and background:false is the same', async () => {
    await (await up()).text();
    await (await up({ background: false })).text();
    expect(windows).toEqual([JOB_ATTACH_WINDOW_MS, JOB_ATTACH_WINDOW_MS]);
  });

  it('a backgrounded request never leaks its flag into the next request', async () => {
    await (await up({ background: true })).text();
    await (await up()).text();
    expect(windows).toEqual([0, JOB_ATTACH_WINDOW_MS]);
  });
});
