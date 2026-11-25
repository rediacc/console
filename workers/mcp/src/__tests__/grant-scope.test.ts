/**
 * Lifetime and scope of a grant (RW-SCOPE, agent/plans/PLAN-rmcp-remote-worker.md D54, D55, Design 4): OAuth tokens never outlive the grant, a refresh past the grant's expiry is refused, the default grant of 7 days expires on a fake clock, and a tool argument naming another config is refused with `REDIACC_GRANT_SCOPE` before anything is forwarded.
 *
 * The OAuth library runs over the SQLite-backed KV as in oauth.test.ts; only `Date` is faked, so the library's token and grant lifetimes, the resolver's expiry and the test's clock agree.
 */
import { createHash, randomBytes } from 'node:crypto';
import { DatabaseSync } from 'node:sqlite';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { deriveAuthTag } from '../../../../packages/shared/src/config-crypto/agent-grant.js';
import { SqliteKvNamespace } from '../../../../packages/shared/src/mcp-host/sqlite-kv.js';
import { callTool, type GrantCaller } from '../call.js';
import type { McpCallForward } from '../executor.js';
import { createOAuth, type OAuth, type OAuthEnv } from '../oauth/index.js';
import type { GrantContext } from '../scope.js';
import { activeGrant, SECRET_BYTES, secretTextOf } from './helpers/grant.js';

const HOST = 'mcp.test.rediacc.cloud';
const ACCOUNT = 'https://account.test';
const GRANT = 'eu_scope_grant';
const CALLBACK = 'https://claude.ai/api/mcp/auth_callback';
const DEFAULT_GRANT_TTL_MS = 7 * 24 * 60 * 60 * 1000;
const START = Date.parse('2026-12-01T00:00:00.000Z');

const ctx = {
  waitUntil() {},
  passThroughOnException() {},
  props: {},
} as unknown as ExecutionContext;

interface Tokens {
  access_token: string;
  refresh_token: string;
  expires_in: number;
}

let db: DatabaseSync;
let env: OAuthEnv;
let oauth: OAuth;
/** What the account answers for the grant now: mutable, the way a revocation or an expiry is. */
let account: { grant: GrantContext | null; fail: boolean };

function setClock(ms: number): void {
  vi.setSystemTime(ms);
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  setClock(START);
  db = new DatabaseSync(':memory:');
  env = { OAUTH_KV: new SqliteKvNamespace(db) as unknown as KVNamespace };
  account = {
    grant: activeGrant(GRANT, {
      userId: 'user-1',
      configId: 'cfg-1',
      expiresAt: new Date(START + DEFAULT_GRANT_TTL_MS).toISOString(),
    }),
    fail: false,
  };
  const tag = deriveAuthTag(SECRET_BYTES);
  oauth = createOAuth({
    host: HOST,
    accountUrl: ACCOUNT,
    authRequestKey: 'k'.repeat(40),
    resolveGrant: async (grantId, authTag) => {
      if (account.fail) throw new Error('account unreachable');
      return grantId === GRANT && authTag === (await tag) ? account.grant : null;
    },
    resolveHost: () => Promise.resolve(['93.184.216.34']),
  });
  vi.stubGlobal('Cloudflare', { compatibilityFlags: { global_fetch_strictly_public: true } });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  db.close();
});

function call(path: string, init?: RequestInit): Promise<Response> {
  return oauth.fetch(
    new Request(`https://${HOST}${path}`, { redirect: 'manual', ...init }),
    env,
    ctx
  ) as Promise<Response>;
}

function form(fields: Record<string, string>, headers: Record<string, string> = {}): RequestInit {
  return {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded', ...headers },
    body: new URLSearchParams(fields).toString(),
  };
}

async function registerClient(): Promise<string> {
  const response = await call('/register', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      client_name: 'Claude',
      redirect_uris: [CALLBACK],
      token_endpoint_auth_method: 'none',
      grant_types: ['authorization_code', 'refresh_token'],
      response_types: ['code'],
    }),
  });
  return ((await response.json()) as { client_id: string }).client_id;
}

/** The code flow up to the token response; returns the status and the body. */
async function signIn(clientId: string): Promise<{ status: number; body: Tokens }> {
  const verifier = randomBytes(32).toString('base64url');
  const challenge = createHash('sha256').update(verifier).digest('base64url');
  const resource = `https://${HOST}/g/${GRANT}`;
  const authorize = await call(
    `/authorize?${new URLSearchParams({
      response_type: 'code',
      client_id: clientId,
      redirect_uri: CALLBACK,
      scope: 'mcp',
      state: 's',
      code_challenge: challenge,
      code_challenge_method: 'S256',
      resource,
    })}`
  );
  const handle = new URL(authorize.headers.get('location') ?? '').searchParams.get('authRequest');
  const done = await call(
    '/authorize/complete',
    form({ authRequest: handle ?? '', grantId: GRANT, S: secretTextOf(GRANT) }, { origin: ACCOUNT })
  );
  const code = new URL(done.headers.get('location') ?? '').searchParams.get('code') ?? '';
  const token = await call(
    '/oauth/token',
    form({
      grant_type: 'authorization_code',
      code,
      redirect_uri: CALLBACK,
      client_id: clientId,
      code_verifier: verifier,
      resource,
    })
  );
  return { status: token.status, body: (await token.json()) as Tokens };
}

async function refresh(
  clientId: string,
  refreshToken: string
): Promise<{ status: number; body: Tokens & { error?: string } }> {
  const response = await call(
    '/oauth/token',
    form({ grant_type: 'refresh_token', refresh_token: refreshToken, client_id: clientId })
  );
  return { status: response.status, body: (await response.json()) as Tokens & { error?: string } };
}

const verify = (token: string) => oauth.verifyAccessToken(env)(token, `https://${HOST}/g/${GRANT}`);

describe('token lifetime follows the grant (D54)', () => {
  it('expires the default 7-day grant: tokens work inside it, a refresh at its end is refused', async () => {
    const clientId = await registerClient();
    const first = await signIn(clientId);
    expect(first.status).toBe(200);
    expect(first.body.expires_in).toBe(3600);

    // Six days in, a refresh still works and the new access token lasts its full hour.
    setClock(START + 6 * 24 * 3600 * 1000);
    const midway = await refresh(clientId, first.body.refresh_token);
    expect(midway.status).toBe(200);
    expect(midway.body.expires_in).toBe(3600);
    expect((await verify(midway.body.access_token)).status).toBe('valid');

    // Seven days after the grant began: the account says it expired, so the refresh is refused.
    setClock(START + DEFAULT_GRANT_TTL_MS);
    account.grant = { ...(account.grant as GrantContext), state: 'expired' };
    const late = await refresh(clientId, midway.body.refresh_token);
    expect(late.status).toBe(400);
    expect(late.body.error).toBe('invalid_grant');
    expect((await verify(midway.body.access_token)).status).toBe('invalid');
  });

  it('caps an access token at the time the grant has left', async () => {
    const clientId = await registerClient();
    account.grant = {
      ...(account.grant as GrantContext),
      expiresAt: new Date(START + 20 * 60 * 1000).toISOString(),
    };
    const signed = await signIn(clientId);
    expect(signed.status).toBe(200);
    expect(signed.body.expires_in).toBe(20 * 60);

    setClock(START + 15 * 60 * 1000);
    const next = await refresh(clientId, signed.body.refresh_token);
    expect(next.status).toBe(200);
    expect(next.body.expires_in).toBe(5 * 60);
  });

  it('gives the refresh token the lifetime of the grant, whatever the account answers later', async () => {
    const clientId = await registerClient();
    const signed = await signIn(clientId);
    // A later answer that no longer limits the grant must not stretch the refresh token.
    account.grant = {
      ...(account.grant as GrantContext),
      expiresAt: '2099-01-01T00:00:00.000Z',
    };
    setClock(START + DEFAULT_GRANT_TTL_MS + 1000);
    const late = await refresh(clientId, signed.body.refresh_token);
    expect(late.status).toBe(400);
    expect(late.body.error).toBe('invalid_grant');
  });

  it('refuses the code exchange of a grant that expired between consent and exchange', async () => {
    const clientId = await registerClient();
    const verifier = randomBytes(32).toString('base64url');
    const challenge = createHash('sha256').update(verifier).digest('base64url');
    const authorize = await call(
      `/authorize?${new URLSearchParams({
        response_type: 'code',
        client_id: clientId,
        redirect_uri: CALLBACK,
        scope: 'mcp',
        code_challenge: challenge,
        code_challenge_method: 'S256',
      })}`
    );
    const handle = new URL(authorize.headers.get('location') ?? '').searchParams.get('authRequest');
    const done = await call(
      '/authorize/complete',
      form(
        { authRequest: handle ?? '', grantId: GRANT, S: secretTextOf(GRANT) },
        { origin: ACCOUNT }
      )
    );
    const code = new URL(done.headers.get('location') ?? '').searchParams.get('code') ?? '';
    account.grant = { ...(account.grant as GrantContext), state: 'revoked' };
    const token = await call(
      '/oauth/token',
      form({
        grant_type: 'authorization_code',
        code,
        redirect_uri: CALLBACK,
        client_id: clientId,
        code_verifier: verifier,
      })
    );
    expect(token.status).toBe(400);
    expect(((await token.json()) as { error: string }).error).toBe('invalid_grant');
  });

  it('answers a failed lookup 503 and leaves the OAuth grant alive for the retry', async () => {
    const clientId = await registerClient();
    const signed = await signIn(clientId);
    account.fail = true;
    const down = await call(
      '/oauth/token',
      form({
        grant_type: 'refresh_token',
        refresh_token: signed.body.refresh_token,
        client_id: clientId,
      })
    );
    expect(down.status).toBe(503);
    expect(((await down.json()) as { error: string }).error).toBe('temporarily_unavailable');
    account.fail = false;
    expect((await refresh(clientId, signed.body.refresh_token)).status).toBe(200);
  });
});

describe('one config per grant (D55)', () => {
  const caller = (configId: string | undefined): GrantCaller => ({
    grant: activeGrant('eu_cfg_grant', { configId }),
    secret: secretTextOf('eu_cfg_grant'),
  });

  function setup() {
    const forwards: McpCallForward[] = [];
    const deps = {
      reauthUrl: (id: string) => `${ACCOUNT}/account/mcp/authorize?grant=${id}`,
      executor: {
        call: (_routing: unknown, forward: McpCallForward) => {
          forwards.push(forward);
          return Promise.resolve({
            ok: true as const,
            answer: { result: { content: [{ type: 'text', text: 'ran' }], isError: false } },
          });
        },
      },
    };
    return { forwards, deps };
  }

  it('refuses an argument naming another config and forwards nothing', async () => {
    const { forwards, deps } = setup();
    for (const key of ['config', 'config_id', 'configId']) {
      const result = await callTool(deps, caller('cfg-1'), 'repo_list', { [key]: 'cfg-2' });
      expect(result.isError).toBe(true);
      expect(result.structuredContent).toMatchObject({
        code: 'REDIACC_GRANT_SCOPE',
        argument: key,
      });
    }
    expect(forwards).toEqual([]);
  });

  it('refuses a config argument of a grant that names no config, and a non-string one', async () => {
    const { forwards, deps } = setup();
    const unnamed = await callTool(deps, caller(undefined), 'repo_list', { config: 'cfg-1' });
    expect(unnamed.structuredContent).toMatchObject({ code: 'REDIACC_GRANT_SCOPE' });
    const object = await callTool(deps, caller('cfg-1'), 'repo_list', { config: { id: 'cfg-1' } });
    expect(object.structuredContent).toMatchObject({ code: 'REDIACC_GRANT_SCOPE' });
    expect(forwards).toEqual([]);
  });

  it('forwards a call that names the grant config or none', async () => {
    const { forwards, deps } = setup();
    const named = await callTool(deps, caller('cfg-1'), 'repo_list', { config: 'cfg-1' });
    const plain = await callTool(deps, caller('cfg-1'), 'repo_list', {});
    expect(named.isError).toBeFalsy();
    expect(plain.isError).toBeFalsy();
    expect(forwards).toHaveLength(2);
  });
});
