import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { CliUpdateState } from '@rediacc/shared/update';
import { isCooldownExpired } from '@rediacc/shared/update';
import {
  cleanupStaleStagedFiles,
  getStagedBinaryPath,
  readUpdateState,
  writeUpdateState,
} from '../update-state.js';

const mockFs = vi.hoisted(() => ({
  readFile: vi.fn(),
  writeFile: vi.fn().mockResolvedValue(undefined),
  rename: vi.fn().mockResolvedValue(undefined),
  mkdir: vi.fn().mockResolvedValue(undefined),
  readdir: vi.fn().mockResolvedValue([]),
  unlink: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('node:fs', () => ({
  promises: mockFs,
}));

vi.mock('../../utils/platform.js', () => ({
  STAGED_UPDATE_DIR: '/home/testuser/.cache/rediacc/staged-update',
  UPDATE_STATE_FILE: '/home/testuser/.local/state/rediacc/update-state.json',
}));

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

describe('services/update-state', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    delete process.env.RDC_UPDATE_INTERVAL_HOURS;
  });

  describe('readUpdateState()', () => {
    it('returns default state when file is missing', async () => {
      mockFs.readFile.mockRejectedValue(new Error('ENOENT'));

      const state = await readUpdateState();

      expect(state.schemaVersion).toBe(1);
      expect(state.lastCheckAt).toBeNull();
      expect(state.pendingUpdate).toBeNull();
      expect(state.consecutiveFailures).toBe(0);
    });

    it('returns default state on corrupt JSON', async () => {
      mockFs.readFile.mockResolvedValue('not valid json{{{');

      const state = await readUpdateState();

      expect(state.schemaVersion).toBe(1);
      expect(state.consecutiveFailures).toBe(0);
    });

    it('parses valid state file', async () => {
      const saved = makeState({
        lastCheckAt: '2026-01-01T00:00:00.000Z',
        consecutiveFailures: 2,
        lastError: 'network timeout',
      });
      mockFs.readFile.mockResolvedValue(JSON.stringify(saved));

      const state = await readUpdateState();

      expect(state.lastCheckAt).toBe('2026-01-01T00:00:00.000Z');
      expect(state.consecutiveFailures).toBe(2);
      expect(state.lastError).toBe('network timeout');
    });

    it('returns default state if schemaVersion is not 1', async () => {
      const saved = { schemaVersion: 99, lastCheckAt: '2026-01-01T00:00:00.000Z' };
      mockFs.readFile.mockResolvedValue(JSON.stringify(saved));

      const state = await readUpdateState();

      expect(state.schemaVersion).toBe(1);
      expect(state.lastCheckAt).toBeNull();
    });
  });

  describe('writeUpdateState()', () => {
    it('writes state atomically via temp + rename', async () => {
      const state = makeState({ consecutiveFailures: 3 });

      await writeUpdateState(state);

      expect(mockFs.mkdir).toHaveBeenCalled();
      expect(mockFs.writeFile).toHaveBeenCalledWith(
        expect.stringContaining('.tmp'),
        expect.stringContaining('"consecutiveFailures": 3'),
        { mode: 0o600 }
      );
      expect(mockFs.rename).toHaveBeenCalledWith(
        expect.stringContaining('.tmp'),
        '/home/testuser/.local/state/rediacc/update-state.json'
      );
    });
  });

  describe('isCooldownExpired()', () => {
    it('returns true when lastAttemptAt is null', () => {
      const state = makeState({ lastAttemptAt: null });
      expect(isCooldownExpired(state)).toBe(true);
    });

    it('returns false when within cooldown period', () => {
      const thirtyMinAgo = new Date(Date.now() - 30 * 60 * 1000).toISOString();
      const state = makeState({ lastAttemptAt: thirtyMinAgo });
      expect(isCooldownExpired(state)).toBe(false);
    });

    it('returns true when cooldown has expired', () => {
      const twoHoursAgo = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString();
      const state = makeState({ lastAttemptAt: twoHoursAgo });
      expect(isCooldownExpired(state)).toBe(true);
    });

    it('applies exponential backoff on failures', () => {
      // With 1 failure: cooldown = 1 * 2^1 = 2 hours
      const ninetyMinAgo = new Date(Date.now() - 90 * 60 * 1000).toISOString();
      const state = makeState({ lastAttemptAt: ninetyMinAgo, consecutiveFailures: 1 });
      // 1.5 hours < 2 hours → not expired
      expect(isCooldownExpired(state)).toBe(false);

      // With 1 failure and 3 hours elapsed
      const threeHoursAgo = new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString();
      const state2 = makeState({ lastAttemptAt: threeHoursAgo, consecutiveFailures: 1 });
      expect(isCooldownExpired(state2)).toBe(true);
    });

    it('caps backoff at 24 hours', () => {
      // With 10 failures: min(1 * 2^10, 24) = min(1024, 24) = 24 hours
      const twentyFiveHoursAgo = new Date(Date.now() - 25 * 60 * 60 * 1000).toISOString();
      const state = makeState({ lastAttemptAt: twentyFiveHoursAgo, consecutiveFailures: 10 });
      expect(isCooldownExpired(state)).toBe(true);

      const twentyThreeHoursAgo = new Date(Date.now() - 23 * 60 * 60 * 1000).toISOString();
      const state2 = makeState({ lastAttemptAt: twentyThreeHoursAgo, consecutiveFailures: 10 });
      expect(isCooldownExpired(state2)).toBe(false);
    });

    it('respects RDC_UPDATE_INTERVAL_HOURS env override', () => {
      process.env.RDC_UPDATE_INTERVAL_HOURS = '1';
      const twoHoursAgo = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString();
      const state = makeState({ lastAttemptAt: twoHoursAgo });
      // 1-hour base, 0 failures → 1 hour cooldown. 2 hours elapsed → expired
      expect(isCooldownExpired(state)).toBe(true);
    });
  });

  describe('getStagedBinaryPath()', () => {
    it('returns path without .exe on non-Windows', () => {
      const path = getStagedBinaryPath('0.5.0');
      expect(path).toBe('/home/testuser/.cache/rediacc/staged-update/rdc-0.5.0');
    });
  });

  describe('cleanupStaleStagedFiles()', () => {
    it('removes non-matching files', async () => {
      const state = makeState({
        pendingUpdate: {
          version: '0.5.0',
          stagedPath: '/home/testuser/.cache/rediacc/staged-update/rdc-0.5.0',
          sha256: 'abc',
          platformKey: 'linux-x64',
          downloadedAt: '2026-01-01T00:00:00.000Z',
        },
      });
      mockFs.readdir.mockResolvedValue(['rdc-0.4.0', 'rdc-0.5.0', 'rdc-0.3.0.tmp']);

      await cleanupStaleStagedFiles(state);

      expect(mockFs.unlink).toHaveBeenCalledWith(
        '/home/testuser/.cache/rediacc/staged-update/rdc-0.4.0'
      );
      expect(mockFs.unlink).toHaveBeenCalledWith(
        '/home/testuser/.cache/rediacc/staged-update/rdc-0.3.0.tmp'
      );
      // Should NOT unlink the matching file
      expect(mockFs.unlink).not.toHaveBeenCalledWith(
        '/home/testuser/.cache/rediacc/staged-update/rdc-0.5.0'
      );
    });

    it('removes all files when no pending update', async () => {
      const state = makeState();
      mockFs.readdir.mockResolvedValue(['rdc-0.4.0', 'old.tmp']);

      await cleanupStaleStagedFiles(state);

      expect(mockFs.unlink).toHaveBeenCalledTimes(2);
    });

    it('does not throw on errors', async () => {
      mockFs.readdir.mockRejectedValue(new Error('ENOENT'));
      const state = makeState();

      await expect(cleanupStaleStagedFiles(state)).resolves.not.toThrow();
    });
  });
});
