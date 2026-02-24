import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { CliUpdateState } from '@rediacc/shared/update';
import {
  applyPendingUpdate,
  maybeSpawnBackgroundUpdate,
  runBackgroundUpdateWorker,
} from '../background-updater.js';

// ============================================================================
// Hoisted mocks (vi.hoisted + vi.mock are hoisted by vitest's transform)
// ============================================================================

const mockFs = vi.hoisted(() => ({
  access: vi.fn().mockResolvedValue(undefined),
  chmod: vi.fn().mockResolvedValue(undefined),
  copyFile: vi.fn().mockResolvedValue(undefined),
  mkdir: vi.fn().mockResolvedValue(undefined),
  readFile: vi.fn(),
  rename: vi.fn().mockResolvedValue(undefined),
  unlink: vi.fn().mockResolvedValue(undefined),
  writeFile: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('node:fs', () => ({
  promises: mockFs,
}));

const mockSpawn = vi.hoisted(() => vi.fn());
const mockSpawnSync = vi.hoisted(() => vi.fn());
vi.mock('node:child_process', () => ({
  spawn: mockSpawn,
  spawnSync: mockSpawnSync,
}));

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, string>) => {
    if (params) {
      let result = key;
      for (const [k, v] of Object.entries(params)) {
        result += ` ${k}=${v}`;
      }
      return result;
    }
    return key;
  },
}));

vi.mock('../../version.js', () => ({
  VERSION: '0.4.42',
}));

const mockReleaseLock = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));

const mockPlatform = vi.hoisted(() => ({
  isSEA: vi.fn().mockReturnValue(true),
  isUpdateDisabled: vi.fn().mockReturnValue(false),
  getPlatformKey: vi.fn().mockReturnValue('linux-x64'),
  acquireUpdateLock: vi.fn().mockResolvedValue(mockReleaseLock),
  cleanupOldBinary: vi.fn().mockResolvedValue(undefined),
  getOldBinaryPath: vi.fn().mockReturnValue('/usr/local/bin/rdc.old'),
  STAGED_UPDATE_DIR: '/home/testuser/.cache/rediacc/staged-update',
  UPDATE_STATE_FILE: '/home/testuser/.local/state/rediacc/update-state.json',
}));

vi.mock('../../utils/platform.js', () => mockPlatform);

const mockSharedUpdate = vi.hoisted(() => ({
  isCooldownExpired: vi.fn().mockReturnValue(true),
}));

vi.mock('@rediacc/shared/update', () => mockSharedUpdate);

const mockUpdateState = vi.hoisted(() => ({
  readUpdateState: vi.fn(),
  writeUpdateState: vi.fn().mockResolvedValue(undefined),
  getStagedBinaryPath: vi.fn().mockReturnValue('/home/testuser/.cache/rediacc/staged-update/rdc-0.5.0'),
  cleanupStaleStagedFiles: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('../update-state.js', () => mockUpdateState);

const mockUpdater = vi.hoisted(() => ({
  fetchManifest: vi.fn(),
  compareVersions: vi.fn(),
  computeSha256: vi.fn(),
  downloadFile: vi.fn().mockResolvedValue(undefined),
  checkForUpdate: vi.fn(),
  performUpdate: vi.fn(),
}));

vi.mock('../updater.js', () => mockUpdater);

const mockTelemetry = vi.hoisted(() => ({
  telemetryService: {
    trackEvent: vi.fn(),
  },
}));

vi.mock('../telemetry.js', () => mockTelemetry);

function makeState(overrides: Partial<CliUpdateState> = {}): CliUpdateState {
  return {
    schemaVersion: 1,
    lastCheckAt: null,
    lastAttemptAt: null,
    pendingUpdate: null,
    consecutiveFailures: 0,
    lastError: null,
    ...overrides,
  };
}

describe('services/background-updater', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    // Reset platform mocks
    mockPlatform.isSEA.mockReturnValue(true);
    mockPlatform.isUpdateDisabled.mockReturnValue(false);
    mockPlatform.getPlatformKey.mockReturnValue('linux-x64');
    mockReleaseLock.mockResolvedValue(undefined);
    mockPlatform.acquireUpdateLock.mockResolvedValue(mockReleaseLock);
    mockPlatform.cleanupOldBinary.mockResolvedValue(undefined);
    mockPlatform.getOldBinaryPath.mockReturnValue('/usr/local/bin/rdc.old');

    // Reset update-state mocks
    mockUpdateState.readUpdateState.mockResolvedValue(makeState());
    mockUpdateState.writeUpdateState.mockResolvedValue(undefined);
    mockSharedUpdate.isCooldownExpired.mockReturnValue(true);
    mockUpdateState.getStagedBinaryPath.mockReturnValue(
      '/home/testuser/.cache/rediacc/staged-update/rdc-0.5.0'
    );
    mockUpdateState.cleanupStaleStagedFiles.mockResolvedValue(undefined);

    // Reset updater mocks
    mockUpdater.downloadFile.mockResolvedValue(undefined);
    mockUpdater.compareVersions.mockReturnValue(0);
    mockUpdater.computeSha256.mockResolvedValue('');

    // Reset fs mocks
    mockFs.access.mockResolvedValue(undefined);
    mockFs.chmod.mockResolvedValue(undefined);
    mockFs.copyFile.mockResolvedValue(undefined);
    mockFs.mkdir.mockResolvedValue(undefined);
    mockFs.rename.mockResolvedValue(undefined);
    mockFs.unlink.mockResolvedValue(undefined);

    // Default: warmup passes
    mockSpawnSync.mockReturnValue({ status: 0 });

    Object.defineProperty(process, 'execPath', { value: '/usr/local/bin/rdc', writable: true });
    Object.defineProperty(process, 'platform', { value: 'linux', writable: true });
  });

  // ==========================================================================
  // A. runBackgroundUpdateWorker()
  // ==========================================================================

  describe('runBackgroundUpdateWorker()', () => {
    it('exits early when lock is held', async () => {
      mockPlatform.acquireUpdateLock.mockResolvedValue(null);

      await runBackgroundUpdateWorker();

      expect(mockUpdater.fetchManifest).not.toHaveBeenCalled();
    });

    it('exits when cooldown is not expired (race protection)', async () => {
      mockSharedUpdate.isCooldownExpired.mockReturnValue(false);

      await runBackgroundUpdateWorker();

      expect(mockUpdater.fetchManifest).not.toHaveBeenCalled();
      expect(mockReleaseLock).toHaveBeenCalled();
    });

    it('downloads and stages binary when update is available', async () => {
      const manifest = {
        version: '0.5.0',
        releaseDate: '2026-01-01T00:00:00Z',
        releaseNotesUrl: 'https://example.com/release',
        binaries: {
          'linux-x64': { url: 'https://example.com/rdc-linux-x64', sha256: 'expectedhash' },
        },
      };
      mockUpdater.fetchManifest.mockResolvedValue(manifest);
      mockUpdater.compareVersions.mockReturnValue(-1); // current < new
      mockUpdater.computeSha256.mockResolvedValue('expectedhash');

      await runBackgroundUpdateWorker();

      expect(mockUpdater.downloadFile).toHaveBeenCalledWith(
        'https://example.com/rdc-linux-x64',
        expect.stringContaining('.tmp')
      );
      expect(mockUpdateState.writeUpdateState).toHaveBeenCalledWith(
        expect.objectContaining({
          pendingUpdate: expect.objectContaining({
            version: '0.5.0',
            sha256: 'expectedhash',
          }),
          consecutiveFailures: 0,
        })
      );
      expect(mockReleaseLock).toHaveBeenCalled();
    });

    it('increments failure counter on error', async () => {
      mockUpdater.fetchManifest.mockRejectedValue(new Error('network error'));
      mockSharedUpdate.isCooldownExpired.mockReturnValue(true);

      await runBackgroundUpdateWorker();

      // The error handler reads state again and increments failures
      expect(mockUpdateState.writeUpdateState).toHaveBeenCalledWith(
        expect.objectContaining({
          consecutiveFailures: 1,
          lastError: 'network error',
        })
      );
    });

    it('records successful check when already up to date', async () => {
      const manifest = {
        version: '0.4.42',
        releaseDate: '2026-01-01T00:00:00Z',
        releaseNotesUrl: '',
        binaries: {},
      };
      mockUpdater.fetchManifest.mockResolvedValue(manifest);
      mockUpdater.compareVersions.mockReturnValue(0); // current == new

      await runBackgroundUpdateWorker();

      expect(mockUpdateState.writeUpdateState).toHaveBeenCalledWith(
        expect.objectContaining({
          consecutiveFailures: 0,
          lastError: null,
        })
      );
      expect(mockUpdater.downloadFile).not.toHaveBeenCalled();
    });

    it('aborts on SHA256 mismatch after download', async () => {
      const manifest = {
        version: '0.5.0',
        releaseDate: '2026-01-01T00:00:00Z',
        releaseNotesUrl: '',
        binaries: {
          'linux-x64': { url: 'https://example.com/rdc', sha256: 'expected' },
        },
      };
      mockUpdater.fetchManifest.mockResolvedValue(manifest);
      mockUpdater.compareVersions.mockReturnValue(-1);
      mockUpdater.computeSha256.mockResolvedValue('wrong_hash');

      await runBackgroundUpdateWorker();

      // Temp file should be deleted
      expect(mockFs.unlink).toHaveBeenCalled();
      // Failure counter incremented
      expect(mockUpdateState.writeUpdateState).toHaveBeenCalledWith(
        expect.objectContaining({
          consecutiveFailures: 1,
          lastError: expect.stringContaining('SHA256'),
        })
      );
    });
  });

  // ==========================================================================
  // B. maybeSpawnBackgroundUpdate()
  // ==========================================================================

  describe('maybeSpawnBackgroundUpdate()', () => {
    it('does nothing when not SEA', async () => {
      mockPlatform.isSEA.mockReturnValue(false);

      await maybeSpawnBackgroundUpdate();

      expect(mockSpawn).not.toHaveBeenCalled();
    });

    it('does nothing when update is disabled', async () => {
      mockPlatform.isUpdateDisabled.mockReturnValue(true);

      await maybeSpawnBackgroundUpdate();

      expect(mockSpawn).not.toHaveBeenCalled();
    });

    it('does nothing when cooldown is active', async () => {
      mockSharedUpdate.isCooldownExpired.mockReturnValue(false);

      await maybeSpawnBackgroundUpdate();

      expect(mockSpawn).not.toHaveBeenCalled();
    });

    it('spawns detached child process when cooldown expired', async () => {
      const mockChild = { unref: vi.fn() };
      mockSpawn.mockReturnValue(mockChild);

      await maybeSpawnBackgroundUpdate();

      expect(mockSpawn).toHaveBeenCalledWith(process.execPath, ['--background-update'], {
        detached: true,
        stdio: 'ignore',
      });
      expect(mockChild.unref).toHaveBeenCalled();
    });

    it('tracks update.spawn telemetry event', async () => {
      const mockChild = { unref: vi.fn() };
      mockSpawn.mockReturnValue(mockChild);

      await maybeSpawnBackgroundUpdate();

      expect(mockTelemetry.telemetryService.trackEvent).toHaveBeenCalledWith('update.spawn');
    });
  });

  // ==========================================================================
  // C. applyPendingUpdate()
  // ==========================================================================

  describe('applyPendingUpdate()', () => {
    it('returns false when no pending update', async () => {
      mockUpdateState.readUpdateState.mockResolvedValue(makeState());

      const result = await applyPendingUpdate();

      expect(result).toBe(false);
    });

    it('returns false when not SEA', async () => {
      mockPlatform.isSEA.mockReturnValue(false);

      const result = await applyPendingUpdate();

      expect(result).toBe(false);
    });

    it('skips when staged version is not newer than current', async () => {
      mockUpdateState.readUpdateState.mockResolvedValue(
        makeState({
          pendingUpdate: {
            version: '0.4.42',
            stagedPath: '/home/testuser/.cache/rediacc/staged-update/rdc-0.4.42',
            sha256: 'abc',
            platformKey: 'linux-x64',
            downloadedAt: '2026-01-01T00:00:00.000Z',
          },
        })
      );

      const result = await applyPendingUpdate();

      expect(result).toBe(false);
      // Should clear the stale pending update
      expect(mockUpdateState.writeUpdateState).toHaveBeenCalledWith(
        expect.objectContaining({ pendingUpdate: null })
      );
    });

    it('clears pendingUpdate on SHA256 mismatch', async () => {
      mockUpdater.compareVersions.mockReturnValue(-1); // current < staged
      mockUpdateState.readUpdateState.mockResolvedValue(
        makeState({
          pendingUpdate: {
            version: '0.5.0',
            stagedPath: '/home/testuser/.cache/rediacc/staged-update/rdc-0.5.0',
            sha256: 'expected_hash',
            platformKey: 'linux-x64',
            downloadedAt: '2026-01-01T00:00:00.000Z',
          },
        })
      );
      mockUpdater.computeSha256.mockResolvedValue('different_hash');

      const result = await applyPendingUpdate();

      expect(result).toBe(false);
      expect(mockUpdateState.writeUpdateState).toHaveBeenCalledWith(
        expect.objectContaining({
          pendingUpdate: null,
          lastError: 'SHA256 verification failed before apply',
        })
      );
    });

    it('rejects staged binary that fails warmup validation', async () => {
      mockUpdater.compareVersions.mockReturnValue(-1);
      mockUpdateState.readUpdateState.mockResolvedValue(
        makeState({
          pendingUpdate: {
            version: '0.5.0',
            stagedPath: '/home/testuser/.cache/rediacc/staged-update/rdc-0.5.0',
            sha256: 'correct_hash',
            platformKey: 'linux-x64',
            downloadedAt: '2026-01-01T00:00:00.000Z',
          },
        })
      );
      mockUpdater.computeSha256.mockResolvedValue('correct_hash');
      mockSpawnSync.mockReturnValue({ status: 1 }); // warmup fails

      const result = await applyPendingUpdate();

      expect(result).toBe(false);
      // Staged binary should be deleted
      expect(mockFs.unlink).toHaveBeenCalled();
      // pendingUpdate should be cleared
      expect(mockUpdateState.writeUpdateState).toHaveBeenCalledWith(
        expect.objectContaining({
          pendingUpdate: null,
          lastError: 'Staged binary failed warmup validation',
        })
      );
      // Telemetry event should be tracked
      expect(mockTelemetry.telemetryService.trackEvent).toHaveBeenCalledWith(
        'update.apply.validation_failed',
        { version: '0.5.0' }
      );
    });

    it('stops retrying after MAX_APPLY_ATTEMPTS', async () => {
      mockUpdater.compareVersions.mockReturnValue(-1);
      mockUpdateState.readUpdateState.mockResolvedValue(
        makeState({
          pendingUpdate: {
            version: '0.5.0',
            stagedPath: '/home/testuser/.cache/rediacc/staged-update/rdc-0.5.0',
            sha256: 'correct_hash',
            platformKey: 'linux-x64',
            downloadedAt: '2026-01-01T00:00:00.000Z',
            applyAttempts: 5, // Already at max
          },
        })
      );
      mockUpdater.computeSha256.mockResolvedValue('correct_hash');

      const result = await applyPendingUpdate();

      expect(result).toBe(false);
      // Should clear pendingUpdate after exceeding max attempts
      expect(mockUpdateState.writeUpdateState).toHaveBeenCalledWith(
        expect.objectContaining({
          pendingUpdate: null,
          lastError: expect.stringContaining('5 attempts'),
        })
      );
      // Should clean up staged files
      expect(mockUpdateState.cleanupStaleStagedFiles).toHaveBeenCalled();
      // Telemetry event should be tracked
      expect(mockTelemetry.telemetryService.trackEvent).toHaveBeenCalledWith(
        'update.apply.skipped_max_retries',
        expect.objectContaining({ version: '0.5.0' })
      );
    });

    it('increments applyAttempts on each attempt', async () => {
      mockUpdater.compareVersions.mockReturnValue(-1);
      const stderrSpy = vi.spyOn(process.stderr, 'write').mockImplementation(() => true);
      mockUpdateState.readUpdateState.mockResolvedValue(
        makeState({
          pendingUpdate: {
            version: '0.5.0',
            stagedPath: '/home/testuser/.cache/rediacc/staged-update/rdc-0.5.0',
            sha256: 'correct_hash',
            platformKey: 'linux-x64',
            downloadedAt: '2026-01-01T00:00:00.000Z',
            applyAttempts: 2,
          },
        })
      );
      mockUpdater.computeSha256.mockResolvedValue('correct_hash');

      // Capture state snapshots at each writeUpdateState call
      const snapshots: unknown[] = [];
      mockUpdateState.writeUpdateState.mockImplementation((state: CliUpdateState) => {
        snapshots.push(JSON.parse(JSON.stringify(state)));
        return Promise.resolve();
      });

      await applyPendingUpdate();

      // First writeUpdateState call should increment applyAttempts to 3
      const firstSnapshot = snapshots[0] as CliUpdateState;
      expect(firstSnapshot.pendingUpdate?.applyAttempts).toBe(3);
      stderrSpy.mockRestore();
    });

    it('retains pendingUpdate on EBUSY error (Windows retry)', async () => {
      mockUpdater.compareVersions.mockReturnValue(-1); // current < staged
      mockUpdateState.readUpdateState.mockResolvedValue(
        makeState({
          pendingUpdate: {
            version: '0.5.0',
            stagedPath: '/home/testuser/.cache/rediacc/staged-update/rdc-0.5.0',
            sha256: 'correct_hash',
            platformKey: 'linux-x64',
            downloadedAt: '2026-01-01T00:00:00.000Z',
          },
        })
      );
      mockUpdater.computeSha256.mockResolvedValue('correct_hash');
      const ebusyError = new Error('EBUSY') as NodeJS.ErrnoException;
      ebusyError.code = 'EBUSY';
      mockFs.copyFile.mockRejectedValue(ebusyError);

      const result = await applyPendingUpdate();

      expect(result).toBe(false);
      // EBUSY path returns false without clearing pendingUpdate
      // writeUpdateState should NOT have been called with pendingUpdate: null and lastError
      const writeCalls = mockUpdateState.writeUpdateState.mock.calls;
      for (const call of writeCalls) {
        const state = call[0] as CliUpdateState;
        if (state.pendingUpdate === null && state.lastError) {
          throw new Error('pendingUpdate was incorrectly cleared on EBUSY');
        }
      }
    });

    it('applies update successfully', async () => {
      const stderrSpy = vi.spyOn(process.stderr, 'write').mockImplementation(() => true);
      mockUpdater.compareVersions.mockReturnValue(-1); // current < staged
      mockUpdateState.readUpdateState.mockResolvedValue(
        makeState({
          pendingUpdate: {
            version: '0.5.0',
            stagedPath: '/home/testuser/.cache/rediacc/staged-update/rdc-0.5.0',
            sha256: 'correct_hash',
            platformKey: 'linux-x64',
            downloadedAt: '2026-01-01T00:00:00.000Z',
          },
        })
      );
      mockUpdater.computeSha256.mockResolvedValue('correct_hash');

      const result = await applyPendingUpdate();

      expect(result).toBe(true);
      expect(mockFs.copyFile).toHaveBeenCalled();
      expect(mockFs.rename).toHaveBeenCalled();
      expect(mockUpdateState.writeUpdateState).toHaveBeenCalledWith(
        expect.objectContaining({ pendingUpdate: null })
      );
      expect(stderrSpy).toHaveBeenCalledWith(expect.stringContaining('0.5.0'));
      // Telemetry should track success
      expect(mockTelemetry.telemetryService.trackEvent).toHaveBeenCalledWith(
        'update.apply.success',
        { from: '0.4.42', to: '0.5.0' }
      );
      stderrSpy.mockRestore();
    });

    it('rolls back when second rename fails', async () => {
      mockUpdater.compareVersions.mockReturnValue(-1);
      mockUpdateState.readUpdateState.mockResolvedValue(
        makeState({
          pendingUpdate: {
            version: '0.5.0',
            stagedPath: '/home/testuser/.cache/rediacc/staged-update/rdc-0.5.0',
            sha256: 'correct_hash',
            platformKey: 'linux-x64',
            downloadedAt: '2026-01-01T00:00:00.000Z',
          },
        })
      );
      mockUpdater.computeSha256.mockResolvedValue('correct_hash');

      // First rename succeeds (execPath → oldPath), second fails (temp → execPath)
      let renameCallCount = 0;
      mockFs.rename.mockImplementation(() => {
        renameCallCount++;
        if (renameCallCount === 2) {
          return Promise.reject(new Error('disk full'));
        }
        return Promise.resolve();
      });

      const result = await applyPendingUpdate();

      expect(result).toBe(false);
      // Third rename call should be the rollback (oldPath → execPath)
      expect(mockFs.rename).toHaveBeenCalledTimes(3);
    });

    it('retries on transient EBUSY before giving up', async () => {
      mockUpdater.compareVersions.mockReturnValue(-1);
      mockUpdateState.readUpdateState.mockResolvedValue(
        makeState({
          pendingUpdate: {
            version: '0.5.0',
            stagedPath: '/home/testuser/.cache/rediacc/staged-update/rdc-0.5.0',
            sha256: 'correct_hash',
            platformKey: 'linux-x64',
            downloadedAt: '2026-01-01T00:00:00.000Z',
          },
        })
      );
      mockUpdater.computeSha256.mockResolvedValue('correct_hash');

      // First rename: EBUSY twice then succeeds on third try
      let renameCallCount = 0;
      const ebusyError = new Error('EBUSY') as NodeJS.ErrnoException;
      ebusyError.code = 'EBUSY';
      mockFs.rename.mockImplementation(() => {
        renameCallCount++;
        // Calls 1-2 are EBUSY retries for the first rename, call 3 succeeds
        // Calls 4-5 would be the second rename
        if (renameCallCount <= 2) {
          return Promise.reject(ebusyError);
        }
        return Promise.resolve();
      });

      const stderrSpy = vi.spyOn(process.stderr, 'write').mockImplementation(() => true);
      const result = await applyPendingUpdate();

      // First rename: 2 EBUSY + 1 success = 3 calls, second rename: 1 success = 1 call
      expect(result).toBe(true);
      expect(renameCallCount).toBe(4);
      stderrSpy.mockRestore();
    });
  });
});
