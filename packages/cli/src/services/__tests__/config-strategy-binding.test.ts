import { beforeEach, describe, expect, it, vi } from 'vitest';

// Mock configFileStorage — required by the module graph, unused by these tests.
let mockConfig: Record<string, unknown> = {};

vi.mock('../../adapters/config-file-storage.js', () => ({
  configFileStorage: {
    update: vi.fn(
      (_name: string, fn: (cfg: Record<string, unknown>) => Record<string, unknown>) => {
        mockConfig = fn(mockConfig);
      }
    ),
    read: vi.fn(() => mockConfig),
  },
}));

interface TestMachine {
  ip: string;
  user: string;
  backupStrategies?: string[];
}

let mockMachines: Record<string, TestMachine> = {};
let mockStrategies: Record<string, { destinations: unknown[]; schedule: string }> = {};

vi.mock('../config/config-base.js', () => ({
  ConfigServiceBase: class {
    getEffectiveConfigName() {
      return 'test';
    }
    // ConfigService overrides requireSelfHosted() and resolves it through
    // getCurrent(), so the strategies have to be reachable from HERE — mocking
    // requireSelfHosted on the base class would never be consulted.
    getCurrent() {
      return Promise.resolve({ version: 1, resources: { backupStrategies: mockStrategies } });
    }
    getResourceState() {
      return Promise.resolve({
        getMachines: () => mockMachines,
        setMachines: (m: Record<string, TestMachine>) => {
          mockMachines = m;
          return Promise.resolve();
        },
      });
    }
  },
}));

// See config-resources-guid-map.test.ts: the per-test dynamic import cold-loads
// the full config module graph, which can exceed the 5s default on CI.
describe('backup strategy binding', { timeout: 30000 }, () => {
  beforeEach(() => {
    mockConfig = {};
    mockMachines = { hostinger: { ip: '1.2.3.4', user: 'root' } };
    mockStrategies = { 'weekly-cold': { destinations: [], schedule: '15 3 * * 0' } };
  });

  const load = async () => await import('../config/config-strategy-binding.js');

  it('binds a strategy to a machine', async () => {
    const svc = await load();
    await expect(svc.bindBackupStrategy('hostinger', 'weekly-cold')).resolves.toBe(true);
    expect(mockMachines.hostinger.backupStrategies).toEqual(['weekly-cold']);
  });

  // Re-binding must not duplicate: backup schedule iterates this list to build
  // systemd units, so a duplicate entry would deploy the same unit twice.
  it('is idempotent and reports that the binding already existed', async () => {
    const svc = await load();
    await svc.bindBackupStrategy('hostinger', 'weekly-cold');
    await expect(svc.bindBackupStrategy('hostinger', 'weekly-cold')).resolves.toBe(false);
    expect(mockMachines.hostinger.backupStrategies).toEqual(['weekly-cold']);
  });

  it('refuses to bind a strategy that does not exist', async () => {
    const svc = await load();
    await expect(svc.bindBackupStrategy('hostinger', 'ghost')).rejects.toThrow(/not found/);
    expect(mockMachines.hostinger.backupStrategies).toBeUndefined();
  });

  it('refuses to bind to a machine that does not exist', async () => {
    const svc = await load();
    await expect(svc.bindBackupStrategy('nope', 'weekly-cold')).rejects.toThrow(/not found/);
  });

  it('unbinds a strategy, preserving the others', async () => {
    mockStrategies['twiceweekly-hot'] = { destinations: [], schedule: '0 22 * * 2,4' };
    mockMachines.hostinger.backupStrategies = ['weekly-cold', 'twiceweekly-hot'];
    const svc = await load();
    await expect(svc.unbindBackupStrategy('hostinger', 'weekly-cold')).resolves.toBe(true);
    expect(mockMachines.hostinger.backupStrategies).toEqual(['twiceweekly-hot']);
  });

  // config-refs-prune writes `undefined`, not `[]`, when it drops the last
  // dangling ref. Diverging here would give the same logical state two on-disk
  // spellings depending on which code path emptied the list.
  it('collapses an emptied binding list to undefined, matching prune', async () => {
    mockMachines.hostinger.backupStrategies = ['weekly-cold'];
    const svc = await load();
    await svc.unbindBackupStrategy('hostinger', 'weekly-cold');
    expect(mockMachines.hostinger.backupStrategies).toBeUndefined();
  });

  it('reports a no-op when unbinding something that was never bound', async () => {
    const svc = await load();
    await expect(svc.unbindBackupStrategy('hostinger', 'weekly-cold')).resolves.toBe(false);
  });
});
