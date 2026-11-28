/**
 * RW-OP0 spike (PLAN-rmcp-remote-worker.md D53, Design 11): does
 * `@cloudflare/workers-oauth-provider` run unmodified on both hosts, and does a
 * public client get refresh-token rotation with reuse detection?
 *
 * Each host serves the same Worker entry (fixtures/oauth-worker.ts):
 * - cloudflare: the entry bundled by esbuild and run in workerd through Miniflare,
 *   with a real KV binding as OAUTH_KV;
 * - node: the entry imported in-process, `cloudflare:workers` resolved by
 *   installCloudflareWorkersShim(), and OAUTH_KV a SqliteKvNamespace over
 *   `node:sqlite`.
 *
 * Every flow runs on both. The "library alone" cases pin down what the published
 * library does on reuse; the "with the reuse guard" cases are the behaviour the
 * plan requires.
 */
import { createHash, randomBytes } from 'node:crypto';
import { DatabaseSync } from 'node:sqlite';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';
import { convertV4MiniflareOptions, Miniflare } from 'miniflare';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { createNodeExecutionContext, installCloudflareWorkersShim } from '../node-workers-shim.js';
import { REFRESH_USED_PREFIX } from '../refresh-reuse-guard.js';
import { SqliteKvNamespace } from '../sqlite-kv.js';

// Matches SPIKE_ORIGIN in the fixture; the fixture is imported only after the shim is installed.
const ORIGIN = 'https://mcp.spike.test';
const REDIRECT_URI = 'http://127.0.0.1:33418/callback';
const WORKER_ENTRY = fileURLToPath(new URL('./fixtures/oauth-worker.ts', import.meta.url));

interface Host {
  fetch(path: string, init?: RequestInit): Promise<Response>;
  /** Every key in the host's OAUTH_KV, to show where the library stored its state. */
  kvKeys(): Promise<string[]>;
  close(): Promise<void>;
}

type HostFactory = (reuseGuard: boolean) => Promise<Host>;

let bundledWorker: string | undefined;

async function workerBundle(): Promise<string> {
  if (bundledWorker === undefined) {
    const result = await build({
      entryPoints: [WORKER_ENTRY],
      bundle: true,
      format: 'esm',
      platform: 'neutral',
      target: 'es2022',
      conditions: ['workerd', 'worker', 'import'],
      mainFields: ['module', 'main'],
      external: ['cloudflare:workers'],
      write: false,
      logLevel: 'silent',
    });
    bundledWorker = result.outputFiles[0]!.text;
  }
  return bundledWorker;
}

const cloudflareHost: HostFactory = async (reuseGuard) => {
  const mf = new Miniflare(
    convertV4MiniflareOptions({
      modules: [
        {
          type: 'ESModule',
          path: 'worker.mjs',
          contents: await workerBundle(),
        },
      ],
      compatibilityDate: '2026-11-01',
      kvNamespaces: ['OAUTH_KV'],
      bindings: { REUSE_GUARD: reuseGuard ? '1' : '0' },
    })
  );
  await mf.ready;
  return {
    async fetch(path, init) {
      const response = await mf.dispatchFetch(`${ORIGIN}${path}`, {
        ...(init as Record<string, unknown>),
        redirect: 'manual',
      });
      // Miniflare answers with undici's Response; re-wrap it in Node's global one.
      return new Response(await response.arrayBuffer(), {
        status: response.status,
        headers: Object.fromEntries(response.headers.entries()),
      });
    },
    async kvKeys() {
      const kv = (await mf.getKVNamespace('OAUTH_KV')) as unknown as {
        list(options: {
          cursor?: string;
        }): Promise<
          { keys: { name: string }[] } & (
            | { list_complete: true }
            | { list_complete: false; cursor: string }
          )
        >;
      };
      const keys: string[] = [];
      let cursor: string | undefined;
      for (;;) {
        const page = await kv.list(cursor === undefined ? {} : { cursor });
        keys.push(...page.keys.map((key) => key.name));
        if (page.list_complete) return keys;
        cursor = page.cursor;
      }
    },
    close: () => mf.dispose(),
  };
};

const nodeHost: HostFactory = async (reuseGuard) => {
  installCloudflareWorkersShim();
  const worker = (await import('./fixtures/oauth-worker.js')).default;
  const db = new DatabaseSync(':memory:');
  const kv = new SqliteKvNamespace(db);
  const env = { OAUTH_KV: kv, REUSE_GUARD: reuseGuard ? '1' : '0' };
  return {
    async fetch(path, init) {
      const ctx = createNodeExecutionContext();
      const response = await worker.fetch(new Request(`${ORIGIN}${path}`, init), env, ctx);
      await ctx.drain();
      return response;
    },
    async kvKeys() {
      const page = await kv.list();
      return page.keys.map((key) => key.name);
    },
    close: () => {
      db.close();
      return Promise.resolve();
    },
  };
};

const HOSTS: [string, HostFactory][] = [
  ['cloudflare (Miniflare)', cloudflareHost],
  ['node (SQLite KV)', nodeHost],
];

function base64url(bytes: Buffer): string {
  return bytes.toString('base64url');
}

function form(fields: Record<string, string>): RequestInit {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams(fields).toString(),
  };
}

interface TokenSet {
  access_token: string;
  refresh_token: string;
}

class Client {
  clientId = '';

  constructor(private readonly host: Host) {}

  async register(): Promise<Response> {
    const response = await this.host.fetch('/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        client_name: 'rw-op0 spike',
        redirect_uris: [REDIRECT_URI],
        token_endpoint_auth_method: 'none',
        grant_types: ['authorization_code', 'refresh_token'],
        response_types: ['code'],
      }),
    });
    const body = (await response.clone().json()) as { client_id: string };
    this.clientId = body.client_id;
    return response;
  }

  /** Authorization code flow with PKCE S256; returns the first token set. */
  async signIn(): Promise<TokenSet> {
    const verifier = base64url(randomBytes(32));
    const challenge = base64url(createHash('sha256').update(verifier).digest());
    const state = base64url(randomBytes(8));
    const query = new URLSearchParams({
      response_type: 'code',
      client_id: this.clientId,
      redirect_uri: REDIRECT_URI,
      scope: 'mcp:read offline_access',
      state,
      code_challenge: challenge,
      code_challenge_method: 'S256',
    });
    const authorize = await this.host.fetch(`/authorize?${query.toString()}`);
    expect(authorize.status).toBe(302);
    const location = new URL(authorize.headers.get('Location')!);
    expect(`${location.origin}${location.pathname}`).toBe(REDIRECT_URI);
    expect(location.searchParams.get('state')).toBe(state);
    const code = location.searchParams.get('code');
    expect(code).toBeTruthy();
    const token = await this.host.fetch(
      '/oauth/token',
      form({
        grant_type: 'authorization_code',
        code: code!,
        redirect_uri: REDIRECT_URI,
        client_id: this.clientId,
        code_verifier: verifier,
      })
    );
    expect(token.status).toBe(200);
    const tokens = (await token.json()) as TokenSet;
    expect(tokens.access_token).toBeTruthy();
    expect(tokens.refresh_token).toBeTruthy();
    return tokens;
  }

  refresh(refreshToken: string): Promise<Response> {
    return this.host.fetch(
      '/oauth/token',
      form({
        grant_type: 'refresh_token',
        refresh_token: refreshToken,
        client_id: this.clientId,
      })
    );
  }

  revoke(token: string): Promise<Response> {
    return this.host.fetch('/oauth/token', form({ token, client_id: this.clientId }));
  }

  api(accessToken: string): Promise<Response> {
    return this.host.fetch('/api', {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
  }
}

describe.each(HOSTS)('workers-oauth-provider on %s', (_name, factory) => {
  describe('library alone', () => {
    let host: Host;
    beforeAll(async () => {
      host = await factory(false);
    });
    afterAll(() => host?.close());

    it('registers a public client, authorizes with PKCE S256 and serves the API', async () => {
      const client = new Client(host);
      const registered = await client.register();
      expect(registered.status).toBe(201);
      const registration = (await registered.json()) as Record<string, unknown>;
      expect(registration.token_endpoint_auth_method).toBe('none');
      expect(registration.client_secret).toBeUndefined();
      const tokens = await client.signIn();
      const api = await client.api(tokens.access_token);
      expect(api.status).toBe(200);
      expect(await api.json()).toEqual({ props: { userId: 'spike-user' } });
      const keys = await host.kvKeys();
      expect(keys.some((key) => key.startsWith('client:'))).toBe(true);
      expect(keys.some((key) => key.startsWith('grant:spike-user:'))).toBe(true);
      expect(keys.some((key) => key.startsWith('token:spike-user:'))).toBe(true);
    });

    it('rotates the refresh token on every refresh', async () => {
      const client = new Client(host);
      await client.register();
      const first = await client.signIn();
      const refreshed = await client.refresh(first.refresh_token);
      expect(refreshed.status).toBe(200);
      const second = (await refreshed.json()) as TokenSet;
      expect(second.refresh_token).not.toBe(first.refresh_token);
      expect(second.access_token).not.toBe(first.access_token);
      expect((await client.api(second.access_token)).status).toBe(200);
    });

    it('has no reuse detection: a replayed rotated token is accepted and the grant survives', async () => {
      const client = new Client(host);
      await client.register();
      const r0 = (await client.signIn()).refresh_token;
      const r1 = ((await (await client.refresh(r0)).json()) as TokenSet).refresh_token;
      // The replay of R0 succeeds (the library keeps the previous token as a retry grace)...
      const replay = await client.refresh(r0);
      expect(replay.status).toBe(200);
      const attacker = (await replay.json()) as TokenSet;
      // ...the legitimate holder's R1 is displaced, and the replayer keeps a live grant.
      expect((await client.refresh(r1)).status).toBe(400);
      expect((await client.api(attacker.access_token)).status).toBe(200);
      expect((await client.refresh(attacker.refresh_token)).status).toBe(200);
    });

    it('revokes the grant when its refresh token is revoked', async () => {
      const client = new Client(host);
      await client.register();
      const tokens = await client.signIn();
      expect((await client.revoke(tokens.refresh_token)).status).toBe(200);
      expect((await client.refresh(tokens.refresh_token)).status).toBe(400);
      expect((await client.api(tokens.access_token)).status).toBe(401);
    });

    it('revokes an access token', async () => {
      const client = new Client(host);
      await client.register();
      const tokens = await client.signIn();
      expect((await client.revoke(tokens.access_token)).status).toBe(200);
      expect((await client.api(tokens.access_token)).status).toBe(401);
    });
  });

  describe('with the reuse guard', () => {
    let host: Host;
    beforeAll(async () => {
      host = await factory(true);
    });
    afterAll(() => host?.close());

    it('a refresh token presented twice revokes the whole family', async () => {
      const client = new Client(host);
      await client.register();
      const r0 = (await client.signIn()).refresh_token;
      const refreshed = (await (await client.refresh(r0)).json()) as TokenSet;
      expect((await client.api(refreshed.access_token)).status).toBe(200);
      const replay = await client.refresh(r0);
      expect(replay.status).toBe(400);
      expect(((await replay.json()) as { error: string }).error).toBe('invalid_grant');
      // The successor refresh token and its access token die with the grant.
      expect((await client.refresh(refreshed.refresh_token)).status).toBe(400);
      expect((await client.api(refreshed.access_token)).status).toBe(401);
      const keys = await host.kvKeys();
      expect(keys.some((key) => key.startsWith('grant:'))).toBe(false);
      expect(keys.some((key) => key.startsWith(REFRESH_USED_PREFIX))).toBe(true);
    });

    it('a normal rotation chain keeps working', async () => {
      const client = new Client(host);
      await client.register();
      let refreshToken = (await client.signIn()).refresh_token;
      for (let round = 0; round < 3; round += 1) {
        const response = await client.refresh(refreshToken);
        expect(response.status).toBe(200);
        const tokens = (await response.json()) as TokenSet;
        expect((await client.api(tokens.access_token)).status).toBe(200);
        refreshToken = tokens.refresh_token;
      }
    });

    it('revocation still revokes the grant', async () => {
      const client = new Client(host);
      await client.register();
      const tokens = await client.signIn();
      expect((await client.revoke(tokens.refresh_token)).status).toBe(200);
      expect((await client.refresh(tokens.refresh_token)).status).toBe(400);
      expect((await client.api(tokens.access_token)).status).toBe(401);
    });
  });
});
