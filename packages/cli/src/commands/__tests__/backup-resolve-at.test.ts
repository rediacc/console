/**
 * `--at` resolution through GET /backups/snapshots/resolve (D-listing, F11).
 *
 * The manifest listing is capped at 500 rows a lineage page, so a resolver that filters the
 * listing client-side loses every snapshot older than the cap and answers `streamUnknown` for an
 * anchor that is simply old. The server answers one row through an indexed query instead. These
 * tests serve the resolve route and a deliberately useless 500-row listing, so only a caller that
 * uses the route can pass.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key} ${JSON.stringify(params)}` : key,
}));

const mockAccountServerFetch = vi.hoisted(() => vi.fn());
vi.mock('../../services/account/subscription-auth.js', () => ({
  getSubscriptionTokenState: () => ({
    kind: 'ready',
    token: { token: 't' },
    serverUrl: 'https://acct.example',
  }),
  getSubscriptionServerUrl: () => 'https://acct.example',
}));
vi.mock('../../services/account/account-client.js', () => ({
  accountServerFetch: mockAccountServerFetch,
}));

const mockInfo = vi.hoisted(() => vi.fn());
const mockWarn = vi.hoisted(() => vi.fn());
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: mockInfo,
    success: vi.fn(),
    warn: mockWarn,
    error: vi.fn(),
    print: vi.fn(),
  },
}));

const LINEAGE = 'f6545d49-c46e-4c14-8006-0ad5b37f3e08';
const RESOLVE = '/account/api/v1/backups/snapshots/resolve';
const ANCHOR = '20260101T000000Z-aaaaaaaaaaaaaaaa';

const row = (snapshotId: string, createdAt: string, hasIndex = true) => ({
  snapshotId,
  lineageGuid: LINEAGE,
  streamId: 's1',
  cellSizeBytes: 1,
  totalBytes: 1,
  addedBytes: 0,
  addedChunkCount: 0,
  hasIndex,
  createdAt,
});

/** A 404 as accountServerFetch raises it. */
const notFound = () =>
  Object.assign(new Error('No snapshot matches in this lineage'), { status: 404 });

/** The 500 newest rows of a long history: none of them is the snapshot being asked for. */
const cappedListing = () => ({
  manifests: Array.from({ length: 500 }, (_, i) =>
    row(
      `20260301T0000${String(i % 60).padStart(2, '0')}Z-${String(i).padStart(16, '0')}`,
      '2026-03-01T00:00:00.000Z'
    )
  ),
  nextBefore: 'x~y',
});

const queryOf = (path: string): URLSearchParams => new URL(path, 'https://x').searchParams;
const resolveCalls = (): string[] =>
  mockAccountServerFetch.mock.calls.map((c) => String(c[0])).filter((p) => p.startsWith(RESOLVE));

afterEach(() => {
  mockAccountServerFetch.mockReset();
  mockInfo.mockReset();
  mockWarn.mockReset();
});

describe('resolveSnapshotAt through the resolve route', () => {
  it('resolves a time older than the 500-row page, naming the stream by its anchor', async () => {
    mockAccountServerFetch.mockImplementation((path: string) =>
      path.startsWith(RESOLVE)
        ? Promise.resolve(row('old-snap', '2026-01-02T00:00:00.000Z'))
        : Promise.resolve(cappedListing())
    );
    const { resolveSnapshotAt } = await import('../backup.js');
    // THE DEFECT: with the anchor older than the page, the listing holds no anchor row and the resolver refuses with streamUnknown.
    await expect(
      resolveSnapshotAt(LINEAGE, '2026-01-02T12:00:00Z', {
        anyStream: false,
        anchorSnapshotId: ANCHOR,
      })
    ).resolves.toBe('old-snap');
    const [call] = resolveCalls();
    const q = queryOf(call);
    expect(q.get('lineage')).toBe(LINEAGE);
    expect(q.get('anchorSnapshotId')).toBe(ANCHOR);
    expect(q.get('at')).toBe('2026-01-02T12:00:00.000Z');
    expect(q.get('anyStream')).toBeNull();
  });

  it('--any-stream sends anyStream=1 and no anchor', async () => {
    mockAccountServerFetch.mockResolvedValue(row('snap-any', '2026-01-02T00:00:00.000Z'));
    const { resolveSnapshotAt } = await import('../backup.js');
    await expect(
      resolveSnapshotAt(LINEAGE, '2026-01-02T12:00:00Z', { anyStream: true })
    ).resolves.toBe('snap-any');
    const q = queryOf(resolveCalls()[0]);
    expect(q.get('anyStream')).toBe('1');
    expect(q.get('anchorSnapshotId')).toBeNull();
  });

  it('refuses without a call when the source machine reports no anchor', async () => {
    const { resolveSnapshotAt } = await import('../backup.js');
    await expect(
      resolveSnapshotAt(LINEAGE, '2026-01-02T12:00:00Z', {
        anyStream: false,
        anchorSnapshotId: undefined,
      })
    ).rejects.toThrow(/commands.backup.restore.streamUnknown/);
    expect(mockAccountServerFetch).not.toHaveBeenCalled();
  });

  it('a 404 for a time with an anchor that exists says no snapshot, not streamUnknown', async () => {
    mockAccountServerFetch.mockImplementation((path: string) => {
      const q = queryOf(path);
      // The anchor alone resolves; the anchor at the time does not.
      return q.has('at')
        ? Promise.reject(notFound())
        : Promise.resolve(row(ANCHOR, '2026-01-01T00:00:00.000Z'));
    });
    const { resolveSnapshotAt } = await import('../backup.js');
    await expect(
      resolveSnapshotAt(LINEAGE, '2025-12-01T00:00:00Z', {
        anyStream: false,
        anchorSnapshotId: ANCHOR,
      })
    ).rejects.toThrow(/commands.backup.restore.atNoSnapshot/);
  });

  it('a 404 for an anchor the index does not hold says streamUnknown', async () => {
    mockAccountServerFetch.mockRejectedValue(notFound());
    const { resolveSnapshotAt } = await import('../backup.js');
    await expect(
      resolveSnapshotAt(LINEAGE, '2026-01-02T12:00:00Z', {
        anyStream: false,
        anchorSnapshotId: ANCHOR,
      })
    ).rejects.toThrow(/commands.backup.restore.streamUnknown/);
  });

  it('an error that is not a 404 is not turned into "no snapshot"', async () => {
    mockAccountServerFetch.mockRejectedValue(Object.assign(new Error('boom'), { status: 500 }));
    const { resolveSnapshotAt } = await import('../backup.js');
    await expect(
      resolveSnapshotAt(LINEAGE, '2026-01-02T12:00:00Z', { anyStream: true })
    ).rejects.toThrow('boom');
  });
});

describe('resolveSnapshotAt for a listing (browse, restore --path)', () => {
  it('keeps the exact snapshot when it has an index', async () => {
    mockAccountServerFetch.mockResolvedValue(row('snap-a', '2026-01-02T00:00:00.000Z', true));
    const { resolveSnapshotAt } = await import('../backup.js');
    await expect(
      resolveSnapshotAt(LINEAGE, '2026-01-02T12:00:00Z', { anyStream: true }, { indexed: true })
    ).resolves.toBe('snap-a');
    expect(resolveCalls()).toHaveLength(1);
    expect(mockWarn).not.toHaveBeenCalled();
  });

  it('falls back to the nearest indexed snapshot and states the time gap', async () => {
    mockAccountServerFetch.mockImplementation((path: string) =>
      Promise.resolve(
        queryOf(path).get('needIndex') === '1'
          ? row('snap-indexed', '2026-01-02T09:00:00.000Z', true)
          : row('snap-bare', '2026-01-02T11:30:00.000Z', false)
      )
    );
    const { resolveSnapshotAt } = await import('../backup.js');
    await expect(
      resolveSnapshotAt(LINEAGE, '2026-01-02T12:00:00Z', { anyStream: true }, { indexed: true })
    ).resolves.toBe('snap-indexed');
    const warned = mockWarn.mock.calls.map((c) => String(c[0])).join('\n');
    expect(warned).toContain('commands.backup.restore.atIndexGap');
    // 11:30 to 09:00 is 2 h 30 min.
    expect(warned).toContain('2h 30m');
  });

  it('keeps the unindexed snapshot when no indexed one exists, so the verb reports it', async () => {
    mockAccountServerFetch.mockImplementation((path: string) =>
      queryOf(path).get('needIndex') === '1'
        ? Promise.reject(notFound())
        : Promise.resolve(row('snap-bare', '2026-01-02T11:30:00.000Z', false))
    );
    const { resolveSnapshotAt } = await import('../backup.js');
    await expect(
      resolveSnapshotAt(LINEAGE, '2026-01-02T12:00:00Z', { anyStream: true }, { indexed: true })
    ).resolves.toBe('snap-bare');
  });
});

describe('the other callers of the listing (F11)', () => {
  it('resolveRestoreSizeGb reads the snapshot by id, not out of a page', async () => {
    mockAccountServerFetch.mockImplementation((path: string) =>
      path.startsWith(RESOLVE)
        ? Promise.resolve({
            ...row('old-snap', '2026-01-02T00:00:00.000Z'),
            totalBytes: 5 * 1024 ** 3,
          })
        : Promise.resolve(cappedListing())
    );
    const { resolveRestoreSizeGb } = await import(
      '../../services/executor/repo-license-context.js'
    );
    // THE DEFECT: an id older than the page is not in it, so the licence is requested at the floor and caps the restored repository for life.
    await expect(resolveRestoreSizeGb(LINEAGE, 'old-snap')).resolves.toBe(5);
    expect(queryOf(resolveCalls()[0]).get('anchorSnapshotId')).toBe('old-snap');
  });
});
