/**
 * `rdc backup status` prints one row per destination store (multi-target S1).
 *
 * A unit runs every destination of its strategy in turn, so its last run and outcome are the unit's; the store, its
 * newest snapshot, its last verify and its clean-up state are the destination's. A row without a store is `home`, and
 * a store without a clean-up state is `enabled`.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockPrint = vi.hoisted(() => vi.fn());
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: vi.fn(),
    success: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    print: mockPrint,
  },
}));
vi.mock('../../utils/errors.js', async () => {
  const actual =
    await vi.importActual<typeof import('../../utils/errors.js')>('../../utils/errors.js');
  return { ...actual, getOutputFormat: () => 'json' };
});

const { renderBackupScheduleStatus } = await import('../../services/backup/backup-schedule.js');
const { expandStatusRows, summarizeStatus } = await import(
  '../../services/backup/backup-store-pick.js'
);

const UNIT = { unitName: 'nightly', strategyName: 'nightly', schedule: '0 3 * * *' };
/** `systemctl show` for a loaded, active timer whose service last ran fine. */
const SHOW = [
  'Id=rediacc-backup-nightly.timer',
  'LoadState=loaded',
  'ActiveState=active',
  'NextElapseUSecRealtime=Sat 2999-01-02 03:00:00 UTC',
  'LastTriggerUSec=Sat 2999-01-01 03:00:00 UTC',
  '',
  'Id=rediacc-backup-nightly.service',
  'LoadState=loaded',
  'Result=success',
  'ExecMainExitTimestamp=Sat 2999-01-01 03:01:00 UTC',
].join('\n');

const stream = (
  storeId: string | undefined,
  extra: Partial<{
    lineageGuid: string;
    lastRunAt: string | null;
    lastRunStatus: string | null;
    newestSnapshotAt: string | null;
    lastVerifyStatus: string | null;
  }> = {}
) => ({
  ...(storeId === undefined ? {} : { storeId }),
  lineageGuid: 'L1',
  lastRunAt: '2026-11-07T01:00:00Z',
  lastRunStatus: 'ok',
  newestSnapshotAt: '2026-11-07T01:00:00Z',
  lastVerifyStatus: 'verified',
  ...extra,
});

/** A status row the way expandStatusRows reads a store. */
const known = (extra: Record<string, unknown> = {}) => ({
  lastRunAt: null,
  lastRunStatus: null,
  newestSnapshotAt: '2026-11-07T01:00:00Z',
  verify: 'ok' as const,
  cleanup: 'enabled',
  ...extra,
});

beforeEach(() => {
  mockPrint.mockClear();
});

describe('summarizeStatus', () => {
  it('sums a store over streams: latest run, newest snapshot, a failed verify wins, clean-up state', () => {
    const stores = summarizeStatus(
      {
        stores: [{ storeId: 'eu-west', cleanup: 'disabled -- delete refused by the store' }],
        streams: [
          stream(undefined),
          stream('eu-west'),
          stream('home', {
            lastRunAt: '2026-11-08T00:00:00Z',
            lastRunStatus: 'failed',
            newestSnapshotAt: '2026-11-08T00:00:00Z',
            lastVerifyStatus: 'failed',
          }),
          stream('eu-west', { lastVerifyStatus: null, lineageGuid: 'L-other' }),
        ],
      },
      new Set(['L1'])
    );
    // A stream without storeId is home.
    expect(stores.home).toEqual({
      lastRunAt: '2026-11-08T00:00:00Z',
      lastRunStatus: 'failed',
      newestSnapshotAt: '2026-11-08T00:00:00Z',
      verify: 'failed',
      cleanup: 'enabled',
    });
    expect(stores['eu-west']).toEqual({
      lastRunAt: '2026-11-07T01:00:00Z',
      lastRunStatus: 'ok',
      newestSnapshotAt: '2026-11-07T01:00:00Z',
      verify: 'ok',
      cleanup: 'disabled -- delete refused by the store',
    });
  });

  it('ignores streams of lineages the machine does not hold', () => {
    expect(
      summarizeStatus({ streams: [stream('home', { lineageGuid: 'X' })] }, new Set(['L1']))
    ).toEqual({});
  });
});

describe('expandStatusRows', () => {
  const rows = [{ strategy: 'nightly', unit: 'nightly', status: 'scheduled', result: 'success' }];

  it('gives a strategy with no destinations and no data one home row', () => {
    expect(expandStatusRows(rows)).toEqual([
      {
        strategy: 'nightly',
        unit: 'nightly',
        store: 'home',
        status: 'scheduled',
        result: 'success',
        newestSnapshot: '-',
        verify: '-',
        cleanup: 'enabled',
      },
    ]);
  });

  it('gives one row per destination store, each with its own store data', () => {
    const out = expandStatusRows(rows, {
      byStrategy: { nightly: ['home', 'eu-west'] },
      stores: {
        home: known(),
        'eu-west': known({
          newestSnapshotAt: null,
          verify: 'failed',
          cleanup: 'disabled -- x',
          lastRunAt: '2026-11-06T00:00:00Z',
          lastRunStatus: 'failed',
        }),
      },
    });
    expect(out.map((r) => [r.store, r.newestSnapshot, r.verify, r.cleanup])).toEqual([
      ['home', '2026-11-07T01:00:00Z', 'ok', 'enabled'],
      ['eu-west', '-', 'failed', 'disabled -- x'],
    ]);
    expect(out.every((r) => r.status === 'scheduled')).toBe(true);
    // A store the account has a run for says its own outcome; one with none keeps the unit's.
    expect(out.map((r) => r.result)).toEqual(['success', 'failed']);
  });
});

describe('renderBackupScheduleStatus', () => {
  it('prints one row per destination store with the unit columns kept', () => {
    renderBackupScheduleStatus('m1', [UNIT], SHOW, {
      byStrategy: { nightly: ['home', 'offsite'] },
      stores: {
        home: known(),
      },
    });
    const printed = mockPrint.mock.calls[0][0] as Record<string, string>[];
    expect(printed.map((r) => r.store)).toEqual(['home', 'offsite']);
    expect(printed[0]).toMatchObject({
      strategy: 'nightly',
      unit: 'nightly',
      status: 'scheduled',
      result: 'success',
      newestSnapshot: '2026-11-07T01:00:00Z',
      verify: 'ok',
      cleanup: 'enabled',
    });
    expect(printed[1]).toMatchObject({ store: 'offsite', newestSnapshot: '-', verify: '-' });
  });

  it('keeps one home row, plus the store column, when no target data came with the plan', () => {
    renderBackupScheduleStatus('m1', [UNIT], SHOW);
    const printed = mockPrint.mock.calls[0][0] as Record<string, string>[];
    expect(printed).toHaveLength(1);
    expect(printed[0]).toMatchObject({ store: 'home', unit: 'nightly', result: 'success' });
  });
});
