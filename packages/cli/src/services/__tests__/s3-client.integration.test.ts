/**
 * S3ClientService integration tests against a real S3-compatible server (RustFS).
 *
 * Requires S3_TEST_ENDPOINT, S3_TEST_ACCESS_KEY, S3_TEST_SECRET_KEY, S3_TEST_BUCKET.
 */

import { describe, it, expect, afterAll } from 'vitest';
import { S3OperationError } from '../s3-client.js';
import { createTestS3Client, getS3TestConfig, cleanupS3Prefix } from './s3-test-config.js';

const config = getS3TestConfig();
const client = createTestS3Client();

afterAll(async () => {
  await cleanupS3Prefix(client, '');
});

describe('S3ClientService (real S3)', () => {
  describe('verifyAccess', () => {
    it('should succeed with valid credentials', async () => {
      await expect(client.verifyAccess()).resolves.toBeUndefined();
    });

    it('should throw S3OperationError with bad credentials', async () => {
      const badClient = createTestS3Client({
        accessKeyId: 'invalid-key',
        secretAccessKey: 'invalid-secret',
      });

      await expect(badClient.verifyAccess()).rejects.toThrow(S3OperationError);
    });
  });

  describe('putRaw / getRaw', () => {
    it('should round-trip a string value', async () => {
      await client.putRaw('raw/hello.txt', 'Hello, RustFS!');
      const result = await client.getRaw('raw/hello.txt');
      expect(result).toBe('Hello, RustFS!');
    });

    it('should return null for non-existent key', async () => {
      const result = await client.getRaw(`raw/does-not-exist-${Date.now()}`);
      expect(result).toBeNull();
    });

    it('should overwrite existing key', async () => {
      await client.putRaw('raw/overwrite.txt', 'original');
      await client.putRaw('raw/overwrite.txt', 'updated');
      const result = await client.getRaw('raw/overwrite.txt');
      expect(result).toBe('updated');
    });

    it('should handle empty string', async () => {
      await client.putRaw('raw/empty.txt', '');
      const result = await client.getRaw('raw/empty.txt');
      expect(result).toBe('');
    });

    it('should handle keys with slashes (directory-like paths)', async () => {
      await client.putRaw('raw/a/b/c/deep.txt', 'deep value');
      const result = await client.getRaw('raw/a/b/c/deep.txt');
      expect(result).toBe('deep value');
    });
  });

  describe('putJson / getJson', () => {
    it('should round-trip a JSON object', async () => {
      const data = { name: 'test', count: 42, nested: { ok: true } };
      await client.putJson('json/object.json', data);
      const result = await client.getJson('json/object.json');
      expect(result).toEqual(data);
    });

    it('should round-trip a JSON array', async () => {
      const data = [1, 'two', { three: 3 }];
      await client.putJson('json/array.json', data);
      const result = await client.getJson('json/array.json');
      expect(result).toEqual(data);
    });

    it('should return null for non-existent key', async () => {
      const result = await client.getJson(`json/nope-${Date.now()}`);
      expect(result).toBeNull();
    });
  });

  describe('deleteObject', () => {
    it('should delete an existing object', async () => {
      await client.putRaw('del/target.txt', 'to delete');
      await client.deleteObject('del/target.txt');
      const result = await client.getRaw('del/target.txt');
      expect(result).toBeNull();
    });

    it('should be idempotent (delete non-existent is OK)', async () => {
      await expect(
        client.deleteObject(`del/never-existed-${Date.now()}`)
      ).resolves.toBeUndefined();
    });
  });

  describe('listKeys', () => {
    it('should list keys under a prefix', async () => {
      await client.putRaw('list/a.txt', '1');
      await client.putRaw('list/b.txt', '2');
      await client.putRaw('list/c.txt', '3');

      const keys = await client.listKeys('list/');
      expect(keys).toContain('list/a.txt');
      expect(keys).toContain('list/b.txt');
      expect(keys).toContain('list/c.txt');
    });

    it('should return empty array when no keys match', async () => {
      const keys = await client.listKeys(`no-such-prefix-${Date.now()}/`);
      expect(keys).toEqual([]);
    });

    it('should return keys relative to configured prefix', async () => {
      await client.putRaw('rel/item.txt', 'x');
      const keys = await client.listKeys('rel/');
      // Keys should NOT include the test run prefix — they're already relative
      for (const key of keys) {
        expect(key).not.toContain(config.prefix);
      }
    });
  });

  describe('moveObject', () => {
    it('should move object from source to destination', async () => {
      await client.putRaw('move/src.txt', 'movable');
      await client.moveObject('move/src.txt', 'move/dst.txt');
      const result = await client.getRaw('move/dst.txt');
      expect(result).toBe('movable');
    });

    it('should remove source after move', async () => {
      await client.putRaw('move/gone.txt', 'bye');
      await client.moveObject('move/gone.txt', 'move/arrived.txt');
      const srcResult = await client.getRaw('move/gone.txt');
      expect(srcResult).toBeNull();
    });
  });
});
