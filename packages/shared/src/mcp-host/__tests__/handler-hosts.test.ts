/**
 * RW-OP1: one handler suite, run against the Cloudflare adapters (the handler bundled into Miniflare with a real KV binding) and the Node adapters (the handler imported in-process over the SQLite KV adapter). Every case asserts the same answer on both hosts, which is the portability claim of PLAN-rmcp-remote-worker.md Design 11.
 */
import { DatabaseSync } from 'node:sqlite';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';
import { convertV4MiniflareOptions, Miniflare } from 'miniflare';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { createNodeExecutionContext, installCloudflareWorkersShim } from '../node-workers-shim.js';
import { SqliteKvNamespace } from '../sqlite-kv.js';

const HOST = 'mcp.eu.rediacc.cloud';
const ENTRY = fileURLToPath(new URL('./fixtures/mcp-worker.ts', import.meta.url));
const BINDINGS = {
  REGION: 'eu',
  ENVIRONMENT: 'test',
  MCP_HOST: HOST,
  ACCOUNT_URL: 'https://eu.rediacc.cloud',
  AUTH_REQUEST_KEY: 'host-suite-auth-request-key',
  INTERNAL_REVOKE_TOKEN: 'host-suite-revoke-token',
};

interface Host {
  fetch(path: string, init?: RequestInit): Promise<Response>;
  close(): Promise<void>;
}

type HostFactory = () => Promise<Host>;

let bundled: string | undefined;

async function bundle(): Promise<string> {
  if (bundled === undefined) {
    const result = await build({
      entryPoints: [ENTRY],
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
    bundled = result.outputFiles[0]!.text;
  }
  return bundled;
}

const cloudflareHost: HostFactory = async () => {
  const mf = new Miniflare(
    convertV4MiniflareOptions({
      modules: [{ type: 'ESModule', path: 'worker.mjs', contents: await bundle() }],
      compatibilityDate: '2026-11-01',
      kvNamespaces: ['OAUTH_KV'],
      bindings: BINDINGS,
    })
  );
  await mf.ready;
  return {
    async fetch(path, init) {
      const response = await mf.dispatchFetch(`https://${HOST}${path}`, {
        ...(init as Record<string, unknown>),
        redirect: 'manual',
      });
      // Miniflare answers with undici's Response; re-wrap it in Node's global one.
      const empty = [204, 205, 304].includes(response.status);
      return new Response(empty ? null : await response.arrayBuffer(), {
        status: response.status,
        headers: Object.fromEntries(response.headers.entries()),
      });
    },
    close: () => mf.dispose(),
  };
};

const nodeHost: HostFactory = async () => {
  installCloudflareWorkersShim();
  const worker = (await import('./fixtures/mcp-worker.js')).default;
  const db = new DatabaseSync(':memory:');
  const env = { ...BINDINGS, OAUTH_KV: new SqliteKvNamespace(db) };
  return {
    async fetch(path, init) {
      const ctx = createNodeExecutionContext();
      const response = await worker.fetch(
        new Request(`https://${HOST}${path}`, { redirect: 'manual', ...init }),
        env,
        ctx
      );
      await ctx.drain();
      return response;
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

describe.each(HOSTS)('shared MCP handler on %s', (_name, factory) => {
  let host: Host;
  beforeAll(async () => {
    host = await factory();
  }, 60_000);
  afterAll(async () => {
    await host.close();
  });

  it('serves the authorization server metadata with this host as issuer', async () => {
    const response = await host.fetch('/.well-known/oauth-authorization-server');
    expect(response.status).toBe(200);
    const metadata = (await response.json()) as {
      issuer: string;
      code_challenge_methods_supported: string[];
    };
    expect(metadata.issuer).toBe(`https://${HOST}`);
    expect(metadata.code_challenge_methods_supported).toEqual(['S256']);
  });

  it('answers an MCP request without a credential 401', async () => {
    const response = await host.fetch('/g/eu_host_suite', {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        accept: 'application/json, text/event-stream',
      },
      body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/list' }),
    });
    expect(response.status).toBe(401);
  });

  it('refuses a grant of another region with its region URL', async () => {
    const response = await host.fetch('/g/us_host_suite', { method: 'POST', body: '{}' });
    expect(response.status).toBe(421);
    const body = (await response.json()) as { code: string; mcpUrl: string };
    expect(body.code).toBe('REDIACC_WRONG_REGION');
    expect(body.mcpUrl).toBe('https://mcp.us.rediacc.cloud/g/us_host_suite');
  });

  it('guards the revoke route with its bearer secret', async () => {
    const body = JSON.stringify({ grantId: 'eu_host_suite' });
    const bare = await host.fetch('/internal/revoke', { method: 'POST', body });
    expect(bare.status).toBe(401);
    const authorized = await host.fetch('/internal/revoke', {
      method: 'POST',
      headers: { authorization: `Bearer ${BINDINGS.INTERNAL_REVOKE_TOKEN}` },
      body,
    });
    expect(authorized.status).toBe(204);
  });
});
