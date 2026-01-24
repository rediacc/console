import { readFile, rm, unlink, writeFile } from 'node:fs/promises';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  acquireUpdateLock,
  cleanupOldBinary,
  getOldBinaryPath,
  getPlatformKey,
  isSEA,
  isUpdateDisabled,
  releaseUpdateLock,
} from '../platform.js';

vi.mock('node:fs/promises', () => ({
  mkdir: vi.fn().mockResolvedValue(undefined),
  readFile: vi.fn(),
  rm: vi.fn().mockResolvedValue(undefined),
  unlink: vi.fn(),
  writeFile: vi.fn(),
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
        value: '/c/Program Files/node.exe',
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

    it('returns true when execPath contains /node_modules/', () => {
      Object.defineProperty(process, 'execPath', {
        value: '/home/user/project/node_modules/.bin/rdc',
        writable: true,
      });
      expect(isUpdateDisabled()).toBe(true);
    });

    it('returns true when execPath contains /dist/', () => {
      Object.defineProperty(process, 'execPath', {
        value: '/home/user/project/dist/rdc',
        writable: true,
      });
      expect(isUpdateDisabled()).toBe(true);
    });

    it('returns true when execPath contains /build/', () => {
      Object.defineProperty(process, 'execPath', {
        value: '/home/user/project/build/rdc',
        writable: true,
      });
      expect(isUpdateDisabled()).toBe(true);
    });

    it('returns false when none of the above conditions apply', () => {
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
  });

  describe('getOldBinaryPath()', () => {
    it('returns path.old on Linux/macOS', () => {
      Object.defineProperty(process, 'platform', { value: 'linux' });
      expect(getOldBinaryPath('/usr/local/bin/rdc')).toBe('/usr/local/bin/rdc.old');
    });

    it('returns path.old.exe on Windows', () => {
      Object.defineProperty(process, 'platform', { value: 'win32' });
      const winPath = 'C:\\Program Files\\rdc.exe';
      const expected = 'C:\\Program Files\\rdc.old.exe';
      expect(getOldBinaryPath(winPath)).toBe(expected);
    });
  });

  describe('acquireUpdateLock() / releaseUpdateLock()', () => {
    beforeEach(() => {
      vi.mocked(readFile).mockRejectedValue(new Error('ENOENT'));
      vi.mocked(writeFile).mockResolvedValue();
      vi.mocked(unlink).mockResolvedValue();
    });

    it('acquires lock when no lock exists and returns true', async () => {
      vi.mocked(readFile).mockRejectedValue(new Error('ENOENT'));

      const result = await acquireUpdateLock();

      expect(result).toBe(true);
      expect(writeFile).toHaveBeenCalledWith(
        expect.stringContaining('update.lock'),
        String(process.pid),
        'utf-8'
      );
    });

    it('writes PID to lock file', async () => {
      vi.mocked(readFile).mockRejectedValue(new Error('ENOENT'));

      await acquireUpdateLock();

      expect(writeFile).toHaveBeenCalledWith(expect.any(String), String(process.pid), 'utf-8');
    });

    it('returns false when lock exists with alive PID', async () => {
      const alivePid = process.pid;
      vi.mocked(readFile).mockResolvedValue(String(alivePid));
      const killSpy = vi.spyOn(process, 'kill').mockImplementation(() => true);

      const result = await acquireUpdateLock();

      expect(result).toBe(false);
      killSpy.mockRestore();
    });

    it('acquires lock when lock exists with dead PID (stale lock)', async () => {
      vi.mocked(readFile).mockResolvedValue('99999999');
      const killSpy = vi.spyOn(process, 'kill').mockImplementation(throwEsrch);

      const result = await acquireUpdateLock();

      expect(result).toBe(true);
      expect(writeFile).toHaveBeenCalled();
      killSpy.mockRestore();
    });

    it('releaseUpdateLock removes the lock file', async () => {
      await releaseUpdateLock();

      expect(unlink).toHaveBeenCalledWith(expect.stringContaining('update.lock'));
    });
  });

  describe('cleanupOldBinary()', () => {
    it('removes old binary with force flag', async () => {
      vi.mocked(rm).mockResolvedValue();

      await cleanupOldBinary('/usr/local/bin/rdc.old');

      expect(rm).toHaveBeenCalledWith('/usr/local/bin/rdc.old', { force: true });
    });

    it('does not throw if file does not exist', async () => {
      vi.mocked(rm).mockResolvedValue();

      await expect(cleanupOldBinary('/usr/local/bin/rdc.old')).resolves.toBeUndefined();
    });
  });
});

function throwEsrch(): never {
  throw new Error('ESRCH');
}
