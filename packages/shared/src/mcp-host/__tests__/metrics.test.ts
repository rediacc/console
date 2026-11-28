/**
 * Monitoring of the hosted Worker (agent/plans/PLAN-rmcp-remote-worker.md Design 10, RW-D3): the counters handler.ts writes through a real request, and the alert rule over them. A burst of `REDIACC_GRANT_*` refusals from one grant raises the alert and a quiet grant does not.
 */
import './helpers/workers-shim.js';
import { readdirSync, readFileSync } from 'node:fs';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { WK_MCP_EU_HOST } from '../../config/well-known.generated.js';
import { deriveAuthTag } from '../../config-crypto/agent-grant.js';
import type { HostExecutionContext } from '../host-types.js';
import {
  ALERT_RULE,
  alertQuery,
  evaluateAlerts,
  type GrantWindow,
  type MetricsDataset,
  UNAUTHENTICATED_INDEX,
} from '../metrics.js';
import type { ResolvedGrantWire } from '../resolve.js';
import { bearerFor, SECRET_BYTES } from './helpers/grant.js';

const HOST = WK_MCP_EU_HOST;

type Point = { indexes?: string[]; blobs?: string[]; doubles?: number[] };

function wire(grantId: string, state: 'active' | 'revoked'): ResolvedGrantWire {
  return {
    grantId,
    state,
    orgId: 'org-test',
    placement: 1,
    tier: 'standard',
    userId: 'user-1',
    teamId: null,
    configId: 'cfg-1',
    region: 'eu',
    scope: { readOnly: false },
    expiresAt: '2099-01-01T00:00:00.000Z',
  };
}

beforeEach(() => {
  vi.resetModules();
});

/** The Worker over one grant state, a recording dataset, and a `call` helper posting a `tools/call`. */
async function workerFor(
  grantId: string,
  state: 'active' | 'revoked',
  withDataset = true,
  options: {
    env?: Record<string, unknown>;
    ctx?: 'waitUntil' | 'bare';
    handler?: 'factory';
    module?: typeof import('../handler.js');
  } = {}
) {
  // The handler keeps its transport for the first env it sees; a fresh module per Worker keeps two Workers of one test apart.
  vi.resetModules();
  const module = options.module ?? (await import('../handler.js'));
  const worker = options.handler === 'factory' ? module.createMcpHandler() : module.default;
  const points: Point[] = [];
  const dataset: MetricsDataset = { writeDataPoint: (p) => points.push(p) };
  const tag = await deriveAuthTag(SECRET_BYTES);
  const env = {
    REGION: 'eu',
    ENVIRONMENT: 'test',
    MCP_HOST: HOST,
    ACCOUNT_URL: 'https://account.test',
    GRANTS: {
      resolveGrant: (_id: string, authTag: string) =>
        Promise.resolve(authTag === tag ? wire(grantId, state) : null),
    },
    EXECUTOR: {
      call: () =>
        Promise.resolve({
          ok: true as const,
          answer: { result: { content: [{ type: 'text', text: 'ran' }], isError: false } },
        }),
    },
    ...(withDataset ? { MCP_METRICS: dataset } : {}),
    ...options.env,
  };
  const kept: Promise<unknown>[] = [];
  const waitUntil = vi.fn((p: Promise<unknown>) => void kept.push(p));
  const passThroughOnException = (): void => undefined;
  // The bare host is the one shape the type forbids (no `waitUntil`), which is exactly the case under test.
  const ctx: HostExecutionContext =
    options.ctx === 'bare'
      ? ({ passThroughOnException } as unknown as HostExecutionContext)
      : { waitUntil, passThroughOnException };
  const post = (tool: string, bearer = bearerFor(grantId)): Promise<Response> =>
    worker.fetch(
      new Request(`https://${HOST}/g/${grantId}`, {
        method: 'POST',
        headers: {
          authorization: `Bearer ${bearer}`,
          'content-type': 'application/json',
          accept: 'application/json, text/event-stream',
        },
        body: JSON.stringify({
          jsonrpc: '2.0',
          id: 1,
          method: 'tools/call',
          params: { name: tool, arguments: {} },
        }),
      }),
      env as never,
      ctx
    );
  const call = async (tool: string, bearer = bearerFor(grantId)): Promise<Response> => {
    const response = await post(tool, bearer);
    // A real isolate settles the `waitUntil` work after the answer; the helper settles it before the test reads the points.
    await Promise.all(kept.splice(0));
    return response;
  };
  return { call, post, points, waitUntil };
}

function windowOf(points: Point[]): GrantWindow[] {
  const byGrant = new Map<string, GrantWindow>();
  for (const p of points) {
    const id = p.indexes?.[0] ?? '';
    const row = byGrant.get(id) ?? { grant_id: id, grant_refusals: 0, destructive_calls: 0 };
    if (p.blobs?.[1]?.startsWith('REDIACC_GRANT_')) row.grant_refusals += 1;
    row.destructive_calls += p.doubles?.[2] ?? 0;
    byGrant.set(id, row);
  }
  return [...byGrant.values()];
}

describe('per-grant counters', () => {
  it('writes one point per call with the grant as index and no argument or credential', async () => {
    const { call, points } = await workerFor('eu_quiet', 'active');
    await call('repo_list');
    await call('backup_restore');
    expect(points).toHaveLength(2);
    expect(points[0].indexes).toEqual(['eu_quiet']);
    expect(points[0].blobs).toEqual(['repo_list', 'ok', 'eu']);
    expect(points[0].doubles?.slice(1)).toEqual([0, 0]);
    expect(points[1].doubles?.slice(1)).toEqual([0, 1]);
    expect(points[0].doubles?.[0]).toBeGreaterThanOrEqual(0);
    expect(JSON.stringify(points)).not.toContain(bearerFor('eu_quiet'));
  });

  it('records the REDIACC_GRANT code of a refused call and counts it as an error', async () => {
    const { call, points } = await workerFor('eu_gone', 'revoked');
    await call('repo_list');
    expect(points).toHaveLength(1);
    expect(points[0].indexes).toEqual(['eu_gone']);
    expect(points[0].blobs?.[1]).toBe('REDIACC_GRANT_REVOKED');
    expect(points[0].doubles?.[1]).toBe(1);
  });

  it('never indexes a 401 by the unproven grant id', async () => {
    const { call, points } = await workerFor('eu_known', 'active');
    const response = await call('repo_list', bearerFor('eu_known', new Uint8Array(32)));
    expect(response.status).toBe(401);
    expect(points).toHaveLength(1);
    expect(points[0].indexes).toEqual([UNAUTHENTICATED_INDEX]);
    expect(points[0].blobs?.[1]).toBe('HTTP_401');
  });

  it('records nothing and answers the same without the MCP_METRICS binding', async () => {
    const { call, points } = await workerFor('eu_quiet', 'active', false);
    const response = await call('repo_list');
    expect(response.status).toBe(200);
    expect(points).toHaveLength(0);
  });
});

describe('a host without waitUntil', () => {
  /** Makes reading any Response body through `text()` never settle: the stand-in for an open stream. */
  function hangBodies() {
    return vi.spyOn(Response.prototype, 'text').mockImplementation(() => new Promise(() => {}));
  }
  const settled = (promise: Promise<unknown>) =>
    Promise.race([
      promise.then(() => 'answered'),
      new Promise((resolve) => setTimeout(() => resolve('held'), 400)),
    ]);

  it('answers while the counter is still reading the body', async () => {
    const { post } = await workerFor('eu_bare', 'active', true, { ctx: 'bare' });
    const spy = hangBodies();
    try {
      expect(await settled(post('repo_list'))).toBe('answered');
    } finally {
      spy.mockRestore();
    }
  });

  it('hands the counter to waitUntil when the host has one, with the same answer', async () => {
    const hosted = await workerFor('eu_hosted', 'active', true);
    const spy = hangBodies();
    try {
      expect(await settled(hosted.post('repo_list'))).toBe('answered');
      expect(hosted.waitUntil).toHaveBeenCalledTimes(1);
    } finally {
      spy.mockRestore();
    }
  });
});

describe('createMcpHandler and RATE_LIMITER', () => {
  const limiter = () => {
    const taken: string[] = [];
    return {
      taken,
      acquire: (grantId: string) => {
        taken.push(grantId);
        return Promise.resolve({ ok: true as const, release: () => Promise.resolve() });
      },
      burn: () => Promise.resolve(true),
    };
  };
  const durableObjects = {
    idFromName: () => {
      throw new Error('the RATE namespace must not be used when RATE_LIMITER is bound');
    },
    get: () => {
      throw new Error('the RATE namespace must not be used when RATE_LIMITER is bound');
    },
  };

  it('takes its slot from RATE_LIMITER ahead of the RATE namespace', async () => {
    const mine = limiter();
    const { call } = await workerFor('eu_limited', 'active', true, {
      env: { RATE_LIMITER: mine, RATE: durableObjects },
    });
    const response = await call('repo_list');
    expect(response.status).toBe(200);
    expect(mine.taken).toEqual(['eu_limited']);
  });

  it('gives each factory instance its own transport, so two hosts never share a limiter', async () => {
    const one = limiter();
    const two = limiter();
    // One module for both: only the factory keeps the two instances' state apart.
    const module = await import('../handler.js');
    const a = await workerFor('eu_one', 'active', true, {
      handler: 'factory',
      module,
      env: { RATE_LIMITER: one },
    });
    const b = await workerFor('eu_two', 'active', true, {
      handler: 'factory',
      module,
      env: { RATE_LIMITER: two },
    });
    await a.call('repo_list');
    await b.call('repo_list');
    expect(one.taken).toEqual(['eu_one']);
    expect(two.taken).toEqual(['eu_two']);
  });
});

describe('alert rule', () => {
  it('raises an alert for a burst of refusals from one grant and none for a quiet grant', async () => {
    const noisy = await workerFor('eu_noisy', 'revoked');
    const quiet = await workerFor('eu_quiet', 'active');
    for (let i = 0; i < ALERT_RULE.grantRefusals; i += 1) await noisy.call('repo_list');
    await quiet.call('repo_list');
    await quiet.call('repo_list');
    // The quiet grant really ran as active, so the noisy one's resolver is not the one answering both.
    expect(quiet.points.map((p) => p.blobs?.[1])).toEqual(['ok', 'ok']);
    expect(noisy.points.every((p) => p.blobs?.[1] === 'REDIACC_GRANT_REVOKED')).toBe(true);

    const alerts = evaluateAlerts(windowOf([...noisy.points, ...quiet.points]));
    expect(alerts).toEqual([
      { grantId: 'eu_noisy', reason: 'grant-refusals', count: ALERT_RULE.grantRefusals },
    ]);
  });

  it('stays quiet one refusal below the threshold', async () => {
    const grant = await workerFor('eu_edge', 'revoked');
    for (let i = 0; i < ALERT_RULE.grantRefusals - 1; i += 1) await grant.call('repo_list');
    expect(evaluateAlerts(windowOf(grant.points))).toEqual([]);
  });

  it('raises an alert for a burst of destructive calls from one grant', async () => {
    const grant = await workerFor('eu_destroyer', 'active');
    for (let i = 0; i < ALERT_RULE.destructiveCalls; i += 1) await grant.call('backup_restore');
    expect(evaluateAlerts(windowOf(grant.points))).toEqual([
      { grantId: 'eu_destroyer', reason: 'destructive-calls', count: ALERT_RULE.destructiveCalls },
    ]);
  });

  it('names the same thresholds in the query the ops job runs, over the dataset it was given', () => {
    const query = alertQuery('mcp_eu');
    expect(query).toContain(`INTERVAL '${ALERT_RULE.windowMinutes}' MINUTE`);
    expect(query).toContain('REDIACC_GRANT_%');
    expect(query).toContain(' FROM mcp_eu WHERE ');
    expect(query).not.toMatch(/[<@]/);
  });

  it('refuses a placeholder or malformed dataset name', () => {
    for (const name of ['mcp_<region>', '@@DATASET@@', 'mcp_eu; DROP', 'mcp_', '', 'eu']) {
      expect(() => alertQuery(name), name).toThrow('not an MCP metrics dataset name');
    }
  });

  it('accepts every dataset the wrangler files bind', () => {
    const dir = new URL('../../../../../workers/mcp/', import.meta.url).pathname;
    const bound = readdirSync(dir)
      .filter((file) => /^wrangler\.(?!template).*\.toml$/.test(file))
      .map((file) => /^dataset = "([^"]+)"/m.exec(readFileSync(`${dir}${file}`, 'utf8'))?.[1]);
    // Three regions and three bench regions today; fewer would prove nothing.
    expect(bound.length).toBeGreaterThanOrEqual(6);
    for (const name of bound) expect(() => alertQuery(name as string), String(name)).not.toThrow();
  });
});
