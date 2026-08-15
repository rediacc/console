/**
 * `rdc backup restore --at` point-in-time RESOLUTION.
 *
 * WHY THIS FILE EXISTS. `resolveSnapshotAt` decides WHICH point in time gets
 * restored, and it had zero test references anywhere in the repo — the final
 * testing-surface audit found that and it was right. The failure mode is the
 * nastiest kind: a boundary error restores the WRONG snapshot and the restore
 * SUCCEEDS, so nothing surfaces the mistake. The operator gets a healthy repo
 * containing data from the wrong moment, and learns about it whenever they
 * next compare it against reality.
 *
 * The only other coverage is e2e suite 26's RESTORE tier, which needs a
 * two-worker fleet and a real bucket and therefore never runs in CI.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key} ${JSON.stringify(params)}` : key,
}));

const mockAccountServerFetch = vi.hoisted(() => vi.fn());
vi.mock('../../services/account/account-client.js', () => ({
  accountServerFetch: mockAccountServerFetch,
}));

vi.mock('../../services/core/output.js', () => ({
  outputService: { info: vi.fn(), success: vi.fn(), warn: vi.fn(), error: vi.fn(), print: vi.fn() },
}));

const LINEAGE = 'f6545d49-c46e-4c14-8006-0ad5b37f3e08';

/** One index row; only the two fields the resolver reads are meaningful. */
const manifest = (snapshotId: string, createdAt: string) => ({
  snapshotId,
  lineageGuid: LINEAGE,
  streamId: 's',
  cellSizeBytes: 1,
  totalBytes: 1,
  addedBytes: 0,
  addedChunkCount: 0,
  createdAt,
});

afterEach(() => {
  mockAccountServerFetch.mockReset();
});

describe('resolveSnapshotAt', () => {
  it('passes a snapshot id through without consulting the server', async () => {
    const { resolveSnapshotAt } = await import('../backup.js');
    const id = '20260814T120000Z-0011223344556677';
    await expect(resolveSnapshotAt(LINEAGE, id)).resolves.toBe(id);
    // THE DEFECT: treating a snapshot id as a time. It would parse as NaN and
    // refuse, or worse, round-trip through Date and select something else.
    expect(mockAccountServerFetch).not.toHaveBeenCalled();
  });

  it('picks the NEWEST snapshot at or before the requested time', async () => {
    mockAccountServerFetch.mockResolvedValue({
      manifests: [
        manifest('snap-old', '2026-08-14T09:00:00.000Z'),
        manifest('snap-mid', '2026-08-14T11:00:00.000Z'),
        manifest('snap-new', '2026-08-14T13:00:00.000Z'),
      ],
    });
    const { resolveSnapshotAt } = await import('../backup.js');
    // THE DEFECT: picking the OLDEST match, or the newest overall. Both restore
    // a real snapshot and exit zero, so neither looks like a failure.
    await expect(resolveSnapshotAt(LINEAGE, '2026-08-14T12:00:00Z')).resolves.toBe('snap-mid');
  });

  it('treats an EXACTLY equal timestamp as eligible', async () => {
    mockAccountServerFetch.mockResolvedValue({
      manifests: [
        manifest('snap-a', '2026-08-14T09:00:00.000Z'),
        manifest('snap-exact', '2026-08-14T12:00:00.000Z'),
      ],
    });
    const { resolveSnapshotAt } = await import('../backup.js');
    // THE DEFECT: a strict `<` instead of `<=`. "Restore to 12:00" would then
    // skip the snapshot taken AT 12:00 and silently return the earlier one.
    await expect(resolveSnapshotAt(LINEAGE, '2026-08-14T12:00:00Z')).resolves.toBe('snap-exact');
  });

  it('reads createdAt, NOT the timestamp embedded in the snapshot id', async () => {
    // Snapshot ids are time-sortable, so sorting by id looks correct and is
    // wrong: the id records when it was MINTED and the manifest commits when
    // the upload FINISHES. On a long upload the two disagree, and a resolver
    // that trusts the id restores a different point in time than the operator
    // asked for. Here the id order and the createdAt order are DELIBERATELY
    // opposite, so only a createdAt-based resolver can pass.
    mockAccountServerFetch.mockResolvedValue({
      manifests: [
        manifest('20260814T080000Z-aaaaaaaaaaaaaaaa', '2026-08-14T11:30:00.000Z'),
        manifest('20260814T100000Z-bbbbbbbbbbbbbbbb', '2026-08-14T09:00:00.000Z'),
      ],
    });
    const { resolveSnapshotAt } = await import('../backup.js');
    await expect(resolveSnapshotAt(LINEAGE, '2026-08-14T12:00:00Z')).resolves.toBe(
      '20260814T080000Z-aaaaaaaaaaaaaaaa'
    );
  });

  it('refuses a time BEFORE every snapshot rather than restoring the oldest', async () => {
    mockAccountServerFetch.mockResolvedValue({
      manifests: [manifest('snap-a', '2026-08-14T09:00:00.000Z')],
    });
    const { resolveSnapshotAt } = await import('../backup.js');
    // THE DEFECT: falling back to the oldest snapshot. That restores data the
    // operator did not ask for, successfully.
    await expect(resolveSnapshotAt(LINEAGE, '2026-08-13T00:00:00Z')).rejects.toThrow();
  });

  it('refuses a value that is neither a snapshot id nor a time', async () => {
    const { resolveSnapshotAt } = await import('../backup.js');
    await expect(resolveSnapshotAt(LINEAGE, 'yesterdayish')).rejects.toThrow();
    expect(mockAccountServerFetch).not.toHaveBeenCalled();
  });

  it('scopes the index query to the lineage', async () => {
    mockAccountServerFetch.mockResolvedValue({
      manifests: [manifest('snap-a', '2026-08-14T09:00:00.000Z')],
    });
    const { resolveSnapshotAt } = await import('../backup.js');
    await resolveSnapshotAt(LINEAGE, '2026-08-14T12:00:00Z');
    // THE DEFECT: an unscoped query, which would let ANOTHER repository's
    // snapshot win the "newest at or before" race and be restored over this one.
    expect(String(mockAccountServerFetch.mock.calls[0][0])).toContain(
      `lineage=${encodeURIComponent(LINEAGE)}`
    );
  });
});
