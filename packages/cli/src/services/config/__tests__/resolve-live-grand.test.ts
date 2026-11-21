import { describe, expect, it } from 'vitest';
import type { RepositoryConfig } from '../../../types/index.js';
import {
  grandTagsOf,
  resolveDestructiveTargetFromRepos,
  resolveLiveGrandKey,
  resolveRepoKey,
} from '../config-resources-resolve.js';

const GRAND_GUID = '6b7133ad-86f0-4609-b5c6-6a44d9f47299';

function repo(overrides: Partial<RepositoryConfig>): RepositoryConfig {
  return { repositoryGuid: 'guid-x', credential: 'c', ...overrides } as RepositoryConfig;
}

/** The config vm:check met: the grand was forgotten, one fork of it stayed under the same base name. */
const forkOnly: Record<string, RepositoryConfig> = {
  'vmcheck-base:vmc-11071810-cc310c-f': repo({
    repositoryGuid: '384e6ec8-2d67-424f-a39a-ab50b84a4927',
    grandGuid: GRAND_GUID,
    parentGuid: GRAND_GUID,
    tag: 'vmc-11071810-cc310c-f',
  }),
};
const forkOnlyTags = grandTagsOf({ 'vmcheck-base': { grand: 'vmc-11071810-cc310c-f' } });

describe('a bare name over a family of forks whose grand is gone', () => {
  it('is no live repo for create and refused by delete, so the two verbs agree', () => {
    // The old create check: the grand pointer lands on the fork, so the name read as taken.
    expect(resolveRepoKey(forkOnly, 'vmcheck-base', forkOnlyTags)).toBe(
      'vmcheck-base:vmc-11071810-cc310c-f'
    );
    // Delete refuses that fork under a bare name.
    expect(() => resolveDestructiveTargetFromRepos(forkOnly, 'vmcheck-base', forkOnlyTags)).toThrow(
      /a fork of a grand not in this config/
    );
    // The live-grand lookup create now uses finds nothing, so the grand can be created.
    expect(resolveLiveGrandKey(forkOnly, 'vmcheck-base', forkOnlyTags)).toBeUndefined();
  });

  it('still resolves the fork by its explicit tag', () => {
    expect(resolveLiveGrandKey(forkOnly, 'vmcheck-base:vmc-11071810-cc310c-f', forkOnlyTags)).toBe(
      'vmcheck-base:vmc-11071810-cc310c-f'
    );
  });
});

describe('resolveLiveGrandKey agrees with delete where a live repo exists', () => {
  it('finds the grand beside its forks', () => {
    const repos = {
      ...forkOnly,
      'vmcheck-base:latest': repo({ repositoryGuid: GRAND_GUID, tag: 'latest' }),
    };
    const tags = grandTagsOf({ 'vmcheck-base': { grand: 'latest' } });
    expect(resolveLiveGrandKey(repos, 'vmcheck-base', tags)).toBe('vmcheck-base:latest');
    expect(resolveDestructiveTargetFromRepos(repos, 'vmcheck-base:latest', tags).key).toBe(
      'vmcheck-base:latest'
    );
  });

  it('counts a restored record (a lone latest carrying foreign lineage) as live', () => {
    const repos = {
      'shop:latest': repo({ repositoryGuid: 'new', grandGuid: 'old-lineage', tag: 'latest' }),
    };
    expect(resolveLiveGrandKey(repos, 'shop')).toBe('shop:latest');
    expect(resolveDestructiveTargetFromRepos(repos, 'shop').key).toBe('shop:latest');
  });

  it('finds nothing for an unknown name', () => {
    expect(resolveLiveGrandKey(forkOnly, 'other', forkOnlyTags)).toBeUndefined();
  });
});
