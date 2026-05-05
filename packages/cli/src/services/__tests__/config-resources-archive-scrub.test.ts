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
  return { ...actual, hasCloudCredentials: () => false };
});

const { configService } = await import('../config-resources.js');

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
    expect(archived.name).toBe('app:latest');
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
