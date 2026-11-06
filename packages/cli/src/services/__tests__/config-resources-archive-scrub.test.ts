import { beforeEach, describe, expect, it, vi } from 'vitest';

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

let mockRepos: Record<string, Record<string, unknown>> = {};
let mockDeleted: Record<string, unknown>[] = [];

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
        getDeletedRepositories: () => mockDeleted,
        setRepositories: (next: typeof mockRepos) => {
          mockRepos = next;
          return Promise.resolve();
        },
        setDeletedRepositories: (next: typeof mockDeleted) => {
          mockDeleted = next;
          return Promise.resolve();
        },
      });
    }
  },
}));

vi.mock('../../types/index.js', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../types/index.js');
  return { ...actual };
});

const { configService } = await import('../config/config-resources.js');

describe('archiveRepository — scrubs secrets', () => {
  beforeEach(() => {
    mockRepos = {
      'app:latest': {
        repositoryGuid: '00000000-0000-0000-0000-000000000001',
        credential: 'luks-passphrase',
        secrets: {
          STRIPE: { mode: 'env', value: 'sk_live_x' },
          DKIM: { mode: 'file', value: '----PEM----' },
        },
      },
    };
    mockDeleted = [];
  });

  it('archived entry preserves identity but drops secrets', async () => {
    await configService.archiveRepository('app:latest');
    expect(mockDeleted).toHaveLength(1);
    const archived = mockDeleted[0];
    expect(archived.name).toBe('app');
    expect(archived.tag).toBe('latest');
    expect(archived.repositoryGuid).toBe('00000000-0000-0000-0000-000000000001');
    expect(archived.credential).toBe('luks-passphrase');
    expect(archived.deletedAt).toBeDefined();
    expect(archived.secrets).toBeUndefined();
  });

  it('original repo entry is removed entirely (including secrets)', async () => {
    await configService.archiveRepository('app:latest');
    expect(mockRepos['app:latest']).toBeUndefined();
  });
});

describe('archiveRepositories — a deprovisioned machine repos in one write per bucket', () => {
  beforeEach(() => {
    mockRepos = {
      'app:latest': {
        repositoryGuid: '00000000-0000-0000-0000-000000000001',
        credential: 'luks-a',
        secrets: { STRIPE: { mode: 'env', value: 'sk_live_x' } },
      },
      'app:t1': { repositoryGuid: '00000000-0000-0000-0000-000000000002', credential: 'luks-b' },
      'shop:latest': { repositoryGuid: '00000000-0000-0000-0000-000000000003' },
    };
    mockDeleted = [];
  });

  it('archives the named keys, skips unknown ones, scrubs secrets, keeps the rest', async () => {
    const archived = await configService.archiveRepositories(['app:latest', 'app:t1', 'gone:x']);
    expect(archived).toEqual(['app:latest', 'app:t1']);
    expect(Object.keys(mockRepos)).toEqual(['shop:latest']);
    expect(mockDeleted.map((d) => `${d.name}:${d.tag}`)).toEqual(['app:latest', 'app:t1']);
    expect(mockDeleted.map((d) => d.credential)).toEqual(['luks-a', 'luks-b']);
    expect(mockDeleted[0].secrets).toBeUndefined();
  });

  it('writes nothing when no key is in the config', async () => {
    expect(await configService.archiveRepositories(['gone:x'])).toEqual([]);
    expect(mockDeleted).toEqual([]);
    expect(Object.keys(mockRepos)).toHaveLength(3);
  });
});
