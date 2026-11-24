/**
 * The dispatch counter and `GET /v1/busy` (agent/plans/PLAN-console-run-index.md D5): the executor
 * counts the dispatches it runs, so the proxy's alarm can hold a container awake for one whose client left.
 */

import type { RdcConfig } from '@rediacc/shared/config-schema';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../../utils/agent-guard.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../utils/agent-guard.js')>()),
  isAgentEnvironment: () => false,
}));

await vi.hoisted(async () => {
  const { mkdtempSync } = await import('node:fs');
  const os = await import('node:os');
  const scratch = mkdtempSync(`${os.tmpdir()}/rdc-busy-`);
  process.env.XDG_CONFIG_HOME = scratch;
  process.env.XDG_STATE_HOME = scratch;
  process.env.XDG_CACHE_HOME = scratch;
  process.env.REDIACC_TELEMETRY_DISABLED = '1';
});

import { CLI_CONTRACT_VERSION } from '@rediacc/shared/cli-contract';
import { PROXY_ROUTES } from '@rediacc/shared/cli-contract/wire';
import type { ExecuteResult } from '../../executor/types.js';
import { AuthVerifier } from '../auth.js';
import { createBusyCounter } from '../busy.js';
import { serveCrypto } from '../crypto.js';
import { authorize } from '../policy.js';
import { createServeApp } from '../server.js';
import { SessionStore } from '../sessions.js';
import {
  bootContainerExecutor,
  type ContainerExecutor,
  createFakeConfigStore,
  OPEN_POLICY,
  OWNER_TOKEN,
} from './writeback-harness.js';

describe('the busy counter', () => {
  it('counts a dispatch until it settles, success or failure', async () => {
    const busy = createBusyCounter();
    let release: () => void = () => undefined;
    const running = busy.track(
      () =>
        new Promise<void>((resolve) => {
          release = resolve;
        })
    );
    expect(busy.count()).toBe(1);
    release();
    await running;
    expect(busy.count()).toBe(0);

    await expect(busy.track(() => Promise.reject(new Error('boom')))).rejects.toThrow('boom');
    expect(busy.count()).toBe(0);
  });
});

function storedConfig(): RdcConfig {
  return {
    schemaVersion: 3,
    id: '00000000-0000-4000-8000-0000000000e1',
    version: 1,
    credentials: { ssh: { privateKey: 'KEY' } },
    resources: { machines: { m1: { ip: '10.1.1.1', user: 'root', port: 22 } }, repositories: {} },
    state: {},
    encryption: { mode: 'plaintext' },
  } as unknown as RdcConfig;
}

describe('GET /v1/busy', () => {
  let executor: ContainerExecutor | undefined;

  afterEach(async () => {
    await executor?.close();
    executor = undefined;
  });

  it('answers the running dispatch count in the container tier', async () => {
    let release: (result: ExecuteResult) => void = () => undefined;
    let started: () => void = () => undefined;
    const dispatching = new Promise<void>((resolve) => {
      started = resolve;
    });
    const store = await createFakeConfigStore(storedConfig(), OPEN_POLICY);
    executor = await bootContainerExecutor(store, {
      execute: () =>
        new Promise<ExecuteResult>((resolve) => {
          release = resolve;
          started();
        }),
    });
    await executor.grantKey();
    const busy = async () =>
      (await (await fetch(`${executor?.baseUrl}${PROXY_ROUTES.busy}`)).json()) as { busy: number };

    expect(await busy()).toEqual({ busy: 0 });
    const command = fetch(`${executor.baseUrl}${PROXY_ROUTES.command}`, {
      method: 'POST',
      headers: { authorization: `Bearer ${OWNER_TOKEN}`, 'content-type': 'application/json' },
      body: JSON.stringify({
        contractVersion: CLI_CONTRACT_VERSION,
        pathKey: 'repo list',
        params: { machine: 'm1' },
        positionals: {},
      }),
    }).then((response) => response.text());
    await dispatching;
    expect(await busy()).toEqual({ busy: 1 });

    release({ success: true, exitCode: 0, durationMs: 1, stdout: '' });
    await command;
    await vi.waitFor(async () => expect(await busy()).toEqual({ busy: 0 }));
  });

  it('control: a daemon does not serve it', async () => {
    const app = createServeApp({
      mode: 'daemon',
      auth: new AuthVerifier({
        accountUrl: 'https://account.test',
        executorToken: 'rdt_executor',
        fetchImpl: (() => Promise.resolve(Response.json({}))) as unknown as typeof fetch,
      }),
      sessions: new SessionStore(),
      crypto: serveCrypto,
      loadConfig: () => Promise.reject(new Error('unused')),
      authorize,
      executor: { execute: () => Promise.reject(new Error('unused')) },
    });
    expect((await app.request(PROXY_ROUTES.busy)).status).toBe(404);
  });
});
