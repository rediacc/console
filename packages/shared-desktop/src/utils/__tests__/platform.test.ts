import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  isMSYS2,
  unixToWindowsPath,
  windowsPathToWSL,
  windowsToUnixPath,
  wslPathToWindows,
} from '../platform.js';

describe('utils/platform', () => {
  describe('windowsToUnixPath', () => {
    it('should convert Windows drive path to MSYS2 format', () => {
      expect(windowsToUnixPath('C:\\Users\\foo')).toBe('/c/Users/foo');
    });

    it('should handle lowercase drive letter', () => {
      expect(windowsToUnixPath('c:\\Users\\foo')).toBe('/c/Users/foo');
    });

    it('should convert different drive letters', () => {
      expect(windowsToUnixPath('D:\\Projects')).toBe('/d/Projects');
      expect(windowsToUnixPath('E:\\Data\\files')).toBe('/e/Data/files');
    });

    it('should handle UNC paths', () => {
      expect(windowsToUnixPath('\\\\server\\share')).toBe('//server/share');
      expect(windowsToUnixPath('\\\\server\\share\\folder')).toBe('//server/share/folder');
    });

    it('should replace backslashes in relative paths', () => {
      expect(windowsToUnixPath('folder\\subfolder\\file.txt')).toBe('folder/subfolder/file.txt');
    });

    it('should handle path with spaces', () => {
      expect(windowsToUnixPath('C:\\Program Files\\App')).toBe('/c/Program Files/App');
    });

    it('should return empty string for empty input', () => {
      expect(windowsToUnixPath('')).toBe('');
    });

    it('should return null/undefined as-is', () => {
      expect(windowsToUnixPath(null as unknown as string)).toBe(null);
      expect(windowsToUnixPath(undefined as unknown as string)).toBe(undefined);
    });

    it('should handle path ending with backslash', () => {
      expect(windowsToUnixPath('C:\\Users\\')).toBe('/c/Users/');
    });

    it('should handle root drive path', () => {
      expect(windowsToUnixPath('C:\\')).toBe('/c/');
    });
  });

  describe('unixToWindowsPath', () => {
    it('should convert MSYS2 path to Windows format', () => {
      expect(unixToWindowsPath('/c/Users/foo')).toBe('C:\\Users\\foo');
    });

    it('should handle lowercase drive letter', () => {
      expect(unixToWindowsPath('/c/Projects')).toBe('C:\\Projects');
    });

    it('should handle uppercase drive letter', () => {
      expect(unixToWindowsPath('/C/Projects')).toBe('C:\\Projects');
    });

    it('should convert different drive letters', () => {
      expect(unixToWindowsPath('/d/Projects')).toBe('D:\\Projects');
      expect(unixToWindowsPath('/e/Data/files')).toBe('E:\\Data\\files');
    });

    it('should not convert paths without drive letter prefix', () => {
      expect(unixToWindowsPath('/home/user')).toBe('/home/user');
      expect(unixToWindowsPath('/var/log')).toBe('/var/log');
    });

    it('should handle path with spaces', () => {
      expect(unixToWindowsPath('/c/Program Files/App')).toBe('C:\\Program Files\\App');
    });

    it('should return empty string for empty input', () => {
      expect(unixToWindowsPath('')).toBe('');
    });

    it('should return null/undefined as-is', () => {
      expect(unixToWindowsPath(null as unknown as string)).toBe(null);
      expect(unixToWindowsPath(undefined as unknown as string)).toBe(undefined);
    });

    it('should handle root drive path', () => {
      expect(unixToWindowsPath('/c/')).toBe('C:\\');
    });

    it('should handle path ending with slash', () => {
      expect(unixToWindowsPath('/c/Users/')).toBe('C:\\Users\\');
    });
  });

  describe('windowsPathToWSL', () => {
    it('should convert Windows path to WSL /mnt format', () => {
      expect(windowsPathToWSL('C:\\Users\\foo')).toBe('/mnt/c/Users/foo');
    });

    it('should handle lowercase drive letter', () => {
      expect(windowsPathToWSL('c:\\Users\\foo')).toBe('/mnt/c/Users/foo');
    });

    it('should convert different drive letters', () => {
      expect(windowsPathToWSL('D:\\Projects')).toBe('/mnt/d/Projects');
      expect(windowsPathToWSL('E:\\Data')).toBe('/mnt/e/Data');
    });

    it('should handle .ssh directory path', () => {
      expect(windowsPathToWSL('C:\\Users\\john\\.ssh')).toBe('/mnt/c/Users/john/.ssh');
    });

    it('should handle path with spaces', () => {
      expect(windowsPathToWSL('C:\\Program Files\\App')).toBe('/mnt/c/Program Files/App');
    });

    it('should return empty string for empty input', () => {
      expect(windowsPathToWSL('')).toBe('');
    });

    it('should return null/undefined as-is', () => {
      expect(windowsPathToWSL(null as unknown as string)).toBe(null);
      expect(windowsPathToWSL(undefined as unknown as string)).toBe(undefined);
    });

    it('should replace backslashes in relative paths', () => {
      expect(windowsPathToWSL('folder\\subfolder')).toBe('folder/subfolder');
    });

    it('should handle root drive path', () => {
      expect(windowsPathToWSL('C:\\')).toBe('/mnt/c/');
    });
  });

  describe('wslPathToWindows', () => {
    it('should convert WSL /mnt path to Windows format', () => {
      expect(wslPathToWindows('/mnt/c/Users/foo')).toBe('C:\\Users\\foo');
    });

    it('should handle lowercase drive letter', () => {
      expect(wslPathToWindows('/mnt/c/Projects')).toBe('C:\\Projects');
    });

    it('should handle uppercase drive letter', () => {
      expect(wslPathToWindows('/mnt/C/Projects')).toBe('C:\\Projects');
    });

    it('should convert different drive letters', () => {
      expect(wslPathToWindows('/mnt/d/Projects')).toBe('D:\\Projects');
      expect(wslPathToWindows('/mnt/e/Data')).toBe('E:\\Data');
    });

    it('should handle .ssh directory path', () => {
      expect(wslPathToWindows('/mnt/c/Users/john/.ssh')).toBe('C:\\Users\\john\\.ssh');
    });

    it('should not convert non-mnt paths', () => {
      expect(wslPathToWindows('/home/user')).toBe('/home/user');
      expect(wslPathToWindows('/var/log')).toBe('/var/log');
      expect(wslPathToWindows('/c/Users')).toBe('/c/Users');
    });

    it('should return empty string for empty input', () => {
      expect(wslPathToWindows('')).toBe('');
    });

    it('should return null/undefined as-is', () => {
      expect(wslPathToWindows(null as unknown as string)).toBe(null);
      expect(wslPathToWindows(undefined as unknown as string)).toBe(undefined);
    });

    it('should handle root drive path', () => {
      expect(wslPathToWindows('/mnt/c/')).toBe('C:\\');
    });
  });

  describe('isMSYS2', () => {
    const originalEnv = process.env;

    beforeEach(() => {
      // Clear MSYSTEM for each test
      delete process.env.MSYSTEM;
    });

    afterEach(() => {
      // Restore original env
      process.env = originalEnv;
    });

    it('should return true for MINGW64', () => {
      process.env.MSYSTEM = 'MINGW64';
      expect(isMSYS2()).toBe(true);
    });

    it('should return true for MINGW32', () => {
      process.env.MSYSTEM = 'MINGW32';
      expect(isMSYS2()).toBe(true);
    });

    it('should return true for UCRT64', () => {
      process.env.MSYSTEM = 'UCRT64';
      expect(isMSYS2()).toBe(true);
    });

    it('should return true for CLANG64', () => {
      process.env.MSYSTEM = 'CLANG64';
      expect(isMSYS2()).toBe(true);
    });

    it('should return true for MSYS', () => {
      process.env.MSYSTEM = 'MSYS';
      expect(isMSYS2()).toBe(true);
    });

    it('should return false for undefined MSYSTEM', () => {
      delete process.env.MSYSTEM;
      expect(isMSYS2()).toBe(false);
    });

    it('should return false for unknown MSYSTEM value', () => {
      process.env.MSYSTEM = 'UNKNOWN';
      expect(isMSYS2()).toBe(false);
    });

    it('should return false for empty MSYSTEM', () => {
      process.env.MSYSTEM = '';
      expect(isMSYS2()).toBe(false);
    });
  });

  describe('path conversion roundtrips', () => {
    it('should roundtrip windowsToUnixPath -> unixToWindowsPath', () => {
      const original = 'C:\\Users\\test\\Documents';
      const unix = windowsToUnixPath(original);
      const back = unixToWindowsPath(unix);
      expect(back).toBe(original);
    });

    it('should roundtrip unixToWindowsPath -> windowsToUnixPath', () => {
      const original = '/c/Users/test/Documents';
      const windows = unixToWindowsPath(original);
      const back = windowsToUnixPath(windows);
      expect(back).toBe(original);
    });

    it('should roundtrip windowsPathToWSL -> wslPathToWindows', () => {
      const original = 'C:\\Users\\test\\Documents';
      const wsl = windowsPathToWSL(original);
      const back = wslPathToWindows(wsl);
      expect(back).toBe(original);
    });

    it('should roundtrip wslPathToWindows -> windowsPathToWSL', () => {
      const original = '/mnt/c/Users/test/Documents';
      const windows = wslPathToWindows(original);
      const back = windowsPathToWSL(windows);
      expect(back).toBe(original);
    });
  });
});
