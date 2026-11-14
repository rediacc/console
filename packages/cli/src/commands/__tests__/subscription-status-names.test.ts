/**
 * `subscription status` (account view): a table of the repositories this config holds sorted by
 * urgency, one summary line for every other licence, `--all` for those others, and `-o json` with
 * every row and its presence.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

type Column = { key: string; header: string };
const mockPrint = vi.hoisted(() => vi.fn());
const reports = vi.hoisted(() => [] as string[]);
const tables = vi.hoisted(
  () => [] as { rows: Record<string, string>[]; columns: { key: string; header: string }[] }[]
);
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: vi.fn(),
    format: (rows: Record<string, string>[], _format: string, columns: Column[]) => {
      tables.push({ rows, columns });
      return `TABLE#${tables.length}`;
    },
    report: (m: string) => reports.push(m),
    warn: vi.fn(),
    success: vi.fn(),
    print: mockPrint,
  },
}));

const mockReport = vi.hoisted(() => vi.fn());
vi.mock('../../services/account/license.js', () => ({
  fetchSubscriptionLicenseReportOrThrow: mockReport,
}));
vi.mock('../../services/account/subscription-auth.js', () => ({
  getSubscriptionTokenState: () => ({ kind: 'ready', token: {} }),
  getSubscriptionScopeMismatch: () => null,
  getSubscriptionServerUrl: () => 'http://localhost',
}));
const mockConfig = vi.hoisted(() => ({ value: null as unknown }));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getTeam: vi.fn().mockResolvedValue(undefined),
    getCurrent: () =>
      mockConfig.value instanceof Error
        ? Promise.reject(mockConfig.value)
        : Promise.resolve(mockConfig.value),
  },
}));

import { setOutputFormat } from '../../utils/errors.js';
import { executeSubscriptionStatus } from '../subscription-actions.js';

const GRAND = '11111111-aaaa-4aaa-8aaa-000000000001';
const FORK = '22222222-bbbb-4bbb-8bbb-000000000002';
const DELETED = '33333333-cccc-4ccc-8ccc-000000000003';
const STRANGER = '44444444-dddd-4ddd-8ddd-000000000004';
const STRANGER_FRESH = '55555555-eeee-4eee-8eee-000000000005';
const VALID = '66666666-ffff-4fff-8fff-000000000006';
const LIVE_OK = '77777777-aaaa-4aaa-8aaa-000000000007';

const recent = [
  {
    repositoryGuid: LIVE_OK,
    freshness: 'valid',
    kind: 'grand',
    refreshRecommendedAt: '2027-01-01T00:00:00.000Z',
    hardExpiresAt: '2027-02-01T00:00:00.000Z',
  },
  {
    repositoryGuid: GRAND,
    freshness: 'refresh_recommended',
    kind: 'grand',
    refreshRecommendedAt: '2026-11-01T00:00:00.000Z',
    hardExpiresAt: '2026-11-20T00:00:00.000Z',
  },
  {
    repositoryGuid: FORK,
    freshness: 'hard_expired',
    kind: 'fork',
    refreshRecommendedAt: '2026-10-01T00:00:00.000Z',
    hardExpiresAt: '2026-10-10T00:00:00.000Z',
  },
  {
    repositoryGuid: DELETED,
    freshness: 'hard_expired',
    kind: 'grand',
    hardExpiresAt: '2026-10-05T00:00:00.000Z',
  },
  {
    repositoryGuid: STRANGER,
    freshness: 'hard_expired',
    kind: 'grand',
    hardExpiresAt: '2026-10-15T00:00:00.000Z',
  },
  {
    repositoryGuid: STRANGER_FRESH,
    freshness: 'refresh_recommended',
    kind: 'grand',
    hardExpiresAt: '2026-11-25T00:00:00.000Z',
  },
  {
    repositoryGuid: VALID,
    freshness: 'valid',
    kind: 'grand',
    hardExpiresAt: '2027-01-01T00:00:00.000Z',
  },
];

function statusReport(licenses: unknown[] | undefined) {
  return {
    planCode: 'ENTERPRISE',
    status: 'active',
    machineSlots: { active: 0, max: 1, machines: [] as unknown[] },
    repoLicenseIssuances: { used: 0, limit: 10 },
    repoLicenses: {
      totalTrackedRepos: licenses?.length ?? 0,
      validCount: 1,
      refreshRecommendedCount: 2,
      hardExpiredCount: 3,
      ...(licenses && { recent: licenses }),
    },
  };
}

type Licence = {
  guid: string;
  name: string | null;
  machine: string | null;
  presence: string;
  fix: string | null;
  freshness: string;
};

const repoNames = (table: { rows: Record<string, string>[] }) => table.rows.map((r) => r.repo);

async function printedJson(): Promise<Record<string, unknown>> {
  setOutputFormat('json');
  try {
    await executeSubscriptionStatus();
  } finally {
    setOutputFormat('table');
  }
  expect(mockPrint).toHaveBeenCalledTimes(1);
  return mockPrint.mock.calls[0][0] as Record<string, unknown>;
}

function summaryItem(kind: 'Deleted' | 'Absent', state: string): string {
  return `elsewhere${kind}:{"count":1,"state":"commands.subscription.licenceState.${state}"}`;
}

describe('subscription status view', () => {
  beforeEach(() => {
    reports.length = 0;
    tables.length = 0;
    mockPrint.mockReset();
    setOutputFormat('table');
    mockReport.mockResolvedValue(statusReport(recent));
    mockConfig.value = {
      resources: {
        repositories: {
          web: {
            grand: 'main',
            placement: { machine: 'box' },
            tags: { main: { repositoryGuid: GRAND }, feat: { repositoryGuid: FORK } },
          },
          api: {
            grand: 'main',
            placement: { machine: 'box' },
            tags: { main: { repositoryGuid: LIVE_OK } },
          },
        },
        deletedRepositories: [{ name: 'old', tag: 'main', repositoryGuid: DELETED }],
      },
    };
  });

  it('puts only the repositories of this config in the table, with the six columns', async () => {
    await executeSubscriptionStatus();
    expect(tables).toHaveLength(1);
    expect(tables[0].columns.map((c) => c.key)).toEqual([
      'repo',
      'machine',
      'kind',
      'state',
      'refreshBy',
      'hardExpiry',
    ]);
    expect(tables[0].rows).toHaveLength(3);
    const shown = JSON.stringify(tables[0].rows);
    for (const other of [DELETED, STRANGER, STRANGER_FRESH, VALID]) {
      expect(shown).not.toContain(other.slice(0, 8));
    }
    expect(tables[0].rows.find((r) => r.repo === 'web')).toMatchObject({
      machine: 'box',
      kind: 'grand',
      refreshBy: '2026-11-01',
      hardExpiry: '2026-11-20',
    });
  });

  it('sorts by urgency: hard expired, refresh recommended, valid', async () => {
    await executeSubscriptionStatus();
    expect(repoNames(tables[0])).toEqual(['web:feat', 'web', 'api']);
  });

  it('breaks a tie of states by the soonest hard expiry (control for the sort key)', async () => {
    mockReport.mockResolvedValue(
      statusReport([
        { repositoryGuid: GRAND, freshness: 'valid', kind: 'grand', hardExpiresAt: '2028-01-01' },
        { repositoryGuid: LIVE_OK, freshness: 'valid', kind: 'grand', hardExpiresAt: '2027-01-01' },
      ])
    );
    await executeSubscriptionStatus();
    expect(repoNames(tables[0])).toEqual(['api', 'web']);
  });

  it('prints no per-row fix lines and one refresh hint', async () => {
    await executeSubscriptionStatus();
    const out = reports.join('\n');
    expect(out).not.toContain('licenceFix');
    expect(out.match(/status\.refreshHint/g)).toHaveLength(1);
  });

  it('prints no refresh hint when every live repository is valid (control)', async () => {
    mockReport.mockResolvedValue(
      statusReport([{ repositoryGuid: LIVE_OK, freshness: 'valid', kind: 'grand' }])
    );
    await executeSubscriptionStatus();
    expect(reports.join('\n')).not.toContain('refreshHint');
  });

  it('counts every other category in one summary line, deleted repositories included', async () => {
    await executeSubscriptionStatus();
    const summary = reports.filter((r) => r.includes('elsewhereSummary'));
    expect(summary).toHaveLength(1);
    const line = JSON.parse(summary[0].slice(summary[0].indexOf(':') + 1)) as { items: string };
    expect(line.items.split(', ')).toEqual([
      `commands.subscription.status.${summaryItem('Deleted', 'hardExpired')}`,
      `commands.subscription.status.${summaryItem('Absent', 'hardExpired')}`,
      `commands.subscription.status.${summaryItem('Absent', 'refreshRecommended')}`,
      `commands.subscription.status.${summaryItem('Absent', 'valid')}`,
    ]);
  });

  it('names the retire command only when a hard-expired other exists, and the --all listing', async () => {
    await executeSubscriptionStatus();
    expect(reports.join('\n')).toContain('status.retireHint');
    expect(reports.join('\n')).toContain('status.listHint');
    reports.length = 0;
    mockReport.mockResolvedValue(
      statusReport([{ repositoryGuid: VALID, freshness: 'valid', kind: 'grand' }])
    );
    await executeSubscriptionStatus();
    expect(reports.join('\n')).not.toContain('retireHint');
    expect(reports.join('\n')).toContain('listHint');
  });

  it('lists the others in a second table with --all, and not without it', async () => {
    await executeSubscriptionStatus();
    expect(tables).toHaveLength(1);
    tables.length = 0;
    reports.length = 0;
    await executeSubscriptionStatus({ all: true });
    expect(tables).toHaveLength(2);
    const others = tables[1];
    expect(others.columns.map((c) => c.key)).toEqual([
      'guid',
      'name',
      'kind',
      'state',
      'hardExpiry',
      'where',
    ]);
    expect(others.rows.map((r) => r.guid)).toEqual([
      '33333333',
      '44444444',
      '55555555',
      '66666666',
    ]);
    expect(others.rows[0]).toMatchObject({
      name: 'old:main',
      where: 'commands.subscription.status.whereDeleted',
    });
    expect(others.rows[1]).toMatchObject({
      name: '-',
      where: 'commands.subscription.status.whereAbsent',
    });
    expect(reports.join('\n')).not.toContain('listHint');
  });

  it('adds presence to every licence in -o json and keeps all rows', async () => {
    const data = (await printedJson()) as { licences: Licence[] };
    expect(tables).toHaveLength(0);
    expect(data.licences).toHaveLength(7);
    const presence = Object.fromEntries(data.licences.map((l) => [l.guid, l.presence]));
    expect(presence).toEqual({
      [GRAND]: 'config',
      [FORK]: 'config',
      [LIVE_OK]: 'config',
      [DELETED]: 'deleted',
      [STRANGER]: 'absent',
      [STRANGER_FRESH]: 'absent',
      [VALID]: 'absent',
    });
    const byGuid = new Map(data.licences.map((l) => [l.guid, l]));
    expect(byGuid.get(GRAND)).toMatchObject({
      name: 'web',
      machine: 'box',
      fix: 'rdc subscription refresh --repo web',
    });
    expect(byGuid.get(DELETED)).toMatchObject({
      name: 'old:main',
      fix: 'rdc subscription retire 33333333',
    });
    expect(byGuid.get(VALID)?.fix).toBeNull();
  });

  it('lists licences with no names and presence absent when there is no config', async () => {
    mockConfig.value = null;
    const data = (await printedJson()) as { licences: Licence[]; repoLicenses: unknown };
    expect(data.licences).toHaveLength(7);
    expect(data.licences.every((l) => l.name === null && l.presence === 'absent')).toBe(true);
    expect(data.repoLicenses).toMatchObject({ scope: 'account' });
  });

  it('has no licences key and prints the account counts when the server sends no per-repo list', async () => {
    mockReport.mockResolvedValue(statusReport(undefined));
    expect(await printedJson()).not.toHaveProperty('licences');
    await executeSubscriptionStatus();
    expect(reports.join('\n')).toContain('status.remoteRepoLicenses:');
    expect(reports.join('\n')).not.toContain('licencesHeader');
  });

  it('prints no licence section when the account tracks no licence', async () => {
    mockReport.mockResolvedValue(statusReport([]));
    await executeSubscriptionStatus();
    expect(reports.join('\n')).not.toContain('licencesHeader');
    expect(tables).toHaveLength(0);
  });

  it('says so when the config holds no repository with a licence', async () => {
    mockReport.mockResolvedValue(
      statusReport([{ repositoryGuid: STRANGER, freshness: 'hard_expired', kind: 'grand' }])
    );
    await executeSubscriptionStatus();
    expect(reports.join('\n')).toContain('status.noLiveLicences');
    expect(tables).toHaveLength(0);
  });

  it('renders the machine slots as a table', async () => {
    const report = statusReport(recent);
    report.machineSlots = {
      active: 2,
      max: 1,
      machines: [
        { machineId: 'aaaaaaaaaaaaaaaaaaaa', lastSeenAt: '2026-11-01', overLimit: false },
        { machineId: 'bbbbbbbbbbbbbbbbbbbb', lastSeenAt: '2026-11-02', overLimit: true },
      ],
    };
    mockReport.mockResolvedValue(report);
    await executeSubscriptionStatus();
    expect(tables.at(-1)?.rows).toEqual([
      { machine: 'aaaaaaaaaaaa...', lastSeen: '2026-11-01', state: '-' },
      {
        machine: 'bbbbbbbbbbbb...',
        lastSeen: '2026-11-02',
        state: 'commands.subscription.status.overLimitCell',
      },
    ]);
  });

  it('a config that cannot be read fails the status instead of printing it without names', async () => {
    mockConfig.value = new Error('config unreadable');
    await expect(executeSubscriptionStatus()).rejects.toThrow('config unreadable');
    expect(reports.join('\n')).not.toContain('licencesHeader');
  });
});
