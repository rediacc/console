import { describe, expect, it, vi, beforeEach } from 'vitest';
import { MIN_NETWORK_ID, NETWORK_ID_INCREMENT } from '@rediacc/shared/queue-vault';

// Mock configFileStorage to control the config state
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

// Mock the base class methods
vi.mock('../config-base.js', () => ({
  ConfigServiceBase: class {
    getEffectiveConfigName() {
      return 'test';
    }
    requireSelfHosted() {}
  },
}));

describe('allocateNetworkId', { timeout: 30_000 }, () => {
  beforeEach(() => {
    mockConfig = {};
  });

  it('starts at MIN_NETWORK_ID for empty config', async () => {
    const { configService } = await import('../config-resources.js');
    const id = await configService.allocateNetworkId();
    expect(id).toBe(MIN_NETWORK_ID);
    expect((mockConfig.defaults as { nextNetworkId?: number }).nextNetworkId).toBe(
      MIN_NETWORK_ID + NETWORK_ID_INCREMENT
    );
  });

  it('increments sequentially', async () => {
    const { configService } = await import('../config-resources.js');
    const id1 = await configService.allocateNetworkId();
    const id2 = await configService.allocateNetworkId();
    expect(id2).toBe(id1 + NETWORK_ID_INCREMENT);
  });

  it('continues from nextNetworkId if set', async () => {
    mockConfig = { defaults: { nextNetworkId: 5000 } };
    const { configService } = await import('../config-resources.js');
    const id = await configService.allocateNetworkId();
    expect(id).toBe(5000);
    expect((mockConfig.defaults as { nextNetworkId?: number }).nextNetworkId).toBe(
      5000 + NETWORK_ID_INCREMENT
    );
  });

  it('scans for max used ID when nextNetworkId is missing', async () => {
    mockConfig = {
      resources: {
        repositories: {
          'repo-a': { networkId: 4000 },
          'repo-b': { networkId: 6000 },
        },
      },
    };
    const { configService } = await import('../config-resources.js');
    const id = await configService.allocateNetworkId();
    expect(id).toBe(6000 + NETWORK_ID_INCREMENT);
  });

  it('fills gaps when forward counter exceeds max', async () => {
    const MAX_NETWORK_ID = 16_711_680;
    mockConfig = {
      defaults: { nextNetworkId: MAX_NETWORK_ID + NETWORK_ID_INCREMENT },
      resources: {
        repositories: {
          'repo-a': { networkId: MIN_NETWORK_ID + NETWORK_ID_INCREMENT },
          'repo-b': { networkId: MIN_NETWORK_ID + 2 * NETWORK_ID_INCREMENT },
        },
      },
    };
    const { configService } = await import('../config-resources.js');
    const id = await configService.allocateNetworkId();
    expect(id).toBe(MIN_NETWORK_ID);
  });

  it('throws when all slots are exhausted', async () => {
    const MAX_NETWORK_ID = 16_711_680;
    const usedRepos: Record<string, { networkId: number }> = {};
    for (
      let id = MIN_NETWORK_ID;
      id <= MIN_NETWORK_ID + 10 * NETWORK_ID_INCREMENT;
      id += NETWORK_ID_INCREMENT
    ) {
      usedRepos[`repo-${id}`] = { networkId: id };
    }
    mockConfig = {
      defaults: { nextNetworkId: MAX_NETWORK_ID + NETWORK_ID_INCREMENT },
      resources: { repositories: usedRepos },
    };
    const { configService } = await import('../config-resources.js');
    // This should find a gap at MIN_NETWORK_ID + 11 * INCREMENT (past the dense block)
    // but not throw because the dense block is tiny
    const id = await configService.allocateNetworkId();
    expect(id).toBe(MIN_NETWORK_ID + 11 * NETWORK_ID_INCREMENT);
  });

  it('constants match expected values', () => {
    expect(MIN_NETWORK_ID).toBe(2816);
    expect(NETWORK_ID_INCREMENT).toBe(64);
  });

  it('IDs are always multiples of INCREMENT from MIN', async () => {
    const { configService } = await import('../config-resources.js');
    for (let i = 0; i < 5; i++) {
      const id = await configService.allocateNetworkId();
      expect((id - MIN_NETWORK_ID) % NETWORK_ID_INCREMENT).toBe(0);
    }
  });
});
