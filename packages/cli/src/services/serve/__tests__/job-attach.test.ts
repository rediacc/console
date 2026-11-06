/**
 * The attach window of a proxied command (PLAN-detached-jobs J6, J6b).
 *
 * `/v1/command` answers with the job line the instant a job starts (machine, overlaps), a heartbeat every
 * quiet period, and one result line: `state: 'running'` when the job outlived the executor seam's attach
 * window. A request id from the body is the invocation id, minted per call as `<id>:<machine>:<seq>`; a
 * client that leaves mid-window never fails the dispatch. The executor is faked (the attach decision itself
 * is the seam's, pinned in the executor tests); everything between HTTP and the dispatch is production code.
 */

import { mkdtempSync, rmSync } from 'node:fs';
import type { AddressInfo } from 'node:net';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { serve } from '@hono/node-server';
import { CLI_CONTRACT_VERSION } from '@rediacc/shared/cli-contract';
import {
  JobPollResponseSchema,
  PROXY_ROUTES,
  type StreamLine,
  StreamLineSchema,
} from '@rediacc/shared/cli-contract/wire';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// The dispatched command runs the real CLI, which would otherwise read the developer's own config from disk. This is the config the EXECUTOR holds.
vi.mock('../../config/network-id-discovery.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../config/network-id-discovery.js')>()),
  ensureRepositoryNetworkId: vi.fn(() => Promise.resolve(7)),
}));
vi.mock('../../config/config-resources.js', () => ({
  configService: {
    resetResourceView: vi.fn(),
    // A key with a tag is a fork, which is what a mutating verb must target to pass the executor's grand-repo guard.
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
    // `shop` is placed on `hostinger` so a derived-machine repo verb (`repo cat`, the positional-ref acceptance vehicle after `_refprobe` retired) resolves its execution machine from placement (spec/03 §2.3), not from a dead `-m`.
    getCurrent: vi.fn(() =>
      Promise.resolve({
        state: {},
        resources: {
          repositories: {
            shop: { grand: 'base', tags: { base: {} }, placement: { machine: 'hostinger' } },
            demo: {
              grand: 'base',
              tags: { base: {}, trial: {} },
              placement: { machine: 'hostinger' },
            },
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

// The poll route reads the job's spool through the job-remote seam; no machine is touched.
const { spool, observed } = vi.hoisted(() => ({
  spool: { stdout: '' },
  observed: [] as { jobId: string; state: string }[],
}));
vi.mock('../../executor/job-remote.js', async (original) => ({
  ...(await original<Record<string, unknown>>()),
  connectForJobs: vi.fn((machine: string) =>
    Promise.resolve({
      machineName: machine,
      remoteRenetPath: '/usr/bin/renet',
      lease: { release: vi.fn(), ensure: vi.fn() },
    })
  ),
  runJobCommand: vi.fn(() => Promise.resolve(spool.stdout)),
}));
vi.mock('../../jobs/executor-observation.js', () => ({
  observeTerminalPoll: vi.fn((jobId: string, seen: { state: string }) => {
    observed.push({ jobId, state: seen.state });
    return Promise.resolve(undefined);
  }),
}));

// Telemetry would otherwise try the network on every dispatched command.
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

  describe('a verb that runs through runCommandJob', () => {
    let dir: string;
    let store: TicketStore;
    /** The machine's request index: a known id answers with the job it started, and starts nothing. */
    let jobs: Map<string, string>;

    /** renet's start, restated for the fake: the `repository_up` call is the verb's job, and any other call answers at once. */
    function jobOf(requestId: string): string {
      const known = jobs.get(requestId);
      if (known) return known;
      const jobId = `j18c1c04dd251ce26-${String(jobs.size).padStart(8, '0')}`;
      jobs.set(requestId, jobId);
      return jobId;
    }

    function bootMachine() {
      boot((options) => {
        if (options.functionName !== 'repository_up') {
          return Promise.resolve({ success: true, exitCode: 0, durationMs: 1 });
        }
        const jobId = jobOf(options.requestId ?? '');
        options.onJobStarted?.(jobId, options.machineName);
        return Promise.resolve({
          success: true,
          exitCode: 0,
          durationMs: 1,
          jobId,
          state: 'running',
          attached: false,
        });
      });
    }

    const up = (extra: Record<string, unknown> = {}) =>
      post({ pathKey: 'repo up', params: {}, positionals: { ref: 'demo:trial' }, ...extra });

    beforeEach(() => {
      dir = mkdtempSync(join(tmpdir(), 'job-attach-retry-'));
      store = new TicketStore('test', dir);
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
    });

    afterEach(() => {
      setCommandJobDeps();
      rmSync(dir, { recursive: true, force: true });
    });

    it('a POST retried with the same body id yields one job and one ticket on that id', async () => {
      bootMachine();
      await (await up({ requestId: REQUEST_ID })).text();
      await (await up({ requestId: REQUEST_ID })).text();

      expect([...jobs.keys()]).toHaveLength(1);
      const [id] = [...jobs.keys()];
      expect(id).toMatch(new RegExp(`^${REQUEST_ID}:hostinger:\\d+$`));
      const tickets = store.tickets().filter((t) => t.verb === 'repo up');
      expect(tickets.map((t) => t.requestId)).toEqual([id]);
    });

    it('control: a different body id is a second job, and no body id a fresh one', async () => {
      bootMachine();
      await (await up({ requestId: REQUEST_ID })).text();
      await (await up({ requestId: `${REQUEST_ID}-other` })).text();
      await (await up()).text();
      await (await up()).text();

      expect([...jobs.keys()]).toHaveLength(4);
      expect(new Set([...jobs.keys()]).size).toBe(4);
    });
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

  it('answers an overlap refusal as a result with code BUSY and the overlaps', async () => {
    const overlap = {
      jobId: 'j1-other',
      function: 'repository_up',
      action: 'refuse',
      attach: 'rdc job logs j1-other -m hostinger --follow',
    };
    boot(() =>
      Promise.reject(
        Object.assign(new Error('Refused to start the job: job j1-other holds the same scope.'), {
          overlaps: [overlap],
        })
      )
    );
    const all = await lines(await post());
    expect(all.filter((l) => l.kind === 'job')).toHaveLength(0);
    const result = all.at(-1);
    expect(result).toMatchObject({
      kind: 'result',
      result: { success: false, errorCode: 'BUSY' },
    });
    if (result?.kind !== 'result') throw new Error('no result line');
    expect(result.result.overlaps?.[0]?.attach).toBe(overlap.attach);
  });

  it('is unchanged for a refused command: a 400 before any stream opens', async () => {
    boot(() => Promise.resolve({ success: true, exitCode: 0, durationMs: 1 }));
    const res = await post({ pathKey: 'repo sync status' });
    expect(res.status).toBe(400);
  });
  /** Let the real I/O of the in-process server run while the timers are faked. */
  async function until(condition: () => boolean): Promise<void> {
    for (let i = 0; i < 2000 && !condition(); i++) await new Promise((r) => setImmediate(r));
    expect(condition()).toBe(true);
  }

  /** Fake the timers a long wait uses; the socket layer keeps its own. */
  const fakeTimers = () =>
    vi.useFakeTimers({
      toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date'],
    });

  describe('with fake timers', () => {
    afterEach(() => {
      vi.useRealTimers();
      setCommandJobDeps();
      spool.stdout = '';
      observed.length = 0;
    });

    it('runs the success step exactly once when the client leaves at 1 s of a 2 s job', async () => {
      const dir = mkdtempSync(join(tmpdir(), 'job-attach-'));
      const handled: string[] = [];
      const claims: { steps: string[]; done?: boolean }[] = [];
      setCommandJobDeps({
        store: () => new TicketStore('test', dir),
        stepDeps: () =>
          Promise.resolve({
            observer: { configName: 'test' },
            warn: () => undefined,
            resolve: (name: string) => {
              handled.push(name);
              return Promise.resolve(() => Promise.resolve());
            },
            claim: ({ steps, done }) => {
              claims.push({ steps, ...(done ? { done } : {}) });
              return Promise.resolve(steps.map((name) => ({ name, result: 'claimed' as const })));
            },
          }),
      });
      let started = false;
      let jobDone = false;
      boot(async (options) => {
        if (options.jobSteps === undefined) {
          return { success: true, exitCode: 0, durationMs: 1 };
        }
        started = true;
        options.onJobStarted?.('j18c1c04dd251ce26-0ccf9fe5', 'hostinger');
        await wait(2000);
        jobDone = true;
        return {
          success: true,
          exitCode: 0,
          durationMs: 2000,
          state: 'succeeded',
          attached: true,
          jobId: 'j18c1c04dd251ce26-0ccf9fe5',
          stdout: 'RDC_CAT_B64:aGk=\n',
        };
      });
      try {
        fakeTimers();
        const controller = new AbortController();
        const response = await post(
          { pathKey: 'repo cat', params: { 'remote-file': '/etc/motd' } },
          controller.signal
        );
        await until(() => started);
        await vi.advanceTimersByTimeAsync(1000);
        controller.abort();
        await response.body?.cancel().catch(() => undefined);
        await vi.advanceTimersByTimeAsync(1500);
        await until(() => jobDone);
        await until(() => claims.some((c) => c.done));
        expect(handled).toEqual(['printRepoCat']);
        expect(claims.filter((c) => c.done)).toHaveLength(1);
        expect(claims.filter((c) => !c.done)).toHaveLength(1);
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    });

    it('hands a 40 s job back as running at the 20 s window, and polls finish it', async () => {
      let window: number | undefined;
      let returnedAt = 0;
      let started = false;
      const t0 = Date.now();
      boot(async (options) => {
        window = options.attachWindowMs;
        started = true;
        options.onJobStarted?.('j18c1c04dd251ce26-0ccf9fe5', 'hostinger');
        // The seam's rule, restated for the fake: the attach ends at the window, the job at 40 s.
        await wait(Math.min(40_000, options.attachWindowMs ?? 40_000));
        returnedAt = Date.now() - t0;
        return {
          success: true,
          exitCode: 0,
          durationMs: returnedAt,
          jobId: 'j18c1c04dd251ce26-0ccf9fe5',
          state: 'running',
          attached: false,
        };
      });
      fakeTimers();
      const response = await post();
      await until(() => started);
      await vi.advanceTimersByTimeAsync(JOB_ATTACH_WINDOW_MS);
      const all = await lines(response);
      expect(window).toBe(JOB_ATTACH_WINDOW_MS);
      expect(returnedAt).toBeGreaterThanOrEqual(19_000);
      expect(returnedAt).toBeLessThanOrEqual(21_000);
      expect(all.at(-1)).toMatchObject({ kind: 'result', result: { state: 'running' } });

      // While the job runs, a poll sees it running; after 40 s of fake time the same poll sees it finished.
      const poll = async () =>
        JobPollResponseSchema.parse(
          await (
            await fetch(
              `${baseUrl}${PROXY_ROUTES.jobPoll('j18c1c04dd251ce26-0ccf9fe5')}?machine=hostinger&sinceLine=1&maxLines=100`,
              { headers: { authorization: `Bearer ${TOKEN}` } }
            )
          ).json()
        );
      // The job's own clock: the spool trailer is derived from elapsed fake time, so a poll
      // reports 'succeeded' only once the 40 s job has really run out, not because the test says so.
      const JOB_MS = 40_000;
      const syncSpool = () => {
        const done = Date.now() - t0 >= JOB_MS;
        spool.stdout = `${JSON.stringify({
          type: 'job_status',
          state: done ? 'succeeded' : 'running',
          function: 'repository_up',
          exit_code: done ? 0 : null,
        })}\n`;
      };
      syncSpool();
      expect((await poll()).status?.state).toBe('running');
      await vi.advanceTimersByTimeAsync(19_000);
      syncSpool();
      expect((await poll()).status?.state).toBe('running');
      await vi.advanceTimersByTimeAsync(1_000);
      syncSpool();
      const finished = await poll();
      expect(finished.status).toMatchObject({ state: 'succeeded', exitCode: 0 });
      expect(Date.now() - t0).toBeGreaterThanOrEqual(40_000);
    });

    it('carries exactly two heartbeats, 10 s apart, in a quiet 25 s window', async () => {
      let started = false;
      boot(async () => {
        started = true;
        await wait(25_000);
        return { success: true, exitCode: 0, durationMs: 25_000 };
      });
      fakeTimers();
      const response = await post();
      await until(() => started);
      await vi.advanceTimersByTimeAsync(25_000);
      const all = await lines(response);
      const beats = all.flatMap((l) => (l.kind === 'heartbeat' && l.ts !== undefined ? [Date.parse(l.ts)] : []));
      // A 10 s period gives exactly the beats at 10 s and 20 s; a 5 s period gives four, a 12.5 s one gives one.
      expect(beats).toHaveLength(2);
      expect(beats[1] - beats[0]).toBe(10_000);
      expect(all.at(-1)?.kind).toBe('result');
    });
  });
});
