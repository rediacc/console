import {
  WK_DATASTORE_PATH,
  WK_ETC_DIR,
  WK_OPT_DIR,
} from '@rediacc/shared/config/well-known.generated';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

// First-time module evaluation in CI runners can exceed the 5s default test timeout (this file mocks 30+ deps before importing backup-schedule). Pull
// the import into a single beforeAll with a generous timeout; the per-test
// `await import` calls that follow then hit vitest's module cache and return instantly. Cheaper than bumping every individual test's timeout.
beforeAll(async () => {
  await import('../backup/backup-schedule.js');
}, 30000);

const mockExecStreaming = vi.fn();
const mockConnect = vi.fn().mockResolvedValue(undefined);
const mockClose = vi.fn();

const mockAcquireRemoteRenet = vi
  .fn()
  .mockResolvedValue({ remotePath: '/usr/bin/renet', uploaded: false });
const mockReadSSHKey = vi.fn().mockResolvedValue('PRIVATE_KEY');
const mockRunCommandJob = vi.fn();
const mockRefreshRepoLicensesBatch = vi.fn();

const mockGetBackupStrategy = vi.fn();
// Defaults to "no strategies beyond those under test" so the unbound-strategy warning has something well-formed to read. Tests that care override it.
const mockListBackupStrategies = vi.fn(() => Promise.resolve({}));
const mockGetLocalConfig = vi.fn();
const mockGetCurrent = vi.fn();

const mockOutputInfo = vi.fn();
const mockOutputWarn = vi.fn();

vi.mock('../../remote/sftp/index.js', () => ({
  SFTPClient: vi.fn(
    class MockSFTPClient {
      connect = mockConnect;
      close = mockClose;
      execStreaming = mockExecStreaming;
    }
  ),
}));

vi.mock('../renet/renet-execution.js', () => ({
  acquireRemoteRenet: mockAcquireRemoteRenet,
  readSSHKey: mockReadSSHKey,
}));

vi.mock('../jobs/command-job.js', () => ({
  runCommandJob: mockRunCommandJob,
  pendingExitCode: () => undefined,
}));

vi.mock('../account/license.js', () => ({
  refreshRepoLicensesBatch: mockRefreshRepoLicensesBatch,
}));

vi.mock('../config/config-resources.js', () => ({
  configService: {
    getBackupStrategy: mockGetBackupStrategy,
    listBackupStrategies: mockListBackupStrategies,
    getLocalConfig: mockGetLocalConfig,
    getCurrent: mockGetCurrent,
  },
}));

vi.mock('../core/output.js', () => ({
  outputService: {
    info: mockOutputInfo,
    warn: mockOutputWarn,
  },
}));

// --------------------------------------------------------------------------- Test helpers ---------------------------------------------------------------------------

interface ExecScript {
  match: string | RegExp;
  stdout?: string;
  exit?: number;
}

/**
 * Install a per-test scripted mock for execStreaming. Each call walks the
 * script in order and returns the first matching entry's stdout/exit.
 * Unmatched commands resolve with exit=0 and empty stdout (safe default).
 */
function scriptedExec(scripts: ExecScript[]): void {
  mockExecStreaming.mockImplementation(
    (
      cmd: string,
      opts?: {
        stdin?: string;
        onStdout?: (data: Buffer) => void;
        onStderr?: (data: Buffer) => void;
      }
    ): Promise<number> => {
      for (const s of scripts) {
        const matches = typeof s.match === 'string' ? cmd.includes(s.match) : s.match.test(cmd);
        if (matches) {
          if (s.stdout !== undefined && opts?.onStdout) {
            opts.onStdout(Buffer.from(s.stdout));
          }
          return Promise.resolve(s.exit ?? 0);
        }
      }
      // The deploy reads the machine's core count for the unit's CPUQuota; an unscripted machine has eight.
      if (cmd === 'nproc') opts?.onStdout?.(Buffer.from('8\n'));
      return Promise.resolve(0);
    }
  );
}

/** Build a `systemctl show` record block for a single unit. */
function showRecord(id: string, props: Record<string, string>): string {
  const lines = [`Id=${id}`, ...Object.entries(props).map(([k, v]) => `${k}=${v}`)];
  return `${lines.join('\n')}\n\n`;
}

function idleServiceRecord(unit: string): string {
  return showRecord(unit, {
    LoadState: 'loaded',
    ActiveState: 'inactive',
    SubState: 'dead',
    UnitFileState: 'static',
  });
}

function healthyTimerRecord(unit: string): string {
  return showRecord(unit, {
    LoadState: 'loaded',
    ActiveState: 'active',
    SubState: 'waiting',
    UnitFileState: 'enabled',
  });
}

/** The two timers a strategy unit renders: its schedule and the daily full verify. */
function healthyTimers(unitName: string): string {
  return (
    healthyTimerRecord(`rediacc-backup-${unitName}.timer`) +
    healthyTimerRecord(`rediacc-backup-${unitName}.verify.timer`)
  );
}

/** Every unit the default strategy renders on the scripted machine, as the machine would hold them. */
async function fullDesired() {
  const { computeDesiredUnits } = await import('../backup/backup-schedule-reconcile.js');
  const { machineUnitSpecs } = await import('../backup/backup-schedule-targets.js');
  const { sha256Hex } = await import('../backup/backup-schedule-unit-generator.js');
  const { expectedAccountServerOrigin } = await import('../backup/backup-store-universe.js');
  const units = computeDesiredUnits(
    machineUnitSpecs(
      [{ name: 'hourly-hot', config: DEFAULT_STRATEGY as never }],
      rdcConfig() as never,
      'hostinger'
    ),
    '/usr/bin/renet',
    8,
    expectedAccountServerOrigin()
  );
  const dir = '/etc/systemd/system';
  const files: { path: string; hash: string; unit: string; kind: 'service' | 'timer' }[] = [];
  for (const [name, unit] of units) {
    files.push({
      path: `${dir}/rediacc-backup-${name}.service`,
      hash: sha256Hex(unit.serviceContent),
      unit: name,
      kind: 'service',
    });
    if (unit.timerContent) {
      files.push({
        path: `${dir}/rediacc-backup-${name}.timer`,
        hash: sha256Hex(unit.timerContent),
        unit: name,
        kind: 'timer',
      });
    }
  }
  const find = files.map((f) => `${f.path}\n`).join('');
  const sha = (override: (f: (typeof files)[number]) => string = (f) => f.hash) =>
    files.map((f) => `${override(f)}  ${f.path}\n`).join('');
  const show =
    [...units.keys()].map((n) => idleServiceRecord(`rediacc-backup-${n}.service`)).join('') +
    files
      .filter((f) => f.kind === 'timer')
      .map((f) => healthyTimerRecord(`rediacc-backup-${f.unit}.timer`))
      .join('');
  return { files, find, sha, show };
}

function notFoundRecord(unit: string): string {
  return showRecord(unit, {
    LoadState: 'not-found',
    ActiveState: 'inactive',
    SubState: 'dead',
    UnitFileState: '',
  });
}

const DEFAULT_LOCAL_CONFIG = {
  renetPath: '/local/renet',
  sshPrivateKey: 'PRIVATE_KEY',
  ssh: { privateKeyPath: '/tmp/key' },
  machines: {
    hostinger: {
      ip: '72.61.137.225',
      user: 'muhammed',
      port: 22,
      datastore: WK_DATASTORE_PATH,
      backupStrategies: ['hourly-hot'],
    },
  },
};

/**
 * The only destination kind a unit can be generated for since the retired
 * sync path was removed on 2026-08-15.
 */
const HOSTED_DEST: import('../../types/index.js').BackupStrategyDestination = {
  kind: 'hosted-service',
  name: 'chunks-hourly',
  enabled: true,
};

/**
 * A destination as the operator's real config holds it: no `kind` field at all.
 * The schema defaults it to `storage` on parse; the generator must refuse it
 * either way rather than emitting a unit with no ExecStart.
 */
const KINDLESS_DEST = {
  name: 'onedrive-hourly',
  storage: 'microsoft',
} as unknown as import('../../types/index.js').BackupStrategyDestination;

const MAIL_GUID = 'aaaaaaaa-0000-4000-8000-000000000001';
const MAIL_FORK_GUID = 'aaaaaaaa-0000-4000-8000-000000000002';
const GITLAB_GUID = 'bbbbbbbb-0000-4000-8000-000000000001';
const POOL_REPO_GUID = 'cccccccc-0000-4000-8000-000000000001';

/** The RdcConfig the scheduler resolves include/exclude names and placements from. */
function rdcConfig(over: { mailFork?: boolean; pool?: boolean } = {}) {
  const mailTags: Record<string, { repositoryGuid: string }> = {
    latest: { repositoryGuid: MAIL_GUID },
  };
  if (over.mailFork) mailTags.trial = { repositoryGuid: MAIL_FORK_GUID };
  return {
    resources: {
      machines: {
        hostinger: { ip: '72.61.137.225', user: 'muhammed', datastore: WK_DATASTORE_PATH },
      },
      datastores: over.pool
        ? { pool: { backend: { kind: 'local', machine: 'hostinger', path: '/mnt/pool' } } }
        : {},
      repositories: {
        mail: { placement: { machine: 'hostinger' }, grand: 'latest', tags: mailTags },
        gitlab: {
          placement: { machine: 'hostinger' },
          grand: 'latest',
          tags: { latest: { repositoryGuid: GITLAB_GUID } },
        },
        ...(over.pool && {
          poolrepo: {
            placement: { datastore: 'pool' },
            grand: 'latest',
            tags: { latest: { repositoryGuid: POOL_REPO_GUID } },
          },
        }),
      },
    },
  };
}

const DEFAULT_STRATEGY = {
  schedule: '0 * * * *',
  mode: 'hot',
  destinations: [HOSTED_DEST],
};

// --------------------------------------------------------------------------- Pure-function unit tests ---------------------------------------------------------------------------

describe('generateServiceUnit', () => {
  it('keeps bwlimit on argv and needs no EnvironmentFile= at all', async () => {
    const { _testing } = await import('../backup/backup-schedule.js');
    const { serviceContent, envVars } = _testing.generateServiceUnit(
      'hourly-hot',
      { schedule: '0 * * * *', mode: 'hot', bandwidthLimit: '6M', destinations: [] },
      [HOSTED_DEST],
      WK_DATASTORE_PATH,
      '/usr/bin/renet'
    );
    expect(serviceContent).toContain('ExecStart=/usr/bin/renet backup snapshot');
    // Converted to bytes/second: `backup snapshot --bwlimit` is an Int64, and the unit-suffixed '6M' the schema declares would die at cobra's flag parse inside the timer, at run time, on a machine nobody is watching.
    expect(serviceContent).toContain('--bwlimit 6000000');
    expect(serviceContent).not.toContain('--bwlimit 6M');
    // The chunk store carries no credentials by construction, so the
    // EnvironmentFile= sidecar has nothing to hold any more.
    expect(serviceContent).not.toContain('EnvironmentFile=');
    expect(envVars).toEqual({});
  });

  it('never writes credentials into the unit or a sidecar for a chunk-store destination', async () => {
    // Successor to the retired test that pinned credentials OUT of ExecStart and
    // INTO a 0600 EnvironmentFile=. There is no credential to place any more:
    // the machine authenticates with its signed licence blob, so the correct assertion is that nothing credential-shaped appears anywhere.
    const { _testing } = await import('../backup/backup-schedule.js');
    const { serviceContent, envVars } = _testing.generateServiceUnit(
      'nightly-snapshot',
      { schedule: '0 3 * * *', destinations: [] },
      [HOSTED_DEST],
      WK_DATASTORE_PATH,
      '/usr/bin/renet'
    );
    expect(envVars).toEqual({});
    expect(serviceContent).not.toMatch(/--setenv|token/i);
    expect(serviceContent).not.toContain('EnvironmentFile=');
  });

  it('emits no --mode flag, which `backup snapshot` does not have', async () => {
    // private/renet/cmd/renet/backup_snapshot.go declares no --mode. Pinned so nothing starts emitting one that cobra would reject at flag-parse time, inside the timer, on a machine nobody is watching.
    const { _testing } = await import('../backup/backup-schedule.js');
    const { serviceContent } = _testing.generateServiceUnit(
      'hourly-hot',
      { schedule: '0 * * * *', mode: 'hot', destinations: [] },
      [HOSTED_DEST],
      WK_DATASTORE_PATH,
      '/usr/bin/renet'
    );
    expect(serviceContent).not.toContain('--mode');
  });

  it('emits --cold for a cold strategy, and nothing for a hot one', async () => {
    // This assertion used to say the opposite: cold was REFUSED, because the scheduled verb could only take a hot snapshot and deploying one would have handed back unquiesced snapshots of a database the operator asked to be stopped first. `backup snapshot --cold` closed that gap, so the flag is emitted rather than the strategy rejected.
    //
    // Both directions are asserted deliberately. Checking only the cold case would pass just as happily against a generator that appended --cold to EVERY unit, which would impose a nightly outage on every hot strategy on the machine, the mirror image of the bug this replaced.
    const { _testing } = await import('../backup/backup-schedule.js');
    const gen = (mode: 'hot' | 'cold') =>
      _testing.generateServiceUnit(
        `nightly-${mode}`,
        { schedule: '0 3 * * *', mode, destinations: [] },
        [HOSTED_DEST],
        WK_DATASTORE_PATH,
        '/usr/bin/renet'
      ).serviceContent;

    expect(gen('cold')).toContain('--cold');
    expect(gen('hot')).not.toContain('--cold');
    // The retired spelling must not come back: renet takes --cold, not --mode. `--mode cold` parses as an unknown flag and the unit dies inside a timer at 03:00, where nobody is watching.
    expect(gen('cold')).not.toContain('--mode');
  });

  it('gives a cold unit a stop window longer than renet needs to restart', async () => {
    // A SIGTERM inside the cold window leaves containers STOPPED, and renet's handler has to bring them all back before it exits, bounded at 15 min renet-side. The hot budget of 90s would SIGKILL mid-restart and leave the repositories down, turning a clean `systemctl stop` into the outage cold mode exists to keep brief.
    const { _testing } = await import('../backup/backup-schedule.js');
    const stopSec = (mode: 'hot' | 'cold') => {
      const { serviceContent } = _testing.generateServiceUnit(
        `nightly-${mode}`,
        { schedule: '0 3 * * *', mode, destinations: [] },
        [HOSTED_DEST],
        WK_DATASTORE_PATH,
        '/usr/bin/renet'
      );
      const m = /TimeoutStopSec=(\d+)/.exec(serviceContent);
      if (!m) throw new Error(`no TimeoutStopSec in the ${mode} unit`);
      return Number(m[1]);
    };

    // 15 min is renet's coldRestartTimeout; anything at or under it can SIGKILL
    // a restart that is still working.
    expect(stopSec('cold')).toBeGreaterThan(15 * 60);
    // And the hot unit must NOT inherit it: a 16-minute shutdown wait on every reboot, for a path whose cleanup is bounded at 60s, is its own defect.
    expect(stopSec('hot')).toBe(90);
  });

  it('defaults an unset mode to hot rather than to an outage', async () => {
    // A strategy with no `mode` is the common case. Reading undefined as cold would stop every container on the machine nightly, so the default is pinned here rather than left to whichever branch happens to run.
    const { _testing } = await import('../backup/backup-schedule.js');
    const { serviceContent } = _testing.generateServiceUnit(
      'nightly',
      { schedule: '0 3 * * *', destinations: [] },
      [HOSTED_DEST],
      WK_DATASTORE_PATH,
      '/usr/bin/renet'
    );
    expect(serviceContent).not.toContain('--cold');
  });

  it('emits TimeoutStartSec=infinity so long uploads are never killed by systemd', async () => {
    const { _testing } = await import('../backup/backup-schedule.js');
    const { serviceContent } = _testing.generateServiceUnit(
      'nightly-snapshot',
      { schedule: '0 3 * * *', destinations: [] },
      [HOSTED_DEST],
      WK_DATASTORE_PATH,
      '/usr/bin/renet'
    );
    expect(serviceContent).toContain('TimeoutStartSec=infinity');
    const typeIdx = serviceContent.indexOf('Type=oneshot');
    const timeoutIdx = serviceContent.indexOf('TimeoutStartSec=infinity');
    const execIdx = serviceContent.indexOf('ExecStart=');
    expect(typeIdx).toBeGreaterThanOrEqual(0);
    expect(timeoutIdx).toBeGreaterThan(typeIdx);
    expect(execIdx).toBeGreaterThan(timeoutIdx);
  });

  it('renews licences before the backup, and never lets that renewal block it', async () => {
    const { _testing } = await import('../backup/backup-schedule.js');
    const { serviceContent } = _testing.generateServiceUnit(
      'hourly-hot',
      { schedule: '0 * * * *', mode: 'hot', destinations: [] },
      [HOSTED_DEST],
      WK_DATASTORE_PATH,
      '/usr/bin/renet'
    );
    // The '-' prefix is the whole point: a refused renewal (one lapsed repo, a network blip) and an older renet that does not know the `license` verb must both leave the backup running.
    expect(serviceContent).toContain('ExecStartPre=-/usr/bin/renet license renew --jitter 45s');
    const preIdx = serviceContent.indexOf('ExecStartPre=');
    const execIdx = serviceContent.indexOf('ExecStart=/usr/bin/renet backup');
    expect(preIdx).toBeGreaterThanOrEqual(0);
    expect(execIdx).toBeGreaterThan(preIdx);
  });

  it('uses the same renet path for the renewal as for the backup itself', async () => {
    const { _testing } = await import('../backup/backup-schedule.js');
    const { serviceContent } = _testing.generateServiceUnit(
      'nightly-snapshot',
      { schedule: '0 3 * * *', destinations: [] },
      [HOSTED_DEST],
      WK_DATASTORE_PATH,
      `${WK_OPT_DIR}/bin/renet`
    );
    expect(serviceContent).toContain(
      'ExecStartPre=-/opt/rediacc/bin/renet license renew --jitter 45s'
    );
    expect(serviceContent).not.toContain('ExecStartPre=-/usr/bin/renet');
  });

  it('validates every destination, not just the first, before emitting a unit', async () => {
    // Successor to the conflicting-env-var test: destinations no longer contribute env vars that could collide, but the multi-destination validation it protected still matters, a strategy must be rejected whole rather than half-rendered.
    const { _testing } = await import('../backup/backup-schedule.js');
    const call = () =>
      _testing.generateServiceUnit(
        'mixed',
        { schedule: '0 * * * *', destinations: [] },
        [
          HOSTED_DEST,
          {
            kind: 'storage',
            name: 'dest2',
            storage: 'm2',
          } as unknown as import('../../types/index.js').BackupStrategyDestination,
        ],
        WK_DATASTORE_PATH,
        '/usr/bin/renet'
      );
    expect(call).toThrow(/Backup destination "dest2"/);
    expect(call).toThrow(/Refusing to generate a unit that would back up nothing\./);
  });

  it('REFUSES a legacy `storage` destination instead of emitting a unit with no ExecStart', async () => {
    // The exact defect the hosted-service branch was added to fix, reachable again from the other side now that the old path is gone: a config still naming a storage destination must not deploy a timer that backs up nothing.
    const { _testing } = await import('../backup/backup-schedule.js');
    const call = () =>
      _testing.generateServiceUnit(
        'hourly-hot',
        { schedule: '0 * * * *', mode: 'hot', destinations: [] },
        [
          {
            kind: 'storage',
            name: 'onedrive-hourly',
            storage: 'microsoft',
          } as unknown as import('../../types/index.js').BackupStrategyDestination,
        ],
        WK_DATASTORE_PATH,
        '/usr/bin/renet'
      );
    expect(call).toThrow(/Backup destination "onedrive-hourly"/);
    expect(call).toThrow(/kind "storage"/);
    expect(call).toThrow(/Only `hosted-service` destinations can be scheduled/);
    expect(call).toThrow(/Refusing to generate a unit that would back up nothing\./);
  });

  it('REFUSES a destination with no `kind`, which is how the real config reads', async () => {
    const { _testing } = await import('../backup/backup-schedule.js');
    const call = () =>
      _testing.generateServiceUnit(
        'hourly-hot',
        { schedule: '0 * * * *', mode: 'hot', destinations: [] },
        [KINDLESS_DEST],
        WK_DATASTORE_PATH,
        '/usr/bin/renet'
      );
    expect(call).toThrow(/Backup destination "onedrive-hourly"/);
    expect(call).toThrow(/kind "storage"/);
    expect(call).toThrow(/Refusing to generate a unit that would back up nothing\./);
  });
});

describe('sanitizeBackupOutput', () => {
  it('redacts --setenv values for sensitive keys', async () => {
    const { sanitizeBackupOutput } = await import('../backup/backup-schedule.js');
    const input =
      'systemd-run --setenv=ACCOUNT_TOKEN=\'{"access_token":"abc"}\' --setenv=BWLIMIT=\'6M\' --remain-after-exit';
    const out = sanitizeBackupOutput(input);
    expect(out).toContain("--setenv=ACCOUNT_TOKEN='[REDACTED]'");
    expect(out).toContain("--setenv=BWLIMIT='6M'");
  });
});

describe('generateEnvFile', () => {
  it('quotes values and escapes backslashes and double quotes', async () => {
    const { _testing } = await import('../backup/backup-schedule.js');
    const tokenJson = '{"access_token":"ab\\c","refresh_token":"x\\"y"}';
    const content = _testing.generateEnvFile({ ACCOUNT_TOKEN: tokenJson });
    expect(content).toBe(
      `ACCOUNT_TOKEN="{\\"access_token\\":\\"ab\\\\c\\",\\"refresh_token\\":\\"x\\\\\\"y\\"}"\n`
    );
  });

  it('returns empty string for an empty map', async () => {
    const { _testing } = await import('../backup/backup-schedule.js');
    expect(_testing.generateEnvFile({})).toBe('');
  });
});

describe('cronToOnCalendar', () => {
  // Regression: cron ranges like "0-2,4-23" must become systemd "0..2,4..23" (double-dot, not hyphen). Single-dash output trips systemd's parser and renders the timer unit "bad-setting", silently disabling the schedule.
  it('converts hyphen ranges and comma-lists to systemd ..-ranges', async () => {
    const { _testing } = await import('../backup/backup-schedule.js');
    expect(_testing.cronToOnCalendar('0 0-2,4-23 * * *')).toBe('*-*-* 00..02,04..23:00:00');
    expect(_testing.cronToOnCalendar('0 */6 * * *')).toBe('*-*-* 00/6:00:00');
    expect(_testing.cronToOnCalendar('15 3 * * *')).toBe('*-*-* 03:15:00');
    expect(_testing.cronToOnCalendar('0 * * * *')).toBe('*-*-* *:00:00');
  });
});

describe('sha256Hex', () => {
  it('is deterministic for the same UTF-8 input', async () => {
    const { _testing } = await import('../backup/backup-schedule.js');
    expect(_testing.sha256Hex('hello')).toBe(_testing.sha256Hex('hello'));
    // Pinned against a known expected value, guards against an accidental encoding flip (bytes vs hex) that would silently turn every reconcile into "everything updated."
    expect(_testing.sha256Hex('hello')).toBe(
      '2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824'
    );
  });
});

describe('parseSystemctlShow', () => {
  it('parses multiple records anchored on Id=', async () => {
    const { _testing } = await import('../backup/backup-schedule.js');
    const out =
      'Id=unit-a.service\nLoadState=loaded\nActiveState=active\n\n' +
      'Id=unit-b.timer\nLoadState=loaded\nActiveState=inactive\n\n';
    const records = _testing.parseSystemctlShow(out);
    expect(records.get('unit-a.service')?.ActiveState).toBe('active');
    expect(records.get('unit-b.timer')?.ActiveState).toBe('inactive');
  });
});

describe('parseStrategyFromPath', () => {
  it('extracts strategy name from service/timer/env paths', async () => {
    const { _testing } = await import('../backup/backup-schedule.js');
    expect(
      _testing.parseStrategyFromPath('/etc/systemd/system/rediacc-backup-hourly-hot.service')
    ).toEqual({ strategy: 'hourly-hot', type: 'service' });
    expect(
      _testing.parseStrategyFromPath('/etc/systemd/system/rediacc-backup-weekly-cold.timer')
    ).toEqual({ strategy: 'weekly-cold', type: 'timer' });
    expect(_testing.parseStrategyFromPath(`${WK_ETC_DIR}/backup-hourly-hot.env`)).toEqual({
      strategy: 'hourly-hot',
      type: 'env',
    });
  });

  it('excludes -adhoc service files', async () => {
    // `-adhoc` units belong to the on-demand backup path (`machine backup now`) and must not be reconciled as scheduled strategies, otherwise the reconciler would try to remove them as orphans on every run.
    const { _testing } = await import('../backup/backup-schedule.js');
    expect(
      _testing.parseStrategyFromPath('/etc/systemd/system/rediacc-backup-foo-adhoc.service')
    ).toBeNull();
  });

  it('returns null for unrelated files', async () => {
    const { _testing } = await import('../backup/backup-schedule.js');
    expect(_testing.parseStrategyFromPath('/etc/systemd/system/sshd.service')).toBeNull();
  });
});

// Build a RemoteUnitState fixture without hard-coding the internal type.
function buildRemoteFixture(
  overrides: Partial<{
    service: { exists: boolean; sha256: string | null };
    timer: { exists: boolean; sha256: string | null };
    env: { exists: boolean; sha256: string | null };
    isActiveService: boolean;
    isActiveAdhoc: boolean;
    isFailed: boolean;
  }> = {}
) {
  return {
    serviceFile: {
      path: '/etc/systemd/system/rediacc-backup-x.service',
      exists: overrides.service?.exists ?? false,
      sha256: overrides.service?.sha256 ?? null,
    },
    timerFile: {
      path: '/etc/systemd/system/rediacc-backup-x.timer',
      exists: overrides.timer?.exists ?? false,
      sha256: overrides.timer?.sha256 ?? null,
    },
    envFile: {
      path: `${WK_ETC_DIR}/backup-x.env`,
      exists: overrides.env?.exists ?? false,
      sha256: overrides.env?.sha256 ?? null,
    },
    isActiveService: overrides.isActiveService ?? false,
    isActiveAdhoc: overrides.isActiveAdhoc ?? false,
    isEnabledTimer: false,
    isActiveTimer: false,
    isFailed: overrides.isFailed ?? false,
  };
}

describe('computeReconcilePlan', () => {
  function makeUnit(name: string, serviceContent = 's', timerContent = 't', envFileContent = '') {
    return { strategyName: name, serviceContent, timerContent, envFileContent };
  }

  it('classifies fresh strategy as created', async () => {
    const { _testing } = await import('../backup/backup-schedule.js');
    const desired = new Map([['x', makeUnit('x')]]);
    const plan = _testing.computeReconcilePlan(desired, new Map());
    expect(plan.toCreate).toHaveLength(1);
    expect(plan.toCreate[0].changedFiles).toEqual(['service', 'timer']);
    expect(plan.toUpdate).toHaveLength(0);
    expect(plan.toRemove).toHaveLength(0);
    expect(plan.unchanged).toHaveLength(0);
    expect(plan.daemonReloadNeeded).toBe(true);
  });

  it('classifies all-matching hashes as unchanged (no daemon-reload needed)', async () => {
    const { _testing } = await import('../backup/backup-schedule.js');
    const unit = makeUnit('x', 'svc', 'tim');
    const desired = new Map([['x', unit]]);
    const remote = new Map([
      [
        'x',
        buildRemoteFixture({
          service: { exists: true, sha256: _testing.sha256Hex('svc') },
          timer: { exists: true, sha256: _testing.sha256Hex('tim') },
        }),
      ],
    ]);
    const plan = _testing.computeReconcilePlan(desired, remote);
    expect(plan.unchanged).toHaveLength(1);
    expect(plan.toUpdate).toHaveLength(0);
    expect(plan.toCreate).toHaveLength(0);
    expect(plan.daemonReloadNeeded).toBe(false);
  });

  it('classifies differing timer hash as updated with changedFiles=[timer]', async () => {
    const { _testing } = await import('../backup/backup-schedule.js');
    const unit = makeUnit('x', 'svc', 'tim');
    const desired = new Map([['x', unit]]);
    const remote = new Map([
      [
        'x',
        buildRemoteFixture({
          service: { exists: true, sha256: _testing.sha256Hex('svc') },
          timer: { exists: true, sha256: 'DIFFERENT' },
        }),
      ],
    ]);
    const plan = _testing.computeReconcilePlan(desired, remote);
    expect(plan.toUpdate).toHaveLength(1);
    expect(plan.toUpdate[0].changedFiles).toEqual(['timer']);
    expect(plan.unchanged).toHaveLength(0);
  });

  it('classifies strategies not in desired as removed', async () => {
    const { _testing } = await import('../backup/backup-schedule.js');
    const desired = new Map();
    const remote = new Map([
      [
        'obsolete',
        buildRemoteFixture({
          service: { exists: true, sha256: 'a' },
          timer: { exists: true, sha256: 'b' },
        }),
      ],
    ]);
    const plan = _testing.computeReconcilePlan(desired, remote);
    expect(plan.toRemove).toHaveLength(1);
    expect(plan.toRemove[0].changedFiles).toEqual(['service', 'timer']);
    expect(plan.daemonReloadNeeded).toBe(true);
  });

  it('handles env file removal when desired no longer needs credentials', async () => {
    const { _testing } = await import('../backup/backup-schedule.js');
    const unit = makeUnit('x', 'svc', 'tim', '');
    const desired = new Map([['x', unit]]);
    const remote = new Map([
      [
        'x',
        buildRemoteFixture({
          service: { exists: true, sha256: _testing.sha256Hex('svc') },
          timer: { exists: true, sha256: _testing.sha256Hex('tim') },
          env: { exists: true, sha256: 'stale' },
        }),
      ],
    ]);
    const plan = _testing.computeReconcilePlan(desired, remote);
    expect(plan.toUpdate).toHaveLength(1);
    expect(plan.toUpdate[0].changedFiles).toEqual(['env']);
  });

  it('treats new env desire as part of fresh create', async () => {
    const { _testing } = await import('../backup/backup-schedule.js');
    const unit = makeUnit('x', 's', 't', 'creds');
    const desired = new Map([['x', unit]]);
    const plan = _testing.computeReconcilePlan(desired, new Map());
    expect(plan.toCreate[0].changedFiles).toEqual(['service', 'timer', 'env']);
  });
});

describe('applyInFlightGate', () => {
  function planWithActiveUpdate(active: 'service' | 'adhoc') {
    return {
      toCreate: [],
      toUpdate: [
        {
          name: 'x',
          action: 'updated' as const,
          desired: null,
          remote: buildRemoteFixture({
            service: { exists: true, sha256: 'a' },
            timer: { exists: true, sha256: 'b' },
            isActiveService: active === 'service',
            isActiveAdhoc: active === 'adhoc',
          }),
          changedFiles: ['timer'] as ('service' | 'timer' | 'env')[],
        },
      ],
      toRemove: [],
      unchanged: [],
      skippedInFlight: [],
      daemonReloadNeeded: true,
    };
  }

  it('throws with backup cancel hint when a scheduled service is running', async () => {
    const { _testing } = await import('../backup/backup-schedule.js');
    const plan = planWithActiveUpdate('service');
    expect(() => _testing.applyInFlightGate(plan, false)).toThrow(
      /rediacc-backup-x\.service is currently running/
    );
  });

  it('throws when an adhoc service is running', async () => {
    // Adhoc backups are tracked by a distinct `-adhoc` unit; we must not
    // clobber unit files that belong to an in-flight on-demand backup.
    const { _testing } = await import('../backup/backup-schedule.js');
    const plan = planWithActiveUpdate('adhoc');
    expect(() => _testing.applyInFlightGate(plan, false)).toThrow(
      /rediacc-backup-x-adhoc\.service is currently running/
    );
  });

  it('with force=true, emits a warning and does not throw', async () => {
    const { _testing } = await import('../backup/backup-schedule.js');
    const plan = planWithActiveUpdate('service');
    expect(() => _testing.applyInFlightGate(plan, true)).not.toThrow();
    expect(mockOutputWarn).toHaveBeenCalledWith(
      expect.stringContaining('currently running; deploy proceeds')
    );
  });
});

// --------------------------------------------------------------------------- Integration tests, pushBackupSchedule (full flow with scripted SSH) ---------------------------------------------------------------------------

describe('pushBackupSchedule (reconcile)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockExecStreaming.mockResolvedValue(0);
    mockRunCommandJob.mockResolvedValue({
      kind: 'finished',
      result: { success: true, exitCode: 0, durationMs: 1, state: 'succeeded' },
    });
    mockGetLocalConfig.mockResolvedValue(DEFAULT_LOCAL_CONFIG);
    mockGetCurrent.mockResolvedValue(rdcConfig());
    mockGetBackupStrategy.mockResolvedValue(DEFAULT_STRATEGY);
    mockRefreshRepoLicensesBatch.mockResolvedValue({
      scanned: 2,
      issued: 1,
      refreshed: 0,
      unchanged: 1,
      failed: 0,
      valid: 2,
      failures: [],
    });
  });

  function recordedCommands(): string[] {
    return mockExecStreaming.mock.calls.map(([cmd]) => cmd as string);
  }

  interface JobPayload {
    remove: { name: string; timer: boolean; service: boolean; env: boolean; dangling: boolean }[];
    remove_env: string[];
    files: { name: string; kind: string; content: string }[];
    reload: boolean;
    enable: string[];
    reset_failed: string[];
  }

  /** The plan the one `backup-schedule` job was started with: its payload, parsed. */
  function jobPayload(): JobPayload {
    expect(mockRunCommandJob).toHaveBeenCalledTimes(1);
    const options = mockRunCommandJob.mock.calls[0][1] as {
      functionName: string;
      commandKind: { name: string; payload: string; args?: unknown };
    };
    expect(options.functionName).toBe('backup-schedule');
    // The unit bodies carry credentials: they ride the stdin payload, never the arguments.
    expect(options.commandKind.args).toBeUndefined();
    return JSON.parse(options.commandKind.payload) as JobPayload;
  }

  /** No unit file is written, moved or enabled over the client's SSH any more: the job does it. */
  function expectNoClientMutation(): void {
    const cmds = recordedCommands();
    expect(cmds.some((c) => c.includes('tee '))).toBe(false);
    expect(cmds.some((c) => c.startsWith('sudo mv ') || c.startsWith('sudo rm '))).toBe(false);
    expect(cmds.some((c) => c.includes('systemctl daemon-reload'))).toBe(false);
    expect(cmds.some((c) => c.includes('enable --now'))).toBe(false);
  }

  it('test 1: no existing units → one backup-schedule job creates both units, reloads and enables the timer', async () => {
    scriptedExec([
      { match: /find \/etc\/systemd\/system/, stdout: '' },
      {
        match: 'Id,LoadState,ActiveState,SubState,UnitFileState',
        stdout: notFoundRecord('rediacc-backup-hourly-hot.service'),
      },
    ]);

    const { pushBackupSchedule } = await import('../backup/backup-schedule.js');
    expect(await pushBackupSchedule('hostinger')).toBe('applied');

    const payload = jobPayload();
    const hot = payload.files.filter((f) => f.name === 'hourly-hot').map((f) => f.kind);
    expect(hot).toEqual(['service', 'timer']);
    expect(payload.reload).toBe(true);
    expect(payload.enable).toContain('hourly-hot');
    expect(payload.remove).toEqual([]);
    expectNoClientMutation();
  });

  // The failure this covers is PARTIAL binding, which was completely silent: one strategy bound and deployed ("unchanged"), another enabled but bound to no machine, exit 0, no mention of the second. The operator's only signal was a backup that never ran.
  it('warns about an enabled strategy that no machine binds', async () => {
    mockListBackupStrategies.mockResolvedValueOnce({
      'hourly-hot': DEFAULT_STRATEGY,
      'weekly-cold': { ...DEFAULT_STRATEGY, schedule: '15 3 * * 0' },
    });
    scriptedExec([
      { match: /find \/etc\/systemd\/system/, stdout: '' },
      {
        match: 'Id,LoadState,ActiveState,SubState,UnitFileState',
        stdout: notFoundRecord('rediacc-backup-hourly-hot.service'),
      },
      {
        match: 'Id,LoadState,ActiveState,UnitFileState',
        stdout: healthyTimers('hourly-hot'),
      },
    ]);

    const { pushBackupSchedule } = await import('../backup/backup-schedule.js');
    await pushBackupSchedule('hostinger');

    expect(mockOutputWarn).toHaveBeenCalledWith(expect.stringContaining('weekly-cold'));
    expect(mockOutputWarn).toHaveBeenCalledWith(
      expect.stringContaining('rdc backup strategy bind weekly-cold')
    );
    // The bound one must NOT be reported as orphaned.
    expect(mockOutputWarn).not.toHaveBeenCalledWith(expect.stringContaining('"hourly-hot" is'));
  });

  // Other direction: without this the assertion above would pass on a function that warns unconditionally.
  it('stays silent when every enabled strategy is bound somewhere', async () => {
    mockListBackupStrategies.mockResolvedValueOnce({ 'hourly-hot': DEFAULT_STRATEGY });
    scriptedExec([
      { match: /find \/etc\/systemd\/system/, stdout: '' },
      {
        match: 'Id,LoadState,ActiveState,SubState,UnitFileState',
        stdout: notFoundRecord('rediacc-backup-hourly-hot.service'),
      },
      {
        match: 'Id,LoadState,ActiveState,UnitFileState',
        stdout: healthyTimers('hourly-hot'),
      },
    ]);

    const { pushBackupSchedule } = await import('../backup/backup-schedule.js');
    await pushBackupSchedule('hostinger');

    expect(mockOutputWarn).not.toHaveBeenCalledWith(expect.stringContaining('bound to no machine'));
  });

  it('test 2: all hashes match → unchanged, no writes, no daemon-reload', async () => {
    const machine = await fullDesired();
    scriptedExec([
      { match: /find \/etc\/systemd\/system/, stdout: machine.find },
      { match: 'sha256sum', stdout: machine.sha() },
      { match: 'Id,LoadState,ActiveState,SubState,UnitFileState', stdout: machine.show },
    ]);

    const { pushBackupSchedule } = await import('../backup/backup-schedule.js');
    await pushBackupSchedule('hostinger');

    const cmds = recordedCommands();
    expect(cmds.some((c) => c.includes('tee '))).toBe(false);
    expect(cmds.some((c) => c.startsWith('sudo mv '))).toBe(false);
    expect(cmds).not.toContain('sudo systemctl daemon-reload');
    expect(cmds).not.toContain('sudo systemctl enable --now rediacc-backup-hourly-hot.timer');
    expect(mockOutputInfo).toHaveBeenCalledWith(expect.stringContaining('unchanged hourly-hot'));
  });

  it('test 3: schedule changed → only timer staged, service untouched', async () => {
    const machine = await fullDesired();
    const stale = '0'.repeat(64);
    scriptedExec([
      { match: /find \/etc\/systemd\/system/, stdout: machine.find },
      {
        match: 'sha256sum',
        stdout: machine.sha((f) =>
          f.unit === 'hourly-hot' && f.kind === 'timer' ? stale : f.hash
        ),
      },
      { match: 'Id,LoadState,ActiveState,SubState,UnitFileState', stdout: machine.show },
      { match: 'Id,LoadState,ActiveState,UnitFileState', stdout: healthyTimers('hourly-hot') },
    ]);

    const { pushBackupSchedule } = await import('../backup/backup-schedule.js');
    await pushBackupSchedule('hostinger');

    const payload = jobPayload();
    expect(payload.files.filter((f) => f.name === 'hourly-hot').map((f) => f.kind)).toEqual([
      'timer',
    ]);
    expect(payload.reload).toBe(true);
    expectNoClientMutation();
  });

  it('test 4: removed strategy → disable --now, then rm on exact paths (no glob)', async () => {
    const machine = await fullDesired();
    const obsolete = [
      '/etc/systemd/system/rediacc-backup-obsolete.service',
      '/etc/systemd/system/rediacc-backup-obsolete.timer',
    ];
    scriptedExec([
      { match: /find \/etc\/systemd\/system/, stdout: `${machine.find}${obsolete.join('\n')}\n` },
      {
        match: 'sha256sum',
        stdout:
          machine.sha() +
          `abc123abc123abc123abc123abc123abc123abc123abc123abc123abc123abc1  ${obsolete[0]}\n` +
          `def456def456def456def456def456def456def456def456def456def456def4  ${obsolete[1]}\n`,
      },
      {
        match: 'Id,LoadState,ActiveState,SubState,UnitFileState',
        stdout:
          machine.show +
          idleServiceRecord('rediacc-backup-obsolete.service') +
          notFoundRecord('rediacc-backup-obsolete-adhoc.service') +
          idleServiceRecord('rediacc-backup-obsolete.timer'),
      },
    ]);

    const { pushBackupSchedule } = await import('../backup/backup-schedule.js');
    await pushBackupSchedule('hostinger');

    // The job disables the timer, then removes the two named files: units by name, never a glob.
    const payload = jobPayload();
    expect(payload.remove).toEqual([
      { name: 'obsolete', timer: true, service: true, env: false, dangling: false },
    ]);
    expect(payload.reset_failed).toEqual([]);
    expectNoClientMutation();
  });

  it('test 5: update with in-flight service and no --force → throws with cancel hint', async () => {
    scriptedExec([
      {
        match: /find \/etc\/systemd\/system/,
        stdout:
          '/etc/systemd/system/rediacc-backup-hourly-hot.service\n' +
          '/etc/systemd/system/rediacc-backup-hourly-hot.timer\n',
      },
      {
        match: 'sha256sum',
        stdout:
          `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz  /etc/systemd/system/rediacc-backup-hourly-hot.service\n` +
          `yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy  /etc/systemd/system/rediacc-backup-hourly-hot.timer\n`,
      },
      {
        match: 'Id,LoadState,ActiveState,SubState,UnitFileState',
        stdout:
          showRecord('rediacc-backup-hourly-hot.service', {
            LoadState: 'loaded',
            ActiveState: 'active',
            SubState: 'running',
            UnitFileState: 'static',
          }) +
          notFoundRecord('rediacc-backup-hourly-hot-adhoc.service') +
          idleServiceRecord('rediacc-backup-hourly-hot.timer'),
      },
    ]);

    const { pushBackupSchedule } = await import('../backup/backup-schedule.js');
    await expect(pushBackupSchedule('hostinger')).rejects.toThrow(
      /rediacc-backup-hourly-hot\.service is currently running/
    );
    const cmds = recordedCommands();
    expect(cmds.some((c) => c.includes('.new'))).toBe(false);
    expect(cmds.includes('sudo systemctl daemon-reload')).toBe(false);
  });

  it('test 6: update with in-flight service and --force → proceeds with warning, never stops the service', async () => {
    scriptedExec([
      {
        match: /find \/etc\/systemd\/system/,
        stdout:
          '/etc/systemd/system/rediacc-backup-hourly-hot.service\n' +
          '/etc/systemd/system/rediacc-backup-hourly-hot.timer\n',
      },
      {
        match: 'sha256sum',
        stdout:
          `differenthash1differenthash1differenthash1differenthash1differen  /etc/systemd/system/rediacc-backup-hourly-hot.service\n` +
          `differenthash2differenthash2differenthash2differenthash2differen  /etc/systemd/system/rediacc-backup-hourly-hot.timer\n`,
      },
      {
        match: 'Id,LoadState,ActiveState,SubState,UnitFileState',
        stdout:
          showRecord('rediacc-backup-hourly-hot.service', {
            LoadState: 'loaded',
            ActiveState: 'active',
            SubState: 'running',
            UnitFileState: 'static',
          }) +
          notFoundRecord('rediacc-backup-hourly-hot-adhoc.service') +
          idleServiceRecord('rediacc-backup-hourly-hot.timer'),
      },
      {
        match: 'Id,LoadState,ActiveState,UnitFileState',
        stdout: healthyTimers('hourly-hot'),
      },
    ]);

    const { pushBackupSchedule } = await import('../backup/backup-schedule.js');
    await pushBackupSchedule('hostinger', { force: true });

    expect(mockOutputWarn).toHaveBeenCalledWith(
      expect.stringContaining('rediacc-backup-hourly-hot.service is currently running')
    );
    const payload = jobPayload();
    expect(payload.files.length).toBeGreaterThan(0);
    expect(payload.reload).toBe(true);
    // Critically: we did NOT stop the running service; systemd keeps the
    // in-memory copy alive until the invocation finishes.
    expect(recordedCommands().some((c) => c.startsWith('sudo systemctl stop '))).toBe(false);
  });

  it('test 7: a failed job (renet verifies the timers) throws with its reason', async () => {
    scriptedExec([
      { match: /find \/etc\/systemd\/system/, stdout: '' },
      {
        match: 'Id,LoadState,ActiveState,SubState,UnitFileState',
        stdout: notFoundRecord('rediacc-backup-hourly-hot.service'),
      },
    ]);
    mockRunCommandJob.mockResolvedValue({
      kind: 'finished',
      result: {
        success: false,
        exitCode: 1,
        durationMs: 1,
        state: 'failed',
        error:
          'post-deploy verification failed:\n  - rediacc-backup-hourly-hot.timer: ActiveState=inactive',
      },
    });

    const { pushBackupSchedule } = await import('../backup/backup-schedule.js');
    await expect(pushBackupSchedule('hostinger')).rejects.toThrow(
      /Applying the backup schedule on hostinger failed.*rediacc-backup-hourly-hot\.timer.*ActiveState=inactive/s
    );
  });

  it('a job handed back past the attach window is pending, and the steps stay on its ticket', async () => {
    scriptedExec([{ match: /find \/etc\/systemd\/system/, stdout: '' }]);
    mockRunCommandJob.mockResolvedValue({
      kind: 'pending',
      result: { success: true, exitCode: 0, durationMs: 1, state: 'running' },
    });
    const step = { name: 'seedStrategyRetention', on: 'success', params: {} };

    const { pushBackupSchedule } = await import('../backup/backup-schedule.js');
    expect(await pushBackupSchedule('hostinger', { steps: [step] as never })).toBe('pending');

    expect(mockRunCommandJob.mock.calls[0][2]).toEqual([step]);
  });

  it('test 8: --reset-failed does nothing when no touched service was in failed state', async () => {
    scriptedExec([
      { match: /find \/etc\/systemd\/system/, stdout: '' },
      {
        match: 'Id,LoadState,ActiveState,SubState,UnitFileState',
        stdout: notFoundRecord('rediacc-backup-hourly-hot.service'),
      },
      {
        match: 'Id,LoadState,ActiveState,UnitFileState',
        stdout: healthyTimers('hourly-hot'),
      },
    ]);

    const { pushBackupSchedule } = await import('../backup/backup-schedule.js');
    await pushBackupSchedule('hostinger', { resetFailed: true });

    expect(jobPayload().reset_failed).toEqual([]);
    expect(recordedCommands().some((c) => c.includes('reset-failed'))).toBe(false);
  });

  it('test 9: dry-run reads state but performs zero mutations and no license mint', async () => {
    scriptedExec([
      { match: /find \/etc\/systemd\/system/, stdout: '' },
      {
        match: 'Id,LoadState,ActiveState,SubState,UnitFileState',
        stdout: notFoundRecord('rediacc-backup-hourly-hot.service'),
      },
    ]);

    const { pushBackupSchedule } = await import('../backup/backup-schedule.js');
    await pushBackupSchedule('hostinger', { dryRun: true });

    const cmds = recordedCommands();
    expect(cmds.some((c) => c.includes('find /etc/systemd/system'))).toBe(true);
    expect(cmds.some((c) => c.includes('systemctl show'))).toBe(true);
    expect(cmds.some((c) => c.includes('tee '))).toBe(false);
    expect(cmds.some((c) => c.startsWith('sudo mv '))).toBe(false);
    expect(cmds.includes('sudo systemctl daemon-reload')).toBe(false);
    expect(cmds.some((c) => c.includes('enable --now'))).toBe(false);
    expect(mockAcquireRemoteRenet).not.toHaveBeenCalled();
    expect(mockRefreshRepoLicensesBatch).not.toHaveBeenCalled();
    expect(mockRunCommandJob).not.toHaveBeenCalled();
  });

  it('throws when machine has no backupStrategies', async () => {
    mockGetLocalConfig.mockResolvedValue({
      renetPath: '/local/renet',
      sshPrivateKey: 'KEY',
      ssh: { privateKeyPath: '/tmp/key' },
      machines: { hostinger: { ip: '1.2.3.4', user: 'test' } },
    });

    const { pushBackupSchedule } = await import('../backup/backup-schedule.js');
    await expect(pushBackupSchedule('hostinger')).rejects.toThrow('No backup strategies bound');
  });

  it('aborts when no valid repo licenses', async () => {
    mockRefreshRepoLicensesBatch.mockResolvedValueOnce({
      scanned: 2,
      issued: 0,
      refreshed: 0,
      unchanged: 0,
      failed: 2,
      valid: 0,
      failures: [],
    });

    const { pushBackupSchedule } = await import('../backup/backup-schedule.js');
    await expect(pushBackupSchedule('hostinger')).rejects.toThrow('no valid repo licenses');
  });

  /** A machine with no backup units yet, whose timers load once written. */
  function freshMachine(...timers: string[]): void {
    scriptedExec([
      { match: /find \/etc\/systemd\/system/, stdout: '' },
      {
        match: 'Id,LoadState,ActiveState,UnitFileState',
        stdout: timers
          .flatMap((t) => [t, t.replace(/\.timer$/, '.verify.timer')])
          .map((t) => healthyTimerRecord(t))
          .join(''),
      },
    ]);
  }

  /** The content the job writes for a unit file, by its `<name>.<kind>` suffix (as the units were named on the machine). */
  function stagedContent(suffix: string): string | undefined {
    const m = /^rediacc-backup-(.+)\.(service|timer)\.new$/.exec(suffix);
    if (!m) throw new Error(`bad suffix ${suffix}`);
    const payload = JSON.parse(
      (mockRunCommandJob.mock.calls[0]?.[1] as { commandKind: { payload: string } } | undefined)
        ?.commandKind.payload ?? '{"files":[]}'
    ) as JobPayload;
    return payload.files.find((f) => f.name === m[1] && f.kind === m[2])?.content;
  }

  it('G1: resolves include names to GUIDs, never passing a name to renet', async () => {
    mockGetBackupStrategy.mockResolvedValue({ ...DEFAULT_STRATEGY, include: ['mail'] });
    freshMachine('rediacc-backup-hourly-hot.timer');
    const { pushBackupSchedule } = await import('../backup/backup-schedule.js');
    await pushBackupSchedule('hostinger');
    const unit = stagedContent('rediacc-backup-hourly-hot.service.new');
    expect(unit).toContain(`--repo ${MAIL_GUID}`);
    expect(unit).not.toContain(GITLAB_GUID);
    expect(unit).not.toMatch(/--repo mail\b/);
  });

  it('G1: an exclude list becomes --exclude-repo <guid>', async () => {
    mockGetBackupStrategy.mockResolvedValue({ ...DEFAULT_STRATEGY, exclude: ['gitlab'] });
    freshMachine('rediacc-backup-hourly-hot.timer');
    const { pushBackupSchedule } = await import('../backup/backup-schedule.js');
    await pushBackupSchedule('hostinger');
    const unit = stagedContent('rediacc-backup-hourly-hot.service.new');
    expect(unit).toContain(`--exclude-repo ${GITLAB_GUID}`);
    expect(unit).not.toContain('--repo ');
  });

  it('G1: refuses to deploy a strategy naming a repository the config does not know', async () => {
    mockGetBackupStrategy.mockResolvedValue({ ...DEFAULT_STRATEGY, include: ['ghost'] });
    const { pushBackupSchedule } = await import('../backup/backup-schedule.js');
    await expect(pushBackupSchedule('hostinger')).rejects.toThrow(
      /"ghost", which is not in the config/
    );
    expect(mockAcquireRemoteRenet).not.toHaveBeenCalled();
  });

  it('G5: a named datastore on the machine gets its own unit, pointed at its path', async () => {
    mockGetCurrent.mockResolvedValue(rdcConfig({ pool: true }));
    freshMachine('rediacc-backup-hourly-hot.timer', 'rediacc-backup-hourly-hot.ds.pool.timer');
    const { pushBackupSchedule } = await import('../backup/backup-schedule.js');
    await pushBackupSchedule('hostinger');
    const implicit = stagedContent('rediacc-backup-hourly-hot.service.new');
    const pool = stagedContent('rediacc-backup-hourly-hot.ds.pool.service.new');
    expect(implicit).toContain(`--datastore ${WK_DATASTORE_PATH}`);
    expect(pool).toContain('--datastore /mnt/pool');
    expect(stagedContent('rediacc-backup-hourly-hot.ds.pool.timer.new')).toContain('OnCalendar=');
  });

  it('G4: a new fork of an included family re-renders the unit with the fork GUID', async () => {
    mockGetBackupStrategy.mockResolvedValue({ ...DEFAULT_STRATEGY, include: ['mail'] });
    const { _testing, reconcileSchedulesAfterRepoChange } = await import(
      '../backup/backup-schedule.js'
    );
    const { machineUnitSpecs } = await import('../backup/backup-schedule-targets.js');
    // The unit deployed before the fork existed, as the machine holds it.
    const before = machineUnitSpecs(
      [{ name: 'hourly-hot', config: { ...DEFAULT_STRATEGY, include: ['mail'] } as never }],
      rdcConfig() as never,
      'hostinger'
    )[0];
    const deployed = _testing.generateServiceUnit(
      before.unitName,
      before.strategy,
      before.strategy.destinations,
      before.datastore.path,
      '/usr/bin/renet',
      before.scope,
      8
    ).serviceContent;
    const timer = _testing.generateTimerUnit('hourly-hot', _testing.cronToOnCalendar('0 * * * *'));
    const svcPath = '/etc/systemd/system/rediacc-backup-hourly-hot.service';
    const timerPath = '/etc/systemd/system/rediacc-backup-hourly-hot.timer';
    scriptedExec([
      { match: /find \/etc\/systemd\/system/, stdout: `${svcPath}\n${timerPath}\n` },
      {
        match: 'sha256sum',
        stdout: `${_testing.sha256Hex(deployed)}  ${svcPath}\n${_testing.sha256Hex(timer)}  ${timerPath}\n`,
      },
      {
        match: 'Id,LoadState,ActiveState,SubState,UnitFileState',
        stdout:
          idleServiceRecord('rediacc-backup-hourly-hot.service') +
          healthyTimerRecord('rediacc-backup-hourly-hot.timer'),
      },
      {
        match: 'Id,LoadState,ActiveState,UnitFileState',
        stdout: healthyTimers('hourly-hot'),
      },
    ]);
    mockGetCurrent.mockResolvedValue(rdcConfig({ mailFork: true }));

    expect(await reconcileSchedulesAfterRepoChange('hostinger')).toBe(true);
    const staged = stagedContent('rediacc-backup-hourly-hot.service.new');
    expect(staged).toContain(`--repo ${MAIL_GUID}`);
    expect(staged).toContain(`--repo ${MAIL_FORK_GUID}`);
    // The timer did not change, so only the service is rewritten.
    expect(stagedContent('rediacc-backup-hourly-hot.timer.new')).toBeUndefined();
  });

  it('G4: a machine with no bound strategy is left alone after a repo change', async () => {
    mockGetLocalConfig.mockResolvedValue({
      ...DEFAULT_LOCAL_CONFIG,
      machines: { hostinger: { ip: '1.2.3.4', user: 'test' } },
    });
    const { reconcileSchedulesAfterRepoChange } = await import('../backup/backup-schedule.js');
    expect(await reconcileSchedulesAfterRepoChange('hostinger')).toBe(false);
    expect(mockExecStreaming).not.toHaveBeenCalled();
  });

  it('G4: a failed re-render warns and does not throw (the repo change already happened)', async () => {
    mockGetBackupStrategy.mockResolvedValue({ ...DEFAULT_STRATEGY, include: ['ghost'] });
    const { reconcileSchedulesAfterRepoChange } = await import('../backup/backup-schedule.js');
    expect(await reconcileSchedulesAfterRepoChange('hostinger')).toBe(false);
    expect(mockOutputWarn).toHaveBeenCalledWith(expect.stringContaining('was not re-rendered'));
  });

  it('G4: an unreadable config warns and does not throw either', async () => {
    mockGetLocalConfig.mockRejectedValue(new Error('config locked'));
    const { reconcileSchedulesAfterRepoChange } = await import('../backup/backup-schedule.js');
    expect(await reconcileSchedulesAfterRepoChange('hostinger')).toBe(false);
    expect(mockOutputWarn).toHaveBeenCalledWith(expect.stringContaining('config locked'));
  });
});
