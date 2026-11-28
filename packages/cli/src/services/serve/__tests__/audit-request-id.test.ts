/**
 * Review 196c7829.1: the executor ships the command request's id on each audit event it records (the
 * `started` record before a mutating command, its terminal outcome, and the outcome of a dispatch that
 * threw), so the account Worker joins the event to the console run that caused it. A request without an id
 * ships events without the key.
 *
 * The real serve app runs; the audit sink and the machine (a fake renet) are faked.
 */

import { CLI_CONTRACT_VERSION } from '@rediacc/shared/cli-contract';
import { PROXY_ROUTES } from '@rediacc/shared/cli-contract/wire';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../../utils/agent-guard.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../utils/agent-guard.js')>()),
  isAgentEnvironment: () => false,
}));

await vi.hoisted(async () => {
  const { mkdtempSync } = await import('node:fs');
  const os = await import('node:os');
  const scratch = mkdtempSync(`${os.tmpdir()}/rdc-audit-request-id-`);
  process.env.XDG_CONFIG_HOME = scratch;
  process.env.XDG_STATE_HOME = scratch;
  process.env.XDG_CACHE_HOME = scratch;
  process.env.REDIACC_TELEMETRY_DISABLED = '1';
});

import type { ExecutorAuditEvent } from '../deps.js';
import {
  bootContainerExecutor,
  type ContainerExecutor,
  createFakeConfigStore,
  fakeRenet,
  OPEN_POLICY,
  OWNER_TOKEN,
} from './writeback-harness.js';

const REQUEST_ID = 'req-audit.1';

function storedConfig(): RdcConfig {
  return {
    schemaVersion: 3,
    id: '00000000-0000-4000-8000-0000000000c9',
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

describe('the audit events carry the command request id', () => {
  let executor: ContainerExecutor | undefined;

  afterEach(async () => {
    await executor?.close();
    executor = undefined;
  });

  async function run(
    pathKey: string,
    params: Record<string, unknown>,
    positionals: Record<string, unknown>,
    requestId: string | undefined,
    renetFn: Parameters<typeof fakeRenet>[0]
  ) {
    const store = await createFakeConfigStore(storedConfig(), OPEN_POLICY);
    const events: ExecutorAuditEvent[] = [];
    executor = await bootContainerExecutor(store, fakeRenet(renetFn).executor, {
      audit: (event) => {
        events.push(event);
        return Promise.resolve();
      },
    });
    await executor.grantKey();
    const response = await fetch(`${executor.baseUrl}${PROXY_ROUTES.command}`, {
      method: 'POST',
      headers: { authorization: `Bearer ${OWNER_TOKEN}`, 'content-type': 'application/json' },
      body: JSON.stringify({
        contractVersion: CLI_CONTRACT_VERSION,
        pathKey,
        params,
        positionals,
        ...(requestId ? { requestId } : {}),
      }),
    });
    await response.text();
    return events;
  }

  const ok = () => ({
    success: true,
    exitCode: 0,
    durationMs: 1,
    stdout: '{"repositories":[]}',
  });

  it('a mutating command records started and its outcome under the request id', async () => {
    const events = await run('repo delete', { yes: true }, { ref: 'shop' }, REQUEST_ID, ok);
    expect(events.length).toBeGreaterThanOrEqual(2);
    expect(events[0]?.outcome).toBe('started');
    for (const event of events) expect(event.requestId).toBe(REQUEST_ID);
  });

  it('a read records its outcome under the request id', async () => {
    const events = await run('repo list', { machine: 'm1' }, {}, REQUEST_ID, ok);
    expect(events.length).toBeGreaterThanOrEqual(1);
    for (const event of events) expect(event.requestId).toBe(REQUEST_ID);
  });

  it('a dispatch that throws records its failure under the request id', async () => {
    const events = await run('repo list', { machine: 'm1' }, {}, REQUEST_ID, () => {
      throw new Error('renet exploded');
    });
    expect(events.some((event) => !event.success)).toBe(true);
    for (const event of events) expect(event.requestId).toBe(REQUEST_ID);
  });

  // Review 123777d6.2: the observed call's params reach the outcome event, which is where the audit takes the repository identity from.
  it('the outcome event carries the function and params the command actually called', async () => {
    const events = await run('repo delete', { yes: true }, { ref: 'shop' }, REQUEST_ID, ok);
    const outcome = events.find((event) => event.functionName === 'repository_delete');
    expect(outcome?.functionParams).toMatchObject({ repository: 'shop:latest' });
  });

  it('control: a read names no repository in its function params', async () => {
    const events = await run('repo list', { machine: 'm1' }, {}, REQUEST_ID, ok);
    expect(events.length).toBeGreaterThanOrEqual(1);
    for (const event of events) expect(event.functionParams?.repository).toBeUndefined();
  });

  it('control: a request without an id ships events without the key', async () => {
    const events = await run('repo delete', { yes: true }, { ref: 'shop' }, undefined, ok);
    expect(events.length).toBeGreaterThanOrEqual(2);
    for (const event of events) expect(event).not.toHaveProperty('requestId');
  });
});
