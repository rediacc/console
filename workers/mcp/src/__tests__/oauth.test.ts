import { describe, expect, it } from 'vitest';
import { createOAuth } from '../oauth/index.js';
import { ClientUrlRefused, createClientUrlGuard } from '../oauth/ssrf.js';
import { activeGrant, bearerFor, resolverFor, secretTextOf } from './helpers/grant.js';
import {
  ACCOUNT,
  authorizeQuery,
  CIMD_URL,
  CLAUDE_CALLBACK,
  call,
  env,
  Flow,
  form,
  GRANT,
  HOST,
  KEY,
  LOOPBACK,
  OTHER_GRANT,
  oauth,
  PORTAL,
  pkce,
  refresh,
  registerDcr,
  requested,
  resolved,
  resolveGrant,
  setOAuth,
  setResolveGrant,
  signIn,
  Tokens,
} from './helpers/oauth-harness.js';

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
    setResolveGrant(resolverFor([activeGrant(GRANT, { state: 'revoked' })]));
    setOAuth(
      createOAuth({
        host: HOST,
        accountUrl: ACCOUNT,
        authRequestKey: KEY,
        resolveGrant,
        resolveHost: () => Promise.resolve([]),
      })
    );
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
