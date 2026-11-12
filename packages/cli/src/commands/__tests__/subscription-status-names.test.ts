/**
 * `subscription status` (account view) lists every tracked licence with the name the local config
 * gives its GUID, and the exact command that settles it.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const mockPrint = vi.hoisted(() => vi.fn());
const reports = vi.hoisted(() => [] as string[]);
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: vi.fn(),
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

const recent = [
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
    machineSlots: { active: 0, max: 1, machines: [] },
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

async function printedData(): Promise<Record<string, unknown>> {
  setOutputFormat('json');
  try {
    await executeSubscriptionStatus();
  } finally {
    setOutputFormat('table');
  }
  expect(mockPrint).toHaveBeenCalledTimes(1);
  return mockPrint.mock.calls[0][0] as Record<string, unknown>;
}

type Licence = {
  guid: string;
  name: string | null;
  machine: string | null;
  fix: string | null;
  freshness: string;
};

/** The `name` each licence row was rendered with, in print order. */
function rowNames(): string[] {
  return reports
    .filter((r) => r.startsWith('commands.subscription.status.licenceRow:'))
    .map((r) => (JSON.parse(r.slice(r.indexOf(':') + 1)) as { name: string }).name);
}

describe('subscription status names every licence', () => {
  beforeEach(() => {
    reports.length = 0;
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
        },
        deletedRepositories: [{ name: 'old', tag: 'main', repositoryGuid: DELETED }],
      },
    };
  });

  it('prints ref@machine and the refresh command for a GUID in the config', async () => {
    await executeSubscriptionStatus();
    const out = reports.join('\n');
    expect(out).toContain('commands.subscription.status.licencesHeader');
    expect(out).toContain('"name":"web@box"');
    expect(out).toContain('"name":"web:feat@box"');
    expect(out).toContain('"fix":"rdc subscription refresh --repo web"');
    expect(out).toContain('"fix":"rdc subscription refresh --repo web:feat"');
  });

  it('prints the short GUID and "not in this config" for a GUID outside the config', async () => {
    await executeSubscriptionStatus();
    expect(rowNames()).toContain(
      'commands.subscription.status.licenceNotInConfig:{"guid":"44444444"}'
    );
    expect(reports.join('\n')).not.toContain(STRANGER);
  });

  it('prints retire <guid8> for a deleted repository and for a hard-expired GUID outside the config', async () => {
    await executeSubscriptionStatus();
    const out = reports.join('\n');
    expect(rowNames()).toContain('commands.subscription.status.licenceDeleted:{"name":"old:main"}');
    expect(out).toContain('"fix":"rdc subscription retire 33333333"');
    expect(out).toContain('"fix":"rdc subscription retire 44444444"');
  });

  it('orders the rows by hard expiry, soonest first', async () => {
    await executeSubscriptionStatus();
    expect(rowNames()).toEqual([
      'commands.subscription.status.licenceDeleted:{"name":"old:main"}',
      'web:feat@box',
      'commands.subscription.status.licenceNotInConfig:{"guid":"44444444"}',
      'web@box',
      'commands.subscription.status.licenceNotInConfig:{"guid":"55555555"}',
      'commands.subscription.status.licenceNotInConfig:{"guid":"66666666"}',
    ]);
  });

  it('adds licences[] to -o json, each with name, machine, freshness and fix', async () => {
    const data = await printedData();
    const licences = data.licences as Licence[];
    expect(licences).toHaveLength(6);
    const byGuid = new Map(licences.map((l) => [l.guid, l]));
    expect(byGuid.get(GRAND)).toMatchObject({
      name: 'web',
      machine: 'box',
      kind: 'grand',
      freshness: 'refresh_recommended',
      refreshRecommendedAt: '2026-11-01T00:00:00.000Z',
      hardExpiresAt: '2026-11-20T00:00:00.000Z',
      fix: 'rdc subscription refresh --repo web',
    });
    expect(byGuid.get(FORK)).toMatchObject({ name: 'web:feat', machine: 'box' });
    expect(byGuid.get(DELETED)).toMatchObject({
      name: 'old:main',
      machine: null,
      fix: 'rdc subscription retire 33333333',
    });
    expect(byGuid.get(STRANGER)).toMatchObject({
      name: null,
      machine: null,
      fix: 'rdc subscription retire 44444444',
    });
  });

  it('gives a valid licence and a refresh-recommended GUID outside the config no fix (controls)', async () => {
    const licences = (await printedData()).licences as Licence[];
    const byGuid = new Map(licences.map((l) => [l.guid, l]));
    expect(byGuid.get(VALID)?.fix).toBeNull();
    expect(byGuid.get(STRANGER_FRESH)?.fix).toBeNull();
    expect(reports.join('\n')).not.toContain('retire 55555555');
  });

  it('lists the licences with no names when there is no config', async () => {
    mockConfig.value = null;
    const data = await printedData();
    const licences = data.licences as Licence[];
    expect(licences).toHaveLength(6);
    expect(licences.every((l) => l.name === null && l.machine === null)).toBe(true);
    expect(data.repoLicenses).toMatchObject({ scope: 'account' });
  });

  it('has no licences key when the server sends no per-repo list', async () => {
    mockReport.mockResolvedValue(statusReport(undefined));
    const data = await printedData();
    expect(data).not.toHaveProperty('licences');
    await executeSubscriptionStatus();
    expect(reports.join('\n')).not.toContain('licencesHeader');
  });

  it('prints no licence section when the account tracks no licence', async () => {
    mockReport.mockResolvedValue(statusReport([]));
    await executeSubscriptionStatus();
    expect(reports.join('\n')).not.toContain('licencesHeader');
  });

  it('a config that cannot be read fails the status instead of printing it without names', async () => {
    mockConfig.value = new Error('config unreadable');
    await expect(executeSubscriptionStatus()).rejects.toThrow('config unreadable');
    expect(reports.join('\n')).not.toContain('licencesHeader');
  });
});
