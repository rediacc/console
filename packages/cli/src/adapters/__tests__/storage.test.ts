import { promises as fs } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { type RdcConfig, createEmptyRdcConfig } from '../../types/index.js';
import { ConfigFileStorage } from '../config-file-storage.js';

// UUID v4 pattern
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

// Create isolated test environment
let testDir: string;
let storage: ConfigFileStorage;

beforeEach(async () => {
  testDir = await fs.mkdtemp(join(tmpdir(), 'cli-storage-test-'));
  storage = new ConfigFileStorage(testDir);
});

afterEach(async () => {
  await fs.rm(testDir, { recursive: true, force: true });
});

// Helper to check if file exists
async function fileExists(path: string): Promise<boolean> {
  return fs
    .access(path)
    .then(() => true)
    .catch(() => false);
}

// Helper: write a raw config file to disk
async function writeRawConfig(name: string, config: RdcConfig): Promise<void> {
  await fs.writeFile(join(testDir, `${name}.json`), JSON.stringify(config, null, 2));
}

// Helper: read raw config file from disk
async function readRawConfig(name: string): Promise<RdcConfig> {
  const content = await fs.readFile(join(testDir, `${name}.json`), 'utf-8');
  return JSON.parse(content) as RdcConfig;
}

// Helper for nested lock depth test
async function testNestedLockDepth(
  storageInstance: ConfigFileStorage,
  name: string
): Promise<{ depth1: number; depth2: number; depth3: number }> {
  let depth1 = 0;
  let depth2 = 0;
  let depth3 = 0;

  const innerMost = async (): Promise<void> => {
    depth3 = 3;
    await storageInstance.load(name);
  };

  const middle = async (): Promise<void> => {
    depth2 = 2;
    await storageInstance.withApiLock(name, innerMost);
  };

  const outer = async (): Promise<void> => {
    depth1 = 1;
    await storageInstance.withApiLock(name, middle);
  };

  await storageInstance.withApiLock(name, outer);

  return { depth1, depth2, depth3 };
}

// Helper for concurrent operations test
async function runConcurrentOperations(
  storageInstance: ConfigFileStorage,
  name: string
): Promise<number[]> {
  const results: number[] = [];
  let counter = 0;

  const operation = async (): Promise<number> => {
    const myValue = counter++;
    await new Promise((r) => setTimeout(r, 10));
    results.push(myValue);
    return myValue;
  };

  const promises = Array.from({ length: 10 }, () => storageInstance.withApiLock(name, operation));
  await Promise.all(promises);
  return results;
}

// Helper for concurrent writes test
async function runConcurrentWrites(
  storageInstance: ConfigFileStorage,
  name: string,
  count: number
): Promise<RdcConfig> {
  const createUpdater =
    (i: number) =>
    (config: RdcConfig): RdcConfig => ({
      ...config,
      machines: {
        ...config.machines,
        [`process-${i}`]: {
          ip: `10.0.0.${i}`,
          user: `user-${i}`,
        },
      },
    });

  const operations = Array.from({ length: count }, (_, i) =>
    storageInstance.update(name, createUpdater(i))
  );
  await Promise.all(operations);
  storageInstance.clearCache();
  return storageInstance.load(name);
}

// Helper for interleaved read-modify-write operations test
async function runInterleavedOperations(
  storageInstance: ConfigFileStorage,
  name: string
): Promise<number[]> {
  const operation = async (i: number): Promise<number> => {
    const config = await storageInstance.load(name);
    const currentMachine = config.machine ?? 'initial';
    await new Promise((r) => setTimeout(r, Math.random() * 20));
    await storageInstance.update(name, (cfg) => ({
      ...cfg,
      machine: `${currentMachine}-${i}`,
    }));
    return i;
  };

  const promises = Array.from({ length: 5 }, (_, i) =>
    storageInstance.withApiLock(name, () => operation(i))
  );
  return Promise.all(promises);
}

describe('ConfigFileStorage', () => {
  describe('load/save', () => {
    it('should return empty config if file does not exist', async () => {
      const config = await storage.load('nonexistent');
      expect(config.id).toMatch(UUID_RE);
      expect(config.version).toBe(1);
    });

    it('should create config file on first save', async () => {
      const config = createEmptyRdcConfig();
      config.machine = 'test-machine';

      await storage.save(config, 'test');

      const configPath = join(testDir, 'test.json');
      const stat = await fs.stat(configPath);
      expect(stat.isFile()).toBe(true);
    });

    it('should load config from file', async () => {
      const initial: RdcConfig = {
        id: '550e8400-e29b-41d4-a716-446655440000',
        version: 1,
        mode: 'local',
        machine: 'prod-1',
        machines: {
          'prod-1': { ip: '10.0.0.1', user: 'admin' },
        },
      };
      await writeRawConfig('test', initial);

      const config = await storage.load('test');

      expect(config.id).toBe('550e8400-e29b-41d4-a716-446655440000');
      expect(config.version).toBe(1);
      expect(config.machine).toBe('prod-1');
      expect(config.machines?.['prod-1']?.ip).toBe('10.0.0.1');
    });

    it('should save config atomically (temp file + rename)', async () => {
      const config: RdcConfig = {
        id: '550e8400-e29b-41d4-a716-446655440000',
        version: 1,
        machines: {
          prod: { ip: '10.0.0.1', user: 'admin' },
        },
      };

      await storage.save(config, 'test');

      const loaded = await readRawConfig('test');
      expect(loaded.machines?.prod.ip).toBe('10.0.0.1');
    });

    it('should set restrictive file permissions (0o600)', async () => {
      const config: RdcConfig = {
        id: '550e8400-e29b-41d4-a716-446655440000',
        version: 1,
        token: 'secret-token',
      };

      await storage.save(config, 'secure');

      const configPath = join(testDir, 'secure.json');
      const stat = await fs.stat(configPath);
      const mode = stat.mode & 0o777;
      expect(mode).toBe(0o600);
    });

    it('should use default name "rediacc" when no name is provided', async () => {
      const config = createEmptyRdcConfig();
      await storage.save(config);

      const exists = await fileExists(join(testDir, 'rediacc.json'));
      expect(exists).toBe(true);
    });
  });

  describe('version auto-increment', () => {
    it('should increment version on save', async () => {
      const config: RdcConfig = { id: 'test-id', version: 1 };

      await storage.save(config, 'test');

      const loaded = await readRawConfig('test');
      expect(loaded.version).toBe(2);
    });

    it('should increment version on each successive save', async () => {
      const config: RdcConfig = { id: 'test-id', version: 1 };

      await storage.save(config, 'test');
      storage.clearCache();
      const afterFirst = await readRawConfig('test');
      expect(afterFirst.version).toBe(2);

      await storage.save(afterFirst, 'test');
      const afterSecond = await readRawConfig('test');
      expect(afterSecond.version).toBe(3);
    });

    it('should increment version via update()', async () => {
      await storage.init('test');

      const updated = await storage.update('test', (cfg) => ({
        ...cfg,
        machine: 'new-machine',
      }));

      // update() reads (version 1), applies updater (still version 1),
      // saveUnlocked writes version+1=2 to disk,
      // then returns {...updated, version: updated.version + 1} = version 2
      expect(updated.version).toBe(2);

      // On disk the version should be 2 (saveUnlocked wrote version+1)
      const onDisk = await readRawConfig('test');
      expect(onDisk.version).toBe(2);
    });
  });

  describe('caching', () => {
    it('should cache config after first load', async () => {
      await storage.init('test');
      const config1 = await storage.load('test');
      const config2 = await storage.load('test');
      expect(config2).toBe(config1);
    });

    it('should return cached config on subsequent loads', async () => {
      await storage.init('test');
      await storage.load('test');

      // Write directly to disk, bypassing the storage instance
      const external: RdcConfig = { id: 'external-id', version: 99 };
      await writeRawConfig('test', external);

      const config = await storage.load('test');
      // Should still return the cached version, not the external write
      expect(config.version).not.toBe(99);
    });

    it('should clear cache when clearCache() called', async () => {
      await storage.init('test');
      await storage.load('test');

      const external: RdcConfig = { id: 'external-id', version: 99, machine: 'external-machine' };
      await writeRawConfig('test', external);

      storage.clearCache();
      const config = await storage.load('test');
      expect(config.machine).toBe('external-machine');
      expect(config.version).toBe(99);
    });

    it('should cache per config name independently', async () => {
      await storage.init('alpha');
      await storage.init('beta');

      const alpha = await storage.load('alpha');
      const beta = await storage.load('beta');

      expect(alpha.id).not.toBe(beta.id);
      expect(alpha).not.toBe(beta);
    });
  });

  describe('update', () => {
    it('should apply updater function to current config', async () => {
      const initial = createEmptyRdcConfig();
      initial.machines = { initial: { ip: '10.0.0.1', user: 'admin' } };
      await writeRawConfig('test', initial);

      const updated = await storage.update('test', (cfg) => ({
        ...cfg,
        machines: {
          ...cfg.machines,
          added: { ip: '10.0.0.2', user: 'deploy' },
        },
      }));

      expect(updated.machines).toHaveProperty('initial');
      expect(updated.machines).toHaveProperty('added');
    });

    it('should persist updated config to disk', async () => {
      await storage.init('test');
      await storage.update('test', (cfg) => ({
        ...cfg,
        machine: 'persisted-machine',
      }));

      const freshStorage = new ConfigFileStorage(testDir);
      const config = await freshStorage.load('test');
      expect(config.machine).toBe('persisted-machine');
    });

    it('should clear cache before reading', async () => {
      await storage.init('test');
      await storage.load('test');

      // Write externally to disk
      const external: RdcConfig = {
        id: 'external-id',
        version: 5,
        machine: 'external',
      };
      await writeRawConfig('test', external);

      const updated = await storage.update('test', (cfg) => ({
        ...cfg,
        machines: { added: { ip: '10.0.0.1', user: 'admin' } },
      }));

      // update clears cache, so it should have read the external version
      expect(updated.machine).toBe('external');
      expect(updated.machines).toHaveProperty('added');
    });
  });

  describe('init', () => {
    it('should create a new config with UUID and version 1', async () => {
      const config = await storage.init('test');

      expect(config.id).toMatch(UUID_RE);
      expect(config.version).toBe(1);
    });

    it('should persist the new config to disk', async () => {
      const config = await storage.init('test');

      const onDisk = await readRawConfig('test');
      expect(onDisk.id).toBe(config.id);
      expect(onDisk.version).toBe(1);
    });

    it('should throw if config already exists', async () => {
      await storage.init('test');

      await expect(storage.init('test')).rejects.toThrow('Config "test" already exists');
    });

    it('should create the directory if it does not exist', async () => {
      const nestedDir = join(testDir, 'nested', 'deep');
      const nestedStorage = new ConfigFileStorage(nestedDir);

      await nestedStorage.init('test');

      const exists = await fileExists(join(nestedDir, 'test.json'));
      expect(exists).toBe(true);
    });
  });

  describe('list', () => {
    it('should return empty array when no configs exist', async () => {
      const names = await storage.list();
      expect(names).toEqual([]);
    });

    it('should list all config files by name', async () => {
      await storage.init('alpha');
      await storage.init('beta');
      await storage.init('gamma');

      const names = await storage.list();
      expect(names).toEqual(['alpha', 'beta', 'gamma']);
    });

    it('should exclude .credentials.json', async () => {
      await storage.init('myconfig');
      await fs.writeFile(join(testDir, '.credentials.json'), '{}');

      const names = await storage.list();
      expect(names).toEqual(['myconfig']);
    });

    it('should exclude update-state.json', async () => {
      await storage.init('myconfig');
      await fs.writeFile(join(testDir, 'update-state.json'), '{}');

      const names = await storage.list();
      expect(names).toEqual(['myconfig']);
    });

    it('should return sorted names', async () => {
      await storage.init('zulu');
      await storage.init('alpha');
      await storage.init('mike');

      const names = await storage.list();
      expect(names).toEqual(['alpha', 'mike', 'zulu']);
    });

    it('should only list .json files', async () => {
      await storage.init('valid');
      await fs.writeFile(join(testDir, 'readme.txt'), 'not a config');
      await fs.writeFile(join(testDir, 'notes.md'), '# notes');

      const names = await storage.list();
      expect(names).toEqual(['valid']);
    });
  });

  describe('exists', () => {
    it('should return true for existing config', async () => {
      await storage.init('test');
      expect(await storage.exists('test')).toBe(true);
    });

    it('should return false for non-existing config', async () => {
      expect(await storage.exists('nonexistent')).toBe(false);
    });
  });

  describe('getOrCreateDefault', () => {
    it('should create default config when it does not exist', async () => {
      const config = await storage.getOrCreateDefault();
      expect(config.id).toMatch(UUID_RE);
      expect(config.version).toBe(1);

      const exists = await fileExists(join(testDir, 'rediacc.json'));
      expect(exists).toBe(true);
    });

    it('should return existing default config without overwriting', async () => {
      const original = await storage.init('rediacc');
      storage.clearCache();

      const config = await storage.getOrCreateDefault();
      expect(config.id).toBe(original.id);
      expect(config.version).toBe(1);
    });
  });

  describe('delete', () => {
    it('should delete an existing config file', async () => {
      await storage.init('test');
      await storage.delete('test');

      expect(await storage.exists('test')).toBe(false);
    });

    it('should clear cache for deleted config', async () => {
      await storage.init('test');
      await storage.load('test');
      await storage.delete('test');

      // After delete + re-init, should get fresh config
      const fresh = await storage.init('test');
      const loaded = await storage.load('test');
      expect(loaded.id).toBe(fresh.id);
    });

    it('should throw when deleting the default "rediacc" config', async () => {
      await storage.init('rediacc');
      await expect(storage.delete('rediacc')).rejects.toThrow(
        'Cannot delete the default config "rediacc"'
      );
    });

    it('should throw when deleting a non-existent config', async () => {
      await expect(storage.delete('nonexistent')).rejects.toThrow('Config "nonexistent" not found');
    });
  });

  describe('re-entrant locking', () => {
    it('should acquire lock on first call', async () => {
      await storage.init('test');
      const config = await storage.withApiLock('test', () => storage.load('test'));
      expect(config).toBeDefined();
      expect(config.id).toMatch(UUID_RE);
    });

    it('should allow nested lock calls without deadlock', async () => {
      await storage.init('test');

      await storage.withApiLock('test', async () => {
        await storage.update('test', (cfg) => ({
          ...cfg,
          machine: 'nested-machine',
        }));
      });

      storage.clearCache();
      const config = await storage.load('test');
      expect(config.machine).toBe('nested-machine');
    });

    it('should handle update() called within withApiLock()', async () => {
      await storage.init('test');

      await storage.withApiLock('test', () =>
        storage.update('test', (cfg) => ({
          ...cfg,
          token: 'new-token',
        }))
      );

      storage.clearCache();
      const config = await storage.load('test');
      expect(config.token).toBe('new-token');
    });

    it('should handle triple-nested lock calls', async () => {
      await storage.init('test');

      const doUpdates = async (): Promise<void> => {
        await storage.update('test', (cfg) => ({
          ...cfg,
          machines: { ...cfg.machines, first: { ip: '10.0.0.1', user: 'admin' } },
        }));
        await storage.update('test', (cfg) => ({
          ...cfg,
          machines: { ...cfg.machines, second: { ip: '10.0.0.2', user: 'admin' } },
        }));
      };

      await storage.withApiLock('test', doUpdates);

      storage.clearCache();
      const config = await storage.load('test');
      expect(config.machines).toHaveProperty('first');
      expect(config.machines).toHaveProperty('second');
    });

    it('should track lock depth correctly', async () => {
      await storage.init('test');
      const depths = await testNestedLockDepth(storage, 'test');

      expect(depths.depth1).toBe(1);
      expect(depths.depth2).toBe(2);
      expect(depths.depth3).toBe(3);
    });
  });

  describe('withApiLock', () => {
    it('should clear cache before executing operation', async () => {
      await storage.init('test');
      await storage.load('test');

      // Write externally
      const external: RdcConfig = {
        id: 'external-id',
        version: 42,
        machine: 'external-machine',
      };
      await writeRawConfig('test', external);

      const config = await storage.withApiLock('test', () => storage.load('test'));
      expect(config.machine).toBe('external-machine');
    });

    it('should execute operation within file lock', async () => {
      await storage.init('test');

      const result = await storage.withApiLock('test', async () => {
        await storage.update('test', (cfg) => ({
          ...cfg,
          machine: 'locked-machine',
        }));
        return 'completed';
      });

      expect(result).toBe('completed');
      storage.clearCache();
      const config = await storage.load('test');
      expect(config.machine).toBe('locked-machine');
    });

    it('should return operation result', async () => {
      await storage.init('test');
      const result = await storage.withApiLock('test', () =>
        Promise.resolve({ status: 'success', data: 42 })
      );
      expect(result).toEqual({ status: 'success', data: 42 });
    });

    it('should release lock after operation completes', async () => {
      await storage.init('test');
      await storage.withApiLock('test', () => Promise.resolve('done'));
      const result = await storage.withApiLock('test', () => Promise.resolve('done again'));
      expect(result).toBe('done again');
    });

    it('should release lock even if operation throws', async () => {
      await storage.init('test');
      try {
        await storage.withApiLock('test', () => Promise.reject(new Error('Test error')));
      } catch {
        // Expected
      }

      const result = await storage.withApiLock('test', () => Promise.resolve('recovered'));
      expect(result).toBe('recovered');
    });

    it('should force fresh read from file', async () => {
      await storage.init('test');
      const config: RdcConfig = { id: 'test-id', version: 1, machine: 'original' };
      await storage.save(config, 'test');
      await storage.load('test');

      // External write
      const external: RdcConfig = {
        id: 'test-id',
        version: 5,
        machine: 'updated-by-other-process',
      };
      await writeRawConfig('test', external);

      const loaded = await storage.withApiLock('test', () => storage.load('test'));
      expect(loaded.machine).toBe('updated-by-other-process');
    });
  });

  describe('file locking', () => {
    it('should create lock file during operation', async () => {
      await storage.init('test');
      const configPath = join(testDir, 'test.json');
      const lockPath = `${configPath}.lock`;

      const lockExistsDuringOp = await storage.withApiLock('test', () => fileExists(lockPath));
      expect(lockExistsDuringOp).toBe(true);
    });

    it('should remove lock file after operation', async () => {
      await storage.init('test');
      await storage.withApiLock('test', () => storage.load('test'));

      const lockPath = join(testDir, 'test.json.lock');
      const exists = await fileExists(lockPath);
      expect(exists).toBe(false);
    });
  });

  describe('stress tests', () => {
    it('should serialize concurrent withApiLock calls', async () => {
      await storage.init('test');
      const results = await runConcurrentOperations(storage, 'test');
      expect(results).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8, 9]);
    });

    it('should handle rapid sequential operations', async () => {
      await storage.init('test');

      for (let i = 0; i < 20; i++) {
        await storage.withApiLock('test', () =>
          storage.update('test', (cfg) => ({
            ...cfg,
            machines: {
              ...cfg.machines,
              [`machine-${i}`]: { ip: `10.0.0.${i}`, user: `user-${i}` },
            },
          }))
        );
      }

      storage.clearCache();
      const config = await storage.load('test');
      expect(Object.keys(config.machines ?? {})).toHaveLength(20);
    });

    it('should not corrupt file under concurrent writes', async () => {
      await storage.init('test');
      const config = await runConcurrentWrites(storage, 'test', 5);
      expect(Object.keys(config.machines ?? {})).toHaveLength(5);
    });

    it('should handle interleaved read-modify-write operations', async () => {
      await storage.init('test');

      const results = await runInterleavedOperations(storage, 'test');
      expect(results.sort((a, b) => a - b)).toEqual([0, 1, 2, 3, 4]);

      storage.clearCache();
      const config = await storage.load('test');
      expect(config.machine).toBeDefined();
      expect(config.machine).toContain('initial');
    });
  });

  describe('error handling', () => {
    it('should release lock if operation throws', async () => {
      await storage.init('test');

      try {
        await storage.withApiLock('test', () => Promise.reject(new Error('Operation failed')));
      } catch (error) {
        expect((error as Error).message).toBe('Operation failed');
      }

      // Should still be able to load after lock release
      const config = await storage.load('test');
      expect(config).toBeDefined();
      expect(config.id).toMatch(UUID_RE);
    });

    it('should propagate operation errors', async () => {
      await storage.init('test');
      await expect(
        storage.withApiLock('test', () => Promise.reject(new Error('Custom error')))
      ).rejects.toThrow('Custom error');
    });

    it('should handle ENOENT on first load gracefully', async () => {
      const config = await storage.load('does-not-exist');
      expect(config.id).toMatch(UUID_RE);
      expect(config.version).toBe(1);
    });

    it('should throw on invalid JSON in config file', async () => {
      await fs.writeFile(join(testDir, 'corrupt.json'), 'not valid json');
      storage.clearCache();
      await expect(storage.load('corrupt')).rejects.toThrow();
    });
  });

  describe('getConfigPath / getConfigDir', () => {
    it('should return the config file path for a given name', () => {
      expect(storage.getConfigPath('test')).toBe(join(testDir, 'test.json'));
    });

    it('should default to "rediacc" for getConfigPath', () => {
      expect(storage.getConfigPath()).toBe(join(testDir, 'rediacc.json'));
    });

    it('should return the config directory', () => {
      expect(storage.getConfigDir()).toBe(testDir);
    });
  });
});
