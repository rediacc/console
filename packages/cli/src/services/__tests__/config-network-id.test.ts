import { MIN_NETWORK_ID, NETWORK_ID_INCREMENT } from '@rediacc/shared/renet-contract';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// Mock configFileStorage to control the config state. In v3 the network-id counter and the used-id inventory live in the `state` half, written via `updateState` (no version bump).
let mockConfig: Record<string, unknown> = {};

const stateMutator = (
  _name: string,
  fn: (cfg: Record<string, unknown>) => Record<string, unknown>
) => {
  mockConfig = fn(mockConfig);
};

vi.mock('../../adapters/config-file-storage.js', () => ({
  configFileStorage: {
    update: vi.fn(stateMutator),
    updateState: vi.fn(stateMutator),
    read: vi.fn(() => mockConfig),
  },
}));

vi.mock('../config/config-base.js', () => ({
  ConfigServiceBase: class {
    getEffectiveConfigName() {
      return 'test';
    }
    requireSelfHosted() {}
  },
}));

function next(): number | undefined {
  return (mockConfig.state as { networkIds?: { next?: number } } | undefined)?.networkIds?.next;
}

/** Build a state.repos map assigning one networkId per repo under tag `main`. */
function reposState(ids: Record<string, number>): Record<string, unknown> {
  const repos: Record<string, unknown> = {};
  for (const [name, networkId] of Object.entries(ids)) repos[name] = { main: { networkId } };
  return { repos };
}

describe('allocateNetworkId', { timeout: 30_000 }, () => {
  beforeEach(() => {
    mockConfig = {};
  });

  it('starts at MIN_NETWORK_ID for empty config', async () => {
    const { configService } = await import('../config/config-resources.js');
    const id = await configService.allocateNetworkId();
    expect(id).toBe(MIN_NETWORK_ID);
    expect(next()).toBe(MIN_NETWORK_ID + NETWORK_ID_INCREMENT);
  });

  it('increments sequentially', async () => {
    const { configService } = await import('../config/config-resources.js');
    const id1 = await configService.allocateNetworkId();
    const id2 = await configService.allocateNetworkId();
    expect(id2).toBe(id1 + NETWORK_ID_INCREMENT);
  });

  it('continues from state.networkIds.next if set', async () => {
    mockConfig = { state: { networkIds: { next: 5000 } } };
    const { configService } = await import('../config/config-resources.js');
    const id = await configService.allocateNetworkId();
    expect(id).toBe(5000);
    expect(next()).toBe(5000 + NETWORK_ID_INCREMENT);
  });

  it('scans for max used ID when the counter is missing', async () => {
    mockConfig = { state: reposState({ 'repo-a': 4000, 'repo-b': 6000 }) };
    const { configService } = await import('../config/config-resources.js');
    const id = await configService.allocateNetworkId();
    expect(id).toBe(6000 + NETWORK_ID_INCREMENT);
  });

  it('fills gaps when forward counter exceeds max', async () => {
    const MAX_NETWORK_ID = 16_711_680;
    mockConfig = {
      state: {
        networkIds: { next: MAX_NETWORK_ID + NETWORK_ID_INCREMENT },
        ...reposState({
          'repo-a': MIN_NETWORK_ID + NETWORK_ID_INCREMENT,
          'repo-b': MIN_NETWORK_ID + 2 * NETWORK_ID_INCREMENT,
        }),
      },
    };
    const { configService } = await import('../config/config-resources.js');
    const id = await configService.allocateNetworkId();
    expect(id).toBe(MIN_NETWORK_ID);
  });

  it('finds the first gap past a dense block', async () => {
    const MAX_NETWORK_ID = 16_711_680;
    const used: Record<string, number> = {};
    for (
      let id = MIN_NETWORK_ID;
      id <= MIN_NETWORK_ID + 10 * NETWORK_ID_INCREMENT;
      id += NETWORK_ID_INCREMENT
    ) {
      used[`repo-${id}`] = id;
    }
    mockConfig = {
      state: { networkIds: { next: MAX_NETWORK_ID + NETWORK_ID_INCREMENT }, ...reposState(used) },
    };
    const { configService } = await import('../config/config-resources.js');
    const id = await configService.allocateNetworkId();
    expect(id).toBe(MIN_NETWORK_ID + 11 * NETWORK_ID_INCREMENT);
  });

  it('constants match expected values', () => {
    expect(MIN_NETWORK_ID).toBe(2816);
    expect(NETWORK_ID_INCREMENT).toBe(64);
  });

  it('IDs are always multiples of INCREMENT from MIN', async () => {
    const { configService } = await import('../config/config-resources.js');
    for (let i = 0; i < 5; i++) {
      const id = await configService.allocateNetworkId();
      expect((id - MIN_NETWORK_ID) % NETWORK_ID_INCREMENT).toBe(0);
    }
  });
});

// PLAN-config-networkid-discovery T3(d): the floor is the TARGET machine's used set (D3(a)).
describe('allocateNetworkIdInStore floor', { timeout: 30_000 }, () => {
  beforeEach(() => {
    mockConfig = {};
  });

  it('raises next past the target machine highest claimant', async () => {
    mockConfig = { state: { networkIds: { next: MIN_NETWORK_ID } } };
    const { allocateNetworkIdInStore } = await import('../config/config-network-id.js');
    const id = await allocateNetworkIdInStore('test', { floor: [2816, 2880] });
    expect(id).toBe(2944);
    expect(next()).toBe(3008);
  });

  it('never lowers a counter already past the floor', async () => {
    mockConfig = { state: { networkIds: { next: 6016 } } };
    const { allocateNetworkIdInStore } = await import('../config/config-network-id.js');
    expect(await allocateNetworkIdInStore('test', { floor: [2816] })).toBe(6016);
  });

  it('keeps the 64-step grid for an off-grid claimant', async () => {
    const { allocateNetworkIdInStore } = await import('../config/config-network-id.js');
    const id = await allocateNetworkIdInStore('test', { floor: [2900] });
    expect(id).toBe(2944);
    expect((id - MIN_NETWORK_ID) % NETWORK_ID_INCREMENT).toBe(0);
  });

  it('reads only the floor it is given, not the IDs other machines hold in state', async () => {
    // state.repos holds a high ID on ANOTHER machine; the target machine is empty.
    mockConfig = { state: { networkIds: { next: 3008 }, ...reposState({ far: 9152 }) } };
    const { allocateNetworkIdInStore } = await import('../config/config-network-id.js');
    expect(await allocateNetworkIdInStore('test', { floor: [] })).toBe(3008);
  });

  it('an empty floor on a fresh config reproduces the single-device sequence (N7)', async () => {
    const { allocateNetworkIdInStore } = await import('../config/config-network-id.js');
    const ids = [
      await allocateNetworkIdInStore('test', { floor: [] }),
      await allocateNetworkIdInStore('test', { floor: [] }),
      await allocateNetworkIdInStore('test', { floor: [] }),
    ];
    expect(ids).toEqual([2816, 2880, 2944]);
  });

  it('networkIdFloor ignores IDs below the minimum and an empty set', async () => {
    const { networkIdFloor } = await import('../config/config-network-id.js');
    expect(networkIdFloor(undefined)).toBeUndefined();
    expect(networkIdFloor([])).toBeUndefined();
    expect(networkIdFloor([7, 0, -1])).toBeUndefined();
    expect(networkIdFloor([2816])).toBe(2880);
  });
});
