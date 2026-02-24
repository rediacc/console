import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('node:os', () => ({
  homedir: () => '/home/testuser',
}));

vi.mock('node:child_process', () => ({
  execFileSync: vi.fn(),
}));

// Must import after mock setup
const { execFileSync } = await import('node:child_process');
const { getCacheDir, getConfigDir, getEffectiveHomedir, getRediaccDirs, getStateDir } =
  await import('../dirs.js');

const mockExecFileSync = vi.mocked(execFileSync);

describe('paths/dirs', () => {
  const originalPlatform = process.platform;
  const originalEnv = { ...process.env };
  const originalGetuid = process.getuid;

  beforeEach(() => {
    delete process.env.XDG_CONFIG_HOME;
    delete process.env.XDG_STATE_HOME;
    delete process.env.XDG_CACHE_HOME;
    delete process.env.APPDATA;
    delete process.env.LOCALAPPDATA;
    delete process.env.SUDO_USER;
    process.getuid = originalGetuid;
    mockExecFileSync.mockReset();
  });

  afterEach(() => {
    Object.defineProperty(process, 'platform', { value: originalPlatform });
    process.env = { ...originalEnv };
    process.getuid = originalGetuid;
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

  describe('getEffectiveHomedir (sudo awareness)', () => {
    it('returns os.homedir() when not running under sudo', () => {
      expect(getEffectiveHomedir()).toBe('/home/testuser');
      expect(mockExecFileSync).not.toHaveBeenCalled();
    });

    it('returns os.homedir() when SUDO_USER set but not root', () => {
      process.env.SUDO_USER = 'muhammed';
      process.getuid = () => 1000;
      expect(getEffectiveHomedir()).toBe('/home/testuser');
      expect(mockExecFileSync).not.toHaveBeenCalled();
    });

    it('resolves original user home via getent on Linux under sudo', () => {
      Object.defineProperty(process, 'platform', { value: 'linux' });
      process.env.SUDO_USER = 'muhammed';
      process.getuid = () => 0;
      mockExecFileSync.mockReturnValue('muhammed:x:1000:1000::/home/muhammed:/bin/bash\n');

      expect(getEffectiveHomedir()).toBe('/home/muhammed');
      expect(mockExecFileSync).toHaveBeenCalledWith(
        'getent',
        ['passwd', 'muhammed'],
        expect.objectContaining({ encoding: 'utf-8' }),
      );
    });

    it('resolves original user home via dscl on macOS under sudo', () => {
      Object.defineProperty(process, 'platform', { value: 'darwin' });
      process.env.SUDO_USER = 'muhammed';
      process.getuid = () => 0;
      mockExecFileSync.mockReturnValue('NFSHomeDirectory: /Users/muhammed\n');

      expect(getEffectiveHomedir()).toBe('/Users/muhammed');
      expect(mockExecFileSync).toHaveBeenCalledWith(
        'dscl',
        ['.', '-read', '/Users/muhammed', 'NFSHomeDirectory'],
        expect.objectContaining({ encoding: 'utf-8' }),
      );
    });

    it('falls back to os.homedir() when getent fails', () => {
      Object.defineProperty(process, 'platform', { value: 'linux' });
      process.env.SUDO_USER = 'muhammed';
      process.getuid = () => 0;
      mockExecFileSync.mockImplementation(() => {
        throw new Error('getent not found');
      });

      expect(getEffectiveHomedir()).toBe('/home/testuser');
    });

    it('uses resolved home for Linux dirs under sudo', () => {
      Object.defineProperty(process, 'platform', { value: 'linux' });
      process.env.SUDO_USER = 'muhammed';
      process.getuid = () => 0;
      mockExecFileSync.mockReturnValue('muhammed:x:1000:1000::/home/muhammed:/bin/bash\n');

      const dirs = getRediaccDirs();
      expect(dirs.config).toBe(join('/home/muhammed', '.config', 'rediacc'));
      expect(dirs.state).toBe(join('/home/muhammed', '.local', 'state', 'rediacc'));
      expect(dirs.cache).toBe(join('/home/muhammed', '.cache', 'rediacc'));
    });

    it('uses resolved home for macOS dirs under sudo', () => {
      Object.defineProperty(process, 'platform', { value: 'darwin' });
      process.env.SUDO_USER = 'muhammed';
      process.getuid = () => 0;
      mockExecFileSync.mockReturnValue('NFSHomeDirectory: /Users/muhammed\n');

      const dirs = getRediaccDirs();
      expect(dirs.config).toBe(
        join('/Users/muhammed', 'Library', 'Application Support', 'rediacc'),
      );
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
