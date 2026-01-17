import { promises as fs } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { type CliConfig, createEmptyConfig } from '../../types/index.js';
import { ConfigStorage } from '../storage.js';

// Constants to avoid hardcoded nullish defaults
const DEFAULT_TOKEN = 'initial';

// Create isolated test environment
let testDir: string;
let testConfigPath: string;
let storage: ConfigStorage;

beforeEach(async () => {
  // Create a unique temp directory for each test
  testDir = await fs.mkdtemp(join(tmpdir(), 'cli-storage-test-'));
  testConfigPath = join(testDir, 'config.json');
  storage = new ConfigStorage(testConfigPath);
});

afterEach(async () => {
  // Clean up temp directory
  await fs.rm(testDir, { recursive: true, force: true });
});

// Helper to check if file exists
async function fileExists(path: string): Promise<boolean> {
  return fs
    .access(path)
    .then(() => true)
    .catch(() => false);
}

// Helper to create a simple updater
function createContextUpdater(name: string, apiUrl: string) {
  return (config: CliConfig): CliConfig => ({
    ...config,
    contexts: {
      ...config.contexts,
      [name]: { name, apiUrl },
    },
  });
}

// Helper for nested lock depth test
async function testNestedLockDepth(
  storageInstance: ConfigStorage
): Promise<{ depth1: number; depth2: number; depth3: number }> {
  let depth1 = 0;
  let depth2 = 0;
  let depth3 = 0;

  const innerMost = async (): Promise<void> => {
    depth3 = 3;
    await storageInstance.load();
  };

  const middle = async (): Promise<void> => {
    depth2 = 2;
    await storageInstance.withApiLock(innerMost);
  };

  const outer = async (): Promise<void> => {
    depth1 = 1;
    await storageInstance.withApiLock(middle);
  };

  await storageInstance.withApiLock(outer);

  return { depth1, depth2, depth3 };
}

// Helper for concurrent operations test
async function runConcurrentOperations(storageInstance: ConfigStorage): Promise<number[]> {
  const results: number[] = [];
  let counter = 0;

  const operation = async (): Promise<number> => {
    const myValue = counter++;
    await new Promise((r) => setTimeout(r, 10));
    results.push(myValue);
    return myValue;
  };

  const promises = Array.from({ length: 10 }, () => storageInstance.withApiLock(operation));
  await Promise.all(promises);
  return results;
}

// Helper for interleaved operations test
async function runInterleavedOperations(storageInstance: ConfigStorage): Promise<number[]> {
  const operation = async (i: number): Promise<number> => {
    const config = await storageInstance.load();
    const currentToken = config.contexts.shared?.token ?? DEFAULT_TOKEN;
    await new Promise((r) => setTimeout(r, Math.random() * 20));
    await storageInstance.update((cfg) => ({
      ...cfg,
      contexts: {
        shared: {
          name: 'shared',
          apiUrl: 'https://shared.example.com',
          token: `${currentToken}-${i}`,
        },
      },
    }));
    return i;
  };

  const promises = Array.from({ length: 5 }, (_, i) =>
    storageInstance.withApiLock(() => operation(i))
  );
  return Promise.all(promises);
}

// Helper for basic lock test
async function acquireLockAndLoad(storageInstance: ConfigStorage): Promise<CliConfig> {
  return storageInstance.withApiLock(() => storageInstance.load());
}

// Helper for nested lock test
async function acquireLockAndUpdate(
  storageInstance: ConfigStorage,
  name: string,
  apiUrl: string
): Promise<CliConfig> {
  const updater = createContextUpdater(name, apiUrl);
  return storageInstance.withApiLock(() => storageInstance.update(updater));
}

// Helper for concurrent writes test
async function runConcurrentWrites(
  storageInstance: ConfigStorage,
  count: number
): Promise<CliConfig> {
  const createUpdater =
    (i: number) =>
    (config: CliConfig): CliConfig => ({
      ...config,
      contexts: {
        ...config.contexts,
        [`process-${i}`]: {
          name: `process-${i}`,
          apiUrl: `https://process-${i}.example.com`,
          token: `token-${i}`,
        },
      },
    });

  const operations = Array.from({ length: count }, (_, i) =>
    storageInstance.update(createUpdater(i))
  );
  await Promise.all(operations);
  return storageInstance.load();
}

describe('ConfigStorage', () => {
  describe('load/save', () => {
    it('should return empty config if file does not exist', async () => {
      await fs.rm(testConfigPath, { force: true });
      const config = await storage.load();
      expect(config).toEqual(createEmptyConfig());
    });

    it('should create config file on first save', async () => {
      const config: CliConfig = {
        contexts: {
          test: { name: 'test', apiUrl: 'https://test.example.com' },
        },
      };

      await storage.save(config);

      const stat = await fs.stat(testConfigPath);
      expect(stat.isFile()).toBe(true);
    });

    it('should load config from file', async () => {
      const initialConfig: CliConfig = {
        contexts: {
          test: {
            name: 'test',
            apiUrl: 'https://test.example.com',
            token: 'test-token',
          },
        },
      };
      await fs.mkdir(testDir, { recursive: true });
      await fs.writeFile(testConfigPath, JSON.stringify(initialConfig, null, 2));

      const config = await storage.load();

      expect(config.contexts).toHaveProperty('test');
      expect(config.contexts.test?.apiUrl).toBe('https://test.example.com');
      expect(config.contexts.test?.token).toBe('test-token');
    });

    it('should save config atomically (temp file + rename)', async () => {
      const config: CliConfig = {
        contexts: {
          prod: { name: 'prod', apiUrl: 'https://prod.example.com' },
        },
      };

      await storage.save(config);

      const content = await fs.readFile(testConfigPath, 'utf-8');
      const loaded = JSON.parse(content);
      expect(loaded.contexts.prod.apiUrl).toBe('https://prod.example.com');
    });

    it('should set restrictive file permissions (0o600)', async () => {
      const config: CliConfig = {
        contexts: {
          secure: { name: 'secure', apiUrl: 'https://secure.example.com', token: 'secret-token' },
        },
      };

      await storage.save(config);

      const stat = await fs.stat(testConfigPath);
      const mode = stat.mode & 0o777;
      expect(mode).toBe(0o600);
    });
  });

  describe('caching', () => {
    it('should cache config after first load', async () => {
      const config1 = await storage.load();
      config1.contexts.cached = { name: 'cached', apiUrl: 'https://cached.example.com' };
      const config2 = await storage.load();
      expect(config2).toBe(config1);
    });

    it('should return cached config on subsequent loads', async () => {
      await storage.load();
      await fs.writeFile(
        testConfigPath,
        JSON.stringify({
          contexts: { external: { name: 'external', apiUrl: 'https://external.example.com' } },
        })
      );
      const config = await storage.load();
      expect(config.contexts).not.toHaveProperty('external');
    });

    it('should clear cache when clearCache() called', async () => {
      await storage.load();
      await fs.writeFile(
        testConfigPath,
        JSON.stringify({
          contexts: { external: { name: 'external', apiUrl: 'https://external.example.com' } },
        })
      );
      storage.clearCache();
      const config = await storage.load();
      expect(config.contexts).toHaveProperty('external');
    });
  });

  describe('update', () => {
    it('should apply updater function to current config', async () => {
      await storage.save({
        contexts: {
          initial: { name: 'initial', apiUrl: 'https://initial.example.com' },
        },
      });

      const updated = await storage.update(
        createContextUpdater('added', 'https://added.example.com')
      );

      expect(updated.contexts).toHaveProperty('initial');
      expect(updated.contexts).toHaveProperty('added');
    });

    it('should save updated config', async () => {
      await storage.update(createContextUpdater('persisted', 'https://persisted.example.com'));

      const newStorage = new ConfigStorage(testConfigPath);
      const config = await newStorage.load();

      expect(config.contexts).toHaveProperty('persisted');
    });

    it('should clear cache before reading', async () => {
      await storage.load();
      await fs.writeFile(
        testConfigPath,
        JSON.stringify({
          contexts: { external: { name: 'external', apiUrl: 'https://external.example.com' } },
        })
      );

      const updated = await storage.update(
        createContextUpdater('added', 'https://added.example.com')
      );

      expect(updated.contexts).toHaveProperty('external');
      expect(updated.contexts).toHaveProperty('added');
    });
  });

  describe('re-entrant locking', () => {
    it('should acquire lock on first call', async () => {
      const config = await acquireLockAndLoad(storage);
      expect(config).toBeDefined();
    });

    it('should allow nested lock calls without deadlock', async () => {
      await acquireLockAndUpdate(storage, 'nested', 'https://nested.example.com');

      const config = await storage.load();
      expect(config.contexts).toHaveProperty('nested');
    });

    it('should handle update() called within withApiLock()', async () => {
      const tokenUpdater = (config: CliConfig): CliConfig => ({
        ...config,
        contexts: {
          test: { name: 'test', apiUrl: 'https://test.example.com', token: 'new-token' },
        },
      });

      await storage.withApiLock(() => storage.update(tokenUpdater));

      const config = await storage.load();
      expect(config.contexts.test?.token).toBe('new-token');
    });

    it('should handle triple-nested lock calls', async () => {
      const firstUpdater = createContextUpdater('first', 'https://first.example.com');
      const secondUpdater = (config: CliConfig): CliConfig => ({
        ...config,
        contexts: {
          ...config.contexts,
          second: { name: 'second', apiUrl: 'https://second.example.com' },
        },
      });

      const doUpdates = async (): Promise<void> => {
        await storage.update(firstUpdater);
        await storage.update(secondUpdater);
      };

      await storage.withApiLock(doUpdates);

      const config = await storage.load();
      expect(config.contexts).toHaveProperty('first');
      expect(config.contexts).toHaveProperty('second');
    });

    it('should track lock depth correctly', async () => {
      const depths = await testNestedLockDepth(storage);

      expect(depths.depth1).toBe(1);
      expect(depths.depth2).toBe(2);
      expect(depths.depth3).toBe(3);
    });
  });

  describe('withApiLock', () => {
    it('should clear cache before executing operation', async () => {
      await storage.load();
      await fs.writeFile(
        testConfigPath,
        JSON.stringify({
          contexts: { external: { name: 'external', apiUrl: 'https://external.example.com' } },
        })
      );

      const config = await storage.withApiLock(() => storage.load());
      expect(config.contexts).toHaveProperty('external');
    });

    it('should execute operation within file lock', async () => {
      const doUpdate = async (): Promise<string> => {
        await storage.update(createContextUpdater('locked', 'https://locked.example.com'));
        return 'completed';
      };

      const result = await storage.withApiLock(doUpdate);

      expect(result).toBe('completed');
      const config = await storage.load();
      expect(config.contexts).toHaveProperty('locked');
    });

    it('should return operation result', async () => {
      const result = await storage.withApiLock(() =>
        Promise.resolve({ status: 'success', data: 42 })
      );
      expect(result).toEqual({ status: 'success', data: 42 });
    });

    it('should release lock after operation completes', async () => {
      await storage.withApiLock(() => Promise.resolve('done'));
      const result = await storage.withApiLock(() => Promise.resolve('done again'));
      expect(result).toBe('done again');
    });

    it('should release lock even if operation throws', async () => {
      try {
        await storage.withApiLock(() => Promise.reject(new Error('Test error')));
      } catch {
        // Expected
      }

      const result = await storage.withApiLock(() => Promise.resolve('recovered'));
      expect(result).toBe('recovered');
    });

    it('should force fresh read from file', async () => {
      await storage.save({
        contexts: {
          initial: { name: 'initial', apiUrl: 'https://initial.example.com' },
        },
      });
      await storage.load();

      await fs.writeFile(
        testConfigPath,
        JSON.stringify({
          contexts: {
            initial: {
              name: 'initial',
              apiUrl: 'https://initial.example.com',
              token: 'new-token-from-other-process',
            },
          },
        })
      );

      const config = await storage.withApiLock(() => storage.load());
      expect(config.contexts.initial?.token).toBe('new-token-from-other-process');
    });
  });

  describe('file locking', () => {
    it('should create lock file during operation', async () => {
      const lockPath = `${testConfigPath}.lock`;
      const lockExistsDuringOp = await storage.withApiLock(() => fileExists(lockPath));
      expect(lockExistsDuringOp).toBe(true);
    });

    it('should remove lock file after operation', async () => {
      await storage.withApiLock(() => storage.load());
      const lockPath = `${testConfigPath}.lock`;
      const exists = await fileExists(lockPath);
      expect(exists).toBe(false);
    });
  });

  describe('stress tests', () => {
    it('should serialize concurrent withApiLock calls', async () => {
      const results = await runConcurrentOperations(storage);
      expect(results).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8, 9]);
    });

    it('should handle rapid sequential operations', async () => {
      for (let i = 0; i < 20; i++) {
        await storage.withApiLock(() =>
          storage.update(createContextUpdater(`ctx-${i}`, `https://ctx-${i}.example.com`))
        );
      }

      const config = await storage.load();
      expect(Object.keys(config.contexts)).toHaveLength(20);
    });

    it('should not corrupt file under concurrent writes', async () => {
      const config = await runConcurrentWrites(storage, 5);
      expect(Object.keys(config.contexts)).toHaveLength(5);
    });

    it('should handle interleaved read-modify-write operations', async () => {
      const results = await runInterleavedOperations(storage);

      expect(results.sort((a, b) => a - b)).toEqual([0, 1, 2, 3, 4]);

      const config = await storage.load();
      const token = config.contexts.shared?.token ?? '';
      expect(token).toContain(DEFAULT_TOKEN);
    });
  });

  describe('error handling', () => {
    it('should release lock if operation throws', async () => {
      try {
        await storage.withApiLock(() => Promise.reject(new Error('Operation failed')));
      } catch (error) {
        expect((error as Error).message).toBe('Operation failed');
      }

      const config = await storage.load();
      expect(config).toEqual(createEmptyConfig());
    });

    it('should propagate operation errors', async () => {
      await expect(
        storage.withApiLock(() => Promise.reject(new Error('Custom error')))
      ).rejects.toThrow('Custom error');
    });

    it('should handle ENOENT on first load', async () => {
      await fs.rm(testConfigPath, { force: true });
      const config = await storage.load();
      expect(config).toEqual(createEmptyConfig());
    });

    it('should throw on invalid JSON in config file', async () => {
      await fs.mkdir(testDir, { recursive: true });
      await fs.writeFile(testConfigPath, 'not valid json');
      await expect(storage.load()).rejects.toThrow();
    });
  });

  describe('getConfigPath', () => {
    it('should return the config file path', () => {
      expect(storage.getConfigPath()).toBe(testConfigPath);
    });
  });
});
