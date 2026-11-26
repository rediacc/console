import './helpers/workers-shim.js';
import { Client, StreamableHTTPClientTransport } from '@modelcontextprotocol/client';
import { describe, expect, it, vi } from 'vitest';
import { secretTextOf } from './helpers/grant.js';
import {
  ACCOUNT,
  authorizeQuery,
  CLAUDE_CALLBACK,
  ctx,
  env,
  Flow,
  form,
  GRANT,
  HOST,
  KEY,
  OTHER_GRANT,
  PORTAL,
  pkce,
  Tokens,
} from './helpers/oauth-harness.js';

describe('src/index.ts wiring', () => {
  it('serves OAuth routes and accepts the token it minted on the MCP route', async () => {
    vi.resetModules();
    const { default: worker } = await import('../handler.js');
    const tag = await (await import('../../config-crypto/agent-grant.js')).deriveAuthTag(
      new Uint8Array(32).map((_, i) => (i * 37 + 11) % 256)
    );
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
    const { default: worker } = await import('../handler.js');
    const response = await worker.fetch(
      new Request(`https://${HOST}/oauth/token`, { method: 'POST' }),
      { REGION: 'eu', ENVIRONMENT: 'test', MCP_HOST: HOST, ACCOUNT_URL: ACCOUNT } as never,
      ctx
    );
    expect(response.status).toBe(404);
  });
});
