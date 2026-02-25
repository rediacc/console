import { describe, expect, it, vi } from 'vitest';

// Mock configService used by LocalStateProvider
vi.mock('../../services/config-resources.js', () => ({
  configService: {
    listMachines: vi.fn().mockResolvedValue([]),
    addMachine: vi.fn().mockResolvedValue(undefined),
    removeMachine: vi.fn().mockResolvedValue(undefined),
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

  it('should have isCloud set to false', () => {
    const provider = new LocalStateProvider();
    expect(provider.isCloud).toBe(false);
  });
});
