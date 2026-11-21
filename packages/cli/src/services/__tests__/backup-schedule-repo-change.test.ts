/**
 * The two questions a repository change asks before it touches a machine's backup schedule: does the change move a
 * unit at all (answered from the config, no SSH), and does this config own the deployed schedule (the origin the
 * units record in `--expect-account-server`).
 */
import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockGetLocalConfig = vi.hoisted(() => vi.fn());
const mockGetBackupStrategy = vi.hoisted(() => vi.fn());
const mockGetCurrent = vi.hoisted(() => vi.fn());
vi.mock('../config/config-resources.js', () => ({
  configService: {
    getLocalConfig: mockGetLocalConfig,
    getBackupStrategy: mockGetBackupStrategy,
    getCurrent: mockGetCurrent,
  },
}));

const {
  parseRecordedOrigins,
  readRecordedScheduleOrigins,
  repoChangeMovesSchedule,
  scheduleOwnerRefusal,
} = await import('../backup/backup-schedule-repo-change.js');

const MAIL = '20000000-0000-4000-8000-000000000001';
const FORK = '20000000-0000-4000-8000-000000000002';
const GITLAB = '20000000-0000-4000-8000-000000000003';
const STABLE = 'https://account.example.test';
const BENCH = 'https://other.example.test';

function config() {
  return {
    resources: {
      machines: { hostinger: { ip: '10.0.0.1', user: 'u', datastore: WK_DATASTORE_PATH } },
      repositories: {
        mail: {
          placement: { machine: 'hostinger' },
          grand: 'latest',
          tags: { latest: { repositoryGuid: MAIL }, 'pre-cve': { repositoryGuid: FORK } },
        },
        gitlab: {
          placement: { machine: 'hostinger' },
          grand: 'latest',
          tags: { latest: { repositoryGuid: GITLAB } },
        },
      },
    },
    state: {},
  };
}

function bind(strategy: Record<string, unknown> | undefined): void {
  mockGetLocalConfig.mockResolvedValue({
    machines: { hostinger: { ip: '10.0.0.1', backupStrategies: ['nightly'] } },
  });
  mockGetBackupStrategy.mockResolvedValue(
    strategy && { schedule: '0 3 * * *', mode: 'hot', destinations: [], ...strategy }
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGetCurrent.mockResolvedValue(config());
});

describe('repoChangeMovesSchedule', () => {
  it('a per-repo target on the exact grand tag (the hostinger mail shape) is not moved by a fork', async () => {
    bind({ include: ['mail:latest'], repoTargets: { 'mail:latest': { rpo: '24h' } } });
    expect(await repoChangeMovesSchedule('hostinger', FORK)).toBe(false);
  });

  it('an include naming another family is not moved by a fork of mail', async () => {
    bind({ include: ['gitlab'] });
    expect(await repoChangeMovesSchedule('hostinger', FORK)).toBe(false);
  });

  it('a strategy over every repository on the datastore is not moved: its unit names only exclusions', async () => {
    bind({});
    expect(await repoChangeMovesSchedule('hostinger', FORK)).toBe(false);
  });

  it('control: an include naming the family takes the fork GUID, so the schedule moves', async () => {
    bind({ include: ['mail'] });
    expect(await repoChangeMovesSchedule('hostinger', FORK)).toBe(true);
  });

  it('control: a `mail:*` per-repo target gives the fork a unit of its own, so the schedule moves', async () => {
    bind({ repoTargets: { 'mail:*': { rpo: '1h' } } });
    expect(await repoChangeMovesSchedule('hostinger', FORK)).toBe(true);
  });

  it('a machine that binds no strategy, or only a disabled one, is not moved', async () => {
    mockGetLocalConfig.mockResolvedValue({ machines: { hostinger: { ip: '10.0.0.1' } } });
    expect(await repoChangeMovesSchedule('hostinger', FORK)).toBe(false);
    bind({ include: ['mail'], enabled: false });
    expect(await repoChangeMovesSchedule('hostinger', FORK)).toBe(false);
  });

  it('a spec that cannot be resolved answers false rather than throwing', async () => {
    bind({ include: ['ghost'] });
    expect(await repoChangeMovesSchedule('hostinger', FORK)).toBe(false);
  });
});

describe('scheduleOwnerRefusal', () => {
  it('admits a schedule whose every unit records this config', () => {
    expect(scheduleOwnerRefusal([STABLE], STABLE)).toBeUndefined();
  });

  it('refuses a schedule held to another account server, naming both', () => {
    const reason = scheduleOwnerRefusal([STABLE], BENCH);
    expect(reason).toContain(STABLE);
    expect(reason).toContain(BENCH);
  });

  it('refuses when any unit records another server', () => {
    expect(scheduleOwnerRefusal([BENCH, STABLE], STABLE)).toContain(BENCH);
  });

  it('refuses a schedule that records no server, and a config that names none', () => {
    expect(scheduleOwnerRefusal([], STABLE)).toContain('record no account server');
    expect(scheduleOwnerRefusal([STABLE], undefined)).toContain('names no account server');
  });
});

describe('readRecordedScheduleOrigins', () => {
  it('reads the origins with one grep over the backup service units and dedupes them', async () => {
    const execStreaming = vi.fn((_cmd: string, opts: { onStdout?: (d: Buffer) => void }) => {
      opts.onStdout?.(
        Buffer.from(
          `--expect-account-server ${STABLE}\n--expect-account-server ${STABLE}\n--expect-account-server ${BENCH}\n`
        )
      );
      return Promise.resolve(0);
    });
    expect(await readRecordedScheduleOrigins({ execStreaming } as never)).toEqual([STABLE, BENCH]);
    expect(execStreaming).toHaveBeenCalledOnce();
    expect(String(execStreaming.mock.calls[0][0])).toContain(
      '/etc/systemd/system/rediacc-backup-*.service'
    );
  });

  it('parses nothing out of unrelated lines', () => {
    expect(parseRecordedOrigins('\nExecStart=/usr/bin/renet\n--expect-account-server\n')).toEqual(
      []
    );
  });
});
