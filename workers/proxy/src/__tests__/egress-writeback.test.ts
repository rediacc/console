/**
 * The `AccountEgress` config write-back routes (agent/plans/PLAN-rmcp-writeback.md WB5) and the executor's write-back requests checked against the real allowlist.
 */

import { readFileSync } from 'node:fs';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ACCOUNT_EGRESS_HOST } from '../org-executor-support';

vi.mock('cloudflare:workers', () => ({
  WorkerEntrypoint: class {
    constructor(
      protected ctx: unknown,
      protected env: unknown
    ) {}
  },
}));

import {
  forwardAccountEgress,
  MAX_CONFIG_PUSH_BODY_BYTES,
  MAX_SESSION_BODY_BYTES,
} from '../egress';
import { resetIssuedTokenCache } from '../issued-token';
import { API, setup } from './helpers/egress-harness';

/** The method of a chain request that passes none. */
const DEFAULT_METHOD = 'GET';

beforeEach(() => {
  resetIssuedTokenCache();
  vi.spyOn(console, 'warn').mockImplementation(() => undefined);
});

describe('config write-back routes (PLAN-rmcp-writeback.md WB5)', () => {
  const send = (path: string, init: RequestInit) =>
    new Request(`${API}${path}`, { headers: { 'x-config-token': 'ct-1' }, ...init });

  it('admits POST /configs/session with the X-Config-Token kept and no Authorization', async () => {
    const { env, seen, state } = setup();
    const response = await forwardAccountEgress(
      send('/configs/session', { method: 'POST', body: '{}' }),
      env,
      'org-a'
    );
    expect(response.status).toBe(200);
    expect(seen).toHaveLength(1);
    expect(seen[0]?.url).toBe('https://account.test/account/api/v1/configs/session');
    expect(seen[0]?.headers.get('x-config-token')).toBe('ct-1');
    expect(seen[0]?.headers.get('authorization')).toBeNull();
    expect(state.issues).toEqual([]);
  });

  it('admits PUT /configs/<id> with the teamId query and the body intact', async () => {
    const { env, seen } = setup();
    const response = await forwardAccountEgress(
      send('/configs/cfg-1?teamId=team-1', { method: 'PUT', body: '{"version":2}' }),
      env,
      'org-a'
    );
    expect(response.status).toBe(200);
    expect(seen[0]?.method).toBe('PUT');
    expect(seen[0]?.url).toBe('https://account.test/account/api/v1/configs/cfg-1?teamId=team-1');
    expect(await seen[0]?.text()).toBe('{"version":2}');
  });

  it('refuses an oversize push body 413 body-too-large with nothing forwarded', async () => {
    const { env, seen } = setup();
    const response = await forwardAccountEgress(
      send('/configs/cfg-1', {
        method: 'PUT',
        body: new Uint8Array(MAX_CONFIG_PUSH_BODY_BYTES + 1),
      }),
      env,
      'org-a'
    );
    expect(response.status).toBe(413);
    expect(await response.json()).toMatchObject({ reason: 'body-too-large' });
    expect(seen).toHaveLength(0);
  });

  it('refuses an oversize session handshake body 413 body-too-large with nothing forwarded', async () => {
    const { env, seen } = setup();
    const response = await forwardAccountEgress(
      send('/configs/session', {
        method: 'POST',
        body: new Uint8Array(MAX_SESSION_BODY_BYTES + 1),
      }),
      env,
      'org-a'
    );
    expect(response.status).toBe(413);
    expect(await response.json()).toMatchObject({ reason: 'body-too-large' });
    expect(seen).toHaveLength(0);
  });

  it('admits a session handshake body of exactly the cap (control for the refusal)', async () => {
    const { env, seen } = setup();
    const response = await forwardAccountEgress(
      send('/configs/session', { method: 'POST', body: new Uint8Array(MAX_SESSION_BODY_BYTES) }),
      env,
      'org-a'
    );
    expect(response.status).toBe(200);
    expect(seen).toHaveLength(1);
  });

  it('admits a push body of exactly the cap (control for the refusal)', async () => {
    const { env, seen } = setup();
    const response = await forwardAccountEgress(
      send('/configs/cfg-1', { method: 'PUT', body: new Uint8Array(MAX_CONFIG_PUSH_BODY_BYTES) }),
      env,
      'org-a'
    );
    expect(response.status).toBe(200);
    expect(seen).toHaveLength(1);
  });

  it.each([
    ['POST /configs/<id>', '/configs/cfg-1', 'POST', 'route-not-allowed'],
    ['PUT /configs/session', '/configs/session', 'PUT', 'route-not-allowed'],
    ['DELETE /configs/<id>', '/configs/cfg-1', 'DELETE', 'route-not-allowed'],
    ['PUT with an unknown query', '/configs/cfg-1?all=1', 'PUT', 'query-not-allowed'],
    [
      'POST /configs/session with a query',
      '/configs/session?teamId=t',
      'POST',
      'query-not-allowed',
    ],
  ])('still refuses %s', async (_name, path, method, reason) => {
    const { env, seen } = setup();
    const response = await forwardAccountEgress(send(path, { method, body: '{}' }), env, 'org-a');
    expect(response.status).toBe(403);
    expect(await response.json()).toMatchObject({ reason });
    expect(seen).toHaveLength(0);
  });
});

describe('executor write-back requests against the real allowlist', () => {
  const send = (path: string, init: RequestInit = {}) =>
    new Request(`http://${ACCOUNT_EGRESS_HOST}${path}`, {
      headers: { 'x-config-token': 'ct-1' },
      ...init,
    });

  it('admits GET /configs (the revalidate listing) with the token kept and forwards it', async () => {
    const { env, seen } = setup();
    const response = await forwardAccountEgress(send('/account/api/v1/configs'), env, 'org-a');
    expect(response.status).toBe(200);
    expect(seen).toHaveLength(1);
    expect(seen[0]?.url).toBe('https://account.test/account/api/v1/configs');
    expect(seen[0]?.headers.get('x-config-token')).toBe('ct-1');
  });

  it.each([
    ['POST /configs', 'POST', '/account/api/v1/configs', 'route-not-allowed'],
    ['GET /configs with a query', 'GET', '/account/api/v1/configs?teamId=t', 'query-not-allowed'],
    ['GET /configs/ (trailing slash)', 'GET', '/account/api/v1/configs/', 'route-not-allowed'],
  ])('still refuses %s', async (_name, method, path, reason) => {
    const { env, seen } = setup();
    const response = await forwardAccountEgress(send(path, { method }), env, 'org-a');
    expect(response.status).toBe(403);
    expect(await response.json()).toMatchObject({ reason });
    expect(seen).toHaveLength(0);
  });

  /** The method and path of every literal executor-chain request in `source`, and how many `chain.request(` calls it holds in all (a call whose path is a variable is counted but not scanned). */
  function scanWritebackCalls(source: string): {
    calls: { path: string; method: string }[];
    total: number;
  } {
    // Every `chain.request(<'literal' or `template`>, ...` call: the `${query}` interpolation becomes empty, any other `${...}` becomes a placeholder id. The method is the first `method: '<M>'` before the call's `op` argument, else GET.
    const calls = [
      ...source.matchAll(
        /chain\.request\(\s*(['`])(\/account\/api\/v1\/[^'`]*)\1([\s\S]*?)\bop\b/g
      ),
    ].map((m) => {
      const path = (m[2] as string)
        .replace(/\$\{query\}/g, '')
        .replace(/\$\{[^}]*(?:\{[^}]*\}[^}]*)*\}/g, 'cfg-1');
      return { path, method: /method: '(\w+)'/.exec(m[3] as string)?.[1] ?? DEFAULT_METHOD };
    });
    return { calls, total: [...source.matchAll(/chain\.request\(/g)].length };
  }

  function writebackCalls(): { path: string; method: string }[] {
    const source = readFileSync(
      new URL('../../../../packages/cli/src/services/serve/config-writeback.ts', import.meta.url)
        .pathname,
      'utf8'
    );
    const { calls, total } = scanWritebackCalls(source);
    // A call the scan cannot read (a variable or a concatenated path) would pass unchecked, so it fails here instead.
    expect(calls.length, 'every chain.request( call has a literal path the scan reads').toBe(total);
    return calls;
  }

  it('the scan counts a variable-path call it cannot read, and reads a literal one', () => {
    const literal = "chain.request('/account/api/v1/configs', {}, op)";
    const variable = 'chain.request(path, {}, op)';
    expect(scanWritebackCalls(literal)).toMatchObject({ total: 1, calls: [{ method: 'GET' }] });
    const mixed = scanWritebackCalls(`${literal}\n${variable}`);
    expect(mixed.total).toBe(2);
    expect(mixed.calls).toHaveLength(1);
  });

  /** A POST or the listing takes no query; every other call is tried bare and with a team. */
  function writebackQueries(call: { path: string; method: string }): string[] {
    return call.method === 'POST' || call.path.endsWith('/configs') ? [''] : ['', '?teamId=t'];
  }

  it('admits every literal path the executor chain requests in config-writeback.ts', async () => {
    const calls = writebackCalls();
    // Five call sites today: the listing, the session handshake, the push, the pull and the policy read. A scan that finds fewer proves nothing.
    expect(
      calls.map((c) => `${c.method} ${c.path}`).sort((a, b) => Number(a > b) - Number(a < b))
    ).toEqual([
      'GET /account/api/v1/configs',
      'GET /account/api/v1/configs/cfg-1',
      'GET /account/api/v1/configs/cfg-1/policy',
      'POST /account/api/v1/configs/session',
      'PUT /account/api/v1/configs/cfg-1',
    ]);
    for (const { path, method } of calls) {
      for (const query of writebackQueries({ path, method })) {
        const { env, seen } = setup();
        const response = await forwardAccountEgress(
          send(`${path}${query}`, method === 'GET' ? {} : { method, body: '{}' }),
          env,
          'org-a'
        );
        expect(response.status, `${method} ${path}${query}`).toBe(200);
        expect(seen, `${method} ${path}${query}`).toHaveLength(1);
      }
    }
  });

  it('admits GET /configs/<id>/policy with and without teamId, and refuses other shapes', async () => {
    for (const path of [
      '/account/api/v1/configs/cfg-1/policy',
      '/account/api/v1/configs/cfg-1/policy?teamId=t',
    ]) {
      const { env, seen } = setup();
      const response = await forwardAccountEgress(send(path), env, 'org-a');
      expect(response.status, path).toBe(200);
      expect(seen[0]?.headers.get('x-config-token')).toBe('ct-1');
      expect(seen[0]?.headers.get('authorization'), path).toBeNull();
    }
    for (const [method, path, reason] of [
      ['PUT', '/account/api/v1/configs/cfg-1/policy', 'route-not-allowed'],
      ['POST', '/account/api/v1/configs/cfg-1/policy', 'route-not-allowed'],
      ['GET', '/account/api/v1/configs/cfg-1/policy?all=1', 'query-not-allowed'],
      ['GET', '/account/api/v1/configs/cfg-1/policy/x', 'route-not-allowed'],
    ] as const) {
      const { env, seen } = setup();
      const response = await forwardAccountEgress(send(path, { method }), env, 'org-a');
      expect(response.status, `${method} ${path}`).toBe(403);
      expect(await response.json()).toMatchObject({ reason });
      expect(seen).toHaveLength(0);
    }
  });
});
