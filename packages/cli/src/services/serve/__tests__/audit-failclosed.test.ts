/**
 * WB8 (agent/plans/PLAN-rmcp-writeback.md Design 8): a mutating command whose
 * audit record cannot be delivered is not run.
 *
 * The executor records a mutating command as `started` before it dispatches it.
 * With the account server's audit route unreachable, that record fails after its
 * retry, and `repo delete` is refused with AUDIT_UNAVAILABLE before the machine
 * is called. A read changes nothing a missing record would hide: `repo list`
 * runs, and its result carries the warning that it ran unrecorded.
 *
 * The real serve app and the real audit shipper run; only the account server's
 * audit route (unreachable) and the machine (a fake renet) are faked.
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
  const scratch = mkdtempSync(`${os.tmpdir()}/rdc-audit-failclosed-`);
  process.env.XDG_CONFIG_HOME = scratch;
  process.env.XDG_STATE_HOME = scratch;
  process.env.XDG_CACHE_HOME = scratch;
  process.env.REDIACC_TELEMETRY_DISABLED = '1';
});

import { AUDIT_DELIVERY_ATTEMPTS, AUDIT_UNAVAILABLE, createExecutorAudit } from '../audit.js';
import {
  bootContainerExecutor,
  type ContainerExecutor,
  createFakeConfigStore,
  EXECUTOR_TOKEN,
  fakeRenet,
  OPEN_POLICY,
  OWNER_TOKEN,
} from './writeback-harness.js';

function storedConfig(): RdcConfig {
  return {
    schemaVersion: 3,
    id: '00000000-0000-4000-8000-0000000000c8',
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

describe('WB8: audit fails closed for mutating commands', () => {
  let executor: ContainerExecutor | undefined;

  afterEach(async () => {
    await executor?.close();
    executor = undefined;
  });

  async function boot() {
    const store = await createFakeConfigStore(storedConfig(), OPEN_POLICY);
    const renet = fakeRenet(() => ({
      success: true,
      exitCode: 0,
      durationMs: 1,
      stdout: '{"repositories":[]}',
    }));
    const auditAttempts: string[] = [];
    // The audit route never answers; every other account call reaches the fake store.
    const unreachableAudit = ((_url: string | URL, init?: RequestInit) => {
      auditAttempts.push(String(init?.body));
      return Promise.reject(
        Object.assign(new TypeError('fetch failed'), { cause: { code: 'ECONNREFUSED' } })
      );
    }) as typeof fetch;
    executor = await bootContainerExecutor(store, renet.executor, {
      audit: createExecutorAudit({
        accountUrl: 'https://account.test',
        executorToken: EXECUTOR_TOKEN,
        fetchImpl: unreachableAudit,
      }),
    });
    await executor.grantKey();
    return { store, renet, auditAttempts };
  }

  function post(
    pathKey: string,
    params: Record<string, unknown>,
    positionals: Record<string, unknown>
  ) {
    return fetch(`${executor!.baseUrl}${PROXY_ROUTES.command}`, {
      method: 'POST',
      headers: { authorization: `Bearer ${OWNER_TOKEN}`, 'content-type': 'application/json' },
      body: JSON.stringify({ contractVersion: CLI_CONTRACT_VERSION, pathKey, params, positionals }),
    });
  }

  it('an unreachable audit route refuses repo delete with AUDIT_UNAVAILABLE and no host call', async () => {
    const { store, renet, auditAttempts } = await boot();

    const response = await post('repo delete', { yes: true }, { ref: 'shop' });

    expect(response.status).toBe(503);
    const body = (await response.json()) as { error: string; code: string };
    expect(body.code).toBe(AUDIT_UNAVAILABLE);
    expect(body.error).toContain('rdc repo delete');
    expect(body.error).toContain('ECONNREFUSED');
    expect(renet.calls).toEqual([]);
    // The first attempt and its retry, one event under one idempotency key.
    expect(auditAttempts).toHaveLength(AUDIT_DELIVERY_ATTEMPTS);
    expect(new Set(auditAttempts).size).toBe(1);
    // Nothing was written: the repo is still registered.
    expect(Object.keys((await store.current()).resources.repositories)).toEqual(['shop']);
  });

  it('repo list still runs, and its result says it ran without an audit record', async () => {
    const { renet } = await boot();

    const result = await executor!.command('repo list', { machine: 'm1' }, {});

    expect(result.result.success).toBe(true);
    expect(renet.calls).toHaveLength(1);
    expect(result.stderr).toMatch(
      /WARNING: "rdc repo list" ran WITHOUT an audit record: .*ECONNREFUSED/
    );
  });
});
