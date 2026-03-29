import { promises as fs } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { RemoteTokenStorage } from '../remote-token-storage.js';

let testDir: string;
let storage: RemoteTokenStorage;

beforeEach(async () => {
  testDir = await fs.mkdtemp(join(tmpdir(), 'cli-token-storage-test-'));
  storage = new RemoteTokenStorage(testDir);
});

afterEach(async () => {
  await fs.rm(testDir, { recursive: true, force: true });
});

describe('RemoteTokenStorage', () => {
  describe('get', () => {
    it('should return null when file does not exist', async () => {
      const result = await storage.get('nonexistent');
      expect(result).toBeNull();
    });

    it('should read back data written by set', async () => {
      await storage.set('myconfig', { token: 'tok_abc', wrappedCek: 'cek_xyz' });
      const result = await storage.get('myconfig');
      expect(result).toEqual({ token: 'tok_abc', wrappedCek: 'cek_xyz' });
    });
  });

  describe('set', () => {
    it('should create the tokens directory if it does not exist', async () => {
      const nestedDir = join(testDir, 'nested', 'tokens');
      const nestedStorage = new RemoteTokenStorage(nestedDir);

      await nestedStorage.set('test', { token: 'tok_1', wrappedCek: 'cek_1' });

      const result = await nestedStorage.get('test');
      expect(result).toEqual({ token: 'tok_1', wrappedCek: 'cek_1' });
    });

    it('should overwrite existing data', async () => {
      await storage.set('myconfig', { token: 'tok_old', wrappedCek: 'cek_old' });
      await storage.set('myconfig', { token: 'tok_new', wrappedCek: 'cek_new' });

      const result = await storage.get('myconfig');
      expect(result).toEqual({ token: 'tok_new', wrappedCek: 'cek_new' });
    });

    it('should set restrictive file permissions (0o600)', async () => {
      await storage.set('secure', { token: 'tok_sec', wrappedCek: 'cek_sec' });

      const filePath = join(testDir, 'secure.json');
      const stat = await fs.stat(filePath);
      const mode = stat.mode & 0o777;
      expect(mode).toBe(0o600);
    });
  });

  describe('updateToken', () => {
    it('should update only the token, preserving wrappedCek', async () => {
      await storage.set('myconfig', { token: 'tok_original', wrappedCek: 'cek_preserved' });
      await storage.updateToken('myconfig', 'tok_rotated');

      const result = await storage.get('myconfig');
      expect(result).toEqual({ token: 'tok_rotated', wrappedCek: 'cek_preserved' });
    });

    it('should throw when no existing file', async () => {
      await expect(storage.updateToken('missing', 'tok_new')).rejects.toThrow(
        'No token file for config "missing"'
      );
    });
  });

  describe('delete', () => {
    it('should remove the file', async () => {
      await storage.set('myconfig', { token: 'tok_1', wrappedCek: 'cek_1' });

      await storage.delete('myconfig');

      const result = await storage.get('myconfig');
      expect(result).toBeNull();
    });

    it('should be idempotent (no error when file does not exist)', async () => {
      await expect(storage.delete('nonexistent')).resolves.toBeUndefined();
    });
  });
});
