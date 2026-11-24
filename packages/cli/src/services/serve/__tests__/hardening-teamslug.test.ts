/**
 * Design 3 of PLAN-rmcp-executor-hardening: the principal authorize receives
 * carries its team slug, and authorize picks the policy's team tier from it, so a
 * policy document's `teams` rules match. Before the fix the command route passed
 * no slug and every team rule was dead.
 *
 * The real AuthVerifier, policy and Hono app run; the account server, the config
 * loader and the executor are fakes.
 */

import type { AddressInfo } from 'node:net';
import { serve } from '@hono/node-server';
import { CLI_CONTRACT_VERSION } from '@rediacc/shared/cli-contract';
import { PROXY_ROUTES } from '@rediacc/shared/cli-contract/wire';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ExecuteOptions } from '../../executor/types.js';
import { AuthVerifier } from '../auth.js';
import { serveCrypto } from '../crypto.js';
import type { ServeDeps } from '../deps.js';
import { type AuthorizeArgs, authorize } from '../policy.js';
import { createServeApp } from '../server.js';
import { SessionStore } from '../sessions.js';

function identity(bearer: string) {
  const team = bearer === 'rdt_team_a' ? 'a' : 'b';
  return {
    active: true,
    // audit:write so the executor's own self lookup passes the audit capability gate.
    scopes: ['proxy:exec', 'audit:write'],
    orgId: 'org-1',
    teamId: `team-${team}-id`,
    teamSlug: `team-${team}`,
    createdByUserId: `user-${team}`,
    userEmail: `${team}@example.com`,
    orgRole: 'member',
  };
}

const CONFIG = {
  policy: {
    version: 1,
    defaults: { commands: { allow: ['repo *'] }, allowGrandRepos: true },
    teams: { 'team-a': { commands: { allow: ['repo *'], deny: ['repo delete'] } } },
  },
} as unknown as RdcConfig;

describe('team rules reach authorize', () => {
  let server: ReturnType<typeof serve> | undefined;
  let baseUrl = '';
  let seen: AuthorizeArgs[] = [];

  function boot(): void {
    seen = [];
    const fetchImpl = vi.fn((_url: string, init?: RequestInit) => {
      const { token } = JSON.parse(String(init?.body)) as { token: string };
      return Promise.resolve(Response.json(identity(token)));
    });
    const deps: ServeDeps = {
      mode: 'daemon',
      auth: new AuthVerifier({
        accountUrl: 'https://account.test',
        executorToken: 'rdt_executor',
        fetchImpl: fetchImpl as unknown as typeof fetch,
      }),
      sessions: new SessionStore(),
      crypto: serveCrypto,
      executor: {
        execute(_call: ExecuteOptions) {
          return Promise.resolve({ success: true, exitCode: 0, durationMs: 1, stdout: 'ok' });
        },
      },
      loadConfig: () => Promise.resolve(CONFIG),
      authorize: (args) => {
        seen.push(args);
        return authorize(args);
      },
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

  function repoDelete(bearer: string): Promise<Response> {
    return fetch(`${baseUrl}${PROXY_ROUTES.command}`, {
      method: 'POST',
      headers: { authorization: `Bearer ${bearer}`, 'content-type': 'application/json' },
      body: JSON.stringify({
        contractVersion: CLI_CONTRACT_VERSION,
        pathKey: 'repo delete',
        positionals: { ref: 'shop' },
      }),
    });
  }

  it("refuses repo delete for the denying team's member", async () => {
    boot();
    const response = await repoDelete('rdt_team_a');
    const body = (await response.json()) as { error: string };
    expect(response.status).toBe(403);
    expect(body.error).toMatch(/denies|not allowed|policy/i);
    expect(seen[0]?.principal.teamSlug).toBe('team-a');
  });

  it("allows repo delete for another team's member (control)", async () => {
    boot();
    const response = await repoDelete('rdt_team_b');
    await response.text();
    expect(response.status).toBe(200);
    expect(seen[0]?.principal.teamSlug).toBe('team-b');
  });

  it('drops a slug the account server reports without a team id', async () => {
    const verifier = new AuthVerifier({
      accountUrl: 'https://account.test',
      executorToken: 'rdt_executor',
      fetchImpl: (() =>
        Promise.resolve(
          Response.json({ ...identity('rdt_team_a'), teamId: null })
        )) as unknown as typeof fetch,
    });
    const principal = await verifier.verify('rdt_team_a');
    expect(principal.teamSlug).toBeUndefined();
  });
});
