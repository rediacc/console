import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('node:os', () => ({
  homedir: () => '/home/testuser',
}));

// Must import after mock setup
const { getCacheDir, getConfigDir, getRediaccDirs, getStateDir } = await import('../dirs.js');

describe('paths/dirs', () => {
  const originalPlatform = process.platform;
  const originalEnv = { ...process.env };

  beforeEach(() => {
    delete process.env.XDG_CONFIG_HOME;
    delete process.env.XDG_STATE_HOME;
    delete process.env.XDG_CACHE_HOME;
    delete process.env.APPDATA;
    delete process.env.LOCALAPPDATA;
  });

  afterEach(() => {
    Object.defineProperty(process, 'platform', { value: originalPlatform });
    process.env = { ...originalEnv };
  });

  describe('Linux (default)', () => {
    beforeEach(() => {
      Object.defineProperty(process, 'platform', { value: 'linux' });
    });

    it('uses XDG defaults when no env vars set', () => {
      const dirs = getRediaccDirs();
      expect(dirs.config).toBe(join('/home/testuser', '.config', 'rediacc'));
      expect(dirs.state).toBe(join('/home/testuser', '.local', 'state', 'rediacc'));
      expect(dirs.cache).toBe(join('/home/testuser', '.cache', 'rediacc'));
    });

    it('respects XDG_CONFIG_HOME', () => {
      process.env.XDG_CONFIG_HOME = '/custom/config';
      expect(getConfigDir()).toBe(join('/custom/config', 'rediacc'));
    });

    it('respects XDG_STATE_HOME', () => {
      process.env.XDG_STATE_HOME = '/custom/state';
      expect(getStateDir()).toBe(join('/custom/state', 'rediacc'));
    });

    it('respects XDG_CACHE_HOME', () => {
      process.env.XDG_CACHE_HOME = '/custom/cache';
      expect(getCacheDir()).toBe(join('/custom/cache', 'rediacc'));
    });
  });

  describe('macOS (darwin)', () => {
    beforeEach(() => {
      Object.defineProperty(process, 'platform', { value: 'darwin' });
    });

    it('uses Library paths', () => {
      const dirs = getRediaccDirs();
      expect(dirs.config).toBe(join('/home/testuser', 'Library', 'Application Support', 'rediacc'));
      expect(dirs.state).toBe(join('/home/testuser', 'Library', 'Application Support', 'rediacc'));
      expect(dirs.cache).toBe(join('/home/testuser', 'Library', 'Caches', 'rediacc'));
    });
  });

  describe('Windows (win32)', () => {
    beforeEach(() => {
      Object.defineProperty(process, 'platform', { value: 'win32' });
    });

    it('uses APPDATA and LOCALAPPDATA', () => {
      process.env.APPDATA = 'C:\\Users\\test\\AppData\\Roaming';
      process.env.LOCALAPPDATA = 'C:\\Users\\test\\AppData\\Local';

      const dirs = getRediaccDirs();
      expect(dirs.config).toBe(join('C:\\Users\\test\\AppData\\Roaming', 'rediacc'));
      expect(dirs.state).toBe(join('C:\\Users\\test\\AppData\\Local', 'rediacc'));
      expect(dirs.cache).toBe(join('C:\\Users\\test\\AppData\\Local', 'rediacc', 'cache'));
    });

    it('falls back when env vars are missing', () => {
      const dirs = getRediaccDirs();
      expect(dirs.config).toBe(join('/home/testuser', 'AppData', 'Roaming', 'rediacc'));
      expect(dirs.state).toBe(join('/home/testuser', 'AppData', 'Local', 'rediacc'));
    });
  });

  describe('convenience accessors', () => {
    beforeEach(() => {
      Object.defineProperty(process, 'platform', { value: 'linux' });
    });

    it('getConfigDir returns config path', () => {
      expect(getConfigDir()).toBe(getRediaccDirs().config);
    });

    it('getStateDir returns state path', () => {
      expect(getStateDir()).toBe(getRediaccDirs().state);
    });

    it('getCacheDir returns cache path', () => {
      expect(getCacheDir()).toBe(getRediaccDirs().cache);
    });
  });
});
