import { beforeEach, describe, expect, it, vi } from 'vitest';
import { S3QueueService } from '../../services/s3-queue.js';
import { S3VaultService } from '../../services/s3-vault.js';
import type { S3ClientService } from '../../services/s3-client.js';

// Mock the crypto provider for vault tests
vi.mock('../../adapters/crypto.js', () => ({
  nodeCryptoProvider: {
    encrypt: vi.fn().mockImplementation((data: string, _password: string) => {
      return Promise.resolve(Buffer.from(`encrypted:${data}`).toString('base64'));
    }),
    decrypt: vi.fn().mockImplementation((data: string, _password: string) => {
      const decoded = Buffer.from(data, 'base64').toString();
      return Promise.resolve(decoded.replace('encrypted:', ''));
    }),
  },
}));

/**
 * Creates an in-memory mock of S3ClientService for testing.
 */
function createMockS3Client(): S3ClientService {
  const store = new Map<string, string>();

  return {
    getJson: vi.fn().mockImplementation(<T>(key: string): Promise<T | null> => {
      const content = store.get(key);
      if (!content) return Promise.resolve(null);
      return Promise.resolve(JSON.parse(content) as T);
    }),
    putJson: vi.fn().mockImplementation((key: string, data: unknown): Promise<void> => {
      store.set(key, JSON.stringify(data, null, 2));
      return Promise.resolve();
    }),
    getRaw: vi.fn().mockImplementation((key: string): Promise<string | null> => {
      return Promise.resolve(store.get(key) ?? null);
    }),
    putRaw: vi.fn().mockImplementation((key: string, content: string): Promise<void> => {
      store.set(key, content);
      return Promise.resolve();
    }),
    deleteObject: vi.fn().mockImplementation((key: string): Promise<void> => {
      store.delete(key);
      return Promise.resolve();
    }),
    listKeys: vi.fn().mockImplementation((prefix: string): Promise<string[]> => {
      return Promise.resolve(Array.from(store.keys()).filter((k) => k.startsWith(prefix)));
    }),
    verifyAccess: vi.fn().mockResolvedValue(undefined),
    moveObject: vi.fn().mockImplementation((from: string, to: string): Promise<void> => {
      const content = store.get(from);
      if (content) {
        store.set(to, content);
        store.delete(from);
      }
      return Promise.resolve();
    }),
  } as unknown as S3ClientService;
}

describe('S3QueueService', () => {
  let client: S3ClientService;
  let queue: S3QueueService;

  beforeEach(() => {
    client = createMockS3Client();
    queue = new S3QueueService(client);
  });

  it('should create a queue item in pending state', async () => {
    const taskId = await queue.create({
      functionName: 'test_func',
      teamName: 'test-team',
      vaultContent: '{}',
      priority: 3,
    });

    expect(taskId).toBeDefined();
    expect(typeof taskId).toBe('string');

    const item = await queue.trace(taskId);
    expect(item).not.toBeNull();
    expect(item!.status).toBe('PENDING');
  });

  it('should claim a pending item and move to active', async () => {
    const taskId = await queue.create({
      functionName: 'test_func',
      teamName: 'test-team',
      vaultContent: '{}',
      priority: 3,
    });

    const claimed = await queue.claim(taskId);
    expect(claimed.status).toBe('ACTIVE');
    expect(claimed.startedAt).toBeDefined();

    const traced = await queue.trace(taskId);
    expect(traced!.status).toBe('ACTIVE');
  });

  it('should complete an active item', async () => {
    const taskId = await queue.create({
      functionName: 'test_func',
      teamName: 'test-team',
      vaultContent: '{}',
      priority: 3,
    });

    await queue.claim(taskId);
    await queue.complete(taskId, { exitCode: 0 });

    const traced = await queue.trace(taskId);
    expect(traced!.status).toBe('COMPLETED');
    expect(traced!.exitCode).toBe(0);
  });

  it('should mark failed items', async () => {
    const taskId = await queue.create({
      functionName: 'test_func',
      teamName: 'test-team',
      vaultContent: '{}',
      priority: 3,
    });

    await queue.claim(taskId);
    await queue.complete(taskId, { exitCode: 1, errorMessage: 'Something failed' });

    const traced = await queue.trace(taskId);
    expect(traced!.status).toBe('FAILED');
    expect(traced!.exitCode).toBe(1);
    expect(traced!.errorMessage).toBe('Something failed');
  });

  it('should cancel a pending item', async () => {
    const taskId = await queue.create({
      functionName: 'test_func',
      teamName: 'test-team',
      vaultContent: '{}',
      priority: 3,
    });

    await queue.cancel(taskId);

    const traced = await queue.trace(taskId);
    expect(traced!.status).toBe('CANCELLED');
  });

  it('should retry a failed item', async () => {
    const taskId = await queue.create({
      functionName: 'test_func',
      teamName: 'test-team',
      vaultContent: '{}',
      priority: 3,
    });

    await queue.claim(taskId);
    await queue.complete(taskId, { exitCode: 1, errorMessage: 'fail' });

    await queue.retry(taskId);

    const traced = await queue.trace(taskId);
    expect(traced!.status).toBe('PENDING');
    expect(traced!.retryCount).toBe(1);
  });

  it('should delete a queue item', async () => {
    const taskId = await queue.create({
      functionName: 'test_func',
      teamName: 'test-team',
      vaultContent: '{}',
      priority: 3,
    });

    await queue.delete(taskId);

    const traced = await queue.trace(taskId);
    expect(traced).toBeNull();
  });

  it('should list queue items', async () => {
    const taskId1 = await queue.create({
      functionName: 'func1',
      teamName: 'test-team',
      vaultContent: '{}',
      priority: 3,
    });

    const taskId2 = await queue.create({
      functionName: 'func2',
      teamName: 'test-team',
      vaultContent: '{}',
      priority: 5,
    });

    const items = await queue.list();
    expect(items.length).toBeGreaterThanOrEqual(2);
    const taskIds = items.map((i) => i.taskId);
    expect(taskIds).toContain(taskId1);
    expect(taskIds).toContain(taskId2);
  });

  it('should throw when claiming non-existent item', async () => {
    await expect(queue.claim('non-existent')).rejects.toThrow('not found');
  });

  it('should throw when completing non-existent item', async () => {
    await expect(queue.complete('non-existent', { exitCode: 0 })).rejects.toThrow('not found');
  });
});

describe('S3VaultService', () => {
  let client: S3ClientService;
  let vault: S3VaultService;

  beforeEach(() => {
    client = createMockS3Client();
    vault = new S3VaultService(client, 'test-password');
  });

  it('should write and read encrypted vault data', async () => {
    const data = { SSH_PRIVATE_KEY: 'key-content', SSH_PUBLIC_KEY: 'pub-content' };
    await vault.setTeamVault(data);

    const result = await vault.getTeamVault();
    expect(result).toEqual(data);
  });

  it('should write and read machine vault', async () => {
    const data = { ip: '10.0.0.1', user: 'root', known_hosts: 'host-data' };
    await vault.setMachineVault('test-machine', data);

    const result = await vault.getMachineVault('test-machine');
    expect(result).toEqual(data);
  });

  it('should return null for non-existent vault', async () => {
    const result = await vault.getMachineVault('does-not-exist');
    expect(result).toBeNull();
  });

  it('should write and read organization vault', async () => {
    const data = { org_key: 'org-value' };
    await vault.setOrganizationVault(data);

    const result = await vault.getOrganizationVault();
    expect(result).toEqual(data);
  });
});
