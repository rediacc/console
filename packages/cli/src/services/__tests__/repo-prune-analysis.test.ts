import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  current: 'dev',
  currentRepos: [] as { name: string; config: { repositoryGuid?: string } }[],
  archived: [] as { repositoryGuid: string; deletedAt: string }[],
  others: {} as Record<string, unknown>,
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
    load: async (name: string) => mocks.others[name],
  },
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

  it('are bypassed by --force', async () => {
    mocks.others = { rediacc: archivedIn(new Date()) };
    expect((await analyzePrune([ORPHAN], { force: true })).orphaned.map((o) => o.guid)).toEqual([
      ORPHAN,
    ]);
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
