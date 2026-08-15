import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { RdcConfig } from '@rediacc/shared/config-schema';

const mockUpdateState = vi.hoisted(() => vi.fn());
vi.mock('../../adapters/config-file-storage.js', () => ({
  configFileStorage: { updateState: mockUpdateState },
}));

const mockGetEffectiveConfigName = vi.hoisted(() => vi.fn(() => 'rediacc'));
vi.mock('../config/config-resources.js', () => ({
  configService: { getEffectiveConfigName: mockGetEffectiveConfigName },
}));

const { recordBackupRun } = await import('../backup/backup-runs-state.js');

beforeEach(() => {
  vi.clearAllMocks();
});

describe('recordBackupRun', () => {
  it('writes a per-repo record into state.backupRuns via updateState', async () => {
    let written: RdcConfig | undefined;
    mockUpdateState.mockImplementation((_name: string, fn: (c: RdcConfig) => RdcConfig) => {
      written = fn({ schemaVersion: 3, id: 'x', version: 1 });
    });

    await recordBackupRun('shop', { kind: 'verify', status: 'verified', lastRunAt: 'T0' });

    expect(mockGetEffectiveConfigName).toHaveBeenCalled();
    expect(written?.state?.backupRuns?.shop).toEqual({
      kind: 'verify',
      status: 'verified',
      lastRunAt: 'T0',
    });
  });

  it('preserves other repos already recorded', async () => {
    let written: RdcConfig | undefined;
    mockUpdateState.mockImplementation((_name: string, fn: (c: RdcConfig) => RdcConfig) => {
      written = fn({
        schemaVersion: 3,
        id: 'x',
        version: 1,
        // 'backup' is the retired rclone kind on purpose: a record written
        // before the cutover must survive a post-cutover write untouched.
        state: { backupRuns: { other: { kind: 'backup', status: 'ok', lastRunAt: 'T-1' } } },
      });
    });

    await recordBackupRun('shop', { kind: 'restore', status: 'ok', lastRunAt: 'T0' });

    expect(Object.keys(written?.state?.backupRuns ?? {}).sort()).toEqual(['other', 'shop']);
  });

  it('is best-effort: a storage failure never throws', async () => {
    mockUpdateState.mockRejectedValue(new Error('disk full'));
    await expect(
      recordBackupRun('shop', { kind: 'backup', status: 'ok' })
    ).resolves.toBeUndefined();
  });
});
