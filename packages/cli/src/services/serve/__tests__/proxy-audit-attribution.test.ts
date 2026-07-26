/**
 * The audit event names the PERSON, not the worker.
 *
 * This is the property the whole proxy plane exists to protect, and the one the
 * console session-token flow is built around. A console user's command reaches
 * the executor under a short-lived proxy:exec token minted for THEM. The executor
 * ships one audit event per command, authenticated with its OWN audit-write
 * credential — but the event must be ATTRIBUTED to the user's token, via
 * onBehalfOfTokenId, or the account server (which falls back to the
 * authenticating token's owner) would log every console action against the
 * executor fleet.
 *
 * So this test boots the real serve app with the REAL audit shipper and asserts
 * the wire payload: the Authorization header is the executor's credential, but
 * onBehalfOfTokenId is the caller's token. Those being different is the point.
 *
 * A separate file from loopback.test.ts (owned elsewhere) and container-config
 * (which proves config decryption); this isolates attribution.
 */

import type { AddressInfo } from 'node:net';
import { serve } from '@hono/node-server';
import { CLI_CONTRACT_VERSION } from '@rediacc/shared/cli-contract';
import { PROXY_ROUTES } from '@rediacc/shared/cli-contract/wire';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ExecuteOptions, ExecuteResult } from '../../executor/types.js';
import { createExecutorAudit } from '../audit.js';
import { AuthVerifier } from '../auth.js';
import type { ServeDeps } from '../deps.js';
import { authorize } from '../policy.js';
import { createServeApp } from '../server.js';
import { SessionStore } from '../sessions.js';

// /v1/command dispatches the REAL Commander tree, which would otherwise read the
// developer's own config off disk. This is the only stub.
vi.mock('../../config/config-resources.js', () => ({
  configService: {
    resetResourceView: vi.fn(),
    getRepository: vi.fn((name: string) =>
      Promise.resolve({ repositoryGuid: `guid-${name}`, credential: 'set', networkId: 7 })
    ),
    ensureRepositoryNetworkId: vi.fn(() => Promise.resolve(7)),
    getLanguage: vi.fn(() => Promise.resolve('en')),
    applyDefaults: vi.fn((o: Record<string, unknown>) => Promise.resolve(o)),
    setRuntimeConfig: vi.fn(),
    getLocalConfig: vi.fn(() => Promise.resolve({ machines: {}, repositories: {} })),
    getLocalMachine: vi.fn((name: string) =>
      Promise.resolve({ ip: '10.0.0.1', user: 'root', name })
    ),
    // `demo` placed on `prod-1` so `repo status demo` derives its machine (§2.3).
    getCurrent: vi.fn(() =>
      Promise.resolve({
        state: {},
        resources: {
          repositories: {
            demo: { grand: 'base', tags: { base: {} }, placement: { machine: 'prod-1' } },
          },
        },
      })
    ),
  },
}));
process.env.REDIACC_TELEMETRY_DISABLED = '1';

const EXECUTOR_TOKEN = 'rdt_executor_fleet';
/** The console user's short-lived proxy:exec token, as workers/proxy forwards it. */
const SESSION_TOKEN = 'rdt_console_session';
/** The id /proxy/introspect returns for that token — the attribution anchor. */
const SESSION_TOKEN_ID = 'tok-console-user';

/** An owner with no policy document is allowed by MISSING_POLICY_DEFAULT. */
function allowAllConfig(): RdcConfig {
  const config: RdcConfig = {
    schemaVersion: 3,
    id: '00000000-0000-0000-0000-000000000001',
    version: 1,
    encryption: { mode: 'plaintext' },
  };
  return config;
}

interface AuditPost {
  authorization: string | undefined;
  body: {
    events: { onBehalfOfTokenId?: string; type?: string; data?: Record<string, unknown> }[];
  };
}

describe('proxy audit attribution', () => {
  let server: ReturnType<typeof serve>;
  let baseUrl: string;
  let auditPosts: AuditPost[];
  let auditFailures: unknown[];
  /** When false, introspect omits tokenId, mimicking the pre-fix executor. */
  let returnTokenId: boolean;

  function principalFor(token: string): Record<string, unknown> {
    if (token !== SESSION_TOKEN) return { active: false };
    return {
      active: true,
      scopes: ['proxy:exec'],
      orgId: 'org-1',
      teamId: null,
      createdByUserId: 'user-console',
      userEmail: 'console@example.com',
      orgRole: 'owner',
      ...(returnTokenId ? { tokenId: SESSION_TOKEN_ID } : {}),
    };
  }

  beforeEach(() => {
    auditPosts = [];
    auditFailures = [];
    returnTokenId = true;

    const json = (body: unknown): Response =>
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });

    const accountFetch = vi.fn((url: string | URL, init?: RequestInit) => {
      const href = String(url);

      if (href.includes('/proxy/introspect')) {
        const { token } = JSON.parse(init?.body as string) as { token: string };
        return json(principalFor(token));
      }

      if (href.includes('/licenses/audit-events')) {
        const headers = init?.headers as Record<string, string> | undefined;
        auditPosts.push({
          authorization: headers?.authorization,
          body: JSON.parse(init?.body as string),
        });
        return json({ accepted: 1 });
      }

      throw new Error(`unexpected account call: ${href}`);
    }) as unknown as typeof fetch;

    const deps: ServeDeps = {
      mode: 'container',
      auth: new AuthVerifier({
        accountUrl: 'https://account.test',
        executorToken: EXECUTOR_TOKEN,
        fetchImpl: accountFetch,
      }),
      sessions: new SessionStore(),
      crypto: {
        generateEphemeralKeyPair: () =>
          Promise.reject(new Error('not needed: loadConfig is a passthrough here')),
        exportPublicKey: () => Promise.reject(new Error('unused')),
      },
      executor: {
        execute(_options: ExecuteOptions): Promise<ExecuteResult> {
          return Promise.resolve({ success: true, exitCode: 0, durationMs: 3, stdout: 'ok' });
        },
      },
      // Passthrough: this test is about attribution, not config decryption.
      loadConfig: () => Promise.resolve(allowAllConfig()),
      authorize,
      audit: createExecutorAudit({
        accountUrl: 'https://account.test',
        executorToken: EXECUTOR_TOKEN,
        fetchImpl: accountFetch,
        onFailure: (error) => auditFailures.push(error),
      }),
    };

    const app = createServeApp(deps);
    server = serve({ fetch: app.fetch, port: 0 });
    baseUrl = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  });

  afterEach(() => {
    server.close();
  });

  async function runCommand(token = SESSION_TOKEN): Promise<Response> {
    return fetch(`${baseUrl}${PROXY_ROUTES.command}`, {
      method: 'POST',
      headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json' },
      body: JSON.stringify({
        contractVersion: CLI_CONTRACT_VERSION,
        pathKey: 'repo status',
        positionals: { ref: 'demo' },
      }),
    });
  }

  it('attributes the audit event to the caller token, authenticated by the executor credential', async () => {
    const response = await runCommand();
    expect(response.status).toBe(200);
    await response.text();

    expect(auditFailures).toEqual([]);
    expect(auditPosts).toHaveLength(1);
    const post = auditPosts[0];

    // Shipped with the EXECUTOR's own audit-write credential...
    expect(post.authorization).toBe(`Bearer ${EXECUTOR_TOKEN}`);
    // ...but ATTRIBUTED to the console user's token. This is the account server's
    // signal to log the command against the person, not the executor fleet.
    expect(post.body.events).toHaveLength(1);
    expect(post.body.events[0].onBehalfOfTokenId).toBe(SESSION_TOKEN_ID);
  });

  it('never puts the executor credential in the event body (attribution is not the worker)', async () => {
    await (await runCommand()).text();

    const serialized = JSON.stringify(auditPosts[0].body);
    expect(serialized).not.toContain(EXECUTOR_TOKEN);
    expect(serialized).not.toContain(SESSION_TOKEN);
  });

  it('without the introspected tokenId, attribution is LOST — the regression guard', async () => {
    // Reproduce the pre-fix executor: introspection resolves the user but returns
    // no token id. The audit event then carries no onBehalfOfTokenId, and the
    // account server would fall back to the authenticating (executor) token's
    // owner. This asserts exactly the failure the tokenId plumbing prevents.
    returnTokenId = false;

    await (await runCommand()).text();

    expect(auditPosts).toHaveLength(1);
    expect(auditPosts[0].body.events[0].onBehalfOfTokenId).toBeUndefined();
  });
});
