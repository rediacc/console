import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  print: vi.fn(),
  format: { current: 'table' },
}));

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, vars?: Record<string, unknown>) =>
    vars ? `${key} ${JSON.stringify(vars)}` : key,
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: { print: m.print, info: vi.fn(), success: vi.fn() },
}));
vi.mock('../../utils/errors.js', () => ({
  getOutputFormat: () => m.format.current,
  handleError: (error: unknown) => {
    throw error;
  },
}));
vi.mock('../../utils/repo-ref-local.js', () => ({ resolveRepoRefLocal: vi.fn() }));
vi.mock('../../services/config/config-resources.js', () => ({ configService: {} }));
vi.mock('../../services/account/account-client.js', () => ({ accountServerFetch: vi.fn() }));

import { ForensicsClient, type ForensicsFetch } from '../../services/forensics/client.js';
import { runRepoRows } from '../repo-flows.js';

const GUID = '3f2b8c1e-5d4a-4e7b-9a10-0c2d4e6f8a1b';
const NOW = new Date('2026-11-25T12:00:00.000Z');

const flow = {
  id: 'flow:1',
  ts: '2026-11-25T10:00:00.000Z',
  kind: 'flow',
  data: {
    repoGuid: GUID,
    process: 'curl',
    dstAddress: '203.0.113.9',
    dstPort: 443,
    bytesOut: 1200,
    bytesIn: 40,
    asn: 64500,
    country: 'NL',
  },
};
const open = {
  id: 'open:1',
  ts: '2026-11-25T10:01:00.000Z',
  kind: 'open',
  data: { repoGuid: GUID, process: 'cat', path: '/etc/shadow', sensitive: true },
};
const gap = {
  id: 'gap:1',
  ts: '2026-11-25T10:30:00.000Z',
  kind: 'gap',
  data: {
    machineId: 'machine-1',
    from: '2026-11-25T10:20:00.000Z',
    to: '2026-11-25T10:40:00.000Z',
    reason: 'heartbeat',
  },
};

function deps(pages: { rows: unknown[]; nextCursor?: string; unreadable?: number }[]) {
  const calls: string[] = [];
  let page = 0;
  const fetchFn = vi.fn((path: string, options?: { method?: string }) => {
    calls.push(`${options?.method ?? 'GET'} ${path}`);
    if (path.endsWith('/investigations')) return Promise.resolve({ id: 'inv-1' });
    const next = pages[page++] ?? { rows: [] };
    return Promise.resolve({ unreadable: 0, ...next });
  });
  return {
    calls,
    deps: {
      client: new ForensicsClient(fetchFn as unknown as ForensicsFetch),
      repoGuid: () => Promise.resolve(GUID),
      now: () => NOW,
    },
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  m.format.current = 'table';
});

describe('repo flows and opens', () => {
  it('opens an investigation on the repo guid and pages the timeline', async () => {
    const { calls, deps: d } = deps([{ rows: [flow], nextCursor: 'c1' }, { rows: [gap, open] }]);
    const read = await runRepoRows('flow', 'web', { since: '2h' }, d);
    expect(calls[0]).toBe('POST /account/api/v1/console/forensics/investigations');
    expect(calls[1]).toContain('/investigations/inv-1/timeline?from=2026-11-25T10%3A00%3A00.000Z');
    expect(calls[2]).toContain('cursor=c1');
    expect(read.scope).toEqual({ kind: 'repo', ref: GUID });
    // Flows and the gap stay; the file open of the same timeline does not.
    expect(read.rows.map((r) => r.kind)).toEqual(['flow', 'gap']);
  });

  it('prints a gap row where the evidence stops, beside the flow rows', async () => {
    const { deps: d } = deps([{ rows: [flow, gap] }]);
    await runRepoRows('flow', 'web', {}, d);
    const out = String(m.print.mock.calls[0]?.[0]);
    expect(out).toContain('203.0.113.9:443');
    expect(out).toContain('AS64500');
    expect(out).toContain('forensics.gapLine');
    expect(out).toContain('heartbeat');
  });

  it('lists file opens with the sensitive mark', async () => {
    const { deps: d } = deps([{ rows: [flow, open] }]);
    await runRepoRows('open', 'web', {}, d);
    const out = String(m.print.mock.calls[0]?.[0]);
    expect(out).toContain('/etc/shadow');
    expect(out).toContain('forensics.sensitive');
    expect(out).not.toContain('203.0.113.9');
  });

  it('prints the JSON envelope with the scope, window, rows and gap count', async () => {
    m.format.current = 'json';
    const { deps: d } = deps([{ rows: [flow, gap], unreadable: 2 }]);
    await runRepoRows('flow', 'web', { since: '1h' }, d);
    const [payload, format] = m.print.mock.calls[0] ?? [];
    expect(format).toBe('json');
    expect(payload).toMatchObject({
      scope: { kind: 'repo', ref: GUID },
      window: { from: '2026-11-25T11:00:00.000Z', to: '2026-11-25T12:00:00.000Z' },
      kind: 'flow',
      gaps: 1,
      unreadable: 2,
    });
    expect((payload as { rows: unknown[] }).rows).toHaveLength(2);
  });

  it('says so when the window holds no rows', async () => {
    const { deps: d } = deps([{ rows: [] }]);
    await runRepoRows('flow', 'web', {}, d);
    expect(String(m.print.mock.calls[0]?.[0])).toBe('forensics.noFlows');
  });

  it('turns a refused step-up into the portal pointer', async () => {
    const refusal = Object.assign(new Error('Re-authentication required'), {
      status: 403,
      details: { reauthRequired: true },
    });
    const client = new ForensicsClient((() => Promise.reject(refusal)) as ForensicsFetch);
    await expect(
      runRepoRows(
        'flow',
        'web',
        {},
        { client, repoGuid: () => Promise.resolve(GUID), now: () => NOW }
      )
    ).rejects.toMatchObject({ code: 'AUTH_REQUIRED', message: 'forensics.reauthRequired' });
  });

  it('refuses an inverted window before any request', async () => {
    const { calls, deps: d } = deps([]);
    await expect(runRepoRows('flow', 'web', { since: '1h', until: '3h' }, d)).rejects.toThrow(
      'forensics.sinceAfterUntil'
    );
    expect(calls).toEqual([]);
  });
});
