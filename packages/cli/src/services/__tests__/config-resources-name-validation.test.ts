/**
 * The add* writers refuse a name the config schema would reject as a record
 * key BEFORE touching the store. A refused `rdc repo create lvA` once wrote the
 * entry first, so every later command failed with "Invalid key in record" until
 * the file was edited by hand.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

let writes = 0;
let mockRepos: Record<string, unknown> = {};
let mockMachines: Record<string, unknown> = {};

vi.mock('../../adapters/config-file-storage.js', () => ({
  configFileStorage: { update: vi.fn(), read: vi.fn(() => ({})) },
}));

vi.mock('../config/config-base.js', () => ({
  ConfigServiceBase: class {
    getEffectiveConfigName() {
      return 'test';
    }
    requireSelfHosted() {}
    getCurrent() {
      return Promise.resolve({ version: 1 });
    }
    getResourceState() {
      return Promise.resolve({
        getRepositories: () => mockRepos,
        setRepositories: (r: Record<string, unknown>) => {
          writes++;
          mockRepos = r;
          return Promise.resolve();
        },
        getMachines: () => mockMachines,
        setMachines: (m: Record<string, unknown>) => {
          writes++;
          mockMachines = m;
          return Promise.resolve();
        },
      });
    }
  },
}));

describe('add* name validation precedes the write', { timeout: 30000 }, () => {
  beforeEach(() => {
    writes = 0;
    mockRepos = {};
    mockMachines = {};
  });

  it('addRepository refuses an uppercase family name and writes nothing', async () => {
    const { configService } = await import('../config/config-resources.js');
    await expect(
      configService.addRepository('lvA:latest', {
        repositoryGuid: 'g1',
        tag: 'latest',
        credential: 'c',
        networkId: 2816,
      } as never)
    ).rejects.toThrow('Invalid resource name "lvA"');
    expect(writes).toBe(0);
    expect(mockRepos).toEqual({});
  });

  it('addRepository still accepts a valid name:tag', async () => {
    const { configService } = await import('../config/config-resources.js');
    await configService.addRepository('lv:latest', {
      repositoryGuid: 'g2',
      tag: 'latest',
      credential: 'c',
      networkId: 2816,
    } as never);
    expect(writes).toBe(1);
  });
});
