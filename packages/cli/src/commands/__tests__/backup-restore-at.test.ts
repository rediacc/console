/**
 * `rdc backup restore --at` point-in-time RESOLUTION.
 *
 * WHY THIS FILE EXISTS. `resolveSnapshotAt` decides WHICH point in time gets
 * restored, and it had zero test references anywhere in the repo, the final
 * testing-surface audit found that and it was right. The failure mode is the
 * nastiest kind: a boundary error restores the WRONG snapshot and the restore
 * SUCCEEDS, so nothing surfaces the mistake. The operator gets a healthy repo
 * containing data from the wrong moment, and learns about it whenever they
 * next compare it against reality.
 *
 * The only other coverage is e2e suite 26's RESTORE tier, which needs a
 * two-worker fleet and a real bucket and therefore never runs in CI.
 */

import { readFileSync } from 'node:fs';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key} ${JSON.stringify(params)}` : key,
}));

const mockAccountServerFetch = vi.hoisted(() => vi.fn());
// These verbs read the hosted backup plane, which needs a login (PLAN-free-license R13); a logged-in operator is the case under test.
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

vi.mock('../../services/core/output.js', () => ({
  outputService: { info: vi.fn(), success: vi.fn(), warn: vi.fn(), error: vi.fn(), print: vi.fn() },
}));

const ALL = { anyStream: true } as const;
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
    await expect(resolveSnapshotAt(LINEAGE, id, ALL)).resolves.toBe(id);
    // THE DEFECT: treating a snapshot id as a time. It would parse as NaN and refuse, or worse, round-trip through Date and select something else.
    expect(mockAccountServerFetch).not.toHaveBeenCalled();
  });

  it('sends the time as an ISO instant, so "at or before" is decided by the server on createdAt', async () => {
    mockAccountServerFetch.mockResolvedValue(manifest('snap-mid', '2026-08-14T11:00:00.000Z'));
    const { resolveSnapshotAt } = await import('../backup.js');
    // The newest-at-or-before search, its equal-timestamp case and its createdAt-not-id ordering are the server's query now (resolveSnapshot in the account service); this side owns the request.
    await expect(resolveSnapshotAt(LINEAGE, '2026-08-14T12:00:00Z', ALL)).resolves.toBe('snap-mid');
    const url = new URL(String(mockAccountServerFetch.mock.calls[0][0]), 'https://x');
    expect(url.searchParams.get('at')).toBe('2026-08-14T12:00:00.000Z');
  });

  it('refuses a time BEFORE every snapshot rather than restoring the oldest', async () => {
    mockAccountServerFetch.mockRejectedValue(Object.assign(new Error('none'), { status: 404 }));
    const { resolveSnapshotAt } = await import('../backup.js');
    // THE DEFECT: falling back to the oldest snapshot. That restores data the operator did not ask for, successfully.
    await expect(resolveSnapshotAt(LINEAGE, '2026-08-13T00:00:00Z', ALL)).rejects.toThrow(
      /commands.backup.restore.atNoSnapshot/
    );
  });

  it('refuses a value that is neither a snapshot id nor a time', async () => {
    const { resolveSnapshotAt } = await import('../backup.js');
    await expect(resolveSnapshotAt(LINEAGE, 'yesterdayish', ALL)).rejects.toThrow();
    expect(mockAccountServerFetch).not.toHaveBeenCalled();
  });

  it('scopes the query to the lineage', async () => {
    mockAccountServerFetch.mockResolvedValue(manifest('snap-a', '2026-08-14T09:00:00.000Z'));
    const { resolveSnapshotAt } = await import('../backup.js');
    await resolveSnapshotAt(LINEAGE, '2026-08-14T12:00:00Z', ALL);
    // THE DEFECT: an unscoped query, which would let ANOTHER repository's snapshot win the "newest at or before" race and be restored over this one.
    expect(String(mockAccountServerFetch.mock.calls[0][0])).toContain(
      `lineage=${encodeURIComponent(LINEAGE)}`
    );
  });
});

describe('resolveSnapshotAt stream scope', () => {
  it('by default names the stream by the source machine anchor, never by a bare time', async () => {
    mockAccountServerFetch.mockResolvedValue(manifest('a-anchor', '2026-08-14T10:00:00.000Z'));
    const { resolveSnapshotAt } = await import('../backup.js');
    await expect(
      resolveSnapshotAt(LINEAGE, '2026-08-14T12:00:00Z', {
        anyStream: false,
        anchorSnapshotId: 'a-anchor',
      })
    ).resolves.toBe('a-anchor');
    const url = new URL(String(mockAccountServerFetch.mock.calls[0][0]), 'https://x');
    expect(url.searchParams.get('anchorSnapshotId')).toBe('a-anchor');
    expect(url.searchParams.get('anyStream')).toBeNull();
  });

  it('--any-stream widens the choice to every stream of the lineage', async () => {
    mockAccountServerFetch.mockResolvedValue(manifest('b-newer', '2026-08-14T11:00:00.000Z'));
    const { resolveSnapshotAt } = await import('../backup.js');
    await expect(resolveSnapshotAt(LINEAGE, '2026-08-14T12:00:00Z', ALL)).resolves.toBe('b-newer');
    const url = new URL(String(mockAccountServerFetch.mock.calls[0][0]), 'https://x');
    expect(url.searchParams.get('anyStream')).toBe('1');
  });

  it('refuses rather than guessing when the source machine reports no anchor', async () => {
    const { resolveSnapshotAt } = await import('../backup.js');
    await expect(
      resolveSnapshotAt(LINEAGE, '2026-08-14T12:00:00Z', {
        anyStream: false,
        anchorSnapshotId: undefined,
      })
    ).rejects.toThrow(/commands.backup.restore.streamUnknown/);
    expect(mockAccountServerFetch).not.toHaveBeenCalled();
  });

  it('the refusal text in the English catalog points the user at --any-stream', () => {
    // The mocked t() above echoes the key, so the guidance itself is read from the real catalog.
    const cli = JSON.parse(
      readFileSync(new URL('../../i18n/locales/en/cli.json', import.meta.url), 'utf8')
    ) as { commands: { backup: { restore: { streamUnknown: string } } } };
    expect(cli.commands.backup.restore.streamUnknown).toContain('--any-stream');
  });
});
