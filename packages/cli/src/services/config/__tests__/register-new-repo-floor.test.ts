import { MIN_NETWORK_ID } from '@rediacc/shared/renet-contract';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// PLAN-config-networkid-discovery T7 control "floor dropped in registerNewRepo": the real registerNewRepo allocates above the target machine's used set even when the synced counter lags behind an ID another device placed there.

let mockConfig: Record<string, unknown> = {};

const stateMutator = (
  _name: string,
  fn: (cfg: Record<string, unknown>) => Record<string, unknown>
) => {
  mockConfig = fn(mockConfig);
};

vi.mock('../../../adapters/config-file-storage.js', () => ({
  configFileStorage: {
    update: vi.fn(stateMutator),
    updateState: vi.fn(stateMutator),
    read: vi.fn(() => mockConfig),
  },
}));

vi.mock('../config-base.js', () => ({
  ConfigServiceBase: class {
    getEffectiveConfigName() {
      return 'test';
    }
    requireSelfHosted() {}
  },
}));

const h = vi.hoisted(() => ({
  usedIds: [] as number[],
  repository: undefined as unknown,
  liveGrand: undefined as unknown,
}));

vi.mock('../../executor/executor-factory.js', () => ({
  getExecutor: () => ({
    execute: vi.fn((opts: { functionName: string }) =>
      Promise.resolve(
        opts.functionName === 'network_used'
          ? {
              exitCode: 0,
              success: true,
              durationMs: 1,
              stdout: JSON.stringify(
                h.usedIds.map((network_id) => ({ kind: 'repo', name: 'x', network_id }))
              ),
            }
          : { exitCode: 1, success: false, durationMs: 1 }
      )
    ),
  }),
}));

const addRepository = vi.fn();

vi.mock('../config-resources.js', async (orig) => {
  const real = await orig<typeof import('../config-resources.js')>();
  return {
    ...real,
    configService: Object.assign(Object.create(real.configService), {
      // getRepository lands on a fork through the grand pointer; getLiveGrand is the create's duplicate check and is set apart so a revert to the old lookup shows.
      getRepository: () => Promise.resolve(h.repository),
      getLiveGrand: () => Promise.resolve(h.liveGrand),
      addRepository: (...args: unknown[]) => {
        addRepository(...args);
        return Promise.resolve();
      },
    }),
  };
});

describe('registerNewRepo allocation floor', () => {
  beforeEach(() => {
    mockConfig = {};
    h.usedIds = [];
    h.repository = undefined;
    h.liveGrand = undefined;
    addRepository.mockClear();
  });

  it('allocates above a held ID the lagging counter has not seen', async () => {
    // The counter would hand out MIN_NETWORK_ID, which another device already placed on the machine.
    mockConfig = { state: { networkIds: { next: MIN_NETWORK_ID } } };
    h.usedIds = [MIN_NETWORK_ID, MIN_NETWORK_ID + 64];
    const { registerNewRepo } = await import('../../../commands/repo-create-delete.js');
    const { networkId } = await registerNewRepo('shop', { machine: 'm1' }, {}, { machine: 'm1' });
    expect(h.usedIds).not.toContain(networkId);
    expect(networkId).toBeGreaterThan(Math.max(...h.usedIds));
    expect(addRepository).toHaveBeenCalledWith(
      'shop:latest',
      expect.objectContaining({ networkId })
    );
  });

  it('registers over a family holding only forks of a forgotten grand', async () => {
    // getRepository would land on the fork and call the name taken; the live-grand lookup finds none.
    h.repository = { repositoryGuid: 'fork-guid', grandGuid: 'gone-guid', tag: 'f1' };
    h.liveGrand = undefined;
    const { registerNewRepo } = await import('../../../commands/repo-create-delete.js');
    await registerNewRepo('shop', { machine: 'm1' }, {}, { machine: 'm1' });
    expect(addRepository).toHaveBeenCalledWith('shop:latest', expect.anything());
  });

  it('refuses a name whose live grand exists (control)', async () => {
    h.liveGrand = { repositoryGuid: 'grand-guid' };
    h.repository = h.liveGrand;
    const { registerNewRepo } = await import('../../../commands/repo-create-delete.js');
    await expect(
      registerNewRepo('shop', { machine: 'm1' }, {}, { machine: 'm1' })
    ).rejects.toThrow(/shop.*already exists/);
    expect(addRepository).not.toHaveBeenCalled();
  });
});
