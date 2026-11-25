import { existsSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  print: vi.fn(),
  success: vi.fn(),
  info: vi.fn(),
  warn: vi.fn(),
  format: { current: 'table' },
}));

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, vars?: Record<string, unknown>) =>
    vars ? `${key} ${JSON.stringify(vars)}` : key,
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: { print: m.print, info: m.info, success: m.success, warn: m.warn },
}));
vi.mock('../../utils/errors.js', () => ({
  getOutputFormat: () => m.format.current,
  handleError: (error: unknown) => {
    throw error;
  },
}));
vi.mock('../../services/account/account-client.js', () => ({ accountServerFetch: vi.fn() }));

import {
  ForensicsClient,
  type ForensicsFetch,
  type IncidentRecord,
} from '../../services/forensics/client.js';
import { runIncidentExport, runIncidentStatus } from '../incident.js';

const NOW = new Date('2026-11-25T12:00:00.000Z');

const record = (over: Partial<IncidentRecord> = {}): IncidentRecord => ({
  id: 'inc-aaaa1111',
  scopeKind: 'repo',
  scopeRef: '3f2b8c1e-5d4a-4e7b-9a10-0c2d4e6f8a1b',
  windowFrom: '2026-11-24T00:00:00.000Z',
  windowTo: '2026-11-25T00:00:00.000Z',
  status: 'declared',
  declaredBy: 'user-1',
  declaredAt: '2026-11-24T10:00:00.000Z',
  awareAt: '2026-11-24T09:00:00.000Z',
  notifiedAt: null,
  containedAt: null,
  closedAt: null,
  closedBy: null,
  forkRef: null,
  steps: [{ name: 'hold', status: 'ok', at: '2026-11-24T10:00:01.000Z' }],
  releaseAt: null,
  ...over,
});

const INCIDENTS = [record(), record({ id: 'inc-bbbb2222', status: 'closed' })];

function client(extra: Record<string, unknown> = {}) {
  const calls: string[] = [];
  const answer = (path: string): unknown => {
    if (path.endsWith('/incidents')) return { incidents: INCIDENTS };
    if (path.endsWith('/investigations')) return { id: 'inv-1' };
    if (path.includes('/timeline'))
      return { rows: [{ id: 'a', ts: NOW.toISOString(), kind: 'audit' }], unreadable: 1 };
    if (path.includes('/aggregates')) return { bytesOutPerMinute: [], topDestinations: [] };
    if (path.includes('/raw'))
      return {
        files: [{ key: 'k', source: 'audit', day: '2026-11-24', bytes: 5 }],
        bytes: 5,
        tooLarge: false,
      };
    return extra;
  };
  const fetchFn = vi.fn((path: string) => {
    calls.push(path);
    return Promise.resolve(answer(path));
  });
  return {
    calls,
    deps: { client: new ForensicsClient(fetchFn as unknown as ForensicsFetch), now: () => NOW },
  };
}

let out: string;
beforeEach(() => {
  vi.clearAllMocks();
  m.format.current = 'table';
  out = mkdtempSync(join(tmpdir(), 'rdc-incident-'));
});
afterEach(() => rmSync(out, { recursive: true, force: true }));

describe('incident status', () => {
  it('lists every incident', async () => {
    await runIncidentStatus(undefined, client().deps);
    const text = String(m.print.mock.calls[0]?.[0]);
    expect(text).toContain('inc-aaaa1111');
    expect(text).toContain('inc-bbbb2222');
  });

  it('shows one incident by id prefix with its three clocks counted from awareness (early warning already past)', async () => {
    m.format.current = 'json';
    await runIncidentStatus('inc-aaaa', client().deps);
    const [view, format] = m.print.mock.calls[0] ?? [];
    expect(format).toBe('json');
    expect(view).toMatchObject({
      id: 'inc-aaaa1111',
      clocks: [
        { name: 'earlyWarning', dueAt: '2026-11-25T09:00:00.000Z', state: 'overdue' },
        { name: 'notification', dueAt: '2026-11-27T09:00:00.000Z', state: 'pending' },
        { name: 'finalReport', dueAt: '2026-12-27T09:00:00.000Z', state: 'pending' },
      ],
    });
  });

  it('reports an overdue early warning in the detail text', async () => {
    const late = { client: client().deps.client, now: () => new Date('2026-11-26T00:00:00.000Z') };
    await runIncidentStatus('inc-aaaa1111', late);
    expect(String(m.print.mock.calls[0]?.[0])).toContain('"state":"overdue"');
  });

  it('refuses an unknown id and an ambiguous prefix', async () => {
    await expect(runIncidentStatus('inc-zzzz', client().deps)).rejects.toMatchObject({
      code: 'NOT_FOUND',
    });
    await expect(runIncidentStatus('inc-', client().deps)).rejects.toMatchObject({
      code: 'AMBIGUOUS',
    });
  });
});

describe('incident export', () => {
  it('opens an investigation on the incident scope and writes the window to the directory', async () => {
    const { calls, deps } = client();
    await runIncidentExport('inc-aaaa1111', { out }, deps);
    expect(calls.some((c) => c.endsWith('/investigations'))).toBe(true);
    for (const name of [
      'incident.json',
      'timeline.json',
      'aggregates.json',
      'raw-manifest.json',
      'export.json',
    ]) {
      expect(existsSync(join(out, name))).toBe(true);
    }
    const stamp = JSON.parse(readFileSync(join(out, 'export.json'), 'utf8'));
    expect(stamp).toMatchObject({
      incident: 'inc-aaaa1111',
      window: { from: '2026-11-24T00:00:00.000Z', to: '2026-11-25T00:00:00.000Z' },
      timelineRows: 1,
      unreadable: 1,
      raw: { files: 1, bytes: 5, tooLarge: false },
    });
    expect(m.success).toHaveBeenCalled();
    expect(m.warn).toHaveBeenCalled();
  });

  it('prints the export summary as JSON', async () => {
    m.format.current = 'json';
    await runIncidentExport('inc-aaaa1111', { out }, client().deps);
    const [result, format] = m.print.mock.calls[0] ?? [];
    expect(format).toBe('json');
    expect(result).toMatchObject({ incident: 'inc-aaaa1111', timelineRows: 1, rawFiles: 1 });
  });
});
