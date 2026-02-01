import { describe, expect, it, vi } from 'vitest';

// Mock contextService used by LocalStateProvider
vi.mock('../../services/context.js', () => ({
  contextService: {
    listLocalMachines: vi.fn().mockResolvedValue([]),
    addLocalMachine: vi.fn().mockResolvedValue(undefined),
    removeLocalMachine: vi.fn().mockResolvedValue(undefined),
  },
}));

const { LocalStateProvider } = await import('../local-state-provider.js');

describe('LocalStateProvider', () => {
  describe('machines.getWithVaultStatus', () => {
    it('should reject with UnsupportedOperationError', async () => {
      const provider = new LocalStateProvider();

      await expect(
        provider.machines.getWithVaultStatus({ teamName: 'team', machineName: 'machine' })
      ).rejects.toThrow('"machine vault status" is not supported in local mode');
    });

    it('should reject with error named UnsupportedOperationError', async () => {
      const provider = new LocalStateProvider();

      await expect(
        provider.machines.getWithVaultStatus({ teamName: 'team', machineName: 'machine' })
      ).rejects.toMatchObject({ name: 'UnsupportedOperationError' });
    });
  });

  it('should have mode set to local', () => {
    const provider = new LocalStateProvider();
    expect(provider.mode).toBe('local');
  });
});
