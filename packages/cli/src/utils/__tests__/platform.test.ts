import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  acquireUpdateLock,
  cleanupOldBinary,
  getOldBinaryPath,
  getPlatformKey,
  isSEA,
  isUpdateDisabled,
} from '../platform.js';

const mockFs = vi.hoisted(() => ({
  access: vi.fn(),
  mkdir: vi.fn().mockResolvedValue(undefined),
  readFile: vi.fn(),
  unlink: vi.fn().mockResolvedValue(undefined),
  writeFile: vi.fn().mockResolvedValue(undefined),
}));

const mockLockfile = vi.hoisted(() => ({
  lock: vi.fn(),
}));

vi.mock('node:fs', () => ({
  promises: mockFs,
}));

vi.mock('proper-lockfile', () => ({
  default: mockLockfile,
}));

vi.mock('node:os', () => ({
  homedir: () => '/home/testuser',
}));

describe('utils/platform', () => {
  const originalExecPath = process.execPath;
  const originalPlatform = process.platform;
  const originalArch = process.arch;
  const originalEnv = { ...process.env };

  afterEach(() => {
    Object.defineProperty(process, 'execPath', { value: originalExecPath, writable: true });
    Object.defineProperty(process, 'platform', { value: originalPlatform });
    Object.defineProperty(process, 'arch', { value: originalArch });
    process.env = { ...originalEnv };
    vi.restoreAllMocks();
  });

  describe('isSEA()', () => {
    it('returns true when basename is rdc (Linux/macOS)', () => {
      Object.defineProperty(process, 'execPath', { value: '/usr/local/bin/rdc', writable: true });
      expect(isSEA()).toBe(true);
    });

    it('returns true when basename is rdc-linux-x64', () => {
      Object.defineProperty(process, 'execPath', {
        value: '/usr/local/bin/rdc-linux-x64',
        writable: true,
      });
      expect(isSEA()).toBe(true);
    });

    it('returns true when basename is rdc.exe (Windows)', () => {
      Object.defineProperty(process, 'execPath', {
        value: '/c/Program Files/rdc.exe',
        writable: true,
      });
      expect(isSEA()).toBe(true);
    });

    it('returns false when basename is node', () => {
      Object.defineProperty(process, 'execPath', {
        value: '/usr/local/bin/node',
        writable: true,
      });
      expect(isSEA()).toBe(false);
    });

    it('returns false when basename is node.exe', () => {
      Object.defineProperty(process, 'execPath', {
        value: 'C:\\Program Files\\node.exe',
        writable: true,
      });
      expect(isSEA()).toBe(false);
    });
  });

  describe('isUpdateDisabled()', () => {
    beforeEach(() => {
      delete process.env.RDC_DISABLE_AUTOUPDATE;
      delete process.env.CI;
      Object.defineProperty(process, 'execPath', { value: '/usr/local/bin/rdc', writable: true });
    });

    it('returns true when RDC_DISABLE_AUTOUPDATE=1', () => {
      process.env.RDC_DISABLE_AUTOUPDATE = '1';
      expect(isUpdateDisabled()).toBe(true);
    });

    it('returns true when CI=true', () => {
      process.env.CI = 'true';
      expect(isUpdateDisabled()).toBe(true);
    });

    it('returns true when execPath is in node_modules', () => {
      Object.defineProperty(process, 'execPath', {
        value: '/home/user/project/node_modules/.bin/rdc',
        writable: true,
      });
      expect(isUpdateDisabled()).toBe(true);
    });

    it('returns true when execPath is in dist', () => {
      Object.defineProperty(process, 'execPath', {
        value: '/home/user/project/dist/rdc',
        writable: true,
      });
      expect(isUpdateDisabled()).toBe(true);
    });

    it('returns true when execPath is in build', () => {
      Object.defineProperty(process, 'execPath', {
        value: '/home/user/project/build/rdc',
        writable: true,
      });
      expect(isUpdateDisabled()).toBe(true);
    });

    it('returns false when none of the conditions apply', () => {
      expect(isUpdateDisabled()).toBe(false);
    });
  });

  describe('getPlatformKey()', () => {
    it('returns linux-x64 on linux/x64', () => {
      Object.defineProperty(process, 'platform', { value: 'linux' });
      Object.defineProperty(process, 'arch', { value: 'x64' });
      expect(getPlatformKey()).toBe('linux-x64');
    });

    it('returns linux-arm64 on linux/arm64', () => {
      Object.defineProperty(process, 'platform', { value: 'linux' });
      Object.defineProperty(process, 'arch', { value: 'arm64' });
      expect(getPlatformKey()).toBe('linux-arm64');
    });

    it('returns mac-x64 on darwin/x64', () => {
      Object.defineProperty(process, 'platform', { value: 'darwin' });
      Object.defineProperty(process, 'arch', { value: 'x64' });
      expect(getPlatformKey()).toBe('mac-x64');
    });

    it('returns mac-arm64 on darwin/arm64', () => {
      Object.defineProperty(process, 'platform', { value: 'darwin' });
      Object.defineProperty(process, 'arch', { value: 'arm64' });
      expect(getPlatformKey()).toBe('mac-arm64');
    });

    it('returns win-x64 on win32/x64', () => {
      Object.defineProperty(process, 'platform', { value: 'win32' });
      Object.defineProperty(process, 'arch', { value: 'x64' });
      expect(getPlatformKey()).toBe('win-x64');
    });

    it('returns win-arm64 on win32/arm64', () => {
      Object.defineProperty(process, 'platform', { value: 'win32' });
      Object.defineProperty(process, 'arch', { value: 'arm64' });
      expect(getPlatformKey()).toBe('win-arm64');
    });

    it('returns null on unsupported arch (ia32)', () => {
      Object.defineProperty(process, 'platform', { value: 'linux' });
      Object.defineProperty(process, 'arch', { value: 'ia32' });
      expect(getPlatformKey()).toBeNull();
    });

    it('returns null on unsupported platform (freebsd)', () => {
      Object.defineProperty(process, 'platform', { value: 'freebsd' });
      Object.defineProperty(process, 'arch', { value: 'x64' });
      expect(getPlatformKey()).toBeNull();
    });
  });

  describe('getOldBinaryPath()', () => {
    it('returns path.old on Linux/macOS', () => {
      Object.defineProperty(process, 'execPath', { value: '/usr/local/bin/rdc', writable: true });
      Object.defineProperty(process, 'platform', { value: 'linux' });
      expect(getOldBinaryPath()).toBe('/usr/local/bin/rdc.old');
    });

    it('returns path.old.exe on Windows', () => {
      Object.defineProperty(process, 'execPath', {
        value: 'C:\\Program Files\\rdc.exe',
        writable: true,
      });
      Object.defineProperty(process, 'platform', { value: 'win32' });
      expect(getOldBinaryPath()).toBe('C:\\Program Files\\rdc.old.exe');
    });
  });

  describe('cleanupOldBinary()', () => {
    it('unlinks the old binary path', async () => {
      Object.defineProperty(process, 'execPath', { value: '/usr/local/bin/rdc', writable: true });
      Object.defineProperty(process, 'platform', { value: 'linux' });
      mockFs.unlink.mockResolvedValue(undefined);

      await cleanupOldBinary();

      expect(mockFs.unlink).toHaveBeenCalledWith('/usr/local/bin/rdc.old');
    });

    it('does not throw if file does not exist', async () => {
      Object.defineProperty(process, 'execPath', { value: '/usr/local/bin/rdc', writable: true });
      Object.defineProperty(process, 'platform', { value: 'linux' });
      mockFs.unlink.mockRejectedValue(new Error('ENOENT'));

      await expect(cleanupOldBinary()).resolves.toBeUndefined();
    });
  });

  describe('acquireUpdateLock()', () => {
    const mockRelease = vi.fn().mockResolvedValue(undefined);

    beforeEach(() => {
      mockFs.mkdir.mockClear().mockResolvedValue(undefined);
      mockFs.access.mockClear().mockRejectedValue(new Error('ENOENT'));
      mockFs.writeFile.mockClear().mockResolvedValue(undefined);
      mockLockfile.lock.mockClear().mockResolvedValue(mockRelease);
      mockRelease.mockClear().mockResolvedValue(undefined);
    });

    it('returns a release function when lock is acquired', async () => {
      const result = await acquireUpdateLock();

      expect(result).toBeTypeOf('function');
      expect(mockLockfile.lock).toHaveBeenCalledWith(
        expect.stringContaining('update.lock'),
        expect.objectContaining({ stale: 300000, retries: 0 })
      );
    });

    it('creates lock directory recursively', async () => {
      await acquireUpdateLock();

      expect(mockFs.mkdir).toHaveBeenCalledWith(expect.stringContaining('rediacc'), {
        recursive: true,
      });
    });

    it('creates lock file if it does not exist', async () => {
      mockFs.access.mockRejectedValue(new Error('ENOENT'));

      await acquireUpdateLock();

      expect(mockFs.writeFile).toHaveBeenCalledWith(expect.stringContaining('update.lock'), '', {
        mode: 0o600,
      });
    });

    it('does not recreate lock file if it already exists', async () => {
      mockFs.access.mockResolvedValue(undefined);

      await acquireUpdateLock();

      expect(mockFs.writeFile).not.toHaveBeenCalled();
    });

    it('returns null when lock is already held', async () => {
      const error = new Error('Lock file is already being held');
      (error as NodeJS.ErrnoException).code = 'ELOCKED';
      mockLockfile.lock.mockRejectedValue(error);

      const result = await acquireUpdateLock();

      expect(result).toBeNull();
    });

    it('returns null on other errors', async () => {
      mockLockfile.lock.mockRejectedValue(new Error('EACCES'));

      const result = await acquireUpdateLock();

      expect(result).toBeNull();
    });

    it('release function does not throw on errors', async () => {
      const failingRelease = vi.fn().mockRejectedValue(new Error('already released'));
      mockLockfile.lock.mockResolvedValue(failingRelease);

      const release = await acquireUpdateLock();
      expect(release).not.toBeNull();
      await expect(release!()).resolves.toBeUndefined();
    });
  });
});
