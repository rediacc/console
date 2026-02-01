/**
 * S3QueueService integration tests against a real S3-compatible server (RustFS).
 *
 * Requires S3_TEST_ENDPOINT, S3_TEST_ACCESS_KEY, S3_TEST_SECRET_KEY, S3_TEST_BUCKET.
 */

import { describe, it, expect, afterAll } from 'vitest';
import { S3QueueService } from '../s3-queue.js';
import { createTestS3Client, cleanupS3Prefix } from './s3-test-config.js';

const client = createTestS3Client();
const queue = new S3QueueService(client);

afterAll(async () => {
  await cleanupS3Prefix(client, '');
});

function makeItem(overrides?: Record<string, unknown>) {
  return {
    functionName: 'test-fn',
    teamName: 'test-team',
    vaultContent: '{}',
    priority: 3,
    ...overrides,
  };
}

describe('S3QueueService (real S3)', () => {
  describe('create', () => {
    it('should create item in PENDING state with UUID taskId', async () => {
      const taskId = await queue.create(makeItem());
      expect(taskId).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);

      const item = await queue.trace(taskId);
      expect(item).not.toBeNull();
      expect(item!.status).toBe('PENDING');
      expect(item!.taskId).toBe(taskId);
    });

    it('should set timestamps and retryCount=0', async () => {
      const taskId = await queue.create(makeItem());
      const item = await queue.trace(taskId);
      expect(item!.retryCount).toBe(0);
      expect(item!.createdAt).toBeDefined();
      expect(item!.updatedAt).toBeDefined();
    });
  });

  describe('claim', () => {
    it('should move PENDING -> ACTIVE and set startedAt', async () => {
      const taskId = await queue.create(makeItem());
      const claimed = await queue.claim(taskId);

      expect(claimed.status).toBe('ACTIVE');
      expect(claimed.startedAt).toBeDefined();

      const traced = await queue.trace(taskId);
      expect(traced!.status).toBe('ACTIVE');
    });

    it('should throw for non-existent item', async () => {
      await expect(queue.claim('00000000-0000-0000-0000-000000000000')).rejects.toThrow(
        /not found in pending/
      );
    });
  });

  describe('complete', () => {
    it('should move ACTIVE -> COMPLETED on exitCode 0', async () => {
      const taskId = await queue.create(makeItem());
      await queue.claim(taskId);
      await queue.complete(taskId, { exitCode: 0 });

      const item = await queue.trace(taskId);
      expect(item!.status).toBe('COMPLETED');
      expect(item!.exitCode).toBe(0);
      expect(item!.completedAt).toBeDefined();
    });

    it('should move ACTIVE -> FAILED on non-zero exitCode', async () => {
      const taskId = await queue.create(makeItem());
      await queue.claim(taskId);
      await queue.complete(taskId, { exitCode: 1 });

      const item = await queue.trace(taskId);
      expect(item!.status).toBe('FAILED');
      expect(item!.exitCode).toBe(1);
    });

    it('should store errorMessage and consoleOutput', async () => {
      const taskId = await queue.create(makeItem());
      await queue.claim(taskId);
      await queue.complete(taskId, {
        exitCode: 1,
        errorMessage: 'something broke',
        consoleOutput: 'log line 1\nlog line 2',
      });

      const item = await queue.trace(taskId);
      expect(item!.errorMessage).toBe('something broke');
      expect(item!.consoleOutput).toBe('log line 1\nlog line 2');
    });

    it('should throw for non-active item', async () => {
      const taskId = await queue.create(makeItem());
      // Still PENDING, not ACTIVE
      await expect(queue.complete(taskId, { exitCode: 0 })).rejects.toThrow(/not found in active/);
    });
  });

  describe('cancel', () => {
    it('should cancel a PENDING item', async () => {
      const taskId = await queue.create(makeItem());
      await queue.cancel(taskId);

      const item = await queue.trace(taskId);
      expect(item!.status).toBe('CANCELLED');
    });

    it('should cancel an ACTIVE item', async () => {
      const taskId = await queue.create(makeItem());
      await queue.claim(taskId);
      await queue.cancel(taskId);

      const item = await queue.trace(taskId);
      expect(item!.status).toBe('CANCELLED');
    });
  });

  describe('trace', () => {
    it('should find item in each status', async () => {
      // PENDING
      const pendingId = await queue.create(makeItem());
      expect((await queue.trace(pendingId))!.status).toBe('PENDING');

      // ACTIVE
      const activeId = await queue.create(makeItem());
      await queue.claim(activeId);
      expect((await queue.trace(activeId))!.status).toBe('ACTIVE');

      // COMPLETED
      const completedId = await queue.create(makeItem());
      await queue.claim(completedId);
      await queue.complete(completedId, { exitCode: 0 });
      expect((await queue.trace(completedId))!.status).toBe('COMPLETED');

      // FAILED
      const failedId = await queue.create(makeItem());
      await queue.claim(failedId);
      await queue.complete(failedId, { exitCode: 1 });
      expect((await queue.trace(failedId))!.status).toBe('FAILED');

      // CANCELLED
      const cancelledId = await queue.create(makeItem());
      await queue.cancel(cancelledId);
      expect((await queue.trace(cancelledId))!.status).toBe('CANCELLED');
    });

    it('should return null for non-existent', async () => {
      const result = await queue.trace('00000000-0000-0000-0000-999999999999');
      expect(result).toBeNull();
    });
  });

  describe('list', () => {
    it('should list items across all statuses', async () => {
      // Create at least one item so list is non-empty
      await queue.create(makeItem({ functionName: 'list-test' }));
      const items = await queue.list();
      expect(items.length).toBeGreaterThanOrEqual(1);
    });
  });

  describe('retry', () => {
    it('should move FAILED -> PENDING and increment retryCount', async () => {
      const taskId = await queue.create(makeItem());
      await queue.claim(taskId);
      await queue.complete(taskId, { exitCode: 1 });

      await queue.retry(taskId);

      const item = await queue.trace(taskId);
      expect(item!.status).toBe('PENDING');
      expect(item!.retryCount).toBe(1);
      expect(item!.errorMessage).toBeUndefined();
      expect(item!.exitCode).toBeUndefined();
    });
  });

  describe('delete', () => {
    it('should remove item from any status', async () => {
      const taskId = await queue.create(makeItem());
      await queue.delete(taskId);

      const item = await queue.trace(taskId);
      expect(item).toBeNull();
    });
  });

  describe('full lifecycle', () => {
    it('PENDING -> ACTIVE -> COMPLETED', async () => {
      const taskId = await queue.create(makeItem({ functionName: 'lifecycle-ok' }));

      let item = await queue.trace(taskId);
      expect(item!.status).toBe('PENDING');

      await queue.claim(taskId);
      item = await queue.trace(taskId);
      expect(item!.status).toBe('ACTIVE');

      await queue.complete(taskId, { exitCode: 0, consoleOutput: 'done' });
      item = await queue.trace(taskId);
      expect(item!.status).toBe('COMPLETED');
      expect(item!.exitCode).toBe(0);
    });

    it('PENDING -> ACTIVE -> FAILED -> retry -> PENDING -> ACTIVE -> COMPLETED', async () => {
      const taskId = await queue.create(makeItem({ functionName: 'lifecycle-retry' }));

      await queue.claim(taskId);
      await queue.complete(taskId, { exitCode: 1, errorMessage: 'first attempt failed' });

      let item = await queue.trace(taskId);
      expect(item!.status).toBe('FAILED');
      expect(item!.retryCount).toBe(0);

      await queue.retry(taskId);
      item = await queue.trace(taskId);
      expect(item!.status).toBe('PENDING');
      expect(item!.retryCount).toBe(1);

      await queue.claim(taskId);
      await queue.complete(taskId, { exitCode: 0, consoleOutput: 'success on retry' });
      item = await queue.trace(taskId);
      expect(item!.status).toBe('COMPLETED');
      expect(item!.retryCount).toBe(1);
    });

    it('PENDING -> CANCELLED', async () => {
      const taskId = await queue.create(makeItem({ functionName: 'lifecycle-cancel' }));
      await queue.cancel(taskId);

      const item = await queue.trace(taskId);
      expect(item!.status).toBe('CANCELLED');
    });
  });
});
