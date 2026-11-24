/**
 * D5: the executor refuses a client whose contract version differs from its own.
 *
 * The version is a hash of the whole command list, so a client built against a
 * different list would send paths or options this executor does not know. The
 * 409 carries both versions, so the caller can tell which side is stale. The
 * comparison runs before policy and before any command, so the refused request
 * never reaches the executor.
 */

import type { AddressInfo } from 'node:net';
import { serve } from '@hono/node-server';
import { CLI_CONTRACT_VERSION } from '@rediacc/shared/cli-contract';
import { CONTRACT_VERSION_HEADER, PROXY_ROUTES } from '@rediacc/shared/cli-contract/wire';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../../utils/agent-guard.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../utils/agent-guard.js')>()),
  isAgentEnvironment: () => false,
}));

import type { ExecuteOptions, ExecuteResult } from '../../executor/types.js';
import { AuthVerifier } from '../auth.js';
import { serveCrypto } from '../crypto.js';
import type { ServeDeps } from '../deps.js';
import { authorize } from '../policy.js';
import { createServeApp } from '../server.js';
import { SessionStore } from '../sessions.js';

await vi.hoisted(async () => {
  const { mkdtempSync } = await import('node:fs');
  const os = await import('node:os');
  const scratch = mkdtempSync(`${os.tmpdir()}/rdc-contract-mismatch-`);
  process.env.XDG_CONFIG_HOME = scratch;
  process.env.XDG_STATE_HOME = scratch;
  process.env.XDG_CACHE_HOME = scratch;
  process.env.REDIACC_TELEMETRY_DISABLED = '1';
});

const OWNER_TOKEN = 'rdt_owner';
const EXECUTOR_TOKEN = 'rdt_executor';
const STALE_VERSION = 'stale-contract-version';

const IDENTITY = {
  active: true,
  scopes: ['proxy:exec', 'audit:write'],
  orgId: 'org-1',
  teamId: null,
  createdByUserId: 'user-owner',
  userEmail: 'owner@example.com',
  orgRole: 'owner',
};

const CONFIG: RdcConfig = {
  schemaVersion: 3,
  id: '00000000-0000-4000-8000-0000000000cc',
  version: 1,
  credentials: { ssh: { privateKey: 'KEY' } },
  resources: { machines: { m1: { ip: '10.1.1.1', user: 'root', port: 22 } }, repositories: {} },
  encryption: { mode: 'plaintext' },
};

describe('contract version mismatch', () => {
  let server: ReturnType<typeof serve> | undefined;
  let baseUrl: string;
  let executed: ExecuteOptions[];

  function boot(): void {
    executed = [];
    const accountFetch = vi.fn((_url: string | URL, init?: RequestInit) => {
      const { token } = JSON.parse(String(init?.body ?? '{}')) as { token: string };
      return Promise.resolve(
        Response.json(
          token === OWNER_TOKEN || token === EXECUTOR_TOKEN ? IDENTITY : { active: false }
        )
      );
    }) as unknown as typeof fetch;
    const deps: ServeDeps = {
      mode: 'container',
      auth: new AuthVerifier({
        accountUrl: 'https://account.test',
        executorToken: EXECUTOR_TOKEN,
        fetchImpl: accountFetch,
      }),
      sessions: new SessionStore(),
      crypto: serveCrypto,
      executor: {
        execute(call: ExecuteOptions): Promise<ExecuteResult> {
          executed.push(call);
          return Promise.resolve({ success: true, exitCode: 0, durationMs: 1, stdout: 'ok' });
        },
      },
      loadConfig: () => Promise.resolve(CONFIG),
      authorize,
      audit: () => Promise.resolve(),
      detach: () => false,
    };
    server = serve({ fetch: createServeApp(deps).fetch, port: 0 });
    baseUrl = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  }

  afterEach(async () => {
    const running = server;
    server = undefined;
    if (running) await new Promise<void>((resolve) => running.close(() => resolve()));
  });

  function post(version: { body?: string; header?: string }): Promise<Response> {
    return fetch(`${baseUrl}${PROXY_ROUTES.command}`, {
      method: 'POST',
      headers: {
        authorization: `Bearer ${OWNER_TOKEN}`,
        'content-type': 'application/json',
        ...(version.header ? { [CONTRACT_VERSION_HEADER]: version.header } : {}),
      },
      body: JSON.stringify({
        ...(version.body ? { contractVersion: version.body } : {}),
        pathKey: 'repo list',
        params: { machine: 'm1' },
        positionals: {},
      }),
    });
  }

  it('answers 409 with both versions when the body version differs', async () => {
    boot();
    const response = await post({ body: STALE_VERSION });

    expect(response.status).toBe(409);
    const body = (await response.json()) as Record<string, unknown>;
    expect(body.error).toBe('contract_version_mismatch');
    expect(body.clientContractVersion).toBe(STALE_VERSION);
    expect(body.executorContractVersion).toBe(CLI_CONTRACT_VERSION);
    expect(executed).toHaveLength(0);
  });

  it('prefers the header over the body version', async () => {
    boot();
    const response = await post({ header: STALE_VERSION, body: CLI_CONTRACT_VERSION });

    expect(response.status).toBe(409);
    const body = (await response.json()) as Record<string, unknown>;
    expect(body.clientContractVersion).toBe(STALE_VERSION);
  });

  it('does not answer 409 when the version equals the executor contract', async () => {
    boot();
    const response = await post({ body: CLI_CONTRACT_VERSION });

    // The request reaches the command stream: a 200 whose body is the result line (review ad69d23b.1).
    const text = await response.text();
    expect(response.status, text).toBe(200);
    expect(text).toContain('"kind":"result"');
  });
});
