/**
 * Two dispatch paths of the serve command route that the other audit tests never reach.
 *
 * A dispatch that throws (review 196c7829.1, b32c1cdd.3): its failure outcome is still recorded under the request id, and a record that
 * cannot be delivered is reported on the result line. A job that finishes inside the attach window (review ed950aa1.1): its terminal
 * event, shipped by the dispatch, carries the key a poll of the same job would ship.
 *
 * The real serve app and the real audit shipper run; the account server's audit route and the machine (a fake renet) are faked.
 */

import { CLI_CONTRACT_VERSION } from '@rediacc/shared/cli-contract';
import { PROXY_ROUTES } from '@rediacc/shared/cli-contract/wire';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../../utils/agent-guard.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../utils/agent-guard.js')>()),
  isAgentEnvironment: () => false,
}));

const dispatch = vi.hoisted(() => ({ throwNext: false }));
vi.mock('../command-dispatch.js', async (importOriginal) => {
  const original = await importOriginal<typeof import('../command-dispatch.js')>();
  return {
    ...original,
    dispatchCommand: (args: Parameters<typeof original.dispatchCommand>[0]) =>
      dispatch.throwNext
        ? Promise.reject(new Error('dispatch exploded'))
        : original.dispatchCommand(args),
  };
});

await vi.hoisted(async () => {
  const { mkdtempSync } = await import('node:fs');
  const os = await import('node:os');
  const scratch = mkdtempSync(`${os.tmpdir()}/rdc-audit-dispatch-paths-`);
  process.env.XDG_CONFIG_HOME = scratch;
  process.env.XDG_STATE_HOME = scratch;
  process.env.XDG_CACHE_HOME = scratch;
  process.env.REDIACC_TELEMETRY_DISABLED = '1';
});

import { AuditEventsRequestSchema } from '@rediacc/shared';
import { createExecutorAudit, uuidV5 } from '../audit.js';
import type { ExecutorAuditEvent } from '../deps.js';
import {
  bootContainerExecutor,
  type ContainerExecutor,
  createFakeConfigStore,
  EXECUTOR_TOKEN,
  fakeRenet,
  OPEN_POLICY,
  OWNER_TOKEN,
} from './writeback-harness.js';

const REQUEST_ID = 'req-dispatch-paths.1';

function storedConfig(): RdcConfig {
  return {
    schemaVersion: 3,
    id: '00000000-0000-4000-8000-0000000000ca',
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
              credential: 'shop-credential',
            },
          },
        },
      },
    },
    state: { repos: { shop: { latest: { networkId: 2816 } } } },
    encryption: { mode: 'plaintext' },
  } as unknown as RdcConfig;
}

describe('the dispatch paths of the command route', () => {
  let executor: ContainerExecutor | undefined;

  afterEach(async () => {
    dispatch.throwNext = false;
    await executor?.close();
    executor = undefined;
  });

  async function post(
    audit: (event: ExecutorAuditEvent) => Promise<void>,
    answer?: Parameters<typeof fakeRenet>[0]
  ) {
    const store = await createFakeConfigStore(storedConfig(), OPEN_POLICY);
    executor = await bootContainerExecutor(store, fakeRenet(answer).executor, { audit });
    await executor.grantKey();
    return fetch(`${executor.baseUrl}${PROXY_ROUTES.command}`, {
      method: 'POST',
      headers: { authorization: `Bearer ${OWNER_TOKEN}`, 'content-type': 'application/json' },
      body: JSON.stringify({
        contractVersion: CLI_CONTRACT_VERSION,
        pathKey: 'repo delete',
        params: { yes: true },
        positionals: { ref: 'shop' },
        requestId: REQUEST_ID,
      }),
    });
  }

  it('a dispatch that throws records its failure outcome under the request id (review 196c7829.1)', async () => {
    dispatch.throwNext = true;
    const events: ExecutorAuditEvent[] = [];
    const response = await post((event) => {
      events.push(event);
      return Promise.resolve();
    });
    expect(await response.text()).toContain('dispatch exploded');

    expect(events.map((event) => event.outcome)).toEqual(['started', undefined]);
    expect(events[1]).toMatchObject({ success: false, exitCode: 1 });
    for (const event of events) expect(event.requestId).toBe(REQUEST_ID);
  });

  it('a dispatch that throws and cannot record says audit_failed on the result line (review b32c1cdd.3)', async () => {
    dispatch.throwNext = true;
    let delivered = 0;
    const shipper = createExecutorAudit({
      accountUrl: 'https://account.test',
      executorToken: EXECUTOR_TOKEN,
      fetchImpl: (() => {
        delivered++;
        // Only the pre-dispatch `started` record lands.
        return delivered === 1
          ? Promise.resolve(new Response('{}'))
          : Promise.reject(new TypeError('fetch failed'));
      }) as typeof fetch,
    });
    const response = await post(shipper);
    const lines = (await response.text())
      .trim()
      .split('\n')
      .map((line) => JSON.parse(line) as { kind: string; stderr?: string });
    const result = lines.find((line) => line.kind === 'result');
    expect(result?.stderr).toMatch(
      /audit_failed: "rdc repo delete" ran, but its audit record could not be delivered/
    );
  });

  it('a job that finishes inside the attach window ships its terminal event under the poll key (review ed950aa1.1)', async () => {
    const shipped: { idempotencyKey: string; data: { outcome?: string; jobId?: string } }[] = [];
    const shipper = createExecutorAudit({
      accountUrl: 'https://account.test',
      executorToken: EXECUTOR_TOKEN,
      fetchImpl: ((_url: string | URL, init?: RequestInit) => {
        const body = AuditEventsRequestSchema.parse(JSON.parse(init?.body as string));
        for (const event of body.events) shipped.push(event as never);
        return Promise.resolve(new Response('{}'));
      }) as typeof fetch,
    });
    await (
      await post(shipper, () => ({
        success: true,
        exitCode: 0,
        durationMs: 1,
        stdout: '',
        jobId: 'job-dispatch-1',
        state: 'succeeded',
      }))
    ).text();

    const terminal = shipped.find((event) => event.data.outcome === 'succeeded');
    expect(terminal?.data.jobId).toBe('job-dispatch-1');
    // The key a poll of the same job ships (audit.ts auditIdempotencyKey).
    expect(terminal?.idempotencyKey).toBe(
      uuidV5('6f1d7c2e-3b4a-4e8f-9c05-1a2b3c4d5e6f', 'job:job-dispatch-1:terminal')
    );
    // Control: the pre-dispatch record is one occurrence of its own, not the job's terminal key.
    const started = shipped.find((event) => event.data.outcome === 'started');
    expect(started?.idempotencyKey).not.toBe(terminal?.idempotencyKey);
  });
});
