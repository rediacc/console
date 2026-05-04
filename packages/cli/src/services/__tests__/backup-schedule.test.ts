import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

// First-time module evaluation in CI runners can exceed the 5s default test
// timeout (this file mocks 30+ deps before importing backup-schedule). Pull
// the import into a single beforeAll with a generous timeout; the per-test
// `await import` calls that follow then hit vitest's module cache and return
// instantly. Cheaper than bumping every individual test's timeout.
beforeAll(async () => {
  await import('../backup-schedule.js');
}, 30000);

const mockExecStreaming = vi.fn();
const mockConnect = vi.fn().mockResolvedValue(undefined);
const mockClose = vi.fn();
const mockBuildRcloneArgs = vi.fn();

const mockProvisionRenetToRemote = vi
  .fn()
  .mockResolvedValue({ remotePath: '/usr/bin/renet', uploaded: false });
const mockReadSSHKey = vi.fn().mockResolvedValue('PRIVATE_KEY');
const mockRefreshRepoLicensesBatch = vi.fn();

const mockGetBackupStrategy = vi.fn();
const mockListBackupStrategies = vi.fn();
const mockGetLocalConfig = vi.fn();
const mockGetStorage = vi.fn();

const mockOutputInfo = vi.fn();
const mockOutputWarn = vi.fn();

vi.mock('@rediacc/shared-desktop/sftp', () => ({
  SFTPClient: vi.fn(
    class MockSFTPClient {
      connect = mockConnect;
      close = mockClose;
      execStreaming = mockExecStreaming;
    }
  ),
}));

vi.mock('@rediacc/shared/queue-vault', () => ({
  buildRcloneArgs: mockBuildRcloneArgs,
}));

vi.mock('../renet-execution.js', () => ({
  provisionRenetToRemote: mockProvisionRenetToRemote,
  readSSHKey: mockReadSSHKey,
}));

vi.mock('../license.js', () => ({
  refreshRepoLicensesBatch: mockRefreshRepoLicensesBatch,
}));

vi.mock('../config-resources.js', () => ({
  configService: {
    getBackupStrategy: mockGetBackupStrategy,
    listBackupStrategies: mockListBackupStrategies,
    getLocalConfig: mockGetLocalConfig,
    getStorage: mockGetStorage,
  },
}));

vi.mock('../output.js', () => ({
  outputService: {
    info: mockOutputInfo,
    warn: mockOutputWarn,
  },
}));

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

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

function notFoundRecord(unit: string): string {
  return showRecord(unit, {
    LoadState: 'not-found',
    ActiveState: 'inactive',
    SubState: 'dead',
    UnitFileState: '',
  });
}

/** Compute the exact on-disk content the reconciler would produce for a strategy. */
async function desiredContentFor(
  strategyName: string,
  strategy: import('../../types/index.js').BackupStrategyConfig,
  destinations: import('../../types/index.js').BackupStrategyDestination[],
  rcloneArgsByDest: Map<string, { remote: string; params: string[] }>,
  datastore = '/mnt/rediacc',
  remoteRenetPath = '/usr/bin/renet'
) {
  const { _testing } = await import('../backup-schedule.js');
  const { serviceContent, envVars } = _testing.generateServiceUnit(
    strategyName,
    strategy,
    destinations,
    rcloneArgsByDest,
    datastore,
    remoteRenetPath
  );
  const timerContent = _testing.generateTimerUnit(
    strategyName,
    _testing.cronToOnCalendar(strategy.schedule)
  );
  const envFileContent = _testing.generateEnvFile(envVars);
  return {
    serviceContent,
    timerContent,
    envFileContent,
    serviceHash: _testing.sha256Hex(serviceContent),
    timerHash: _testing.sha256Hex(timerContent),
    envHash: envFileContent ? _testing.sha256Hex(envFileContent) : null,
  };
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
      datastore: '/mnt/rediacc',
      backupStrategies: ['hourly-hot'],
    },
  },
};

const DEFAULT_STRATEGY = {
  schedule: '0 * * * *',
  mode: 'hot',
  destinations: [{ name: 'onedrive-hourly', storage: 'microsoft', enabled: true }],
};

const DEFAULT_RCLONE_ARGS = {
  remote: ':s3:rediacc/hostinger',
  // Empty params so the default strategy has no env file — integration
  // tests can focus on unit reconciliation without also mocking env hashes.
  params: [] as string[],
};

// ---------------------------------------------------------------------------
// Pure-function unit tests
// ---------------------------------------------------------------------------

describe('generateServiceUnit', () => {
  it('keeps bwlimit on argv (per-destination) and emits EnvironmentFile=', async () => {
    const { _testing } = await import('../backup-schedule.js');
    const { serviceContent, envVars } = _testing.generateServiceUnit(
      'hourly-hot',
      { schedule: '0 * * * *', mode: 'hot', bandwidthLimit: '6M', destinations: [] },
      [{ name: 'onedrive', storage: 'microsoft' }],
      new Map([['onedrive', { remote: ':onedrive:hostinger', params: [] }]]),
      '/mnt/rediacc',
      '/usr/bin/renet'
    );
    expect(serviceContent).toContain('--mode hot');
    expect(serviceContent).toContain('--rclone-param bwlimit=6M');
    expect(serviceContent).not.toContain('EnvironmentFile=');
    expect(envVars.RCLONE_BWLIMIT).toBeUndefined();
  });

  it('moves rclone credential params to envVars as RCLONE_<KEY> and keeps them out of ExecStart', async () => {
    const { _testing } = await import('../backup-schedule.js');
    const tokenJson = '{"access_token":"abc","refresh_token":"xyz"}';
    const { serviceContent, envVars } = _testing.generateServiceUnit(
      'nightly-cold',
      { schedule: '0 3 * * *', mode: 'cold', destinations: [] },
      [{ name: 'dest', storage: 'microsoft' }],
      new Map([
        [
          'dest',
          {
            remote: ':onedrive:hostinger',
            params: [
              `--onedrive-token=${tokenJson}`,
              '--onedrive-drive-id=4D895B49A06E9E5C',
              '--onedrive-drive-type=personal',
            ],
          },
        ],
      ]),
      '/mnt/rediacc',
      '/usr/bin/renet'
    );
    expect(envVars).toEqual({
      RCLONE_ONEDRIVE_TOKEN: tokenJson,
      RCLONE_ONEDRIVE_DRIVE_ID: '4D895B49A06E9E5C',
      RCLONE_ONEDRIVE_DRIVE_TYPE: 'personal',
    });
    expect(serviceContent).not.toContain('onedrive-token');
    expect(serviceContent).not.toContain('access_token');
    expect(serviceContent).toContain('EnvironmentFile=/etc/rediacc/backup-nightly-cold.env');
  });

  it('emits TimeoutStartSec=infinity so long uploads are never killed by systemd', async () => {
    const { _testing } = await import('../backup-schedule.js');
    const { serviceContent } = _testing.generateServiceUnit(
      'nightly-cold',
      { schedule: '0 3 * * *', mode: 'cold', destinations: [] },
      [{ name: 'dest', storage: 'microsoft' }],
      new Map([['dest', { remote: ':onedrive:hostinger', params: [] }]]),
      '/mnt/rediacc',
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

  it('throws on conflicting env vars across destinations', async () => {
    const { _testing } = await import('../backup-schedule.js');
    const call = () =>
      _testing.generateServiceUnit(
        'mixed',
        { schedule: '0 * * * *', destinations: [] },
        [
          { name: 'dest1', storage: 'm1' },
          { name: 'dest2', storage: 'm2' },
        ],
        new Map([
          ['dest1', { remote: ':onedrive:a', params: ['--onedrive-token=aaa'] }],
          ['dest2', { remote: ':onedrive:b', params: ['--onedrive-token=bbb'] }],
        ]),
        '/mnt/rediacc',
        '/usr/bin/renet'
      );
    expect(call).toThrow(/Conflicting env var "RCLONE_ONEDRIVE_TOKEN"/);
  });
});

describe('sanitizeBackupOutput', () => {
  it('redacts --rclone-param values for sensitive keys', async () => {
    const { sanitizeBackupOutput } = await import('../backup-schedule.js');
    const input =
      'backup sync push --rclone-param \'onedrive-token={"access_token":"x"}\' --rclone-param \'bwlimit=6M\'';
    const out = sanitizeBackupOutput(input);
    expect(out).toContain('onedrive-token=[REDACTED]');
    expect(out).toContain('bwlimit=6M');
  });

  it('redacts --setenv values for sensitive RCLONE_ keys', async () => {
    const { sanitizeBackupOutput } = await import('../backup-schedule.js');
    const input =
      'systemd-run --setenv=RCLONE_ONEDRIVE_TOKEN=\'{"access_token":"abc"}\' --setenv=RCLONE_BWLIMIT=\'6M\' --remain-after-exit';
    const out = sanitizeBackupOutput(input);
    expect(out).toContain("--setenv=RCLONE_ONEDRIVE_TOKEN='[REDACTED]'");
    expect(out).toContain("--setenv=RCLONE_BWLIMIT='6M'");
  });
});

describe('generateEnvFile', () => {
  it('quotes values and escapes backslashes and double quotes', async () => {
    const { _testing } = await import('../backup-schedule.js');
    const tokenJson = '{"access_token":"ab\\c","refresh_token":"x\\"y"}';
    const content = _testing.generateEnvFile({ RCLONE_ONEDRIVE_TOKEN: tokenJson });
    expect(content).toBe(
      `RCLONE_ONEDRIVE_TOKEN="{\\"access_token\\":\\"ab\\\\c\\",\\"refresh_token\\":\\"x\\\\\\"y\\"}"\n`
    );
  });

  it('returns empty string for an empty map', async () => {
    const { _testing } = await import('../backup-schedule.js');
    expect(_testing.generateEnvFile({})).toBe('');
  });
});

describe('cronToOnCalendar', () => {
  // Regression: cron ranges like "0-2,4-23" must become systemd "0..2,4..23"
  // (double-dot, not hyphen). Single-dash output trips systemd's parser and
  // renders the timer unit "bad-setting", silently disabling the schedule.
  it('converts hyphen ranges and comma-lists to systemd ..-ranges', async () => {
    const { _testing } = await import('../backup-schedule.js');
    expect(_testing.cronToOnCalendar('0 0-2,4-23 * * *')).toBe('*-*-* 00..02,04..23:00:00');
    expect(_testing.cronToOnCalendar('0 */6 * * *')).toBe('*-*-* 00/6:00:00');
    expect(_testing.cronToOnCalendar('15 3 * * *')).toBe('*-*-* 03:15:00');
    expect(_testing.cronToOnCalendar('0 * * * *')).toBe('*-*-* *:00:00');
  });
});

describe('sha256Hex', () => {
  it('is deterministic for the same UTF-8 input', async () => {
    const { _testing } = await import('../backup-schedule.js');
    expect(_testing.sha256Hex('hello')).toBe(_testing.sha256Hex('hello'));
    // Pinned against a known expected value — guards against an accidental
    // encoding flip (bytes vs hex) that would silently turn every reconcile
    // into "everything updated."
    expect(_testing.sha256Hex('hello')).toBe(
      '2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824'
    );
  });
});

describe('parseSystemctlShow', () => {
  it('parses multiple records anchored on Id=', async () => {
    const { _testing } = await import('../backup-schedule.js');
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
    const { _testing } = await import('../backup-schedule.js');
    expect(
      _testing.parseStrategyFromPath('/etc/systemd/system/rediacc-backup-hourly-hot.service')
    ).toEqual({ strategy: 'hourly-hot', type: 'service' });
    expect(
      _testing.parseStrategyFromPath('/etc/systemd/system/rediacc-backup-weekly-cold.timer')
    ).toEqual({ strategy: 'weekly-cold', type: 'timer' });
    expect(_testing.parseStrategyFromPath('/etc/rediacc/backup-hourly-hot.env')).toEqual({
      strategy: 'hourly-hot',
      type: 'env',
    });
  });

  it('excludes -adhoc service files', async () => {
    // `-adhoc` units belong to the on-demand backup path (`machine backup now`)
    // and must not be reconciled as scheduled strategies — otherwise the
    // reconciler would try to remove them as orphans on every run.
    const { _testing } = await import('../backup-schedule.js');
    expect(
      _testing.parseStrategyFromPath('/etc/systemd/system/rediacc-backup-foo-adhoc.service')
    ).toBeNull();
  });

  it('returns null for unrelated files', async () => {
    const { _testing } = await import('../backup-schedule.js');
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
      path: '/etc/rediacc/backup-x.env',
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
    const { _testing } = await import('../backup-schedule.js');
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
    const { _testing } = await import('../backup-schedule.js');
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
    const { _testing } = await import('../backup-schedule.js');
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
    const { _testing } = await import('../backup-schedule.js');
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
    const { _testing } = await import('../backup-schedule.js');
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
    const { _testing } = await import('../backup-schedule.js');
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
    const { _testing } = await import('../backup-schedule.js');
    const plan = planWithActiveUpdate('service');
    expect(() => _testing.applyInFlightGate(plan, false)).toThrow(
      /rediacc-backup-x\.service is currently running/
    );
  });

  it('throws when an adhoc service is running', async () => {
    // Adhoc backups are tracked by a distinct `-adhoc` unit; we must not
    // clobber unit files that belong to an in-flight on-demand backup.
    const { _testing } = await import('../backup-schedule.js');
    const plan = planWithActiveUpdate('adhoc');
    expect(() => _testing.applyInFlightGate(plan, false)).toThrow(
      /rediacc-backup-x-adhoc\.service is currently running/
    );
  });

  it('with force=true, emits a warning and does not throw', async () => {
    const { _testing } = await import('../backup-schedule.js');
    const plan = planWithActiveUpdate('service');
    expect(() => _testing.applyInFlightGate(plan, true)).not.toThrow();
    expect(mockOutputWarn).toHaveBeenCalledWith(
      expect.stringContaining('currently running; deploy proceeds')
    );
  });
});

// ---------------------------------------------------------------------------
// Integration tests — pushBackupSchedule (full flow with scripted SSH)
// ---------------------------------------------------------------------------

describe('pushBackupSchedule (reconcile)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockExecStreaming.mockResolvedValue(0);
    mockGetLocalConfig.mockResolvedValue(DEFAULT_LOCAL_CONFIG);
    mockGetBackupStrategy.mockResolvedValue(DEFAULT_STRATEGY);
    mockGetStorage.mockResolvedValue({ vaultContent: { any: 'value' } });
    mockBuildRcloneArgs.mockReturnValue(DEFAULT_RCLONE_ARGS);
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

  it('test 1: no existing units → creates both units atomically via staging + mv', async () => {
    scriptedExec([
      { match: /find \/etc\/systemd\/system/, stdout: '' },
      {
        match: 'Id,LoadState,ActiveState,SubState,UnitFileState',
        stdout: notFoundRecord('rediacc-backup-hourly-hot.service'),
      },
      {
        match: 'Id,LoadState,ActiveState,UnitFileState',
        stdout: healthyTimerRecord('rediacc-backup-hourly-hot.timer'),
      },
    ]);

    const { pushBackupSchedule } = await import('../backup-schedule.js');
    await pushBackupSchedule('hostinger');

    const cmds = recordedCommands();
    expect(cmds).toContain(
      'sudo tee /etc/systemd/system/rediacc-backup-hourly-hot.service.new > /dev/null'
    );
    expect(cmds).toContain(
      'sudo tee /etc/systemd/system/rediacc-backup-hourly-hot.timer.new > /dev/null'
    );
    expect(cmds).toContain(
      `sudo mv '/etc/systemd/system/rediacc-backup-hourly-hot.service.new' '/etc/systemd/system/rediacc-backup-hourly-hot.service'`
    );
    expect(cmds).toContain(
      `sudo mv '/etc/systemd/system/rediacc-backup-hourly-hot.timer.new' '/etc/systemd/system/rediacc-backup-hourly-hot.timer'`
    );
    const reloads = cmds.filter((c) => c === 'sudo systemctl daemon-reload');
    expect(reloads).toHaveLength(1);
    expect(cmds).toContain('sudo systemctl enable --now rediacc-backup-hourly-hot.timer');
    // No legacy glob-remove — only orphan cleanup of *.new files.
    expect(cmds.some((c) => c.includes('rm -f') && c.includes('rediacc-backup-*.service'))).toBe(
      false
    );
  });

  it('test 2: all hashes match → unchanged, no writes, no daemon-reload', async () => {
    const rcloneArgsByDest = new Map([['onedrive-hourly', DEFAULT_RCLONE_ARGS]]);
    const desired = await desiredContentFor(
      'hourly-hot',
      DEFAULT_STRATEGY as import('../../types/index.js').BackupStrategyConfig,
      DEFAULT_STRATEGY.destinations,
      rcloneArgsByDest
    );

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
          `${desired.serviceHash}  /etc/systemd/system/rediacc-backup-hourly-hot.service\n` +
          `${desired.timerHash}  /etc/systemd/system/rediacc-backup-hourly-hot.timer\n`,
      },
      {
        match: 'Id,LoadState,ActiveState,SubState,UnitFileState',
        stdout:
          idleServiceRecord('rediacc-backup-hourly-hot.service') +
          notFoundRecord('rediacc-backup-hourly-hot-adhoc.service') +
          healthyTimerRecord('rediacc-backup-hourly-hot.timer'),
      },
    ]);

    const { pushBackupSchedule } = await import('../backup-schedule.js');
    await pushBackupSchedule('hostinger');

    const cmds = recordedCommands();
    expect(cmds.some((c) => c.includes('tee '))).toBe(false);
    expect(cmds.some((c) => c.startsWith('sudo mv '))).toBe(false);
    expect(cmds).not.toContain('sudo systemctl daemon-reload');
    expect(cmds).not.toContain('sudo systemctl enable --now rediacc-backup-hourly-hot.timer');
    expect(mockOutputInfo).toHaveBeenCalledWith(expect.stringContaining('unchanged hourly-hot'));
  });

  it('test 3: schedule changed → only timer staged, service untouched', async () => {
    const rcloneArgsByDest = new Map([['onedrive-hourly', DEFAULT_RCLONE_ARGS]]);
    const desired = await desiredContentFor(
      'hourly-hot',
      DEFAULT_STRATEGY as import('../../types/index.js').BackupStrategyConfig,
      DEFAULT_STRATEGY.destinations,
      rcloneArgsByDest
    );

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
          `${desired.serviceHash}  /etc/systemd/system/rediacc-backup-hourly-hot.service\n` +
          `0000000000000000000000000000000000000000000000000000000000000000  /etc/systemd/system/rediacc-backup-hourly-hot.timer\n`,
      },
      {
        match: 'Id,LoadState,ActiveState,SubState,UnitFileState',
        stdout:
          idleServiceRecord('rediacc-backup-hourly-hot.service') +
          notFoundRecord('rediacc-backup-hourly-hot-adhoc.service') +
          idleServiceRecord('rediacc-backup-hourly-hot.timer'),
      },
      {
        match: 'Id,LoadState,ActiveState,UnitFileState',
        stdout: healthyTimerRecord('rediacc-backup-hourly-hot.timer'),
      },
    ]);

    const { pushBackupSchedule } = await import('../backup-schedule.js');
    await pushBackupSchedule('hostinger');

    const cmds = recordedCommands();
    expect(cmds).toContain(
      'sudo tee /etc/systemd/system/rediacc-backup-hourly-hot.timer.new > /dev/null'
    );
    expect(cmds.some((c) => c.includes('rediacc-backup-hourly-hot.service.new'))).toBe(false);
    expect(cmds).toContain(
      `sudo mv '/etc/systemd/system/rediacc-backup-hourly-hot.timer.new' '/etc/systemd/system/rediacc-backup-hourly-hot.timer'`
    );
    const reloads = cmds.filter((c) => c === 'sudo systemctl daemon-reload');
    expect(reloads).toHaveLength(1);
  });

  it('test 4: removed strategy → disable --now, then rm on exact paths (no glob)', async () => {
    const rcloneArgsByDest = new Map([['onedrive-hourly', DEFAULT_RCLONE_ARGS]]);
    const desired = await desiredContentFor(
      'hourly-hot',
      DEFAULT_STRATEGY as import('../../types/index.js').BackupStrategyConfig,
      DEFAULT_STRATEGY.destinations,
      rcloneArgsByDest
    );

    scriptedExec([
      {
        match: /find \/etc\/systemd\/system/,
        stdout:
          '/etc/systemd/system/rediacc-backup-hourly-hot.service\n' +
          '/etc/systemd/system/rediacc-backup-hourly-hot.timer\n' +
          '/etc/systemd/system/rediacc-backup-obsolete.service\n' +
          '/etc/systemd/system/rediacc-backup-obsolete.timer\n',
      },
      {
        match: 'sha256sum',
        stdout:
          `${desired.serviceHash}  /etc/systemd/system/rediacc-backup-hourly-hot.service\n` +
          `${desired.timerHash}  /etc/systemd/system/rediacc-backup-hourly-hot.timer\n` +
          `abc123abc123abc123abc123abc123abc123abc123abc123abc123abc123abc1  /etc/systemd/system/rediacc-backup-obsolete.service\n` +
          `def456def456def456def456def456def456def456def456def456def456def4  /etc/systemd/system/rediacc-backup-obsolete.timer\n`,
      },
      {
        match: 'Id,LoadState,ActiveState,SubState,UnitFileState',
        stdout:
          idleServiceRecord('rediacc-backup-hourly-hot.service') +
          notFoundRecord('rediacc-backup-hourly-hot-adhoc.service') +
          idleServiceRecord('rediacc-backup-hourly-hot.timer') +
          idleServiceRecord('rediacc-backup-obsolete.service') +
          notFoundRecord('rediacc-backup-obsolete-adhoc.service') +
          idleServiceRecord('rediacc-backup-obsolete.timer'),
      },
    ]);

    const { pushBackupSchedule } = await import('../backup-schedule.js');
    await pushBackupSchedule('hostinger');

    const cmds = recordedCommands();
    const disableIdx = cmds.findIndex(
      (c) => c === 'sudo systemctl disable --now rediacc-backup-obsolete.timer'
    );
    expect(disableIdx).toBeGreaterThanOrEqual(0);
    const rmIdx = cmds.findIndex(
      (c) =>
        c.startsWith('sudo rm -f') &&
        c.includes('rediacc-backup-obsolete.service') &&
        c.includes('rediacc-backup-obsolete.timer')
    );
    expect(rmIdx).toBeGreaterThan(disableIdx);
    expect(cmds.some((c) => c.includes('reset-failed'))).toBe(false);
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

    const { pushBackupSchedule } = await import('../backup-schedule.js');
    await expect(pushBackupSchedule('hostinger')).rejects.toThrow(
      /rediacc-backup-hourly-hot\.service is currently running/
    );
    const cmds = recordedCommands();
    expect(cmds.some((c) => c.includes('.new'))).toBe(false);
    expect(cmds.some((c) => c === 'sudo systemctl daemon-reload')).toBe(false);
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
        stdout: healthyTimerRecord('rediacc-backup-hourly-hot.timer'),
      },
    ]);

    const { pushBackupSchedule } = await import('../backup-schedule.js');
    await pushBackupSchedule('hostinger', { force: true });

    expect(mockOutputWarn).toHaveBeenCalledWith(
      expect.stringContaining('rediacc-backup-hourly-hot.service is currently running')
    );
    const cmds = recordedCommands();
    expect(cmds.some((c) => c.includes('.new'))).toBe(true);
    expect(cmds).toContain('sudo systemctl daemon-reload');
    // Critically: we did NOT stop the running service; systemd keeps the
    // in-memory copy alive until the invocation finishes.
    expect(cmds.some((c) => c.startsWith('sudo systemctl stop '))).toBe(false);
  });

  it('test 7: post-deploy verification failure throws with timer name and observed state', async () => {
    scriptedExec([
      { match: /find \/etc\/systemd\/system/, stdout: '' },
      {
        match: 'Id,LoadState,ActiveState,SubState,UnitFileState',
        stdout: notFoundRecord('rediacc-backup-hourly-hot.service'),
      },
      {
        match: 'Id,LoadState,ActiveState,UnitFileState',
        stdout: showRecord('rediacc-backup-hourly-hot.timer', {
          LoadState: 'loaded',
          ActiveState: 'inactive',
          SubState: 'dead',
          UnitFileState: 'enabled',
        }),
      },
    ]);

    const { pushBackupSchedule } = await import('../backup-schedule.js');
    await expect(pushBackupSchedule('hostinger')).rejects.toThrow(
      /rediacc-backup-hourly-hot\.timer.*ActiveState=inactive/s
    );
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
        stdout: healthyTimerRecord('rediacc-backup-hourly-hot.timer'),
      },
    ]);

    const { pushBackupSchedule } = await import('../backup-schedule.js');
    await pushBackupSchedule('hostinger', { resetFailed: true });

    const cmds = recordedCommands();
    expect(cmds.some((c) => c.includes('reset-failed'))).toBe(false);
  });

  it('test 9: dry-run reads state but performs zero mutations and no license mint', async () => {
    scriptedExec([
      { match: /find \/etc\/systemd\/system/, stdout: '' },
      {
        match: 'Id,LoadState,ActiveState,SubState,UnitFileState',
        stdout: notFoundRecord('rediacc-backup-hourly-hot.service'),
      },
    ]);

    const { pushBackupSchedule } = await import('../backup-schedule.js');
    await pushBackupSchedule('hostinger', { dryRun: true });

    const cmds = recordedCommands();
    expect(cmds.some((c) => c.includes('find /etc/systemd/system'))).toBe(true);
    expect(cmds.some((c) => c.includes('systemctl show'))).toBe(true);
    expect(cmds.some((c) => c.includes('tee '))).toBe(false);
    expect(cmds.some((c) => c.startsWith('sudo mv '))).toBe(false);
    expect(cmds.some((c) => c === 'sudo systemctl daemon-reload')).toBe(false);
    expect(cmds.some((c) => c.includes('enable --now'))).toBe(false);
    expect(mockProvisionRenetToRemote).not.toHaveBeenCalled();
    expect(mockRefreshRepoLicensesBatch).not.toHaveBeenCalled();
  });

  it('throws when machine has no backupStrategies', async () => {
    mockGetLocalConfig.mockResolvedValue({
      renetPath: '/local/renet',
      sshPrivateKey: 'KEY',
      ssh: { privateKeyPath: '/tmp/key' },
      machines: { hostinger: { ip: '1.2.3.4', user: 'test' } },
    });

    const { pushBackupSchedule } = await import('../backup-schedule.js');
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

    const { pushBackupSchedule } = await import('../backup-schedule.js');
    await expect(pushBackupSchedule('hostinger')).rejects.toThrow('no valid repo licenses');
  });
});
