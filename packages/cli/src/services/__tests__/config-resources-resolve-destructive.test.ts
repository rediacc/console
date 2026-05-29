import { beforeEach, describe, expect, it, vi } from 'vitest';

let mockConfig: Record<string, unknown> = {};
let mockRepos: Record<
  string,
  { repositoryGuid: string; tag?: string; grandGuid?: string; parentGuid?: string }
> = {};

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

vi.mock('../config-base.js', () => ({
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
      });
    }
  },
}));

vi.mock('../../types/index.js', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../types/index.js');
  return { ...actual, hasCloudCredentials: () => false };
});

describe('configService.resolveDestructiveTarget (issue #495)', { timeout: 30000 }, () => {
  beforeEach(() => {
    mockConfig = {};
    mockRepos = {};
  });

  it('(a) legacy bare + name:latest both exist → bare ref errors, both listed', async () => {
    mockRepos = {
      app: { repositoryGuid: 'g-bare', tag: 'latest' },
      'app:latest': { repositoryGuid: 'g-latest', tag: 'latest' },
    };
    const { configService, AmbiguousRepoTargetError } = await import('../config-resources.js');
    await expect(configService.resolveDestructiveTarget('app')).rejects.toBeInstanceOf(
      AmbiguousRepoTargetError
    );
  });

  it('(b) grand + fork sharing base name → bare ref errors; explicit :tag resolves', async () => {
    mockRepos = {
      'app:latest': { repositoryGuid: 'g-grand', tag: 'latest' },
      'app:fork-x': { repositoryGuid: 'g-fork', tag: 'fork-x', grandGuid: 'g-grand' },
    };
    const { configService, AmbiguousRepoTargetError } = await import('../config-resources.js');
    await expect(configService.resolveDestructiveTarget('app')).rejects.toBeInstanceOf(
      AmbiguousRepoTargetError
    );

    const grand = await configService.resolveDestructiveTarget('app:latest');
    expect(grand.key).toBe('app:latest');
    expect(grand.config.repositoryGuid).toBe('g-grand');

    const fork = await configService.resolveDestructiveTarget('app:fork-x');
    expect(fork.key).toBe('app:fork-x');
    expect(fork.config.repositoryGuid).toBe('g-fork');
  });

  it('(c) only fork exists → bare ref errors with did-you-mean hint', async () => {
    mockRepos = {
      'app:test': { repositoryGuid: 'g-fork', tag: 'test', grandGuid: 'g-grand-elsewhere' },
    };
    const { configService } = await import('../config-resources.js');
    await expect(configService.resolveDestructiveTarget('app')).rejects.toThrow(/app:test/);
  });

  it('(d) single grand at name:latest → bare ref resolves cleanly', async () => {
    mockRepos = { 'app:latest': { repositoryGuid: 'g-grand', tag: 'latest' } };
    const { configService } = await import('../config-resources.js');
    const r = await configService.resolveDestructiveTarget('app');
    expect(r.key).toBe('app:latest');
    expect(r.config.repositoryGuid).toBe('g-grand');
  });

  it('(e) single legacy bare grand → bare ref resolves cleanly', async () => {
    mockRepos = { app: { repositoryGuid: 'g-bare', tag: 'latest' } };
    const { configService } = await import('../config-resources.js');
    const r = await configService.resolveDestructiveTarget('app');
    expect(r.key).toBe('app');
  });

  it('refuses bare ref that resolves to a fork (the #495 core case)', async () => {
    mockRepos = {
      'app:latest': { repositoryGuid: 'g-fork', tag: 'latest', grandGuid: 'g-grand-elsewhere' },
    };
    const { configService, AmbiguousRepoTargetError } = await import('../config-resources.js');
    await expect(configService.resolveDestructiveTarget('app')).rejects.toBeInstanceOf(
      AmbiguousRepoTargetError
    );
  });

  it('unknown ref throws plain not-found', async () => {
    mockRepos = { 'app:latest': { repositoryGuid: 'g-grand', tag: 'latest' } };
    const { configService } = await import('../config-resources.js');
    await expect(configService.resolveDestructiveTarget('other')).rejects.toThrow(/not found/);
  });
});
