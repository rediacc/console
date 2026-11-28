/**
 * `subscription retire <guid>`: the confirm gate, the prefix match, the in-config refusal, and the one
 * retire route `repo delete` shares. `--expired`: lists by default, retires with `--apply`, and retires
 * only what the machines' listings prove gone.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const infos = vi.hoisted(() => [] as string[]);
const successes = vi.hoisted(() => [] as string[]);
const warns = vi.hoisted(() => [] as string[]);
const reports = vi.hoisted(() => [] as string[]);
const tables = vi.hoisted(() => [] as unknown[][]);
const mockPrint = vi.hoisted(() => vi.fn());
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: (m: string) => infos.push(m),
    report: (m: string) => reports.push(m),
    format: (rows: unknown[]) => {
      tables.push(rows);
      return 'TABLE';
    },
    warn: (m: string) => warns.push(m),
    success: (m: string) => successes.push(m),
    print: mockPrint,
  },
}));

const mockReport = vi.hoisted(() => vi.fn());
vi.mock('../../services/account/license.js', () => ({
  fetchSubscriptionLicenseReportOrThrow: mockReport,
}));
const tokenKind = vi.hoisted(() => ({ value: 'ready' }));
vi.mock('../../services/account/subscription-auth.js', () => ({
  getSubscriptionTokenState: () => ({ kind: tokenKind.value, token: {} }),
  getSubscriptionScopeMismatch: () => null,
  getSubscriptionServerUrl: () => 'http://localhost',
}));
const mockConfig = vi.hoisted(() => ({ value: null as unknown }));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getTeam: vi.fn().mockResolvedValue(undefined),
    getCurrent: () => Promise.resolve(mockConfig.value),
  },
}));
const mockFetch = vi.hoisted(() => vi.fn());
vi.mock('../../services/account/account-client.js', () => ({ accountServerFetch: mockFetch }));
const mockConfirm = vi.hoisted(() => vi.fn());
vi.mock('../../utils/prompt.js', () => ({ askConfirm: mockConfirm }));
const mockListRepoGuids = vi.hoisted(() => vi.fn());
vi.mock('../../services/repo/repo-mount-check.js', () => ({ listRepoGuids: mockListRepoGuids }));

import { setOutputFormat } from '../../utils/errors.js';
import { settleRepoLicense } from '../repo-delete-settle.js';
import { executeSubscriptionRetire } from '../subscription-retire.js';

const LIVE = '11111111-aaaa-4aaa-8aaa-000000000001';
const GONE = '22222222-bbbb-4bbb-8bbb-000000000002';
const TWIN_A = '33333333-cccc-4ccc-8ccc-000000000003';
const TWIN_B = '33333333-dddd-4ddd-8ddd-000000000004';
const UNKNOWN = '44444444-eeee-4eee-8eee-000000000005';

const recent = [
  { repositoryGuid: LIVE, freshness: 'refresh_recommended' },
  { repositoryGuid: GONE, freshness: 'hard_expired' },
  { repositoryGuid: TWIN_A, freshness: 'hard_expired' },
  { repositoryGuid: TWIN_B, freshness: 'hard_expired' },
  { repositoryGuid: UNKNOWN, freshness: 'valid' },
];

const retirePath = (guid: string) => `/account/api/v1/licenses/repos/${guid}/retire`;

function setTty(value: boolean | undefined): void {
  Object.defineProperty(process.stdin, 'isTTY', { value, configurable: true });
}

describe('subscription retire', () => {
  const originalTty = process.stdin.isTTY;

  beforeEach(() => {
    infos.length = 0;
    successes.length = 0;
    warns.length = 0;
    mockFetch.mockReset().mockResolvedValue({ repositoryGuid: GONE, retired: true });
    mockConfirm.mockReset();
    mockPrint.mockReset();
    tokenKind.value = 'ready';
    setOutputFormat('table');
    setTty(true);
    mockReport.mockResolvedValue({
      planCode: 'ENTERPRISE',
      status: 'active',
      machineSlots: { active: 0, max: 1, machines: [] },
      repoLicenseIssuances: { used: 0, limit: 10 },
      repoLicenses: {
        totalTrackedRepos: 5,
        validCount: 1,
        refreshRecommendedCount: 1,
        hardExpiredCount: 3,
        recent,
      },
    });
    mockConfig.value = {
      resources: {
        repositories: {
          web: {
            grand: 'main',
            placement: { machine: 'box' },
            tags: { main: { repositoryGuid: LIVE } },
          },
        },
        deletedRepositories: [{ name: 'old', tag: 'main', repositoryGuid: GONE }],
      },
    };
  });

  afterEach(() => {
    setTty(originalTty);
  });

  it('posts nothing when the operator answers n at the prompt', async () => {
    mockConfirm.mockResolvedValue(false);
    await executeSubscriptionRetire(GONE.slice(0, 8));
    expect(mockConfirm).toHaveBeenCalledTimes(1);
    expect(mockConfirm.mock.calls[0][0]).toContain('"name":"old:main"');
    expect(mockFetch).not.toHaveBeenCalled();
    expect(successes).toEqual([]);
  });

  it('posts once to the retire route when the operator answers y', async () => {
    mockConfirm.mockResolvedValue(true);
    await executeSubscriptionRetire(GONE.slice(0, 8));
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch).toHaveBeenCalledWith(retirePath(GONE), { method: 'POST' });
    expect(successes.join()).toContain('"name":"old:main"');
  });

  it('--yes posts once without asking', async () => {
    await executeSubscriptionRetire(GONE, { yes: true });
    expect(mockConfirm).not.toHaveBeenCalled();
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch).toHaveBeenCalledWith(retirePath(GONE), { method: 'POST' });
  });

  it('refuses without --yes when stdin is not a terminal, and posts nothing', async () => {
    setTty(undefined);
    await expect(executeSubscriptionRetire(GONE)).rejects.toThrow(
      'commands.subscription.retire.needsYes'
    );
    expect(mockConfirm).not.toHaveBeenCalled();
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('does not need a terminal when --yes is given (control)', async () => {
    setTty(undefined);
    await executeSubscriptionRetire(GONE, { yes: true });
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it('refuses an ambiguous prefix and names every match', async () => {
    const error = await executeSubscriptionRetire('33333333', { yes: true }).catch((e: Error) => e);
    expect((error as Error).message).toContain('commands.subscription.retire.ambiguous');
    expect((error as Error).message).toContain(TWIN_A);
    expect((error as Error).message).toContain(TWIN_B);
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('takes a longer prefix that tells the twins apart (control)', async () => {
    await executeSubscriptionRetire('33333333-cccc', { yes: true });
    expect(mockFetch).toHaveBeenCalledWith(retirePath(TWIN_A), { method: 'POST' });
  });

  it('refuses a prefix shorter than 8 characters and a GUID the report does not hold', async () => {
    await expect(executeSubscriptionRetire('2222222', { yes: true })).rejects.toThrow(
      'commands.subscription.retire.tooShort'
    );
    await expect(executeSubscriptionRetire('99999999', { yes: true })).rejects.toThrow(
      'commands.subscription.retire.notFound'
    );
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('refuses a GUID still in the config whose license is not hard-expired, without --force', async () => {
    await expect(executeSubscriptionRetire(LIVE, { yes: true })).rejects.toThrow(
      'commands.subscription.retire.inConfig'
    );
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('retires that GUID with --force (control)', async () => {
    await executeSubscriptionRetire(LIVE, { yes: true, force: true });
    expect(mockFetch).toHaveBeenCalledWith(retirePath(LIVE), { method: 'POST' });
  });

  it('retires a GUID the config does not know even when its license is valid (control)', async () => {
    await executeSubscriptionRetire(UNKNOWN, { yes: true });
    expect(mockFetch).toHaveBeenCalledWith(retirePath(UNKNOWN), { method: 'POST' });
  });

  it('names a GUID with no config entry by its 8-character form', async () => {
    mockConfig.value = null;
    mockConfirm.mockResolvedValue(false);
    await executeSubscriptionRetire(GONE);
    expect(mockConfirm.mock.calls[0][0]).toContain(`"name":"${GONE.slice(0, 8)}"`);
  });

  it('prints the result as data under -o json', async () => {
    setOutputFormat('json');
    await executeSubscriptionRetire(GONE, { yes: true });
    expect(mockPrint).toHaveBeenCalledWith(
      { repositoryGuid: GONE, name: 'old:main', retired: true },
      'json'
    );
    expect(successes).toEqual([]);
  });

  it('refuses with the login diagnostic when there is no token, and posts nothing', async () => {
    tokenKind.value = 'missing';
    await expect(executeSubscriptionRetire(GONE, { yes: true })).rejects.toThrow(
      'errors.subscription.notLoggedIn'
    );
    expect(mockReport).not.toHaveBeenCalled();
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('shows the server failure instead of reporting a retire that did not happen', async () => {
    mockFetch.mockRejectedValue(new Error('403 forbidden'));
    await expect(executeSubscriptionRetire(GONE, { yes: true })).rejects.toThrow('403 forbidden');
    expect(successes).toEqual([]);
  });
});

describe('subscription retire --expired', () => {
  const LIVE_EXPIRED = '55555555-ffff-4fff-8fff-000000000005';
  const originalTty = process.stdin.isTTY;
  const opts = { expired: true };
  const apply = { expired: true, apply: true };

  function reportWith(extra: { repositoryGuid: string; freshness: string }[]): void {
    const all = [...recent, ...extra];
    mockReport.mockResolvedValue({
      planCode: 'ENTERPRISE',
      status: 'active',
      machineSlots: { active: 0, max: 1, machines: [] },
      repoLicenseIssuances: { used: 0, limit: 10 },
      repoLicenses: {
        totalTrackedRepos: all.length,
        validCount: 1,
        refreshRecommendedCount: 1,
        hardExpiredCount: all.filter((r) => r.freshness === 'hard_expired').length,
        recent: all,
      },
    });
  }

  beforeEach(() => {
    infos.length = 0;
    reports.length = 0;
    tables.length = 0;
    warns.length = 0;
    process.exitCode = undefined;
    mockFetch.mockReset().mockResolvedValue({ repositoryGuid: GONE, retired: true });
    mockConfirm.mockReset().mockResolvedValue(true);
    mockPrint.mockReset();
    tokenKind.value = 'ready';
    setOutputFormat('table');
    setTty(true);
    reportWith([{ repositoryGuid: LIVE_EXPIRED, freshness: 'hard_expired' }]);
    // The machine still holds both config-held images: nothing the config holds is gone.
    mockListRepoGuids.mockReset().mockResolvedValue(new Set([LIVE, LIVE_EXPIRED]));
    mockConfig.value = {
      resources: {
        machines: { box: {} },
        repositories: {
          web: {
            grand: 'main',
            placement: { machine: 'box' },
            tags: { main: { repositoryGuid: LIVE }, dead: { repositoryGuid: LIVE_EXPIRED } },
          },
        },
        deletedRepositories: [{ name: 'old', tag: 'main', repositoryGuid: GONE }],
      },
    };
  });

  afterEach(() => {
    setTty(originalTty);
    process.exitCode = undefined;
    setOutputFormat('table');
  });

  const retiredGuids = () =>
    mockFetch.mock.calls.map((c) => String(c[0]).split('/repos/')[1].split('/')[0]).sort();

  it('lists by default and retires nothing, without asking, and names the apply command', async () => {
    setTty(undefined);
    await executeSubscriptionRetire(undefined, opts);
    expect(mockFetch).not.toHaveBeenCalled();
    expect(mockConfirm).not.toHaveBeenCalled();
    expect(tables).toHaveLength(1);
    expect(tables[0]).toHaveLength(3);
    expect(infos.join()).toContain('expiredDryRun');
  });

  it('--apply retires every hard-expired deleted or unknown licence and never a live one', async () => {
    await executeSubscriptionRetire(undefined, apply);
    expect(retiredGuids()).toEqual([GONE, TWIN_A, TWIN_B]);
    expect(retiredGuids()).not.toContain(LIVE_EXPIRED);
    expect(retiredGuids()).not.toContain(LIVE);
    expect(retiredGuids()).not.toContain(UNKNOWN);
    expect(mockConfirm).not.toHaveBeenCalled();
    expect(reports.join('\n')).toContain('"retired":3,"skipped":1,"failed":0');
    expect(process.exitCode).toBeUndefined();
  });

  it('--apply retires a config-held licence whose image its machine no longer lists', async () => {
    mockListRepoGuids.mockResolvedValue(new Set([LIVE]));
    await executeSubscriptionRetire(undefined, apply);
    expect(retiredGuids()).toEqual(
      [GONE, TWIN_A, TWIN_B, LIVE_EXPIRED].sort((a, b) => (a < b ? -1 : 1))
    );
    const rows = tables[0] as Record<string, string>[];
    const gone = rows.find((r) => r.guid === LIVE_EXPIRED.slice(0, 8));
    expect(gone?.where).toContain('commands.subscription.status.whereGone');
    expect(gone?.where).toContain('"machine":"box"');
    expect(reports.join('\n')).toContain('"retired":4,"skipped":0,"failed":0');
  });

  it('keeps a config-held licence when its machine cannot be listed, and says which machine', async () => {
    mockListRepoGuids.mockRejectedValue(new Error('ssh: connect refused'));
    await executeSubscriptionRetire(undefined, apply);
    expect(retiredGuids()).not.toContain(LIVE_EXPIRED);
    expect(warns.join()).toContain('commands.subscription.retire.expiredListFailed');
    expect(warns.join()).toContain('"place":"box"');
    expect(warns.join()).toContain('ssh: connect refused');
    // One failed listing is warned once, not once per licence that needed it.
    expect(warns.filter((w) => w.includes('expiredListFailed'))).toHaveLength(1);
  });

  it('keeps a deleted or unknown licence whose GUID a machine still lists', async () => {
    mockListRepoGuids.mockResolvedValue(new Set([LIVE, LIVE_EXPIRED, TWIN_A]));
    await executeSubscriptionRetire(undefined, apply);
    expect(retiredGuids()).toEqual([GONE, TWIN_B]);
    expect(reports.join('\n')).toContain('"retired":2,"skipped":2,"failed":0');
  });

  it('lists each place once: every machine, then each local named datastore at its mount', async () => {
    const DS_GUID = '66666666-aaaa-4aaa-8aaa-000000000006';
    const RBD_GUID = '77777777-aaaa-4aaa-8aaa-000000000007';
    reportWith([
      { repositoryGuid: LIVE_EXPIRED, freshness: 'hard_expired' },
      { repositoryGuid: DS_GUID, freshness: 'hard_expired' },
      { repositoryGuid: RBD_GUID, freshness: 'hard_expired' },
    ]);
    mockConfig.value = {
      resources: {
        machines: { box: {} },
        datastores: {
          fast: { backend: { kind: 'local', machine: 'box' } },
          shared: { backend: { kind: 'rbd', pool: 'p' } },
        },
        repositories: {
          web: {
            grand: 'main',
            placement: { machine: 'box' },
            tags: { main: { repositoryGuid: LIVE }, dead: { repositoryGuid: LIVE_EXPIRED } },
          },
          db: {
            grand: 'main',
            placement: { datastore: 'fast' },
            tags: { main: { repositoryGuid: DS_GUID } },
          },
          ceph: {
            grand: 'main',
            placement: { datastore: 'shared' },
            tags: { main: { repositoryGuid: RBD_GUID } },
          },
        },
        deletedRepositories: [{ name: 'old', tag: 'main', repositoryGuid: GONE }],
      },
    };
    // The default datastore holds the web images; the named one is empty, so its repo is gone.
    mockListRepoGuids.mockImplementation((_machine: string, o: { datastore?: string } = {}) =>
      Promise.resolve(o.datastore ? new Set<string>() : new Set([LIVE, LIVE_EXPIRED]))
    );
    await executeSubscriptionRetire(undefined, apply);
    expect(mockListRepoGuids).toHaveBeenCalledTimes(2);
    expect(mockListRepoGuids.mock.calls[0]).toEqual(['box', {}]);
    expect(mockListRepoGuids.mock.calls[1][0]).toBe('box');
    expect(mockListRepoGuids.mock.calls[1][1].datastore).toMatch(/fast$/);
    expect(retiredGuids()).toContain(DS_GUID);
    // An RBD datastore names no machine to list: its licence is kept, never guessed gone.
    expect(retiredGuids()).not.toContain(RBD_GUID);
    expect(retiredGuids()).not.toContain(LIVE_EXPIRED);
  });

  it('lists no machine when nothing is hard-expired', async () => {
    mockReport.mockResolvedValue({
      planCode: 'ENTERPRISE',
      status: 'active',
      machineSlots: { active: 0, max: 1, machines: [] },
      repoLicenseIssuances: { used: 0, limit: 10 },
      repoLicenses: {
        totalTrackedRepos: 1,
        validCount: 1,
        refreshRecommendedCount: 0,
        hardExpiredCount: 0,
        recent: [{ repositoryGuid: LIVE, freshness: 'valid' }],
      },
    });
    await executeSubscriptionRetire(undefined, apply);
    expect(mockListRepoGuids).not.toHaveBeenCalled();
    expect(infos.join()).toContain('expiredNone');
  });

  it('without --apply under -o json prints the would-retire list and changes nothing', async () => {
    setOutputFormat('json');
    await executeSubscriptionRetire(undefined, opts);
    expect(mockFetch).not.toHaveBeenCalled();
    expect(mockPrint).toHaveBeenCalledTimes(1);
    const [payload, format] = mockPrint.mock.calls[0];
    expect(format).toBe('json');
    expect(payload).toMatchObject({ retired: [], failed: [], dryRun: true });
    expect(payload.would).toHaveLength(3);
  });

  it('exits non-zero when any retire failed, after trying the rest', async () => {
    mockFetch.mockImplementation((path: string) =>
      path.includes(TWIN_A) ? Promise.reject(new Error('503')) : Promise.resolve({ retired: true })
    );
    await executeSubscriptionRetire(undefined, apply);
    expect(mockFetch).toHaveBeenCalledTimes(3);
    expect(process.exitCode).toBe(1);
    expect(warns.join()).toContain('503');
    expect(reports.join('\n')).toContain('"retired":2,"skipped":1,"failed":1');
  });

  it('refuses a GUID together with --expired, and --apply without it', async () => {
    await expect(executeSubscriptionRetire(GONE, { ...opts, yes: true })).rejects.toThrow(
      'commands.subscription.retire.expiredWithGuid'
    );
    await expect(executeSubscriptionRetire(undefined, { yes: true })).rejects.toThrow(
      'commands.subscription.retire.needsGuidOrExpired'
    );
    await expect(executeSubscriptionRetire(GONE, { apply: true, yes: true })).rejects.toThrow(
      'commands.subscription.retire.applyNeedsExpired'
    );
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('needs a config that holds repositories', async () => {
    mockConfig.value = null;
    await expect(executeSubscriptionRetire(undefined, apply)).rejects.toThrow(
      'commands.subscription.retire.expiredNeedsConfig'
    );
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('says so when nothing is retirable, and prints data under -o json', async () => {
    mockReport.mockResolvedValue({
      planCode: 'ENTERPRISE',
      status: 'active',
      machineSlots: { active: 0, max: 1, machines: [] },
      repoLicenseIssuances: { used: 0, limit: 10 },
      repoLicenses: {
        totalTrackedRepos: 1,
        validCount: 0,
        refreshRecommendedCount: 0,
        hardExpiredCount: 1,
        recent: [{ repositoryGuid: LIVE_EXPIRED, freshness: 'hard_expired' }],
      },
    });
    await executeSubscriptionRetire(undefined, apply);
    expect(infos.join()).toContain('expiredNone');
    setOutputFormat('json');
    await executeSubscriptionRetire(undefined, apply);
    expect(mockPrint).toHaveBeenCalledWith(
      { retired: [], failed: [], skipped: 1, dryRun: false },
      'json'
    );
    expect(mockFetch).not.toHaveBeenCalled();
  });
});

describe('repo delete retires through the same route', () => {
  beforeEach(() => {
    warns.length = 0;
    tokenKind.value = 'ready';
    mockFetch.mockReset().mockResolvedValue({ repositoryGuid: GONE, retired: true });
  });

  it('posts the repository GUID to the retire route', async () => {
    await settleRepoLicense('old', { repositoryGuid: GONE });
    expect(mockFetch).toHaveBeenCalledWith(retirePath(GONE), { method: 'POST' });
    expect(warns).toEqual([]);
  });

  it('warns and does not throw when the server refuses', async () => {
    mockFetch.mockRejectedValue(new Error('boom'));
    await settleRepoLicense('old', { repositoryGuid: GONE });
    expect(warns.join()).toContain('licenseRetireFailed');
    expect(warns.join()).toContain('boom');
  });

  it('stays quiet on a 404: the server holds no licence of that GUID for this token', async () => {
    mockFetch.mockRejectedValue(Object.assign(new Error('Repository not found'), { status: 404 }));
    await settleRepoLicense('old', { repositoryGuid: GONE });
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(warns).toEqual([]);
  });

  it('posts nothing without a token (control)', async () => {
    tokenKind.value = 'missing';
    await settleRepoLicense('old', { repositoryGuid: GONE });
    expect(mockFetch).not.toHaveBeenCalled();
  });
});
