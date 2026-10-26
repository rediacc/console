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

const h = vi.hoisted(() => ({ usedIds: [] as number[] }));

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
      getRepository: () => Promise.resolve(undefined),
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
});
