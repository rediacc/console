/**
 * The poll and cancel routes of a proxied job (PLAN-detached-jobs J6, Design 4).
 *
 * The routes run `renet job logs ... --with-status` and `job cancel` through the job-remote seam, which is
 * mocked here: no machine is touched. Everything between the HTTP request and that seam is production code:
 * authentication, the policy check on the contract commands `job logs` and `job cancel`, the body schema
 * and the once-per-job terminal audit.
 */

import { JobPollResponseSchema, PROXY_ROUTES } from '@rediacc/shared/cli-contract/wire';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { ran, cancelled, spool } = vi.hoisted(() => ({
  ran: [] as string[],
  cancelled: [] as string[],
  spool: { stdout: '' },
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
  runJobCommand: vi.fn((_conn: unknown, command: string) => {
    ran.push(command);
    return Promise.resolve(spool.stdout);
  }),
  cancelJob: vi.fn((_conn: unknown, jobId: string) => {
    cancelled.push(jobId);
    return Promise.resolve({ state: 'cancelled', exit_code: 130 });
  }),
}));

import { AuthVerifier } from '../auth.js';
import { serveCrypto } from '../crypto.js';
import type { ServeDeps } from '../deps.js';
import { authorize } from '../policy.js';
import { createServeApp } from '../server.js';
import { SessionStore } from '../sessions.js';

const ID = 'j18c1c04dd251ce26-0ccf9fe5';
const TOKEN = 'rdt_owner';

function config(policy?: unknown): RdcConfig {
  return {
    schemaVersion: 3,
    id: '00000000-0000-0000-0000-000000000001',
    version: 1,
    defaults: { language: 'en', datastoreSize: '95%' },
    encryption: { mode: 'plaintext' },
    ...(policy ? { policy } : {}),
  } as RdcConfig;
}

/** The command as the shell would see its words. */
function unquoted(command: string | undefined): string {
  return (command ?? '').replaceAll("'", '');
}

function trailer(extra: Record<string, unknown> = {}): string {
  return JSON.stringify({
    type: 'job_status',
    state: 'running',
    function: 'repository_up',
    exit_code: null,
    ...extra,
  });
}

describe('job poll and cancel routes', () => {
  let audited: { commandPath: string; destructive: boolean; success: boolean }[];
  let app: ReturnType<typeof createServeApp>;

  function boot(policy?: unknown) {
    audited = [];
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
      loadConfig: () => Promise.resolve(config(policy)),
      authorize,
      audit: (event) => {
        audited.push(event);
        return Promise.resolve();
      },
      executor: { execute: () => Promise.reject(new Error('no command runs here')) },
    };
    app = createServeApp(deps);
  }

  const get = (path: string, token: string | undefined = TOKEN) =>
    app.request(path, { headers: token ? { authorization: `Bearer ${token}` } : {} });

  beforeEach(() => {
    ran.length = 0;
    cancelled.length = 0;
    spool.stdout = `${JSON.stringify({ type: 'output', msg: 'a' })}\n${JSON.stringify({ type: 'output', msg: 'b' })}\n${trailer()}\n`;
    boot();
  });

  it('returns the lines past sinceLine with the status, in one body the schema accepts', async () => {
    const res = await get(`${PROXY_ROUTES.jobPoll(ID)}?machine=hostinger&sinceLine=3&maxLines=100`);
    expect(res.status).toBe(200);
    const body = JobPollResponseSchema.parse(await res.json());
    expect(body.events.map((e) => e.line)).toEqual([3, 4]);
    expect(body.nextLine).toBe(5);
    expect(body.more).toBe(false);
    expect(body.status).toEqual({ state: 'running', function: 'repository_up' });
    expect(ran).toHaveLength(1);
    expect(unquoted(ran[0])).toContain('job logs --id');
    expect(unquoted(ran[0])).toContain('--since-line 3');
    expect(unquoted(ran[0])).toContain('--max-lines 100');
    expect(unquoted(ran[0])).toContain('--with-status');
  });

  it('honours maxLines: a full page says more is waiting', async () => {
    spool.stdout = `${[1, 2, 3].map((n) => JSON.stringify({ type: 'output', msg: String(n) })).join('\n')}\n${trailer()}\n`;
    const res = await get(`${PROXY_ROUTES.jobPoll(ID)}?machine=hostinger&sinceLine=0&maxLines=3`);
    const body = JobPollResponseSchema.parse(await res.json());
    expect(body.more).toBe(true);
    expect(unquoted(ran[0])).toContain('--max-lines 3');
  });

  it('refuses a poll with no token, no machine or a made-up id before any exec', async () => {
    expect((await get(`${PROXY_ROUTES.jobPoll(ID)}?machine=hostinger`, '')).status).toBe(401);
    expect((await get(PROXY_ROUTES.jobPoll(ID))).status).toBe(400);
    expect((await get('/v1/jobs/not-a-real-id/poll?machine=hostinger')).status).toBe(400);
    expect(ran).toHaveLength(0);
  });

  it('denies a poll for a machine outside the caller policy (403)', async () => {
    boot({ version: 1, defaults: { commands: { allow: ['repo *'] } } });
    const res = await get(`${PROXY_ROUTES.jobPoll(ID)}?machine=hostinger`);
    expect(res.status).toBe(403);
    expect(ran).toHaveLength(0);
  });

  it('ships exactly one terminal audit event across three polls of a finished job', async () => {
    spool.stdout = `${trailer({ state: 'succeeded', exit_code: 0, finished_at: '2026-11-04T00:00:00Z' })}\n`;
    for (let i = 0; i < 3; i++) {
      expect((await get(`${PROXY_ROUTES.jobPoll(ID)}?machine=hostinger`)).status).toBe(200);
    }
    expect(audited).toHaveLength(1);
    expect(audited[0]).toMatchObject({ commandPath: 'job logs', success: true });
  });

  it('writes no terminal audit while the job still runs', async () => {
    await get(`${PROXY_ROUTES.jobPoll(ID)}?machine=hostinger`);
    expect(audited).toHaveLength(0);
  });

  it('cancels through the cancel route and audits it as destructive', async () => {
    const res = await app.request(`${PROXY_ROUTES.jobCancel(ID)}?machine=hostinger`, {
      method: 'POST',
      headers: { authorization: `Bearer ${TOKEN}` },
    });
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ state: 'cancelled', exitCode: 130 });
    expect(cancelled).toEqual([ID]);
    expect(audited).toHaveLength(1);
    expect(audited[0]).toMatchObject({
      commandPath: 'job cancel',
      destructive: true,
      success: true,
    });
  });

  it('refuses a cancel the policy does not allow', async () => {
    boot({ version: 1, defaults: { commands: { allow: ['job logs'] } } });
    const res = await app.request(`${PROXY_ROUTES.jobCancel(ID)}?machine=hostinger`, {
      method: 'POST',
      headers: { authorization: `Bearer ${TOKEN}` },
    });
    expect(res.status).toBe(403);
    expect(cancelled).toHaveLength(0);
  });

  it('no longer serves the held re-attach route', async () => {
    expect((await get(`/v1/jobs/${ID}/events?machine=hostinger`)).status).toBe(404);
  });
});
