/** The shared fixture of the OAuth tests (oauth.test.ts, oauth-wiring.test.ts): constants, the SQLite-backed KV, the stubbed client-document fetch, the per-test reset, and the flow helpers. */
import { createHash, randomBytes } from 'node:crypto';
import { DatabaseSync } from 'node:sqlite';
import { afterEach, beforeEach, expect, vi } from 'vitest';
import type { HostExecutionContext, HostKvNamespace } from '../../host-types.js';
import { createOAuth, type OAuth, type OAuthEnv } from '../../oauth/index.js';
import { SqliteKvNamespace } from '../../sqlite-kv.js';
import { activeGrant, resolverFor, secretTextOf } from './grant.js';

export const HOST = 'mcp.test.rediacc.cloud';
export const ACCOUNT = 'https://account.test';
export const KEY = 'k'.repeat(40);
export const GRANT = 'eu_oauth_grant';
export const OTHER_GRANT = 'eu_oauth_other';
export const LOOPBACK = 'http://127.0.0.1:40001/callback';
export const CLAUDE_CALLBACK = 'https://claude.ai/api/mcp/auth_callback';
export const CIMD_URL = 'https://client.example.com/oauth/client.json';

/** A synchronous stand-in for the execution context the Worker runtime passes. */
export const ctx = {
  waitUntil() {},
  passThroughOnException() {},
  props: {},
} as unknown as HostExecutionContext;

export let db: DatabaseSync;
export let env: OAuthEnv;
export let oauth: OAuth;
export let requested: string[];
export let resolved: string[];
export let resolveGrant: ReturnType<typeof resolverFor>;

/** Hosts the guard may resolve, each to the addresses it answers. */
export const DNS: Record<string, string[]> = {
  'client.example.com': ['93.184.216.34'],
  'rebind.example.com': ['10.0.0.1'],
  'mixed.example.com': ['93.184.216.34', '169.254.169.254'],
};

export function cimdDocument(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    client_id: CIMD_URL,
    client_name: 'Claude Code',
    redirect_uris: ['http://127.0.0.1:33418/callback'],
    token_endpoint_auth_method: 'none',
    grant_types: ['authorization_code', 'refresh_token'],
    response_types: ['code'],
    ...overrides,
  };
}

beforeEach(() => {
  db = new DatabaseSync(':memory:');
  env = { OAUTH_KV: new SqliteKvNamespace(db) as unknown as HostKvNamespace };
  requested = [];
  resolved = [];
  resolveGrant = resolverFor([
    activeGrant(GRANT, { userId: 'user-1' }),
    activeGrant(OTHER_GRANT, { userId: 'user-1' }),
  ]);
  oauth = createOAuth({
    host: HOST,
    accountUrl: ACCOUNT,
    authRequestKey: KEY,
    resolveGrant,
    resolveHost: (host) => {
      resolved.push(host);
      return Promise.resolve(DNS[host] ?? []);
    },
  });
  vi.stubGlobal('Cloudflare', { compatibilityFlags: { global_fetch_strictly_public: true } });
  vi.stubGlobal(
    'fetch',
    vi.fn((input: string | URL | Request) => {
      const url = String(input instanceof Request ? input.url : input);
      requested.push(url);
      return Promise.resolve(
        url === CIMD_URL
          ? Response.json(cimdDocument(), { headers: { 'cache-control': 'no-store' } })
          : new Response('not found', { status: 404 })
      );
    })
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  db.close();
});

export function call(path: string, init?: RequestInit): Promise<Response> {
  return oauth.fetch(
    new Request(`https://${HOST}${path}`, { redirect: 'manual', ...init }),
    env,
    ctx
  ) as Promise<Response>;
}

export function form(
  fields: Record<string, string>,
  headers: Record<string, string> = {}
): RequestInit {
  return {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded', ...headers },
    body: new URLSearchParams(fields).toString(),
  };
}

export function pkce(): { verifier: string; challenge: string } {
  const verifier = randomBytes(32).toString('base64url');
  return { verifier, challenge: createHash('sha256').update(verifier).digest('base64url') };
}

export interface Tokens {
  access_token: string;
  refresh_token: string;
}

export interface Flow {
  clientId: string;
  redirectUri: string;
  /** What the client puts in `resource`; null sends none. */
  resource?: string | null;
  grantId?: string;
  secret?: string;
  /** Who posts to `/authorize/complete`. */
  origin?: string;
}

export function authorizeQuery(flow: Flow, challenge: string, method = 'S256'): string {
  const query = new URLSearchParams({
    response_type: 'code',
    client_id: flow.clientId,
    redirect_uri: flow.redirectUri,
    scope: 'mcp',
    state: 'st-1',
    code_challenge: challenge,
    code_challenge_method: method,
  });
  if (flow.resource !== null) query.set('resource', flow.resource ?? `https://${HOST}/g/${GRANT}`);
  return query.toString();
}

/** `/authorize` then the portal's two calls; returns the redirect back to the client. */
export async function authorizeAndComplete(flow: Flow, challenge: string): Promise<Response> {
  const authorize = await call(`/authorize?${authorizeQuery(flow, challenge)}`);
  expect(authorize.status).toBe(302);
  const page = new URL(authorize.headers.get('location')!);
  expect(`${page.origin}${page.pathname}`).toBe(`${ACCOUNT}/account/mcp/authorize`);
  const handle = page.searchParams.get('authRequest')!;
  return call(
    '/authorize/complete',
    form(
      {
        authRequest: handle,
        grantId: flow.grantId ?? GRANT,
        S: flow.secret ?? secretTextOf(GRANT),
      },
      { origin: flow.origin ?? ACCOUNT }
    )
  );
}

export async function signIn(flow: Flow): Promise<{ tokens: Tokens; verifier: string }> {
  const { verifier, challenge } = pkce();
  const done = await authorizeAndComplete(flow, challenge);
  expect(done.status).toBe(303);
  const back = new URL(done.headers.get('location')!);
  expect(`${back.origin}${back.pathname}`).toBe(
    new URL(flow.redirectUri).origin + new URL(flow.redirectUri).pathname
  );
  expect(back.searchParams.get('state')).toBe('st-1');
  expect(back.searchParams.get('iss')).toBe(`https://${HOST}`);
  const code = back.searchParams.get('code')!;
  const token = await call(
    '/oauth/token',
    form({
      grant_type: 'authorization_code',
      code,
      redirect_uri: flow.redirectUri,
      client_id: flow.clientId,
      code_verifier: verifier,
      ...(flow.resource === null
        ? {}
        : { resource: flow.resource ?? `https://${HOST}/g/${GRANT}` }),
    })
  );
  expect(token.status).toBe(200);
  return { tokens: (await token.json()) as Tokens, verifier };
}

export async function registerDcr(): Promise<string> {
  const response = await call('/register', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      client_name: 'Claude',
      redirect_uris: [CLAUDE_CALLBACK],
      token_endpoint_auth_method: 'none',
      grant_types: ['authorization_code', 'refresh_token'],
      response_types: ['code'],
    }),
  });
  expect(response.status).toBe(201);
  return ((await response.json()) as { client_id: string }).client_id;
}

export function refresh(clientId: string, refreshToken: string): Promise<Response> {
  return call(
    '/oauth/token',
    form({ grant_type: 'refresh_token', refresh_token: refreshToken, client_id: clientId })
  );
}

/** Replace the grant resolver for the rest of one test; the next test's reset puts the fixture's back. */
export function setResolveGrant(next: ReturnType<typeof resolverFor>): void {
  resolveGrant = next;
}

/** Replace the OAuth server for the rest of one test, as above. */
export function setOAuth(next: OAuth): void {
  oauth = next;
}
