import { describe, expect, it, vi, beforeEach } from 'vitest';

// Mock configFileStorage (unused for this test but required by the module graph).
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

// Mock the base class so getRepositoryGuidMap's getCurrent/getResourceState paths
// are controllable from the test.
let mockRepos: Record<string, { repositoryGuid: string; tag?: string }> = {};

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

// Bump default 5s timeout — the per-test `await import('../config-resources.js')`
// triggers a cold load of the full module graph (commitments/canonical/walker/
// config-base) which can exceed 5s on slower CI runners. A timeout on the
// first test then cascade-fails the remaining five (configService undefined).
describe('getRepositoryGuidMap', { timeout: 30000 }, () => {
  beforeEach(() => {
    mockConfig = {};
    mockRepos = {};
  });

  it('bare key with latest tag produces clean "name:latest"', async () => {
    mockRepos = {
      erpnext: { repositoryGuid: 'guid-erp', tag: 'latest' },
    };
    const { configService } = await import('../config-resources.js');
    const map = await configService.getRepositoryGuidMap();
    expect(map['guid-erp']).toBe('erpnext:latest');
  });

  it('composite key "name:latest" with latest tag produces "name:latest" (no double tag)', async () => {
    mockRepos = {
      'demo-heartbeat:latest': { repositoryGuid: 'guid-hb', tag: 'latest' },
    };
    const { configService } = await import('../config-resources.js');
    const map = await configService.getRepositoryGuidMap();
    expect(map['guid-hb']).toBe('demo-heartbeat:latest');
    expect(map['guid-hb']).not.toContain(':latest:latest');
  });

  it('fork composite key with custom tag produces "name:tag" (no double tag)', async () => {
    mockRepos = {
      'demo-stackoverflow:isolation-final': {
        repositoryGuid: 'guid-fork',
        tag: 'isolation-final',
      },
    };
    const { configService } = await import('../config-resources.js');
    const map = await configService.getRepositoryGuidMap();
    expect(map['guid-fork']).toBe('demo-stackoverflow:isolation-final');
  });

  it('tag field wins when composite key tag differs from stored tag', async () => {
    // Edge case: if a composite key has a stale tag suffix that doesn't match
    // repoConfig.tag, the stored tag is authoritative (prevents stale-key bugs).
    mockRepos = {
      'myapp:stale-tag': { repositoryGuid: 'guid-myapp', tag: 'current-tag' },
    };
    const { configService } = await import('../config-resources.js');
    const map = await configService.getRepositoryGuidMap();
    expect(map['guid-myapp']).toBe('myapp:current-tag');
  });

  it('mixed bare and composite keys in same config both resolve correctly', async () => {
    mockRepos = {
      erpnext: { repositoryGuid: 'guid-erp', tag: 'latest' },
      'demo-heartbeat:latest': { repositoryGuid: 'guid-hb', tag: 'latest' },
      'demo-stackoverflow:v1': { repositoryGuid: 'guid-v1', tag: 'v1' },
    };
    const { configService } = await import('../config-resources.js');
    const map = await configService.getRepositoryGuidMap();
    expect(map['guid-erp']).toBe('erpnext:latest');
    expect(map['guid-hb']).toBe('demo-heartbeat:latest');
    expect(map['guid-v1']).toBe('demo-stackoverflow:v1');
  });

  it('defaults to "latest" when tag field is missing', async () => {
    mockRepos = {
      marketing: { repositoryGuid: 'guid-mkt' },
    };
    const { configService } = await import('../config-resources.js');
    const map = await configService.getRepositoryGuidMap();
    expect(map['guid-mkt']).toBe('marketing:latest');
  });
});
