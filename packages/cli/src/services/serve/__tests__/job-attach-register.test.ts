/**
 * A retried POST of a verb that registers a record before its job (PLAN-detached-jobs J6b): `repo create` and
 * `repo fork` write the repo into the config, then start one machine job. A POST dropped before the job line and
 * retried with the same body id must attach to the record and the job the first attempt made, while a fresh
 * command naming the same repo (no body id, or another one) still refuses as a duplicate.
 *
 * The config is a stateful fake that outlives each request, like a daemon's file. The executor is faked at the
 * machine seam and keeps renet's request index; everything between HTTP and the dispatch is production code.
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

type Row = { repositoryGuid: string; networkId?: number; [key: string]: unknown };

const { rows, parentMachine } = vi.hoisted(() => ({
  rows: new Map<string, Row>(),
  parentMachine: { value: 'hostinger' },
}));

vi.mock('../../config/network-id-discovery.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../config/network-id-discovery.js')>()),
  ensureRepositoryNetworkId: vi.fn(() => Promise.resolve(7)),
  targetFloor: vi.fn(() => Promise.resolve([])),
}));
vi.mock('../../config/config-resources.js', () => ({
  configService: {
    resetResourceView: vi.fn(),
    getRepository: vi.fn((name: string) =>
      Promise.resolve(
        rows.get(name) ?? (name.includes(':') ? undefined : rows.get(`${name}:latest`))
      )
    ),
    addRepository: vi.fn((name: string, row: Row) => {
      rows.set(name, row);
      return Promise.resolve();
    }),
    removeRepository: vi.fn((name: string) => {
      rows.delete(name);
      return Promise.resolve();
    }),
    allocateNetworkId: vi.fn(() => Promise.resolve(41)),
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
          machines: { hostinger: {}, elsewhere: {} },
          repositories: {
            shop: {
              grand: 'base',
              tags: { base: {} },
              placement: { machine: parentMachine.value },
            },
          },
        },
      })
    ),
  },
}));

vi.mock('../../machine/machine-connection.js', () => ({
  machineConnections: {
    acquire: vi.fn(() => Promise.resolve({ ensure: vi.fn(), release: vi.fn() })),
  },
}));
vi.mock('../../repo/repo-key-deployment.js', () => ({
  deployRepoKeyIfNeeded: vi.fn(() => Promise.resolve()),
  removeRepoKeyIfDeployed: vi.fn(() => Promise.resolve()),
}));
vi.mock('../../backup/repo-change-hook.js', () => ({
  reconcileBackupSchedules: vi.fn(() => Promise.resolve()),
}));

const { proxyToken } = vi.hoisted(() => ({ proxyToken: { value: 'rdt_owner' } }));
vi.mock('../../account/subscription-auth.js', async (original) => ({
  ...(await original<Record<string, unknown>>()),
  getSubscriptionTokenState: () => ({ kind: 'ready', token: { token: proxyToken.value } }),
}));

process.env.REDIACC_TELEMETRY_DISABLED = '1';

import type { ExecuteOptions, ExecuteResult } from '../../executor/types.js';
import { setCommandJobDeps } from '../../jobs/command-job.js';
import { TicketStore } from '../../jobs/ticket-store.js';
import { AuthVerifier } from '../auth.js';
import { serveCrypto } from '../crypto.js';
import type { ServeDeps } from '../deps.js';
import { authorize } from '../policy.js';
import { createServeApp } from '../server.js';
import { SessionStore } from '../sessions.js';

const TOKEN = 'rdt_owner';
const REQUEST_ID = 'inv-reg-0123';

const config = {
  schemaVersion: 3,
  id: '00000000-0000-0000-0000-000000000001',
  version: 1,
  defaults: { language: 'en', datastoreSize: '95%' },
  encryption: { mode: 'plaintext' },
} as RdcConfig;

describe('a retried POST of a verb that registers before its job', () => {
  let server: ReturnType<typeof serve>;
  let baseUrl: string;
  let dir: string;
  let jobs: Map<string, string>;

  function bootMachine() {
    const execute = (options: ExecuteOptions): Promise<ExecuteResult> => {
      if (
        options.functionName !== 'repository_create' &&
        options.functionName !== 'repository_fork'
      ) {
        return Promise.resolve({ success: true, exitCode: 0, durationMs: 1 });
      }
      // renet's request index: a known id answers with the job it started, and starts nothing.
      const id = options.requestId ?? '';
      let jobId = jobs.get(id);
      if (!jobId) {
        jobId = `j18c1c04dd251ce26-${String(jobs.size).padStart(8, '0')}`;
        jobs.set(id, jobId);
      }
      options.onJobStarted?.(jobId, options.machineName);
      return Promise.resolve({
        success: true,
        exitCode: 0,
        durationMs: 1,
        jobId,
        state: 'running',
        attached: false,
      });
    };
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
      executor: { execute },
    };
    server = serve({ fetch: createServeApp(deps).fetch, port: 0 });
    baseUrl = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  }

  async function run(
    pathKey: string,
    params: Record<string, unknown>,
    positionals: Record<string, string>,
    extra: Record<string, unknown> = {}
  ): Promise<StreamLine> {
    const response = await fetch(`${baseUrl}/v1/command`, {
      method: 'POST',
      headers: { authorization: `Bearer ${TOKEN}`, 'content-type': 'application/json' },
      body: JSON.stringify({
        contractVersion: CLI_CONTRACT_VERSION,
        pathKey,
        params,
        positionals,
        ...extra,
      }),
    });
    const all = (await response.text())
      .split('\n')
      .filter((l) => l.trim() !== '')
      .map((l) => StreamLineSchema.parse(JSON.parse(l)));
    const last = all.at(-1);
    if (last?.kind !== 'result') throw new Error(`no result line: ${JSON.stringify(all)}`);
    return last;
  }

  const verbs = {
    'repo create': () =>
      ['repo create', { machine: 'hostinger', size: '1G' }, { name: 'fresh' }] as const,
    'repo fork': () => ['repo fork', { tag: 'trial' }, { ref: 'shop' }] as const,
  };
  const rowName = { 'repo create': 'fresh:latest', 'repo fork': 'shop:trial' };

  beforeEach(() => {
    rows.clear();
    parentMachine.value = 'hostinger';
    // The parent of the fork, as the config holds it.
    rows.set('shop', { repositoryGuid: 'guid-shop', credential: 'set', networkId: 7 });
    dir = mkdtempSync(join(tmpdir(), 'job-attach-register-'));
    const store = new TicketStore('test', dir);
    jobs = new Map();
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
    bootMachine();
  });

  afterEach(async () => {
    setCommandJobDeps();
    rmSync(dir, { recursive: true, force: true });
    await new Promise<void>((resolve) => server.close(() => resolve()));
  });

  for (const verb of ['repo create', 'repo fork'] as const) {
    describe(verb, () => {
      const call = (extra: Record<string, unknown> = {}) => run(...verbs[verb](), extra);

      it('attaches a retry with the same body id to the first attempt: one job, one record', async () => {
        const first = await call({ requestId: REQUEST_ID });
        const second = await call({ requestId: REQUEST_ID });

        expect(first).toMatchObject({ result: { success: true } });
        expect(second).toMatchObject({ result: { success: true } });
        expect([...jobs.keys()]).toHaveLength(1);
        expect([...jobs.keys()][0]).toMatch(new RegExp(`^${REQUEST_ID}:hostinger:\\d+$`));
        expect(rows.has(rowName[verb])).toBe(true);
      });

      it('control: no body id, or a different one, still refuses the duplicate', async () => {
        await call({ requestId: REQUEST_ID });
        const other = await call({ requestId: `${REQUEST_ID}-other` });
        const bare = await call();
        const bareAgain = await call();

        for (const refused of [other, bare, bareAgain]) {
          expect(refused).toMatchObject({ result: { success: false } });
        }
        expect([...jobs.keys()]).toHaveLength(1);
      });

      it('control: a record that was there before the request is refused even with a body id', async () => {
        rows.set(rowName[verb], { repositoryGuid: 'someone-elses', credential: 'set' });
        const result = await call({ requestId: REQUEST_ID });
        expect(result).toMatchObject({ result: { success: false } });
        expect(jobs.size).toBe(0);
      });
    });
  }

  it('repo create: the same body id asking for another machine is refused, not reported as the first placement', async () => {
    const [pathKey, params, positionals] = verbs['repo create']();
    await run(pathKey, params, positionals, { requestId: REQUEST_ID });
    const moved = await run(pathKey, { ...params, machine: 'elsewhere' }, positionals, {
      requestId: REQUEST_ID,
    });

    expect(moved).toMatchObject({ result: { success: false } });
    expect([...jobs.keys()]).toHaveLength(1);
  });

  it('repo fork: a retry after the parent moved machines is refused, not reported as the first placement', async () => {
    await run(...verbs['repo fork'](), { requestId: REQUEST_ID });
    parentMachine.value = 'elsewhere';

    const moved = await run(...verbs['repo fork'](), { requestId: REQUEST_ID });

    expect(moved).toMatchObject({ result: { success: false } });
    expect([...jobs.keys()]).toHaveLength(1);
  });

  it('repo fork: a retry finding its row without a network ID is refused, never passed on as ID 0', async () => {
    await run(...verbs['repo fork'](), { requestId: REQUEST_ID });
    const row = rows.get('shop:trial');
    if (!row) throw new Error('the first attempt registered no row');
    delete row.networkId;

    const retried = await run(...verbs['repo fork'](), { requestId: REQUEST_ID });

    expect(retried).toMatchObject({ result: { success: false } });
    expect([...jobs.keys()]).toHaveLength(1);
  });
});
