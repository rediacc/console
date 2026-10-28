import { describe, expect, it } from 'vitest';
import { buildRepositories, type RepoEntryConfig } from '../renet-vault-sections.js';

const entry = (guid: string, name: string, grandGuid?: string): RepoEntryConfig => ({
  guid,
  name,
  networkId: 2816,
  ...(grandGuid ? { grandGuid } : {}),
});

describe('buildRepositories bare-name addressing', () => {
  it('resolves a restored repo (stored as <name>:latest under a foreign lineage grand)', () => {
    const configs = { 'restored:latest': entry('guid-restored', 'restored', 'guid-lineage') };
    const result = buildRepositories({ repository: 'restored' }, configs);
    expect(result.repoGuid).toBe('guid-restored');
  });

  it('prefers the grand over its forks', () => {
    const configs = {
      'app:fork1': entry('guid-fork', 'app', 'guid-grand'),
      'app:latest': entry('guid-grand', 'app'),
    };
    expect(buildRepositories({ repository: 'app' }, configs).repoGuid).toBe('guid-grand');
  });

  it('refuses to pick a fork when the grand is missing and several forks exist', () => {
    const configs = {
      'app:a': entry('guid-a', 'app', 'guid-grand'),
      'app:b': entry('guid-b', 'app', 'guid-grand'),
    };
    expect(() => buildRepositories({ repository: 'app' }, configs)).toThrow(/has no GUID/);
  });
});
