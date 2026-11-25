/**
 * Expiry, revocation and the credential paths (agent/plans/PLAN-rmcp-remote-worker.md RW-T4, Design 3 and 5): an unknown grant and a wrong tag are indistinguishable bare 401s; a grant that stopped serving still lists tools and answers each call with its code and a re-authorization link carrying only the grant id; an OAuth token that expired gets the 401 an OAuth client acts on; a credential in the query string is refused; `x-api-key` is the bearer header's twin.
 */
import { Client, StreamableHTTPClientTransport } from '@modelcontextprotocol/client';
import { describe, expect, it } from 'vitest';
import type { AccessTokenCheck } from '../credential.js';
import type { ExecutorBinding, McpCallForward } from '../executor.js';
import type { GrantContext, GrantState } from '../scope.js';
import { createMcpTransport, type McpTransport } from '../transport.js';
import { activeGrant, bearerFor, resolverFor, secretTextOf } from './helpers/grant.js';

const HOST = 'mcp.eu.rediacc.cloud';
const ACCOUNT = 'https://eu.rediacc.cloud';
const LIVE = 'eu_live';
const METADATA = (grantId: string) =>
  `https://${HOST}/.well-known/oauth-protected-resource/g/${grantId}`;
const OAUTH_VALID = 'oauth-access-valid';
const OAUTH_EXPIRED = 'oauth-access-expired';
const OAUTH_OTHER_GRANT = 'oauth-access-other-grant';

const ENDED: [GrantState, string][] = [
  ['expired', 'REDIACC_GRANT_EXPIRED'],
  ['revoked', 'REDIACC_GRANT_REVOKED'],
  ['key_rotated', 'REDIACC_KEY_ROTATED'],
];

function endedGrant(state: GrantState): GrantContext {
  return activeGrant(`eu_${state}`, {
    state,
    expiresAt: '2026-11-20T00:00:00.000Z',
    ...(state === 'expired' ? {} : { endedAt: '2026-11-19T12:00:00.000Z' }),
  });
}

/** The OAuth layer's answers: one valid token for LIVE, one expired, one minted for another grant. */
function verifyAccessToken(token: string, resource: string): Promise<AccessTokenCheck> {
  if (token === OAUTH_EXPIRED) return Promise.resolve({ status: 'expired' });
  if (token === OAUTH_OTHER_GRANT) {
    return Promise.resolve({
      status: 'valid',
      grantId: 'eu_other',
      secret: secretTextOf('eu_other'),
    });
  }
  if (token === OAUTH_VALID && resource === `https://${HOST}/g/${LIVE}`) {
    return Promise.resolve({ status: 'valid', grantId: LIVE, secret: secretTextOf(LIVE) });
  }
  return Promise.resolve({ status: 'invalid' });
}

function setup() {
  const calls: McpCallForward[] = [];
  const executor: ExecutorBinding = {
    call: (_routing, forward) => {
      calls.push(forward);
      return Promise.resolve({
        ok: true,
        answer: {
          result: { content: [{ type: 'text', text: '{"success":true}' }], isError: false },
        },
      });
    },
  };
  const resolveGrant = resolverFor([
    activeGrant(LIVE),
    ...ENDED.map(([state]) => endedGrant(state)),
  ]);
  const worker = createMcpTransport({
    host: HOST,
    serverVersion: '0.0.0-test',
    accountUrl: ACCOUNT,
    resolveGrant,
    verifyAccessToken,
    executor,
  });
  return { worker, calls, resolveGrant };
}

/** A tools/list request with `headers`, built raw so every credential header is under the test's control. */
function rawList(grantId: string, headers: Record<string, string>, query = ''): Request {
  return new Request(`https://${HOST}/g/${grantId}${query}`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      accept: 'application/json, text/event-stream',
      ...headers,
    },
    body: '{"jsonrpc":"2.0","id":1,"method":"tools/list"}',
  });
}

async function connect(worker: McpTransport, grantId: string, headers: Record<string, string>) {
  const fetchViaWorker = (input: string | URL | Request, init?: RequestInit) => {
    const request = new Request(input, init);
    for (const [name, value] of Object.entries(headers)) request.headers.set(name, value);
    return worker.fetch(request);
  };
  const client = new Client(
    { name: 'rw-t4', version: '0.0.0' },
    { versionNegotiation: { mode: { pin: '2026-07-28' } } }
  );
  await client.connect(
    new StreamableHTTPClientTransport(new URL(`https://${HOST}/g/${grantId}`), {
      fetch: fetchViaWorker,
    })
  );
  return client;
}

async function snapshot(response: Response) {
  return {
    status: response.status,
    body: await response.text(),
    challenge: response.headers.get('www-authenticate'),
  };
}

describe('refusals that must not tell an unknown grant from a wrong tag', () => {
  it('an unknown grant and a wrong tag give the same bare 401', async () => {
    const { worker, resolveGrant } = setup();
    const otherSecret = new Uint8Array(32).fill(1);
    const unknown = await snapshot(
      await worker.fetch(rawList('eu_nope', { authorization: `Bearer ${bearerFor('eu_nope')}` }))
    );
    const wrongTag = await snapshot(
      await worker.fetch(rawList(LIVE, { authorization: `Bearer ${bearerFor(LIVE, otherSecret)}` }))
    );
    const otherPath = await snapshot(
      await worker.fetch(rawList('eu_nope', { authorization: `Bearer ${bearerFor(LIVE)}` }))
    );
    expect(unknown).toEqual({ status: 401, body: 'Unauthorized', challenge: null });
    expect(wrongTag).toEqual(unknown);
    // A bearer for one grant presented on another grant's URL is refused the same way, before any lookup.
    expect(otherPath).toEqual(unknown);
    expect(resolveGrant.lookups).toEqual(['eu_nope', LIVE]);

    // Control: the right secret on the right URL lists tools.
    const ok = await worker.fetch(rawList(LIVE, { authorization: `Bearer ${bearerFor(LIVE)}` }));
    expect(ok.status).toBe(200);
  });

  it('a request with no credential gets the 401 that points an OAuth client at the metadata', async () => {
    const { worker } = setup();
    const res = await worker.fetch(rawList(LIVE, {}));
    expect(res.status).toBe(401);
    expect(res.headers.get('www-authenticate')).toBe(
      `Bearer resource_metadata="${METADATA(LIVE)}"`
    );
  });
});

describe('a grant that stopped serving', () => {
  for (const [state, code] of ENDED) {
    it(`a grant in state ${state} still lists tools and answers tools/call with ${code} and a reauthUrl carrying only the grant id`, async () => {
      const { worker, calls } = setup();
      const grant = endedGrant(state);
      const client = await connect(worker, grant.grantId, {
        authorization: `Bearer ${bearerFor(grant.grantId)}`,
      });
      const { tools } = await client.listTools();
      const result = await client.callTool({ name: 'repo_list', arguments: {} });
      await client.close();

      expect(tools.length).toBeGreaterThan(0);
      expect(result.isError).toBe(true);
      const structured = result.structuredContent as Record<string, unknown>;
      expect(structured.code).toBe(code);
      expect(structured.expiredAt).toBe(grant.endedAt ?? grant.expiresAt);
      const reauth = new URL(String(structured.reauthUrl));
      expect(reauth.origin).toBe(ACCOUNT);
      expect([...reauth.searchParams.keys()]).toEqual(['grant']);
      expect(reauth.searchParams.get('grant')).toBe(grant.grantId);
      expect(String(structured.reauthUrl)).not.toContain(secretTextOf(grant.grantId));
      // The text line hands the model the link to give the user.
      expect(JSON.stringify(result.content)).toContain(String(structured.reauthUrl));
      expect(calls).toHaveLength(0);
    });
  }

  it('control: the live grant forwards the same call', async () => {
    const { worker, calls } = setup();
    const client = await connect(worker, LIVE, { authorization: `Bearer ${bearerFor(LIVE)}` });
    const result = await client.callTool({ name: 'repo_list', arguments: {} });
    await client.close();
    expect(result.isError).toBe(false);
    expect(calls).toHaveLength(1);
  });
});

describe('OAuth access tokens', () => {
  it('an expired access token gets 401 with resource_metadata, so the client refreshes', async () => {
    const { worker } = setup();
    const res = await worker.fetch(rawList(LIVE, { authorization: `Bearer ${OAUTH_EXPIRED}` }));
    expect(res.status).toBe(401);
    expect(res.headers.get('www-authenticate')).toBe(
      `Bearer resource_metadata="${METADATA(LIVE)}", error="invalid_token"`
    );
  });

  it('a token minted for another grant is refused the same way; a valid one lists tools and forwards its S', async () => {
    const { worker, calls } = setup();
    const other = await worker.fetch(
      rawList(LIVE, { authorization: `Bearer ${OAUTH_OTHER_GRANT}` })
    );
    expect(other.status).toBe(401);
    expect(other.headers.get('www-authenticate')).toContain('error="invalid_token"');

    const client = await connect(worker, LIVE, { authorization: `Bearer ${OAUTH_VALID}` });
    await client.callTool({ name: 'repo_list', arguments: {} });
    await client.close();
    expect(calls.map((c) => c.secret)).toEqual([secretTextOf(LIVE)]);
  });
});

describe('where the bearer may travel', () => {
  it('a bearer in a query string gets 400, even beside a valid header', async () => {
    const { worker, resolveGrant } = setup();
    const header = { authorization: `Bearer ${bearerFor(LIVE)}` };
    for (const query of [
      `?token=${bearerFor(LIVE)}`,
      `?access_token=${OAUTH_VALID}`,
      `?x=${encodeURIComponent(bearerFor(LIVE))}`,
    ]) {
      const res = await worker.fetch(rawList(LIVE, header, query));
      expect(res.status, query).toBe(400);
    }
    expect(resolveGrant.lookups).toEqual([]);
    // Control: an unrelated query parameter does not trip the refusal.
    expect((await worker.fetch(rawList(LIVE, header, '?client=cursor'))).status).toBe(200);
  });

  it('x-api-key works like the Authorization header', async () => {
    const { worker, calls } = setup();
    const client = await connect(worker, LIVE, { 'x-api-key': bearerFor(LIVE) });
    const { tools } = await client.listTools();
    const result = await client.callTool({ name: 'repo_list', arguments: {} });
    await client.close();
    expect(tools.length).toBeGreaterThan(0);
    expect(result.isError).toBe(false);
    expect(calls.map((c) => [c.grantId, c.secret])).toEqual([[LIVE, secretTextOf(LIVE)]]);

    const wrong = await worker.fetch(
      rawList(LIVE, { 'x-api-key': bearerFor(LIVE, new Uint8Array(32).fill(2)) })
    );
    expect(await snapshot(wrong)).toEqual({ status: 401, body: 'Unauthorized', challenge: null });
  });
});
