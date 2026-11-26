import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  current: 'dev',
  currentRepos: [] as { name: string; config: { repositoryGuid?: string } }[],
  archived: [] as { repositoryGuid: string; deletedAt: string }[],
  others: {} as Record<string, unknown>,
  inRequest: false,
  loaded: [] as string[],
}));

vi.mock('../config/config-resources.js', () => ({
  configService: {
    getCurrent: async () => ({}),
    getCurrentName: () => mocks.current,
    listRepositories: async () => mocks.currentRepos,
    listArchivedRepositories: async () => mocks.archived,
  },
}));

vi.mock('../../adapters/config-file-storage.js', () => ({
  configFileStorage: {
    list: async () => [mocks.current, ...Object.keys(mocks.others)],
    load: (name: string) => {
      mocks.loaded.push(name);
      return Promise.resolve(mocks.others[name]);
    },
  },
}));

vi.mock('../core/request-context.js', () => ({
  currentRequestContext: () => (mocks.inRequest ? {} : undefined),
}));

vi.mock('../core/output.js', () => ({
  outputService: { info: vi.fn(), warn: vi.fn(), success: vi.fn(), print: vi.fn() },
}));

import { analyzePrune, buildPruneReport } from '../repo/prune.js';

const ORPHAN = '260f0a05-1111-4222-8333-444455556666';
const KNOWN = 'b9521afd-0cbd-4481-92ed-f798268a69dd';
const DAY = 86400000;

beforeEach(() => {
  mocks.currentRepos = [{ name: 'vmcheck-base', config: { repositoryGuid: KNOWN } }];
  mocks.archived = [];
  mocks.others = {};
  mocks.inRequest = false;
  mocks.loaded = [];
});

describe('analyzePrune', () => {
  it('flags a GUID with no config entry anywhere as orphaned', async () => {
    const result = await analyzePrune([KNOWN, ORPHAN]);
    expect(result.orphaned).toEqual([{ guid: ORPHAN, reason: 'not in any config' }]);
    expect(result.protected.map((p) => p.guid)).toEqual([KNOWN]);
  });

  it('protects a GUID archived inside the grace period, and flags it once past it', async () => {
    mocks.archived = [{ repositoryGuid: ORPHAN, deletedAt: new Date().toISOString() }];
    expect((await analyzePrune([ORPHAN])).protected[0]?.reason).toMatch(/^archived 0d ago/);

    mocks.archived = [
      { repositoryGuid: ORPHAN, deletedAt: new Date(Date.now() - 30 * DAY).toISOString() },
    ];
    expect((await analyzePrune([ORPHAN])).orphaned.map((o) => o.guid)).toEqual([ORPHAN]);
  });

  it('protects a GUID named by another config unless forced', async () => {
    mocks.others = {
      rediacc: {
        resources: { repositories: { app: { tags: { latest: { repositoryGuid: ORPHAN } } } } },
      },
    };
    expect((await analyzePrune([ORPHAN])).protected[0]?.reason).toContain('exists in rediacc');
    expect((await analyzePrune([ORPHAN], { force: true })).orphaned[0]?.reason).toBe(
      'forced (in rediacc)'
    );
  });

  it('names no --force in reasons when the caller has no such option', async () => {
    mocks.others = {
      'eu-bench': {
        resources: { repositories: { app: { tags: { latest: { repositoryGuid: ORPHAN } } } } },
      },
    };
    const withForce = (await analyzePrune([ORPHAN])).protected[0]?.reason;
    expect(withForce).toContain('--force');
    const without = (await analyzePrune([ORPHAN], { forceAvailable: false })).protected[0]?.reason;
    expect(without).toContain('exists in eu-bench');
    expect(without).not.toContain('--force');

    mocks.others = {};
    mocks.archived = [{ repositoryGuid: ORPHAN, deletedAt: new Date().toISOString() }];
    const archived = (await analyzePrune([ORPHAN], { forceAvailable: false })).protected[0]?.reason;
    expect(archived).toMatch(/^archived 0d ago/);
    expect(archived).not.toContain('--force');
  });

  it('refuses to judge anything while a config is unreadable', async () => {
    mocks.others = { locked: { encryption: { mode: 'master-password' } } };
    expect(await analyzePrune([ORPHAN])).toEqual({ orphaned: [], protected: [] });
  });
});

describe('archive records of other configs', () => {
  const archivedIn = (deletedAt: Date) => ({
    resources: {
      deletedRepositories: [{ repositoryGuid: ORPHAN, deletedAt: deletedAt.toISOString() }],
    },
  });

  it('apply their grace period', async () => {
    mocks.others = { rediacc: archivedIn(new Date()) };
    const result = await analyzePrune([ORPHAN]);
    expect(result.orphaned).toEqual([]);
    expect(result.protected[0]?.reason).toMatch(/^archived 0d ago/);
  });

  it('expire like the current config does', async () => {
    mocks.others = { rediacc: archivedIn(new Date(Date.now() - 30 * DAY)) };
    expect((await analyzePrune([ORPHAN])).orphaned.map((o) => o.guid)).toEqual([ORPHAN]);
  });

  it('keep the most recent record when several configs name the GUID', async () => {
    mocks.archived = [
      { repositoryGuid: ORPHAN, deletedAt: new Date(Date.now() - 30 * DAY).toISOString() },
    ];
    mocks.others = { rediacc: archivedIn(new Date()) };
    expect((await analyzePrune([ORPHAN])).protected[0]?.reason).toMatch(/^archived/);
  });

  it('never let an unparseable deletedAt shadow a valid one, whatever the scan order', async () => {
    mocks.archived = [{ repositoryGuid: ORPHAN, deletedAt: 'not-a-date' }];
    mocks.others = { rediacc: archivedIn(new Date()) };
    expect((await analyzePrune([ORPHAN])).protected[0]?.reason).toMatch(/^archived 0d ago/);
  });

  it('treat a GUID whose every deletedAt is unparseable as never archived', async () => {
    mocks.archived = [{ repositoryGuid: ORPHAN, deletedAt: 'not-a-date' }];
    mocks.others = {
      rediacc: { resources: { deletedRepositories: [{ repositoryGuid: ORPHAN, deletedAt: 'x' }] } },
    };
    expect((await analyzePrune([ORPHAN])).orphaned.map((o) => o.guid)).toEqual([ORPHAN]);
  });

  it('are bypassed by --force', async () => {
    mocks.others = { rediacc: archivedIn(new Date()) };
    expect((await analyzePrune([ORPHAN], { force: true })).orphaned.map((o) => o.guid)).toEqual([
      ORPHAN,
    ]);
  });
});

describe('inside an executor request (review 219d0972.4)', () => {
  const otherConfig = {
    rediacc: {
      resources: {
        repositories: { app: { tags: { latest: { repositoryGuid: ORPHAN } } } },
        deletedRepositories: [{ repositoryGuid: ORPHAN, deletedAt: new Date().toISOString() }],
      },
    },
  };

  it('control: outside a request another config protects the GUID', async () => {
    mocks.others = otherConfig;
    expect((await analyzePrune([ORPHAN])).protected[0]?.reason).toContain('exists in rediacc');
  });

  it('never loads or judges against the other config files on disk', async () => {
    mocks.inRequest = true;
    mocks.others = otherConfig;
    const result = await analyzePrune([ORPHAN]);
    expect(result.orphaned).toEqual([{ guid: ORPHAN, reason: 'not in any config' }]);
    expect(mocks.loaded).toEqual([]);
  });

  it('still scans the session config', async () => {
    mocks.inRequest = true;
    mocks.others = otherConfig;
    const result = await analyzePrune([KNOWN, ORPHAN]);
    expect(result.protected.map((p) => p.guid)).toEqual([KNOWN]);
    expect(result.orphaned.map((o) => o.guid)).toEqual([ORPHAN]);
  });
});

describe('buildPruneReport', () => {
  it('carries the orphan verdict as data for the json and yaml formats', async () => {
    const analysis = await analyzePrune([KNOWN, ORPHAN]);
    expect(buildPruneReport(analysis, true)).toEqual({
      dry_run: true,
      orphaned_repos: [{ guid: ORPHAN, reason: 'not in any config' }],
      protected_repos: [{ guid: KNOWN, reason: 'active in dev' }],
    });
  });
});
