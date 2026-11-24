/**
 * The run recorder inside the real serve app (agent/plans/PLAN-console-run-index.md D4): a client that
 * disconnects mid-dispatch still produces the end event, an unreachable account route leaves the
 * command's result unchanged, and the sealed tail opens with the session CEK.
 */

import { exportAesKey } from '@rediacc/shared/config-crypto';
import { openRunTail } from '@rediacc/shared/config-crypto/run-tail';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../../utils/agent-guard.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../utils/agent-guard.js')>()),
  isAgentEnvironment: () => false,
}));

await vi.hoisted(async () => {
  const { mkdtempSync } = await import('node:fs');
  const os = await import('node:os');
  const scratch = mkdtempSync(`${os.tmpdir()}/rdc-run-index-`);
  process.env.XDG_CONFIG_HOME = scratch;
  process.env.XDG_STATE_HOME = scratch;
  process.env.XDG_CACHE_HOME = scratch;
  process.env.REDIACC_TELEMETRY_DISABLED = '1';
});

import { CLI_CONTRACT_VERSION } from '@rediacc/shared/cli-contract';
import { PROXY_ROUTES } from '@rediacc/shared/cli-contract/wire';
import type { ExecuteResult, Executor } from '../../executor/types.js';
import { createRunIndex } from '../run-index.js';
import {
  bootContainerExecutor,
  type ContainerExecutor,
  createFakeConfigStore,
  OPEN_POLICY,
  OWNER_TOKEN,
} from './writeback-harness.js';

const RUN_ID = 'run-gone.1';

function storedConfig(): RdcConfig {
  return {
    schemaVersion: 3,
    id: '00000000-0000-4000-8000-0000000000d1',
    version: 1,
    credentials: { ssh: { privateKey: 'KEY' } },
    resources: { machines: { m1: { ip: '10.1.1.1', user: 'root', port: 22 } }, repositories: {} },
    state: {},
    encryption: { mode: 'plaintext' },
  } as unknown as RdcConfig;
}

interface Posted {
  runId: string;
  seq: number;
  state: string;
  tail?: string;
}

describe('the run recorder inside the serve app', () => {
  let executor: ContainerExecutor | undefined;

  afterEach(async () => {
    await executor?.close();
    executor = undefined;
  });

  async function boot(
    execute: Executor['execute'],
    deliver: () => Promise<Response> = () => Promise.resolve(Response.json({ ok: true }))
  ) {
    const store = await createFakeConfigStore(storedConfig(), OPEN_POLICY);
    const posted: Posted[] = [];
    const runIndex = createRunIndex({
      accountUrl: 'https://account.test',
      executorToken: 'rdt_executor',
      fetchImpl: ((_url: string | URL, init?: RequestInit) => {
        posted.push(JSON.parse(init?.body as string) as Posted);
        return deliver();
      }) as typeof fetch,
    });
    executor = await bootContainerExecutor(store, { execute }, { runIndex });
    await executor.grantKey();
    return { posted, store };
  }

  const request = (signal?: AbortSignal) =>
    fetch(`${executor?.baseUrl}${PROXY_ROUTES.command}`, {
      method: 'POST',
      headers: { authorization: `Bearer ${OWNER_TOKEN}`, 'content-type': 'application/json' },
      body: JSON.stringify({
        contractVersion: CLI_CONTRACT_VERSION,
        pathKey: 'repo list',
        params: { machine: 'm1' },
        positionals: {},
        requestId: RUN_ID,
      }),
      ...(signal ? { signal } : {}),
    });

  it('a client that disconnects mid-dispatch still produces the end event', async () => {
    let release: (result: ExecuteResult) => void = () => undefined;
    let started: () => void = () => undefined;
    const dispatching = new Promise<void>((resolve) => {
      started = resolve;
    });
    const { posted } = await boot(
      () =>
        new Promise<ExecuteResult>((resolve) => {
          release = resolve;
          started();
        })
    );

    const controller = new AbortController();
    const pending = request(controller.signal).catch(() => undefined);
    await dispatching;
    controller.abort();
    await pending;
    // The client is gone and the dispatch still runs: only the start was posted.
    expect(posted.map((event) => event.state)).toEqual(['running']);

    release({ success: true, exitCode: 0, durationMs: 5, stdout: 'done' });
    await vi.waitFor(() =>
      expect(posted.map((event) => event.state)).toEqual(['running', 'succeeded'])
    );
    expect(posted.map((event) => event.seq)).toEqual([0, 1]);
    expect(posted.every((event) => event.runId === RUN_ID)).toBe(true);
  });

  it('control: a command that fails posts a failed end, not a success', async () => {
    const { posted } = await boot(() =>
      Promise.resolve({ success: false, exitCode: 3, durationMs: 1, stdout: '', stderr: 'bad' })
    );
    await (await request()).text();
    await vi.waitFor(() => expect(posted.at(-1)?.state).toBe('failed'));
  });

  it('an unreachable account route leaves the command result unchanged', async () => {
    const answer = () =>
      Promise.resolve({ success: true, exitCode: 0, durationMs: 1, stdout: 'fine' });
    const resultOf = async () => {
      const body = await (await request()).text();
      const line = body
        .split('\n')
        .filter(Boolean)
        .map((text) => JSON.parse(text) as { kind: string; result?: object; stdout?: string })
        .find((entry) => entry.kind === 'result');
      return { success: line?.result, stdout: line?.stdout };
    };

    await boot(answer);
    const reachable = await resultOf();
    await executor?.close();

    const { posted } = await boot(answer, () => Promise.reject(new Error('ECONNREFUSED')));
    const unreachable = await resultOf();

    expect(posted.length).toBeGreaterThan(0);
    expect(JSON.stringify(unreachable)).toBe(JSON.stringify(reachable));
  });

  it('seals the tail so it opens with the CEK and not without it', async () => {
    const { posted, store } = await boot(() =>
      Promise.resolve({ success: true, exitCode: 0, durationMs: 1, stdout: 'visible only sealed' })
    );
    await (await request()).text();
    await vi.waitFor(() => expect(posted.at(-1)?.state).toBe('succeeded'));

    const tail = posted.at(-1)?.tail;
    expect(tail).toBeDefined();
    expect(tail).not.toContain('visible');
    const cek = await exportAesKey(store.cek);
    expect(await openRunTail(cek, 'org-1', RUN_ID, tail as string)).toContain(
      'visible only sealed'
    );
    await expect(
      openRunTail(new Uint8Array(32), 'org-1', RUN_ID, tail as string)
    ).rejects.toThrow();
  });
});
