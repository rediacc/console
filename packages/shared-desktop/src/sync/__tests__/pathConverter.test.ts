import { describe, expect, it } from 'vitest';
import {
  ensureTrailingSlash,
  isRemotePath,
  joinRemotePath,
  parseRemotePath,
  removeTrailingSlash,
} from '../pathConverter.js';

describe('sync/pathConverter', () => {
  describe('isRemotePath', () => {
    it('should return true for user@host:/path format', () => {
      expect(isRemotePath('user@host:/path/to/dir')).toBe(true);
    });

    it('should return true for root@ip:/path format', () => {
      expect(isRemotePath('root@192.168.1.1:/home')).toBe(true);
    });

    it('should return true for complex hostname', () => {
      expect(isRemotePath('user@server.example.com:/var/data')).toBe(true);
    });

    it('should return true for path with port-like number in path', () => {
      expect(isRemotePath('user@host:/path/to/8080/dir')).toBe(true);
    });

    it('should return false for local absolute path', () => {
      expect(isRemotePath('/home/user/dir')).toBe(false);
    });

    it('should return false for Windows path', () => {
      expect(isRemotePath('C:\\Users\\name')).toBe(false);
    });

    it('should return false for relative path', () => {
      expect(isRemotePath('./relative/path')).toBe(false);
    });

    it('should return false for path with @ but no colon after', () => {
      expect(isRemotePath('user@host')).toBe(false);
    });

    it('should return false for email-like string without path', () => {
      expect(isRemotePath('user@host.com')).toBe(false);
    });

    it('should return false for empty string', () => {
      expect(isRemotePath('')).toBe(false);
    });

    it('should return false for null/undefined', () => {
      expect(isRemotePath(null as unknown as string)).toBe(false);
      expect(isRemotePath(undefined as unknown as string)).toBe(false);
    });

    it('should return false for path with colon but no @', () => {
      expect(isRemotePath('host:/path')).toBe(false);
    });

    it('should return true for path with just root after colon', () => {
      expect(isRemotePath('user@host:/')).toBe(true);
    });
  });

  describe('ensureTrailingSlash', () => {
    it('should add trailing slash if missing', () => {
      expect(ensureTrailingSlash('/path/to/dir')).toBe('/path/to/dir/');
    });

    it('should preserve existing forward slash', () => {
      expect(ensureTrailingSlash('/path/to/dir/')).toBe('/path/to/dir/');
    });

    it('should preserve existing backslash', () => {
      expect(ensureTrailingSlash('C:\\path\\')).toBe('C:\\path\\');
    });

    it('should add slash to Windows path', () => {
      expect(ensureTrailingSlash('C:\\path')).toBe('C:\\path/');
    });

    it('should add slash to single directory', () => {
      expect(ensureTrailingSlash('dir')).toBe('dir/');
    });

    it('should return empty string for empty input', () => {
      expect(ensureTrailingSlash('')).toBe('');
    });

    it('should return null/undefined as-is', () => {
      expect(ensureTrailingSlash(null as unknown as string)).toBe(null);
      expect(ensureTrailingSlash(undefined as unknown as string)).toBe(undefined);
    });

    it('should handle remote path', () => {
      expect(ensureTrailingSlash('user@host:/path/to/dir')).toBe('user@host:/path/to/dir/');
    });
  });

  describe('removeTrailingSlash', () => {
    it('should remove trailing forward slash', () => {
      expect(removeTrailingSlash('/path/to/dir/')).toBe('/path/to/dir');
    });

    it('should remove trailing backslash', () => {
      expect(removeTrailingSlash('C:\\path\\')).toBe('C:\\path');
    });

    it('should remove multiple trailing slashes', () => {
      expect(removeTrailingSlash('/path/to/dir///')).toBe('/path/to/dir');
    });

    it('should not modify path without trailing slash', () => {
      expect(removeTrailingSlash('/path/to/dir')).toBe('/path/to/dir');
    });

    it('should return empty string for empty input', () => {
      expect(removeTrailingSlash('')).toBe('');
    });

    it('should return null/undefined as-is', () => {
      expect(removeTrailingSlash(null as unknown as string)).toBe(null);
      expect(removeTrailingSlash(undefined as unknown as string)).toBe(undefined);
    });

    it('should handle root path', () => {
      expect(removeTrailingSlash('/')).toBe('');
    });

    it('should handle Windows root', () => {
      expect(removeTrailingSlash('C:\\')).toBe('C:');
    });
  });

  describe('joinRemotePath', () => {
    it('should join destination and path with colon', () => {
      expect(joinRemotePath('user@host', '/path/to/dir')).toBe('user@host:/path/to/dir');
    });

    it('should handle empty path', () => {
      expect(joinRemotePath('user@host', '')).toBe('user@host:');
    });

    it('should handle root path', () => {
      expect(joinRemotePath('user@host', '/')).toBe('user@host:/');
    });

    it('should handle IP address destination', () => {
      expect(joinRemotePath('root@192.168.1.1', '/var/data')).toBe('root@192.168.1.1:/var/data');
    });

    it('should handle complex hostname', () => {
      expect(joinRemotePath('user@server.example.com', '/home/user')).toBe(
        'user@server.example.com:/home/user'
      );
    });
  });

  describe('parseRemotePath', () => {
    it('should parse valid remote path', () => {
      const result = parseRemotePath('user@host:/path/to/dir');
      expect(result).toEqual({
        host: 'user@host',
        path: '/path/to/dir',
      });
    });

    it('should parse IP address host', () => {
      const result = parseRemotePath('root@192.168.1.1:/home');
      expect(result).toEqual({
        host: 'root@192.168.1.1',
        path: '/home',
      });
    });

    it('should parse complex hostname', () => {
      const result = parseRemotePath('user@server.example.com:/var/data');
      expect(result).toEqual({
        host: 'user@server.example.com',
        path: '/var/data',
      });
    });

    it('should parse root path', () => {
      const result = parseRemotePath('user@host:/');
      expect(result).toEqual({
        host: 'user@host',
        path: '/',
      });
    });

    it('should parse empty path after colon', () => {
      const result = parseRemotePath('user@host:');
      expect(result).toEqual({
        host: 'user@host',
        path: '',
      });
    });

    it('should return null for local path', () => {
      expect(parseRemotePath('/local/path')).toBeNull();
    });

    it('should return null for Windows path', () => {
      expect(parseRemotePath('C:\\Windows\\path')).toBeNull();
    });

    it('should return null for relative path', () => {
      expect(parseRemotePath('./relative')).toBeNull();
    });

    it('should return null for empty string', () => {
      expect(parseRemotePath('')).toBeNull();
    });

    it('should handle path with multiple colons', () => {
      const result = parseRemotePath('user@host:/path/to:file');
      expect(result).toEqual({
        host: 'user@host',
        path: '/path/to:file',
      });
    });
  });

  describe('roundtrip: joinRemotePath -> parseRemotePath', () => {
    it('should roundtrip correctly', () => {
      const host = 'user@host';
      const path = '/path/to/dir';
      const joined = joinRemotePath(host, path);
      const parsed = parseRemotePath(joined);

      expect(parsed).toEqual({ host, path });
    });

    it('should roundtrip with complex hostname', () => {
      const host = 'admin@server.prod.example.com';
      const path = '/var/www/html';
      const joined = joinRemotePath(host, path);
      const parsed = parseRemotePath(joined);

      expect(parsed).toEqual({ host, path });
    });
  });
});
