/**
 * `addRepository` must refuse a second LIVE record that reuses another record's
 * `repositoryGuid` under a different credential.
 *
 * The executor's credential map is keyed by GUID (`buildCredentialsMap`), so
 * such a pair has only one slot between them. Nothing failed loudly: one
 * credential won, the other repo's LUKS image stopped unlocking, and which one
 * won depended on the iteration order over config keys — i.e. on where the name
 * the operator happened to type sorted. `backup restore` minted a fresh
 * credential onto the source's GUID and hit exactly this.
 *
 * Archived records live in `resources.deletedRepositories`, never in the
 * repositories dict, so they cannot trip the guard.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

// Required by the module graph; this suite never reads a real config file.
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

type Repo = { repositoryGuid: string; tag?: string; credential?: string };

let mockRepos: Record<string, Repo> = {};

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
        setRepositories: (repos: Record<string, Repo>) => {
          mockRepos = repos;
          return Promise.resolve();
        },
      });
    }
  },
}));

// Cold-loads the full config module graph on first import (see the sibling
// guid-map suite for the same allowance).
describe('addRepository credential collision guard', { timeout: 30000 }, () => {
  beforeEach(() => {
    mockConfig = {};
    mockRepos = {};
  });

  it('refuses a second live record on one GUID with a different credential', async () => {
    mockRepos = {
      'shop:latest': { repositoryGuid: 'guid-a', tag: 'latest', credential: 'cred-a' },
    };
    const { configService } = await import('../config/config-resources.js');

    await expect(
      configService.addRepository('copy:latest', {
        repositoryGuid: 'guid-a',
        tag: 'latest',
        credential: 'cred-b',
      })
    ).rejects.toThrow(/copy:latest[\s\S]*shop:latest/);

    // The refusal is total: nothing is written.
    expect(Object.keys(mockRepos)).toEqual(['shop:latest']);
  });

  it('names both records and the shared GUID so the operator can act', async () => {
    mockRepos = {
      'shop:latest': { repositoryGuid: 'guid-a', tag: 'latest', credential: 'cred-a' },
    };
    const { configService } = await import('../config/config-resources.js');

    const err = await configService
      .addRepository('copy:latest', {
        repositoryGuid: 'guid-a',
        tag: 'latest',
        credential: 'cred-b',
      })
      .then(
        () => {
          throw new Error('expected addRepository to reject, but it resolved');
        },
        (e: unknown) => e as Error
      );

    expect(err).toBeInstanceOf(Error);
    expect(err.message).toContain('copy:latest');
    expect(err.message).toContain('shop:latest');
    expect(err.message).toContain('guid-a');
  });

  it('allows the same GUID when the credential is inherited (restore, promote)', async () => {
    mockRepos = {
      'shop:latest': { repositoryGuid: 'guid-a', tag: 'latest', credential: 'cred-a' },
    };
    const { configService } = await import('../config/config-resources.js');

    await configService.addRepository('copy:latest', {
      repositoryGuid: 'guid-a',
      tag: 'latest',
      credential: 'cred-a',
    });

    expect(mockRepos['copy:latest'].credential).toBe('cred-a');
  });

  it('allows distinct GUIDs with distinct credentials (repo fork, repo create)', async () => {
    mockRepos = {
      'shop:latest': { repositoryGuid: 'guid-a', tag: 'latest', credential: 'cred-a' },
    };
    const { configService } = await import('../config/config-resources.js');

    await configService.addRepository('shop:staging', {
      repositoryGuid: 'guid-b',
      tag: 'staging',
      credential: 'cred-b',
    });

    expect(Object.keys(mockRepos).sort()).toEqual(['shop:latest', 'shop:staging']);
  });

  it('allows rewriting a record in place under its own key', async () => {
    mockRepos = {
      'shop:latest': { repositoryGuid: 'guid-a', tag: 'latest', credential: 'cred-a' },
    };
    const { configService } = await import('../config/config-resources.js');

    await configService.addRepository('shop:latest', {
      repositoryGuid: 'guid-a',
      tag: 'latest',
      credential: 'cred-rotated',
    });

    expect(mockRepos['shop:latest'].credential).toBe('cred-rotated');
  });
});
