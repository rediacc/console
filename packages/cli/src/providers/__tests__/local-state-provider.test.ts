import { describe, expect, it, vi } from 'vitest';

// Mock contextService used by LocalStateProvider
vi.mock('../../services/context.js', () => ({
  contextService: {
    listLocalMachines: vi.fn().mockResolvedValue([]),
    addLocalMachine: vi.fn().mockResolvedValue(undefined),
    removeLocalMachine: vi.fn().mockResolvedValue(undefined),
    getLocalConfig: vi.fn().mockResolvedValue({
      machines: {},
      ssh: { privateKeyPath: '' },
      renetPath: '/usr/bin/renet',
    }),
  },
}));

// Mock machine-status used by getWithVaultStatus
vi.mock('../../services/machine-status.js', () => ({
  fetchMachineStatus: vi.fn().mockResolvedValue({ containers: [], services: [] }),
}));

const { LocalStateProvider } = await import('../local-state-provider.js');

describe('LocalStateProvider', () => {
  describe('machines.getWithVaultStatus', () => {
    it('should return machine status data', async () => {
      const provider = new LocalStateProvider();

      const result = await provider.machines.getWithVaultStatus({
        teamName: 'team',
        machineName: 'machine',
      });
      expect(result).toMatchObject({ machineName: 'machine' });
      expect(result?.vaultStatus).toBeDefined();
    });
  });

  it('should have mode set to local', () => {
    const provider = new LocalStateProvider();
    expect(provider.mode).toBe('local');
  });
});
