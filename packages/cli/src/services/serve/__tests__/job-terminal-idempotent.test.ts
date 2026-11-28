/**
 * WB9 (agent/plans/PLAN-rmcp-writeback.md Design 9): a job's terminal audit event
 * carries the same idempotency key in every executor process.
 *
 * The ledger that ships a terminal event once per job lives in memory and is
 * lost on every container sleep, so a restarted executor's first poll of a
 * finished job ships the terminal event again. Two serve apps (two ledgers, the
 * process before and after a restart) poll one finished job; the real audit
 * shipper must send both events under one key, derived from the job id, so the
 * account server, which keeps a key once, records the job's end once. Any other
 * event still gets a fresh key per occurrence.
 */

import { AuditEventsRequestSchema } from '@rediacc/shared';
import { PROXY_ROUTES } from '@rediacc/shared/cli-contract/wire';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../../executor/job-remote.js', async (original) => ({
  ...(await original<Record<string, unknown>>()),
  connectForJobs: () =>
    Promise.resolve({ remoteRenetPath: '/usr/bin/renet', lease: { release: () => {} } }),
  runJobCommand: () =>
    Promise.resolve(
      `${JSON.stringify({ type: 'job_status', state: 'failed', exit_code: 1, function: 'repository_create' })}\n`
    ),
}));
vi.mock('../../jobs/executor-observation.js', () => ({
  observeTerminalPoll: () => Promise.resolve(undefined),
}));

import { auditIdempotencyKey, createExecutorAudit, uuidV5 } from '../audit.js';
import { AuthVerifier } from '../auth.js';
import { serveCrypto } from '../crypto.js';
import type { ExecutorAuditEvent, ServeDeps } from '../deps.js';
import { authorize } from '../policy.js';
import { createServeApp } from '../server.js';
import { SessionStore } from '../sessions.js';

const JOB_ID = 'j18c1c04dd251ce26-0ccf9fe5';
const TOKEN = 'rdt_owner';

const IDENTITY = {
  active: true,
  scopes: ['proxy:exec', 'audit:write'],
  orgId: 'org-1',
  teamId: 'team-1',
  createdByUserId: 'user-owner',
  userEmail: 'owner@example.com',
  orgRole: 'owner',
};

function config(): RdcConfig {
  return {
    schemaVersion: 3,
    id: '00000000-0000-0000-0000-000000000001',
    version: 1,
    encryption: { mode: 'plaintext' },
  } as RdcConfig;
}

/** One executor process: its own app, so its own in-memory terminal ledger. */
function executorProcess(shipped: { idempotencyKey: string; type: string }[]) {
  const deps: ServeDeps = {
    mode: 'daemon',
    auth: new AuthVerifier({
      accountUrl: 'https://account.test',
      executorToken: 'rdt_executor',
      fetchImpl: (() => Promise.resolve(Response.json(IDENTITY))) as unknown as typeof fetch,
    }),
    sessions: new SessionStore(),
    crypto: serveCrypto,
    loadConfig: () => Promise.resolve(config()),
    authorize,
    // The real shipper; the account server's audit route is the capture.
    audit: createExecutorAudit({
      accountUrl: 'https://account.test',
      executorToken: 'rdt_executor',
      fetchImpl: ((_url: string | URL, init?: RequestInit) => {
        const body = AuditEventsRequestSchema.parse(JSON.parse(init?.body as string));
        for (const event of body.events) {
          shipped.push({ idempotencyKey: event.idempotencyKey, type: event.type });
        }
        return Promise.resolve(Response.json({ ok: true }));
      }) as typeof fetch,
    }),
    executor: { execute: () => Promise.reject(new Error('no command runs here')) },
  };
  return createServeApp(deps);
}

function poll(app: ReturnType<typeof createServeApp>) {
  return app.request(`${PROXY_ROUTES.jobPoll(JOB_ID)}?machine=hostinger`, {
    headers: { authorization: `Bearer ${TOKEN}` },
  });
}

describe('WB9: the terminal audit event is idempotent across executor restarts', () => {
  it('two ledgers, before and after a restart, ship one job terminal event under one key', async () => {
    const shipped: { idempotencyKey: string; type: string }[] = [];

    const before = executorProcess(shipped);
    expect((await poll(before)).status).toBe(200);
    // The same ledger ships it once only.
    expect((await poll(before)).status).toBe(200);
    expect(shipped).toHaveLength(1);

    const after = executorProcess(shipped);
    expect((await poll(after)).status).toBe(200);

    expect(shipped).toHaveLength(2);
    expect(shipped[1]?.idempotencyKey).toBe(shipped[0]?.idempotencyKey);
    expect(shipped[0]?.idempotencyKey).toBe(
      uuidV5('6f1d7c2e-3b4a-4e8f-9c05-1a2b3c4d5e6f', `job:${JOB_ID}:terminal`)
    );
  });

  it('control: an event that is not a job terminal gets a fresh key each time', () => {
    const event: ExecutorAuditEvent = {
      principal: { userId: 'u', orgId: 'o', teamId: null, userEmail: 'u@example.com' } as never,
      commandPath: 'repo up',
      params: {},
      success: true,
      exitCode: 0,
      durationMs: 1,
      destructive: false,
      jobId: JOB_ID,
      outcome: 'started',
    };
    expect(auditIdempotencyKey(event)).not.toBe(auditIdempotencyKey(event));
    // A terminal outcome of another job keys differently.
    expect(auditIdempotencyKey({ ...event, outcome: 'failed' })).not.toBe(
      auditIdempotencyKey({ ...event, jobId: 'j18c1c04dd251ce26-00000000', outcome: 'failed' })
    );
  });

  it('derives an RFC 9562 version-5 UUID (the RFC example vector)', () => {
    // RFC 9562 appendix A.4: "www.example.com" in the DNS namespace.
    expect(uuidV5('6ba7b810-9dad-11d1-80b4-00c04fd430c8', 'www.example.com')).toBe(
      '2ed6657d-e927-568b-95e1-2665a8aea6a2'
    );
  });
});
