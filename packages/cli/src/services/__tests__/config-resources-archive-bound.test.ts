import { beforeEach, describe, expect, it, vi } from 'vitest';

// vm:check teardown 2026-11-11: a config held 663 archived records named `vmcheck-base` and no live one. These pin that an archived record never makes a name taken for `repo create` (whose duplicate check is getLiveGrand), and that archive writes keep the archive bounded.

vi.mock('../../adapters/config-file-storage.js', () => ({
  configFileStorage: { update: vi.fn(), read: vi.fn(() => ({})) },
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

const { configService } = await import('../config/config-resources.js');
const { boundArchive, ARCHIVE_RETENTION_DAYS, ARCHIVED_FORKS_PER_NAME } = await import(
  '../config/config-resources-archive.js'
);

const DAY = 24 * 60 * 60 * 1000;
let seq = 0;
const guid = () => `00000000-0000-0000-0000-${String(++seq).padStart(12, '0')}`;

function grand(): Record<string, unknown> {
  const id = guid();
  return { repositoryGuid: id, credential: `luks-${id}` };
}

function fork(grandGuid: string, tag: string): Record<string, unknown> {
  return { repositoryGuid: guid(), grandGuid, parentGuid: grandGuid, tag, credential: 'parent' };
}

describe('repo create after repo delete --archive-config of the same name', () => {
  beforeEach(() => {
    mockRepos = {};
    mockDeleted = [];
  });

  it('an archived record does not make the name taken; a live one does', async () => {
    mockRepos = { 'vmcheck-base:latest': grand() };
    expect(await configService.getLiveGrand('vmcheck-base')).toBeDefined();

    await configService.archiveRepository('vmcheck-base:latest');
    expect(mockDeleted).toHaveLength(1);
    expect(await configService.getLiveGrand('vmcheck-base')).toBeUndefined();

    // Recreated under a new GUID beside the archived one: the live record is the only one the check sees.
    mockRepos['vmcheck-base:latest'] = grand();
    expect(await configService.getLiveGrand('vmcheck-base')).toBeDefined();

    // A second archive of the same name keeps both records: they are keyed by GUID, not name.
    await configService.archiveRepository('vmcheck-base:latest');
    expect(mockDeleted.map((d) => d.name)).toEqual(['vmcheck-base', 'vmcheck-base']);
    expect(new Set(mockDeleted.map((d) => d.repositoryGuid)).size).toBe(2);
    expect(await configService.getLiveGrand('vmcheck-base')).toBeUndefined();
  });
});

describe('archive writes keep the archive bounded', () => {
  beforeEach(() => {
    mockRepos = {};
    mockDeleted = [];
  });

  it('repeated fork/delete cycles keep only the newest forks per name, every grand stays', async () => {
    const grands: string[] = [];
    for (let cycle = 0; cycle < 30; cycle++) {
      const g = grand();
      grands.push(g.repositoryGuid as string);
      mockRepos['vmcheck-base:latest'] = g;
      for (const t of ['a', 'b', 'c']) {
        mockRepos[`vmcheck-base:vmc-${cycle}-${t}`] = fork(g.repositoryGuid as string, t);
      }
      await configService.archiveRepositories(
        Object.keys(mockRepos).filter((k) => k.includes(':vmc-'))
      );
      await configService.archiveRepository('vmcheck-base:latest');
    }
    const forks = mockDeleted.filter((d) => d.grandGuid);
    const kept = mockDeleted.filter((d) => !d.grandGuid);
    expect(forks).toHaveLength(ARCHIVED_FORKS_PER_NAME);
    // The forks kept are the newest: the last cycle's three are among them.
    expect(forks.slice(-3).map((d) => d.tag)).toEqual(['a', 'b', 'c']);
    expect(kept.map((d) => d.repositoryGuid)).toEqual(grands);
    expect(kept.every((d) => typeof d.credential === 'string')).toBe(true);
  });

  it('drops records past the retention window and keeps an unparseable deletedAt', () => {
    const now = Date.parse('2026-11-11T00:00:00.000Z');
    const at = (days: number) => new Date(now - days * DAY).toISOString();
    const out = boundArchive(
      [
        { name: 'old', repositoryGuid: guid(), deletedAt: at(ARCHIVE_RETENTION_DAYS + 1) },
        { name: 'recent', repositoryGuid: guid(), deletedAt: at(ARCHIVE_RETENTION_DAYS - 1) },
        { name: 'odd', repositoryGuid: guid(), deletedAt: 'not-a-date' },
      ],
      now
    );
    expect(out.map((r) => r.name)).toEqual(['recent', 'odd']);
  });

  it('caps forks per name independently and preserves order', () => {
    const now = Date.parse('2026-11-11T00:00:00.000Z');
    const g = guid();
    // Name `a` is two over the cap and `b` well under it, interleaved so order is observable.
    const names = [...Array(ARCHIVED_FORKS_PER_NAME + 2).fill('a'), 'b', 'b', 'b'];
    const records = names.map((name, i) => ({
      name,
      repositoryGuid: guid(),
      grandGuid: g,
      deletedAt: new Date(now - (100 - i) * 60_000).toISOString(),
    }));
    records.sort((x, y) => (x.repositoryGuid < y.repositoryGuid ? -1 : 1));
    const out = boundArchive(records, now);
    const aNewest = records
      .filter((r) => r.name === 'a')
      .sort((x, y) => Date.parse(y.deletedAt) - Date.parse(x.deletedAt))
      .slice(0, ARCHIVED_FORKS_PER_NAME);
    expect(out).toEqual(records.filter((r) => r.name === 'b' || aNewest.includes(r)));
    expect(out.filter((r) => r.name === 'a')).toHaveLength(ARCHIVED_FORKS_PER_NAME);
    expect(out.filter((r) => r.name === 'b')).toHaveLength(3);
  });

  it('keeps a fork record with an unparseable deletedAt even past the cap', () => {
    const now = Date.parse('2026-11-11T00:00:00.000Z');
    const g = guid();
    const dated = Array.from({ length: ARCHIVED_FORKS_PER_NAME + 1 }, (_, i) => ({
      name: 'a',
      repositoryGuid: guid(),
      grandGuid: g,
      deletedAt: new Date(now - (100 - i) * 60_000).toISOString(),
    }));
    const odd = { name: 'a', repositoryGuid: guid(), grandGuid: g, deletedAt: 'not-a-date' };
    const out = boundArchive([odd, ...dated], now);
    expect(out).toContain(odd);
    expect(out).toHaveLength(ARCHIVED_FORKS_PER_NAME + 1);
    expect(out).not.toContain(dated[0]);
  });
});
