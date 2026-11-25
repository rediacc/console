/**
 * The OAuth authorization server of the hosted Worker (RW-A1, agent/plans/PLAN-rmcp-remote-worker.md Design 2): the full code flow for a CIMD client and a DCR client, the SSRF guard on client URLs, S256-only PKCE, refresh rotation with family revocation on reuse, per-grant audience, the portal handshake (`/authorize/request`, `/authorize/complete`) and the wiring through `src/index.ts`.
 *
 * The library runs on Node over the SQLite-backed KV of packages/shared (the RW-OP0 setup); client metadata documents are served by a stubbed global `fetch`, which records every URL it is asked for so a refusal can be shown to have made no request.
 */
import { createHash, randomBytes } from 'node:crypto';
import { DatabaseSync } from 'node:sqlite';
import { Client, StreamableHTTPClientTransport } from '@modelcontextprotocol/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SqliteKvNamespace } from '../../../../packages/shared/src/mcp-host/sqlite-kv.js';
import { createOAuth, type OAuth, type OAuthEnv } from '../oauth/index.js';
import { ClientUrlRefused, createClientUrlGuard } from '../oauth/ssrf.js';
import { activeGrant, bearerFor, resolverFor, secretTextOf } from './helpers/grant.js';

const HOST = 'mcp.test.rediacc.cloud';
const ACCOUNT = 'https://account.test';
const PORTAL = ACCOUNT;
const KEY = 'k'.repeat(40);
const GRANT = 'eu_oauth_grant';
const OTHER_GRANT = 'eu_oauth_other';
const LOOPBACK = 'http://127.0.0.1:40001/callback';
const CLAUDE_CALLBACK = 'https://claude.ai/api/mcp/auth_callback';
const CIMD_URL = 'https://client.example.com/oauth/client.json';

/** A synchronous stand-in for the execution context the Worker runtime passes. */
const ctx = {
  waitUntil() {},
  passThroughOnException() {},
  props: {},
} as unknown as ExecutionContext;

let db: DatabaseSync;
let env: OAuthEnv;
let oauth: OAuth;
let requested: string[];
let resolved: string[];
let resolveGrant: ReturnType<typeof resolverFor>;

/** Hosts the guard may resolve, each to the addresses it answers. */
const DNS: Record<string, string[]> = {
  'client.example.com': ['93.184.216.34'],
  'rebind.example.com': ['10.0.0.1'],
  'mixed.example.com': ['93.184.216.34', '169.254.169.254'],
};

function cimdDocument(overrides: Record<string, unknown> = {}): Record<string, unknown> {
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
  env = { OAUTH_KV: new SqliteKvNamespace(db) as unknown as KVNamespace };
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

function pkce(): { verifier: string; challenge: string } {
  const verifier = randomBytes(32).toString('base64url');
  return { verifier, challenge: createHash('sha256').update(verifier).digest('base64url') };
}

interface Tokens {
  access_token: string;
  refresh_token: string;
}

interface Flow {
  clientId: string;
  redirectUri: string;
  /** What the client puts in `resource`; null sends none. */
  resource?: string | null;
  grantId?: string;
  secret?: string;
  /** Who posts to `/authorize/complete`. */
  origin?: string;
}

function authorizeQuery(flow: Flow, challenge: string, method = 'S256'): string {
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
async function authorizeAndComplete(flow: Flow, challenge: string): Promise<Response> {
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
      { origin: flow.origin ?? PORTAL }
    )
  );
}

async function signIn(flow: Flow): Promise<{ tokens: Tokens; verifier: string }> {
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

async function registerDcr(): Promise<string> {
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

function refresh(clientId: string, refreshToken: string): Promise<Response> {
  return call(
    '/oauth/token',
    form({ grant_type: 'refresh_token', refresh_token: refreshToken, client_id: clientId })
  );
}

describe('metadata', () => {
  it('advertises S256 only, CIMD, public clients and the iss parameter', async () => {
    const response = await call('/.well-known/oauth-authorization-server');
    expect(response.status).toBe(200);
    const metadata = (await response.json()) as Record<string, unknown>;
    expect(metadata.issuer).toBe(`https://${HOST}`);
    expect(metadata.authorization_endpoint).toBe(`https://${HOST}/authorize`);
    expect(metadata.token_endpoint).toBe(`https://${HOST}/oauth/token`);
    expect(metadata.registration_endpoint).toBe(`https://${HOST}/register`);
    expect(metadata.code_challenge_methods_supported).toEqual(['S256']);
    expect(metadata.client_id_metadata_document_supported).toBe(true);
    expect(metadata.authorization_response_iss_parameter_supported).toBe(true);
    expect(metadata.token_endpoint_auth_methods_supported).toContain('none');
  });

  it('serves the protected-resource document of one grant', async () => {
    const response = await call(`/.well-known/oauth-protected-resource/g/${GRANT}`);
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      resource: `https://${HOST}/g/${GRANT}`,
      authorization_servers: [`https://${HOST}`],
      bearer_methods_supported: ['header'],
    });
  });

  it('leaves every other route to the transport', async () => {
    expect(await call(`/g/${GRANT}`, { method: 'POST' })).toBeNull();
  });
});

describe('the code flow', () => {
  it('signs a CIMD client in, with a loopback port other than the registered one', async () => {
    const flow: Flow = { clientId: CIMD_URL, redirectUri: LOOPBACK };
    const { tokens } = await signIn(flow);
    expect(requested).toContain(CIMD_URL);
    const verify = oauth.verifyAccessToken(env);
    const check = await verify(tokens.access_token, `https://${HOST}/g/${GRANT}`);
    expect(check).toEqual({ status: 'valid', grantId: GRANT, secret: secretTextOf(GRANT) });
    // The bearer the Worker builds from the token resolves the grant like a pasted one.
    expect(bearerFor(GRANT)).toBe(`rmcp_${GRANT}.${secretTextOf(GRANT)}`);
  });

  it('shows the portal the client name and the verified domain of a CIMD client', async () => {
    const { challenge } = pkce();
    const authorize = await call(
      `/authorize?${authorizeQuery({ clientId: CIMD_URL, redirectUri: LOOPBACK }, challenge)}`
    );
    const handle = new URL(authorize.headers.get('location')!).searchParams.get('authRequest')!;
    const described = await call(`/authorize/request?authRequest=${encodeURIComponent(handle)}`, {
      headers: { origin: PORTAL },
    });
    expect(described.status).toBe(200);
    expect(described.headers.get('access-control-allow-origin')).toBe(PORTAL);
    expect(await described.json()).toEqual({
      clientName: 'Claude Code',
      clientDomain: 'client.example.com',
      clientId: CIMD_URL,
    });
  });

  it('signs a DCR client in with the claude.ai callback and shows its redirect host', async () => {
    const clientId = await registerDcr();
    const flow: Flow = { clientId, redirectUri: CLAUDE_CALLBACK };
    const { tokens } = await signIn(flow);
    const check = await oauth.verifyAccessToken(env)(
      tokens.access_token,
      `https://${HOST}/g/${GRANT}`
    );
    expect(check.status).toBe('valid');
    const { challenge } = pkce();
    const authorize = await call(`/authorize?${authorizeQuery(flow, challenge)}`);
    const handle = new URL(authorize.headers.get('location')!).searchParams.get('authRequest')!;
    const described = await call(`/authorize/request?authRequest=${encodeURIComponent(handle)}`);
    expect(await described.json()).toEqual({
      clientName: 'Claude',
      clientDomain: 'claude.ai',
      clientId,
    });
  });

  it('refuses a redirect_uri that is not registered, exactly', async () => {
    const clientId = await registerDcr();
    const { challenge } = pkce();
    const response = await call(
      `/authorize?${authorizeQuery({ clientId, redirectUri: `${CLAUDE_CALLBACK}/extra` }, challenge)}`
    );
    expect(response.status).toBe(400);
  });

  it('refuses plain PKCE, and a request that names no method', async () => {
    const clientId = await registerDcr();
    const flow: Flow = { clientId, redirectUri: CLAUDE_CALLBACK };
    const plain = await call(`/authorize?${authorizeQuery(flow, 'a'.repeat(43), 'plain')}`);
    expect(plain.status).toBe(400);
    expect(((await plain.json()) as { error: string }).error).toBe('invalid_request');
    const query = new URLSearchParams(authorizeQuery(flow, 'a'.repeat(43)));
    query.delete('code_challenge_method');
    expect((await call(`/authorize?${query.toString()}`)).status).toBe(400);
  });

  it('answers the token endpoint well inside ten seconds', async () => {
    const clientId = await registerDcr();
    const started = performance.now();
    await signIn({ clientId, redirectUri: CLAUDE_CALLBACK });
    expect(performance.now() - started).toBeLessThan(10_000);
  });
});

describe('client URLs', () => {
  const REFUSED = [
    ['an RFC 1918 address', 'https://10.0.0.1/client.json'],
    ['the metadata address', 'https://169.254.169.254/latest/meta-data'],
    ['a loopback address', 'https://127.0.0.1/client.json'],
    ['an IPv6 loopback', 'https://[::1]/client.json'],
    ['an IPv4-mapped IPv6 address', 'https://[::ffff:10.0.0.1]/client.json'],
    ['a decimal-encoded address', 'https://2130706433/client.json'],
    ['localhost', 'https://localhost/client.json'],
    ['a single-label host', 'https://intranet/client.json'],
    ['a non-https scheme', 'http://client.example.com/oauth/client.json'],
    ['a host that resolves to 10.0.0.1', 'https://rebind.example.com/client.json'],
    ['a host with one private answer among public ones', 'https://mixed.example.com/client.json'],
    ['a host that does not resolve', 'https://nowhere.example.com/client.json'],
    ['a custom port', 'https://client.example.com:8443/client.json'],
    ['userinfo', 'https://user:pass@client.example.com/client.json'],
  ] as const;

  it.each(REFUSED)('refuses %s at /authorize without fetching it', async (_name, clientId) => {
    const { challenge } = pkce();
    const response = await call(
      `/authorize?${authorizeQuery({ clientId, redirectUri: LOOPBACK }, challenge)}`
    );
    expect(response.status).toBe(400);
    expect(((await response.json()) as { error: string }).error).toBe('invalid_client');
    expect(requested).toEqual([]);
  });

  it('refuses them at /oauth/token too', async () => {
    const response = await call(
      '/oauth/token',
      form({
        grant_type: 'authorization_code',
        code: 'x',
        redirect_uri: LOOPBACK,
        client_id: 'https://169.254.169.254/latest/meta-data',
        code_verifier: 'v'.repeat(43),
      })
    );
    expect(response.status).toBe(400);
    expect(((await response.json()) as { error: string }).error).toBe('invalid_client');
    expect(requested).toEqual([]);
  });

  it('refuses credentials in the URL and a custom port in the guard itself, before any lookup', async () => {
    const lookups: string[] = [];
    const guard = createClientUrlGuard((host) => {
      lookups.push(host);
      return Promise.resolve(['93.184.216.34']);
    });
    await expect(guard.assertPublic('https://user:pass@client.example.com/c.json')).rejects.toThrow(
      ClientUrlRefused
    );
    await expect(guard.assertPublic('https://client.example.com:8443/c.json')).rejects.toThrow(
      ClientUrlRefused
    );
    await expect(guard.assertPublic('https://client.example.com/c.json')).resolves.toBeUndefined();
    expect(lookups).toEqual(['client.example.com']);
  });

  it('asks DNS once per host inside the cache window', async () => {
    const { challenge } = pkce();
    for (let i = 0; i < 3; i += 1) {
      await call(
        `/authorize?${authorizeQuery({ clientId: CIMD_URL, redirectUri: LOOPBACK }, challenge)}`
      );
    }
    expect(resolved).toEqual(['client.example.com']);
  });
});

describe('/authorize/complete', () => {
  const flow: Flow = { clientId: '', redirectUri: CLAUDE_CALLBACK };

  async function handleFor(resource?: string | null): Promise<string> {
    const clientId = await registerDcr();
    const { challenge } = pkce();
    const authorize = await call(
      `/authorize?${authorizeQuery({ ...flow, clientId, resource }, challenge)}`
    );
    return new URL(authorize.headers.get('location')!).searchParams.get('authRequest')!;
  }

  const post = (
    handle: string,
    fields: Partial<Record<'grantId' | 'S', string>> = {},
    origin = PORTAL
  ) =>
    call(
      '/authorize/complete',
      form({ authRequest: handle, grantId: GRANT, S: secretTextOf(GRANT), ...fields }, { origin })
    );

  it('refuses a wrong secret and leaves the handle usable', async () => {
    const handle = await handleFor();
    const wrong = await post(handle, { S: secretTextOf(GRANT).replace(/^./, 'Z') });
    expect(wrong.status).toBe(400);
    expect((await post(handle)).status).toBe(303);
  });

  it('refuses a handle that was used, tampered with or never issued', async () => {
    const handle = await handleFor();
    expect((await post(handle)).status).toBe(303);
    expect((await post(handle)).status).toBe(400);
    const fresh = await handleFor();
    const [id, sig] = fresh.split('.');
    // The first character of a base64url MAC carries six bits, so changing it always changes the bytes (the last carries four).
    const flipped = `${sig[0] === 'A' ? 'B' : 'A'}${sig.slice(1)}`;
    expect((await post(`${id}.${flipped}`)).status).toBe(400);
    expect((await post(`${'x'.repeat(22)}.${sig}`)).status).toBe(400);
  });

  it('refuses a post from any origin but the portal', async () => {
    const handle = await handleFor();
    expect((await post(handle, {}, 'https://evil.example')).status).toBe(403);
    expect((await post(handle)).status).toBe(303);
  });

  it('refuses a grant other than the one the client named in resource', async () => {
    const handle = await handleFor(`https://${HOST}/g/${OTHER_GRANT}`);
    const response = await post(handle);
    expect(response.status).toBe(400);
    expect(((await response.json()) as { error: string }).error).toBe('invalid_target');
  });

  it('refuses a grant that does not serve', async () => {
    resolveGrant = resolverFor([activeGrant(GRANT, { state: 'revoked' })]);
    oauth = createOAuth({
      host: HOST,
      accountUrl: ACCOUNT,
      authRequestKey: KEY,
      resolveGrant,
      resolveHost: () => Promise.resolve([]),
    });
    const handle = await handleFor();
    expect((await post(handle)).status).toBe(400);
  });

  it('answers the portal only from the portal origin', async () => {
    const handle = await handleFor();
    const url = `/authorize/request?authRequest=${encodeURIComponent(handle)}`;
    const foreign = await call(url, { headers: { origin: 'https://evil.example' } });
    expect(foreign.headers.get('access-control-allow-origin')).toBeNull();
    const preflight = await call('/authorize/request', {
      method: 'OPTIONS',
      headers: { origin: PORTAL },
    });
    expect(preflight.status).toBe(204);
    expect(preflight.headers.get('access-control-allow-origin')).toBe(PORTAL);
    expect(
      (await call('/authorize/request?authRequest=nope', { headers: { origin: PORTAL } })).status
    ).toBe(404);
  });

  it('never puts the secret in a URL it answers', async () => {
    const handle = await handleFor();
    const done = await post(handle);
    expect(done.headers.get('location')).not.toContain(secretTextOf(GRANT));
    expect(handle).not.toContain(secretTextOf(GRANT));
  });
});

describe('audience', () => {
  it('refuses a token minted for one grant at another grant', async () => {
    const clientId = await registerDcr();
    const { tokens } = await signIn({ clientId, redirectUri: CLAUDE_CALLBACK });
    const verify = oauth.verifyAccessToken(env);
    expect((await verify(tokens.access_token, `https://${HOST}/g/${GRANT}`)).status).toBe('valid');
    expect((await verify(tokens.access_token, `https://${HOST}/g/${OTHER_GRANT}`)).status).toBe(
      'invalid'
    );
    expect((await verify(tokens.access_token, `https://other.example/g/${GRANT}`)).status).toBe(
      'invalid'
    );
    expect((await verify(tokens.access_token, `https://${HOST}/`)).status).toBe('invalid');
    expect((await verify('not-a-token', `https://${HOST}/g/${GRANT}`)).status).toBe('invalid');
  });

  it('keeps two grants of one client apart', async () => {
    const clientId = await registerDcr();
    const first = await signIn({ clientId, redirectUri: CLAUDE_CALLBACK });
    const second = await signIn({
      clientId,
      redirectUri: CLAUDE_CALLBACK,
      resource: `https://${HOST}/g/${OTHER_GRANT}`,
      grantId: OTHER_GRANT,
      secret: secretTextOf(OTHER_GRANT),
    });
    const verify = oauth.verifyAccessToken(env);
    // The second sign-in must not revoke the first.
    expect((await verify(first.tokens.access_token, `https://${HOST}/g/${GRANT}`)).status).toBe(
      'valid'
    );
    expect(
      (await verify(second.tokens.access_token, `https://${HOST}/g/${OTHER_GRANT}`)).status
    ).toBe('valid');
    expect((await verify(second.tokens.access_token, `https://${HOST}/g/${GRANT}`)).status).toBe(
      'invalid'
    );
  });
});

describe('refresh tokens', () => {
  it('rotates on every refresh', async () => {
    const clientId = await registerDcr();
    const { tokens } = await signIn({ clientId, redirectUri: CLAUDE_CALLBACK });
    const response = await refresh(clientId, tokens.refresh_token);
    expect(response.status).toBe(200);
    const next = (await response.json()) as Tokens;
    expect(next.refresh_token).not.toBe(tokens.refresh_token);
    const check = await oauth.verifyAccessToken(env)(
      next.access_token,
      `https://${HOST}/g/${GRANT}`
    );
    expect(check.status).toBe('valid');
  });

  it('revokes the whole family when a refresh token is used twice', async () => {
    const clientId = await registerDcr();
    const { tokens } = await signIn({ clientId, redirectUri: CLAUDE_CALLBACK });
    const next = (await (await refresh(clientId, tokens.refresh_token)).json()) as Tokens;
    const replay = await refresh(clientId, tokens.refresh_token);
    expect(replay.status).toBe(400);
    expect(((await replay.json()) as { error: string }).error).toBe('invalid_grant');
    // The successor and its access token die with the family.
    expect((await refresh(clientId, next.refresh_token)).status).toBe(400);
    const verify = oauth.verifyAccessToken(env);
    expect((await verify(next.access_token, `https://${HOST}/g/${GRANT}`)).status).toBe('invalid');
    expect((await verify(tokens.access_token, `https://${HOST}/g/${GRANT}`)).status).toBe(
      'invalid'
    );
  });
});

describe('src/index.ts wiring', () => {
  it('serves OAuth routes and accepts the token it minted on the MCP route', async () => {
    vi.resetModules();
    const { default: worker } = await import('../index.js');
    const tag = await (
      await import('../../../../packages/shared/src/config-crypto/agent-grant.js')
    ).deriveAuthTag(new Uint8Array(32).map((_, i) => (i * 37 + 11) % 256));
    const workerEnv = {
      REGION: 'eu',
      ENVIRONMENT: 'test',
      MCP_HOST: HOST,
      ACCOUNT_URL: ACCOUNT,
      OAUTH_KV: env.OAUTH_KV,
      AUTH_REQUEST_KEY: KEY,
      GRANTS: {
        resolveGrant: (grantId: string, authTag: string) =>
          Promise.resolve(
            grantId === GRANT && authTag === tag
              ? {
                  grantId: GRANT,
                  state: 'active' as const,
                  orgId: 'org-test',
                  placement: 0,
                  tier: 'standard',
                  userId: 'user-1',
                  teamId: null,
                  configId: 'cfg-1',
                  region: 'eu',
                  scope: { readOnly: false },
                  expiresAt: '2099-01-01T00:00:00.000Z',
                }
              : null
          ),
      },
    };
    const viaWorker = (path: string, init?: RequestInit) =>
      worker.fetch(
        new Request(`https://${HOST}${path}`, { redirect: 'manual', ...init }),
        workerEnv as never,
        ctx
      );
    const registered = await viaWorker('/register', {
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
    const clientId = ((await registered.json()) as { client_id: string }).client_id;
    const { verifier, challenge } = pkce();
    const flow: Flow = { clientId, redirectUri: CLAUDE_CALLBACK };
    const authorize = await viaWorker(`/authorize?${authorizeQuery(flow, challenge)}`);
    const handle = new URL(authorize.headers.get('location')!).searchParams.get('authRequest')!;
    const done = await viaWorker(
      '/authorize/complete',
      form({ authRequest: handle, grantId: GRANT, S: secretTextOf(GRANT) }, { origin: PORTAL })
    );
    const code = new URL(done.headers.get('location')!).searchParams.get('code')!;
    const token = await viaWorker(
      '/oauth/token',
      form({
        grant_type: 'authorization_code',
        code,
        redirect_uri: CLAUDE_CALLBACK,
        client_id: clientId,
        code_verifier: verifier,
        resource: `https://${HOST}/g/${GRANT}`,
      })
    );
    const { access_token: accessToken } = (await token.json()) as Tokens;

    const client = new Client(
      { name: 'rw-a1', version: '0.0.0' },
      { versionNegotiation: { mode: 'legacy' } }
    );
    const withToken = (input: string | URL | Request, init?: RequestInit) => {
      const request = new Request(input, init);
      request.headers.set('authorization', `Bearer ${accessToken}`);
      return worker.fetch(request, workerEnv as never, ctx);
    };
    await client.connect(
      new StreamableHTTPClientTransport(new URL(`https://${HOST}/g/${GRANT}`), { fetch: withToken })
    );
    expect((await client.listTools()).tools.length).toBeGreaterThan(0);

    // The same token at another grant's URL is the 401 challenge, not a listing.
    const other = await worker.fetch(
      new Request(`https://${HOST}/g/${OTHER_GRANT}`, {
        method: 'POST',
        headers: { authorization: `Bearer ${accessToken}`, 'content-type': 'application/json' },
        body: '{}',
      }),
      workerEnv as never,
      ctx
    );
    expect(other.status).toBe(401);
    expect(other.headers.get('www-authenticate')).toContain(
      `resource_metadata="https://${HOST}/.well-known/oauth-protected-resource/g/${OTHER_GRANT}"`
    );
    await client.close();
  });

  it('serves no OAuth route without OAUTH_KV and AUTH_REQUEST_KEY', async () => {
    vi.resetModules();
    const { default: worker } = await import('../index.js');
    const response = await worker.fetch(
      new Request(`https://${HOST}/oauth/token`, { method: 'POST' }),
      { REGION: 'eu', ENVIRONMENT: 'test', MCP_HOST: HOST, ACCOUNT_URL: ACCOUNT } as never,
      ctx
    );
    expect(response.status).toBe(404);
  });
});
