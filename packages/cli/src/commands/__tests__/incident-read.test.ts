import { existsSync, mkdtempSync, readdirSync, readFileSync, rmSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, relative, sep } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  print: vi.fn(),
  success: vi.fn(),
  info: vi.fn(),
  warn: vi.fn(),
  setExitCode: vi.fn(),
  format: { current: 'table' },
}));

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, vars?: Record<string, unknown>) =>
    vars ? `${key} ${JSON.stringify(vars)}` : key,
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: { print: m.print, info: m.info, success: m.success, warn: m.warn },
}));
vi.mock('../../services/core/request-context.js', () => ({ setExitCode: m.setExitCode }));
vi.mock('../../utils/errors.js', () => ({
  getOutputFormat: () => m.format.current,
  handleError: (error: unknown) => {
    throw error;
  },
}));
vi.mock('../../services/account/account-client.js', () => ({ accountServerFetch: vi.fn() }));

import {
  auditKey,
  MACHINE,
  repoKey,
  rewrite,
  writeFixture,
} from '../../services/forensics/__tests__/evidence-fixture.js';
import {
  ForensicsClient,
  type ForensicsFetch,
  type IncidentRecord,
} from '../../services/forensics/client.js';
import { runForensicsVerify } from '../forensics.js';
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

interface Served {
  files: Record<string, Buffer>;
  keys: { machineId: string; subscriptionId: string; publicKey: string }[];
  incidents?: IncidentRecord[];
}

const DEFAULT_SERVED: Served = {
  files: { 'audit/org-1/notes/k.json': Buffer.from('{}') },
  keys: [],
};

/** The raw manifest, or one raw file base64 in JSON, as the account server answers them. */
function rawAnswer(served: Served, path: string): unknown {
  if (path.includes('/raw/file?')) {
    const key = new URL(path, 'http://x').searchParams.get('key') ?? '';
    const bytes = served.files[key] ?? Buffer.alloc(0);
    return { key, bytes: bytes.length, data: bytes.toString('base64') };
  }
  return {
    files: Object.entries(served.files).map(([key, bytes]) => ({
      key,
      source: key.startsWith('audit/') ? 'audit' : 'forensics',
      day: '2026-11-24',
      bytes: bytes.length,
    })),
    bytes: Object.values(served.files).reduce((n, b) => n + b.length, 0),
    tooLarge: false,
    machineKeys: served.keys,
  };
}

function client(served: Served = DEFAULT_SERVED) {
  const calls: string[] = [];
  const incidents = served.incidents ?? INCIDENTS;
  const answer = (path: string): unknown => {
    if (path.endsWith('/incidents')) return { incidents };
    if (path.endsWith('/investigations')) return { id: 'inv-1' };
    if (path.includes('/timeline'))
      return { rows: [{ id: 'a', ts: NOW.toISOString(), kind: 'audit' }], unreadable: 1 };
    if (path.includes('/aggregates')) return { bytesOutPerMinute: [], topDestinations: [] };
    if (path.includes('/raw')) return rawAnswer(served, path);
    return {};
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

/** The files of a directory by their slash-separated relative path. */
function readTree(root: string, at = root): Record<string, Buffer> {
  const out: Record<string, Buffer> = {};
  for (const name of readdirSync(at)) {
    const full = join(at, name);
    if (statSync(full).isDirectory()) Object.assign(out, readTree(root, full));
    else out[relative(root, full).split(sep).join('/')] = readFileSync(full);
  }
  return out;
}

/** The evidence fixture as the account server would serve it, with its pinned machine key. */
async function servedFixture(): Promise<Served> {
  const source = mkdtempSync(join(tmpdir(), 'rdc-incident-source-'));
  try {
    const fixture = await writeFixture(source);
    return {
      files: readTree(source),
      keys: [{ machineId: MACHINE, subscriptionId: 'sub-1', publicKey: fixture.publicKeyHex }],
      // The fixture's evidence lies on 2026-11-01 and 2026-11-02.
      incidents: [
        record({ windowFrom: '2026-11-01T00:00:00.000Z', windowTo: '2026-11-02T23:59:59.000Z' }),
      ],
    };
  } finally {
    rmSync(source, { recursive: true, force: true });
  }
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
      raw: { files: 1, bytes: 2, tooLarge: false },
      verified: null,
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

  it('downloads the raw files under their keys and verifies both chains under the pinned key', async () => {
    const served = await servedFixture();
    m.format.current = 'json';
    const exporter = client(served).deps;
    await runIncidentExport('inc-aaaa1111', { out }, exporter);
    for (const [key, bytes] of Object.entries(served.files)) {
      expect(readFileSync(join(out, key)).equals(bytes)).toBe(true);
    }
    const [result] = m.print.mock.calls[0] ?? [];
    expect(result).toMatchObject({
      rawFiles: Object.keys(served.files).length,
      verification: { clean: true, heads: { batches: [{ machineId: MACHINE, seq: 2 }] } },
    });
    expect(JSON.parse(readFileSync(join(out, 'verification.json'), 'utf8')).clean).toBe(true);
    expect(JSON.parse(readFileSync(join(out, 'export.json'), 'utf8')).verified).toBe(true);
    expect(m.setExitCode).not.toHaveBeenCalled();

    // The export directory verifies again with no --machine-key: the server's pinned key for the
    // incident export.json names, read again, not the copy in raw-manifest.json.
    m.print.mockClear();
    const verifier = client(served);
    await runForensicsVerify({ dir: out }, { client: () => verifier.deps.client });
    expect(m.setExitCode).not.toHaveBeenCalled();
    expect(m.print.mock.calls[0]?.[0]).toMatchObject({ clean: true });
    expect(verifier.calls.some((c) => c.includes('/raw?'))).toBe(true);
  });

  it('fails the export when the key the server pinned does not sign the downloaded batches', async () => {
    const served = await servedFixture();
    served.keys = served.keys.map((k) => ({ ...k, publicKey: 'ab'.repeat(32) }));
    await runIncidentExport('inc-aaaa1111', { out }, client(served).deps);
    expect(m.setExitCode).toHaveBeenCalledWith(1);
    const warned = m.warn.mock.calls.map((c) => String(c[0])).join('\n');
    expect(warned).toContain('signature does not verify');
  });

  it('exits 1 and names the batch when a served section no longer matches its signed hash', async () => {
    const served = await servedFixture();
    const scratch = mkdtempSync(join(tmpdir(), 'rdc-incident-tamper-'));
    try {
      rewrite(
        scratch,
        repoKey('2026-11-02'),
        `${JSON.stringify({ seq: 1, section: Buffer.from('tampered').toString('base64') })}\n`
      );
      served.files[repoKey('2026-11-02')] = readFileSync(join(scratch, repoKey('2026-11-02')));
    } finally {
      rmSync(scratch, { recursive: true, force: true });
    }
    await runIncidentExport('inc-aaaa1111', { out }, client(served).deps);
    expect(m.setExitCode).toHaveBeenCalledWith(1);
    const warned = m.warn.mock.calls.map((c) => String(c[0])).join('\n');
    expect(warned).toContain(`${MACHINE}#1`);
    expect(warned).toContain('incident.rawNotVerified');
  });

  it('refuses a manifest key that would leave the export directory and writes no raw file', async () => {
    const served: Served = {
      files: {
        [auditKey('2026-11-01')]: Buffer.from('x'),
        '../escape.ndjson.gz': Buffer.from('x'),
      },
      keys: [],
    };
    await expect(runIncidentExport('inc-aaaa1111', { out }, client(served).deps)).rejects.toThrow(
      'forensics.badEvidenceKey'
    );
    expect(existsSync(join(out, auditKey('2026-11-01')))).toBe(false);
    expect(existsSync(join(out, '..', 'escape.ndjson.gz'))).toBe(false);
  });

  it('refuses a raw file whose decoded bytes fall short of the length the server stated', async () => {
    const short = new ForensicsClient(((path: string) =>
      Promise.resolve(
        path.includes('/raw/file?')
          ? { key: 'k', bytes: 10, data: Buffer.from('abc').toString('base64') }
          : {}
      )) as unknown as ForensicsFetch);
    await expect(
      short.rawFile('inv-1', { from: NOW.toISOString(), to: NOW.toISOString() }, 'k')
    ).rejects.toMatchObject({ code: 'SERVER_ERROR', message: /forensics.rawFileTruncated/ });
  });
});
