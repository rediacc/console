/**
 * The hosted Worker's transport (agent/plans/PLAN-rmcp-remote-worker.md RW-T1, Design 1), driven by the real SDK v2 client over the Worker's fetch face: a client pinned to 2026-07-28 negotiates through `server/discover`, a 2025-11-25 client opens with `initialize` on the stateless legacy leg, and both must list the same tools as the local stdio server's parity snapshot.
 */
import { Client, StreamableHTTPClientTransport } from '@modelcontextprotocol/client';
import { describe, expect, it } from 'vitest';
import snapshot from '../../../../packages/shared/src/mcp/__tests__/tools-list.snapshot.json' with {
  type: 'json',
};
import type { GrantScope } from '../scope.js';
import { createMcpTransport, type McpTransport } from '../transport.js';
import { activeGrant, bearerFor, resolverFor } from './helpers/grant.js';

const HOST = 'mcp.eu.rediacc.cloud';
const GRANT_ID = 'grant_t1';
const URL_ = `https://${HOST}/g/${GRANT_ID}`;
const MODERN = '2026-07-28';
const LEGACY = '2025-11-25';

const FULL: GrantScope = { readOnly: false, tools: null, machines: null, repos: null };

function transportWith(scope: GrantScope = FULL): McpTransport {
  return createMcpTransport({
    host: HOST,
    serverVersion: '0.0.0-test',
    accountUrl: 'https://eu.rediacc.cloud',
    resolveGrant: resolverFor([activeGrant(GRANT_ID, { scope })]),
    executor: undefined,
  });
}

interface Captured {
  method: string;
  headers: Headers;
  body: string;
}

/** A client whose HTTP goes straight into `worker.fetch`, recording every request it sends. */
async function connect(
  worker: McpTransport,
  mode: 'legacy' | { pin: string },
  sent: Captured[] = []
): Promise<Client> {
  const fetchViaWorker = async (input: string | URL | Request, init?: RequestInit) => {
    const request = new Request(input, init);
    request.headers.set('authorization', `Bearer ${bearerFor(GRANT_ID)}`);
    sent.push({
      method: request.method,
      headers: new Headers(request.headers),
      body: await request.clone().text(),
    });
    return worker.fetch(request);
  };
  const client = new Client({ name: 'rw-t1', version: '0.0.0' }, { versionNegotiation: { mode } });
  await client.connect(new StreamableHTTPClientTransport(new URL(URL_), { fetch: fetchViaWorker }));
  return client;
}

function byCodeUnits(a: string, b: string): number {
  if (a < b) return -1;
  return a > b ? 1 : 0;
}

describe('the hosted MCP transport', () => {
  it('a 2026-07-28 client negotiates through server/discover and lists the snapshot tools', async () => {
    const client = await connect(transportWith(), { pin: MODERN });
    expect(client.getProtocolEra()).toBe('modern');
    expect(client.getNegotiatedProtocolVersion()).toBe(MODERN);
    const { tools } = await client.listTools();
    expect(tools).toEqual(snapshot);
    await client.close();
  });

  it('a 2025-11-25 client opens with initialize on the stateless leg and lists the same tools', async () => {
    const sent: Captured[] = [];
    const client = await connect(transportWith(), 'legacy', sent);
    expect(client.getProtocolEra()).toBe('legacy');
    expect(client.getNegotiatedProtocolVersion()).toBe(LEGACY);
    expect(sent.some((r) => r.body.includes('"initialize"'))).toBe(true);
    const { tools } = await client.listTools();
    expect(tools).toEqual(snapshot);
    await client.close();
  });

  it('tools/list order is stable and sorted by code units', async () => {
    const client = await connect(transportWith(), { pin: MODERN });
    const first = (await client.listTools()).tools.map((t) => t.name);
    const second = (await client.listTools()).tools.map((t) => t.name);
    expect(second).toEqual(first);
    expect([...first].sort(byCodeUnits)).toEqual(first);
    // Control: the listing is the proxy slice, not an empty or a one-tool answer.
    expect(first.length).toBe(snapshot.length);
    await client.close();
  });

  it('a protocol header that contradicts the body gives 400 with -32020', async () => {
    const worker = transportWith();
    const sent: Captured[] = [];
    const client = await connect(worker, { pin: MODERN }, sent);
    await client.listTools();
    await client.close();
    const list = sent.find((r) => r.headers.get('mcp-method') === 'tools/list');
    expect(list, 'the modern client sent Mcp-Method on tools/list').toBeDefined();
    if (!list) return;

    // Control: the recorded request replays cleanly.
    const replay = await worker.fetch(
      new Request(URL_, { method: 'POST', headers: list.headers, body: list.body })
    );
    expect(replay.status).toBe(200);

    const headers = new Headers(list.headers);
    headers.set('mcp-method', 'tools/call');
    const res = await worker.fetch(new Request(URL_, { method: 'POST', headers, body: list.body }));
    expect(res.status).toBe(400);
    const body = (await res.json()) as { error?: { code?: number } };
    expect(body.error?.code).toBe(-32020);
  });

  it('a browser Origin outside the allowlist gives 403, and an allowed one passes', async () => {
    const worker = transportWith();
    const sent: Captured[] = [];
    const client = await connect(worker, { pin: MODERN }, sent);
    await client.listTools();
    await client.close();
    const list = sent.find((r) => r.headers.get('mcp-method') === 'tools/list');
    if (!list) throw new Error('no tools/list request recorded');
    const withOrigin = (origin: string) => {
      const headers = new Headers(list.headers);
      headers.set('origin', origin);
      return worker.fetch(new Request(URL_, { method: 'POST', headers, body: list.body }));
    };
    expect((await withOrigin('https://evil.example')).status).toBe(403);
    expect((await withOrigin('https://claude.ai')).status).toBe(200);
    expect((await withOrigin(`https://${HOST}`)).status).toBe(200);
  });

  it('GET and DELETE get 405, since there is no session to stream or end', async () => {
    const worker = transportWith();
    for (const method of ['GET', 'DELETE']) {
      const res = await worker.fetch(new Request(URL_, { method }));
      expect(res.status, method).toBe(405);
      expect(res.headers.get('allow')).toBe('POST');
    }
  });

  it('an unknown grant gets a bare 401 and a path outside /g/<id> gets 404', async () => {
    const worker = transportWith();
    const unknown = await worker.fetch(
      new Request(`https://${HOST}/g/nope`, {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          authorization: `Bearer ${bearerFor('nope')}`,
        },
        body: '{"jsonrpc":"2.0","id":1,"method":"tools/list"}',
      })
    );
    expect(unknown.status).toBe(401);
    expect(await unknown.text()).toBe('Unauthorized');
    expect((await worker.fetch(new Request(`https://${HOST}/`, { method: 'POST' }))).status).toBe(
      404
    );
  });

  it('tools/list is filtered by the grant scope', async () => {
    const readOnly = await connect(transportWith({ ...FULL, readOnly: true }), { pin: MODERN });
    const ro = (await readOnly.listTools()).tools;
    await readOnly.close();
    expect(ro.length).toBeGreaterThan(0);
    expect(ro.length).toBeLessThan(snapshot.length);
    expect(ro.every((t) => t.annotations?.readOnlyHint === true)).toBe(true);

    // machine_list is not a proxy-surface tool, so naming it in the allowlist does not serve it.
    const allow = ['repo_list', 'machine_list', 'backup_browse'];
    const listed = await connect(transportWith({ ...FULL, tools: allow }), { pin: MODERN });
    const names = (await listed.listTools()).tools.map((t) => t.name);
    await listed.close();
    expect(names).toEqual(['backup_browse', 'repo_list']);
  });
});
