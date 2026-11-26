/**
 * One MCP Worker per region (RW-REG, agent/plans/PLAN-rmcp-remote-worker.md Design 12, D58): the region is in the URL and in the RFC 9728 and RFC 8414 documents, no OAuth state binds a grant of another region, a grant presented to the wrong region is answered `REDIACC_WRONG_REGION` with the right region's URL and no upstream call, and each region's wrangler file binds only its own account and proxy Workers.
 */
import { readdirSync, readFileSync } from 'node:fs';
import { DatabaseSync } from 'node:sqlite';
import { fileURLToPath } from 'node:url';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  WK_ACCOUNT_DEFAULT_ORIGIN,
  WK_MCP_EU_HOST,
} from '../../../../packages/shared/src/config/well-known.generated.js';
import { SqliteKvNamespace } from '../../../../packages/shared/src/mcp-host/sqlite-kv.js';
import { createOAuth, type OAuth, type OAuthEnv } from '../oauth/index.js';
import { grantRegionOf, hostOfRegion } from '../oauth/region.js';
import { bearerFor, secretTextOf } from './helpers/grant.js';

const ctx = {
  waitUntil() {},
  passThroughOnException() {},
  props: {},
} as unknown as ExecutionContext;

beforeEach(() => {
  // index.ts keeps its resolver, transport and OAuth server per isolate, so each test loads a fresh module.
  vi.resetModules();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

interface Spied {
  grantLookups: string[];
  executorCalls: number;
  worker: { fetch(request: Request, env: never, ctx: ExecutionContext): Promise<Response> };
  env: Record<string, unknown>;
}

async function workerOf(region: string, host: string, environment = 'edge'): Promise<Spied> {
  const { default: worker } = await import('../index.js');
  const spied: Spied = {
    grantLookups: [],
    executorCalls: 0,
    worker: worker as Spied['worker'],
    env: {},
  };
  spied.env = {
    REGION: region,
    ENVIRONMENT: environment,
    MCP_HOST: host,
    ACCOUNT_URL: `https://${region}.rediacc.cloud`,
    GRANTS: {
      resolveGrant: (grantId: string) => {
        spied.grantLookups.push(grantId);
        return Promise.resolve(null);
      },
    },
    EXECUTOR: {
      call: () => {
        spied.executorCalls += 1;
        return Promise.reject(new Error('the executor must not be called'));
      },
    },
  };
  return spied;
}

function mcpPost(host: string, grantId: string): Request {
  return new Request(`https://${host}/g/${grantId}`, {
    method: 'POST',
    headers: {
      authorization: `Bearer ${bearerFor(grantId)}`,
      'content-type': 'application/json',
    },
    body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/list' }),
  });
}

describe('a grant presented to the wrong region', () => {
  it('is refused with the right region URL, before any lookup or upstream call', async () => {
    const us = await workerOf('us', 'mcp.us.rediacc.cloud');
    const answer = await us.worker.fetch(
      mcpPost('mcp.us.rediacc.cloud', 'eu_grant_1') as never,
      us.env as never,
      ctx
    );
    expect(answer.status).toBe(421);
    expect(await answer.json()).toEqual({
      code: 'REDIACC_WRONG_REGION',
      message: `This grant lives in the eu region. Use https://${WK_MCP_EU_HOST}/g/eu_grant_1.`,
      region: 'eu',
      mcpUrl: `https://${WK_MCP_EU_HOST}/g/eu_grant_1`,
    });
    expect(us.grantLookups).toEqual([]);
    expect(us.executorCalls).toBe(0);
  });

  it('names the matching bench region from a bench host', async () => {
    const bench = await workerOf('asia', 'mcp.bench-asia.rediacc.cloud', 'bench');
    const answer = await bench.worker.fetch(
      mcpPost('mcp.bench-asia.rediacc.cloud', 'eu_grant_1') as never,
      bench.env as never,
      ctx
    );
    expect(answer.status).toBe(421);
    expect(((await answer.json()) as { mcpUrl: string }).mcpUrl).toBe(
      'https://mcp.bench-eu.rediacc.cloud/g/eu_grant_1'
    );
  });

  it('answers a bare 401 for an id with no region prefix, and hands a grant of its own region to the lookup', async () => {
    const eu = await workerOf('eu', WK_MCP_EU_HOST);
    const bare = await eu.worker.fetch(
      mcpPost(WK_MCP_EU_HOST, 'plain_grant') as never,
      eu.env as never,
      ctx
    );
    expect(bare.status).toBe(401);
    expect(await bare.text()).toBe('Unauthorized');
    const own = await eu.worker.fetch(
      mcpPost(WK_MCP_EU_HOST, 'eu_grant_1') as never,
      eu.env as never,
      ctx
    );
    expect(own.status).toBe(401);
    expect(own.headers.get('content-type')).toBe('text/plain');
    // Both reached the lookup, which answered nothing: the unprefixed id is an unknown grant, not a wrong region.
    expect(eu.grantLookups).toEqual(['plain_grant', 'eu_grant_1']);
  });

  it('reads the region from the id only at its first underscore', () => {
    expect(grantRegionOf('us_abc')).toBe('us');
    expect(grantRegionOf('asia_a_b')).toBe('asia');
    expect(grantRegionOf('mars_abc')).toBeNull();
    expect(grantRegionOf('eu_')).toBeNull();
    expect(grantRegionOf('_eu')).toBeNull();
    expect(hostOfRegion(WK_MCP_EU_HOST, 'eu', 'us')).toBe('mcp.us.rediacc.cloud');
    expect(hostOfRegion('localhost', 'eu', 'us')).toBeNull();
  });
});

describe('the region in the OAuth documents', () => {
  let db: DatabaseSync;
  let env: OAuthEnv;
  let oauth: OAuth;
  const HOST = WK_MCP_EU_HOST;

  beforeEach(() => {
    db = new DatabaseSync(':memory:');
    env = { OAUTH_KV: new SqliteKvNamespace(db) as unknown as KVNamespace };
    oauth = createOAuth({
      host: HOST,
      region: 'eu',
      accountUrl: WK_ACCOUNT_DEFAULT_ORIGIN,
      authRequestKey: 'k'.repeat(40),
      resolveGrant: () => Promise.resolve(null),
      resolveHost: () => Promise.resolve(['93.184.216.34']),
    });
    vi.stubGlobal('Cloudflare', { compatibilityFlags: { global_fetch_strictly_public: true } });
  });

  afterEach(() => db.close());

  const call = (path: string, init?: RequestInit) =>
    oauth.fetch(
      new Request(`https://${HOST}${path}`, { redirect: 'manual', ...init }),
      env,
      ctx
    ) as Promise<Response>;

  it('names the region host in the protected-resource and authorization-server documents', async () => {
    const resource = await call('/.well-known/oauth-protected-resource/g/eu_grant_1');
    expect(await resource.json()).toMatchObject({
      resource: `https://${WK_MCP_EU_HOST}/g/eu_grant_1`,
      authorization_servers: [`https://${WK_MCP_EU_HOST}`],
    });
    const server = (await (await call('/.well-known/oauth-authorization-server')).json()) as {
      issuer: string;
      token_endpoint: string;
    };
    expect(server.issuer).toBe(`https://${WK_MCP_EU_HOST}`);
    expect(server.token_endpoint).toBe(`https://${WK_MCP_EU_HOST}/oauth/token`);
  });

  it('serves no document for a grant of another region', async () => {
    const answer = await call('/.well-known/oauth-protected-resource/g/us_grant_1');
    expect(answer.status).toBe(404);
  });

  it('binds no grant of another region: not as a resource, not at the portal post', async () => {
    const registered = await call('/register', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        client_name: 'Claude',
        redirect_uris: ['https://claude.ai/api/mcp/auth_callback'],
        token_endpoint_auth_method: 'none',
        grant_types: ['authorization_code'],
        response_types: ['code'],
      }),
    });
    const clientId = ((await registered.json()) as { client_id: string }).client_id;
    const authorize = await call(
      `/authorize?${new URLSearchParams({
        response_type: 'code',
        client_id: clientId,
        redirect_uri: 'https://claude.ai/api/mcp/auth_callback',
        scope: 'mcp',
        code_challenge: 'x'.repeat(43),
        code_challenge_method: 'S256',
        resource: `https://${WK_MCP_EU_HOST}/g/us_grant_1`,
      })}`
    );
    expect(authorize.status).toBe(400);
    expect(((await authorize.json()) as { error: string }).error).toBe('invalid_target');

    const posted = await call('/authorize/complete', {
      method: 'POST',
      headers: {
        'content-type': 'application/x-www-form-urlencoded',
        origin: WK_ACCOUNT_DEFAULT_ORIGIN,
      },
      body: new URLSearchParams({
        authRequest: 'none',
        grantId: 'us_grant_1',
        S: secretTextOf('us_grant_1'),
      }).toString(),
    });
    expect(posted.status).toBe(400);
    expect(((await posted.json()) as { error_description: string }).error_description).toBe(
      'The grant is not valid.'
    );
    const verified = await oauth.verifyAccessToken(env)(
      'any-token',
      `https://${WK_MCP_EU_HOST}/g/us_grant_1`
    );
    expect(verified.status).toBe('invalid');
  });
});

describe('the wrangler files bind only their own region', () => {
  const root = fileURLToPath(new URL('../../../', import.meta.url).href);
  const suffixOf = (file: string) => /^wrangler\.(.+)\.toml$/.exec(file)?.[1] ?? null;

  const read = (worker: string, file: string) => readFileSync(`${root}${worker}/${file}`, 'utf8');
  const firstName = (text: string) => /^name = "([^"]+)"/m.exec(text)?.[1];

  /** The Worker names a wrangler file binds through `[[services]]`. */
  function boundServices(text: string): string[] {
    return [...text.matchAll(/^service = "([^"]+)"/gm)].map((m) => m[1]);
  }

  const files = readdirSync(`${root}mcp`).filter((f) => {
    const suffix = suffixOf(f);
    return suffix !== null && suffix !== 'template';
  });

  it('covers every production and bench region', () => {
    expect(files.map(suffixOf).sort()).toEqual([
      'asia',
      'bench-asia',
      'bench-eu',
      'bench-us',
      'eu',
      'us',
    ]);
  });

  it.each(files)(
    '%s names its own region and binds only its own account and proxy Workers',
    (file) => {
      const suffix = suffixOf(file) as string;
      const text = read('mcp', file);
      const own = [firstName(read('account', file)), firstName(read('proxy', file))] as string[];
      expect(own.every((name) => typeof name === 'string')).toBe(true);
      for (const service of boundServices(text)) expect(own).toContain(service);
      const region = suffix.replace(/^bench-/, '');
      expect(/^REGION = "([^"]+)"/m.exec(text)?.[1]).toBe(region);
      expect(/^MCP_HOST = "mcp\.([^.]+)\./m.exec(text)?.[1]).toBe(suffix);
    }
  );

  it('detects a binding to another region (control)', () => {
    const own = ['account-eu', 'proxy-eu'];
    const crossing = '[[services]]\nbinding = "GRANTS"\nservice = "account-us"\n';
    expect(boundServices(crossing)).toEqual(['account-us']);
    expect(boundServices(crossing).every((service) => own.includes(service))).toBe(false);
  });
});
