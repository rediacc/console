import type { RdcConfig } from '@rediacc/shared/config-schema';
import { describe, expect, it } from 'vitest';
import { findOrphanRepos, pruneOrphanStateRepos } from '../config/config-prune.js';

type Repos = NonNullable<NonNullable<RdcConfig['resources']>['repositories']>;

function configWith(repositories: Repos): RdcConfig {
  const cfg: RdcConfig = {
    schemaVersion: 3,
    id: '00000000-0000-0000-0000-000000000000',
    version: 1,
    resources: {
      machines: { hostinger: { ip: '1.2.3.4', user: 'root' } },
      repositories,
    },
  };
  return cfg;
}

const tags = (guid: string) => ({ latest: { repositoryGuid: guid } });

describe('findOrphanRepos', () => {
  it('flags a repository entry with no placement at all', () => {
    const cfg = configWith({
      'my-app2': { grand: 'latest', tags: tags('72d630f2-5d46-49c5-aac5-f53c48dbab91') },
    });

    expect(findOrphanRepos(cfg)).toEqual([
      { name: 'my-app2', guid: '72d630f2-5d46-49c5-aac5-f53c48dbab91' },
    ]);
  });

  it('does not flag a machine-placed repository', () => {
    const cfg = configWith({
      marketing: {
        grand: 'latest',
        placement: { machine: 'hostinger' },
        tags: tags('2fc4bea2-065b-4d12-9ec4-8a1bf80412db'),
      },
    });

    expect(findOrphanRepos(cfg)).toEqual([]);
  });

  it('does not flag a DATASTORE-placed repository', () => {
    // placement is a union: { machine } | { datastore }. Checking only for a
    // machine would classify every datastore-placed repo as an orphan, and
    // removing one destroys the only copy of its LUKS credential and SSH key.
    const cfg = configWith({
      archived: {
        grand: 'latest',
        placement: { datastore: 'pool-a' },
        tags: tags('33333333-3333-3333-3333-333333333333'),
      },
    });

    expect(findOrphanRepos(cfg)).toEqual([]);
  });

  it('flags an entry whose placement is present but empty', () => {
    const cfg = configWith({
      broken: {
        grand: 'latest',
        placement: { machine: '' },
        tags: tags('44444444-4444-4444-4444-444444444444'),
      },
    });

    expect(findOrphanRepos(cfg).map((r) => r.name)).toEqual(['broken']);
  });

  it('reports the grand tag GUID so the entry can be cross-checked before removal', () => {
    const cfg = configWith({
      forked: {
        grand: 'stable',
        tags: {
          stable: { repositoryGuid: '55555555-5555-5555-5555-555555555555' },
          latest: { repositoryGuid: '66666666-6666-6666-6666-666666666666' },
        },
      },
    });

    expect(findOrphanRepos(cfg)[0].guid).toBe('55555555-5555-5555-5555-555555555555');
  });

  it('separates placed from unplaced across a mixed set', () => {
    const cfg = configWith({
      marketing: {
        grand: 'latest',
        placement: { machine: 'hostinger' },
        tags: tags('2fc4bea2-065b-4d12-9ec4-8a1bf80412db'),
      },
      pooled: {
        grand: 'latest',
        placement: { datastore: 'pool-a' },
        tags: tags('77777777-7777-7777-7777-777777777777'),
      },
      'my-app2': { grand: 'latest', tags: tags('72d630f2-5d46-49c5-aac5-f53c48dbab91') },
    });

    expect(findOrphanRepos(cfg).map((r) => r.name)).toEqual(['my-app2']);
  });

  it('returns empty when there are no repositories at all', () => {
    expect(findOrphanRepos(configWith({}))).toEqual([]);
  });
});

/** Attach a state.repos block to a config fixture. */
function withState(cfg: RdcConfig, repos: NonNullable<RdcConfig['state']>['repos']): RdcConfig {
  const withRepos: RdcConfig = { ...cfg, state: { ...cfg.state, repos } };
  return withRepos;
}

describe('pruneOrphanStateRepos', () => {
  it('drops a state record whose repository entry is gone', () => {
    // The exact leftover observed after removing my-app2: the resource entry
    // was deleted but its state record kept a networkId alive.
    const cfg = withState(configWith({}), { 'my-app2': { latest: { networkId: 16192 } } });

    expect(pruneOrphanStateRepos(cfg)).toEqual(['my-app2']);
    expect(cfg.state?.repos).toEqual({});
  });

  it('keeps state records that still have a repository entry', () => {
    const cfg = withState(
      configWith({
        marketing: {
          grand: 'latest',
          placement: { machine: 'hostinger' },
          tags: tags('2fc4bea2-065b-4d12-9ec4-8a1bf80412db'),
        },
      }),
      { marketing: { latest: { networkId: 3200 } } }
    );

    expect(pruneOrphanStateRepos(cfg)).toEqual([]);
    expect(Object.keys(cfg.state?.repos ?? {})).toEqual(['marketing']);
  });

  it('drops only the unowned records in a mixed set', () => {
    const cfg = withState(
      configWith({
        marketing: {
          grand: 'latest',
          placement: { machine: 'hostinger' },
          tags: tags('2fc4bea2-065b-4d12-9ec4-8a1bf80412db'),
        },
      }),
      {
        marketing: { latest: { networkId: 3200 } },
        'my-app2': { latest: { networkId: 16192 } },
        ghost: { latest: { networkId: 9999 } },
      }
    );

    expect(pruneOrphanStateRepos(cfg).sort()).toEqual(['ghost', 'my-app2']);
    expect(Object.keys(cfg.state?.repos ?? {})).toEqual(['marketing']);
  });

  it('is a no-op when there is no state block', () => {
    expect(pruneOrphanStateRepos(configWith({}))).toEqual([]);
  });
});
