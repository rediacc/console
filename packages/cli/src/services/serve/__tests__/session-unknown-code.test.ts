/**
 * R2: an exec naming a session the store no longer holds (a redeploy wiped it)
 * answers 404 with the code EXECUTOR_SESSION_UNKNOWN, and nothing is dispatched.
 * The real SessionStore and Hono app run; only the executor and the account
 * server are fakes.
 */

import type { AddressInfo } from 'node:net';
import { serve } from '@hono/node-server';
import { CLI_CONTRACT_VERSION } from '@rediacc/shared/cli-contract';
import { PROXY_ROUTES } from '@rediacc/shared/cli-contract/wire';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ExecuteOptions } from '../../executor/types.js';
import { AuthVerifier } from '../auth.js';
import { serveCrypto } from '../crypto.js';
import type { ServeDeps } from '../deps.js';
import { authorize } from '../policy.js';
import { createServeApp } from '../server.js';
import { SessionError, SessionStore } from '../sessions.js';

const OWNER = {
  active: true,
  scopes: ['proxy:exec'],
  orgId: 'org-1',
  teamId: null,
  createdByUserId: 'user-owner',
  userEmail: 'owner@example.com',
  orgRole: 'owner',
};

describe('EXECUTOR_SESSION_UNKNOWN', () => {
  let server: ReturnType<typeof serve> | undefined;
  let baseUrl = '';
  let executed: ExecuteOptions[] = [];
  let loadConfig = vi.fn();

  function boot(): void {
    executed = [];
    loadConfig = vi.fn(() => Promise.reject(new SessionError('config fetch failed')));
    const deps: ServeDeps = {
      mode: 'container',
      auth: new AuthVerifier({
        accountUrl: 'https://account.test',
        executorToken: 'rdt_executor',
        fetchImpl: (() => Promise.resolve(Response.json(OWNER))) as unknown as typeof fetch,
      }),
      sessions: new SessionStore(),
      crypto: serveCrypto,
      executor: {
        execute(call: ExecuteOptions) {
          executed.push(call);
          return Promise.resolve({ success: true, exitCode: 0, durationMs: 1, stdout: 'ok' });
        },
      },
      loadConfig,
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

  function exec(headers: Record<string, string>): Promise<Response> {
    return fetch(`${baseUrl}${PROXY_ROUTES.command}`, {
      method: 'POST',
      headers: {
        authorization: 'Bearer rdt_owner',
        'content-type': 'application/json',
        ...headers,
      },
      body: JSON.stringify({
        contractVersion: CLI_CONTRACT_VERSION,
        pathKey: 'repo status',
        positionals: { ref: 'shop' },
      }),
    });
  }

  it('carries the code in the 404 body for a wiped session and dispatches nothing', async () => {
    boot();
    const response = await exec({ 'x-config-session': 'wiped-session-id' });
    const body = (await response.json()) as { error: string; code?: string };

    expect(response.status).toBe(404);
    expect(body.code).toBe('EXECUTOR_SESSION_UNKNOWN');
    expect(body.error).toMatch(/Unknown or expired session/);
    expect(loadConfig).not.toHaveBeenCalled();
    expect(executed).toHaveLength(0);
  });

  it('leaves a config-fetch SessionError uncoded', async () => {
    boot();
    const response = await exec({});
    const body = (await response.json()) as { error: string; code?: string };

    expect(response.status).toBe(404);
    expect(body.error).toBe('config fetch failed');
    expect(body.code).toBeUndefined();
    expect(executed).toHaveLength(0);
  });
});
