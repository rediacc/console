import { beforeEach, describe, expect, it, vi } from 'vitest';

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

describe('generateServiceUnit', () => {
  it('keeps bwlimit on argv (per-destination) and emits EnvironmentFile=', async () => {
    // bwlimit is NOT a credential, and two destinations may legitimately
    // set different rates — so it lives on argv, not in the shared env file.
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
    // No credentials in this test -> no EnvironmentFile= directive emitted.
    expect(serviceContent).not.toContain('EnvironmentFile=');
    expect(envVars.RCLONE_BWLIMIT).toBeUndefined();
  });

  it('per-dest bwlimit overrides strategy bwlimit on argv', async () => {
    const { _testing } = await import('../backup-schedule.js');
    const { serviceContent, envVars } = _testing.generateServiceUnit(
      'test',
      { schedule: '0 * * * *', bandwidthLimit: '6M', destinations: [] },
      [{ name: 'fast-dest', storage: 'microsoft', bandwidthLimit: '50M' }],
      new Map([['fast-dest', { remote: ':s3:bucket', params: [] }]]),
      '/mnt/rediacc',
      '/usr/bin/renet'
    );
    expect(serviceContent).toContain('--rclone-param bwlimit=50M');
    expect(serviceContent).not.toContain('bwlimit=6M');
    expect(envVars.RCLONE_BWLIMIT).toBeUndefined();
  });

  it('allows two destinations with different bwlimits in one strategy', async () => {
    // Regression: moving bwlimit to envVars caused mergeEnvVars to throw on
    // conflicting per-destination rates, breaking a legitimate config.
    const { _testing } = await import('../backup-schedule.js');
    const { serviceContent } = _testing.generateServiceUnit(
      'mixed-rates',
      { schedule: '0 * * * *', destinations: [] },
      [
        { name: 'slow', storage: 'microsoft', bandwidthLimit: '1M' },
        { name: 'fast', storage: 'microsoft', bandwidthLimit: '100M' },
      ],
      new Map([
        ['slow', { remote: ':onedrive:slow', params: [] }],
        ['fast', { remote: ':onedrive:fast', params: [] }],
      ]),
      '/mnt/rediacc',
      '/usr/bin/renet'
    );
    expect(serviceContent).toContain('--rclone-param bwlimit=1M');
    expect(serviceContent).toContain('--rclone-param bwlimit=100M');
  });

  it('includes --include-repo when strategy has include', async () => {
    const { _testing } = await import('../backup-schedule.js');
    const { serviceContent } = _testing.generateServiceUnit(
      'critical',
      { schedule: '0 * * * *', include: ['mail', 'nextcloud'], destinations: [] },
      [{ name: 'dest', storage: 'microsoft' }],
      new Map([['dest', { remote: ':onedrive:hostinger', params: [] }]]),
      '/mnt/rediacc',
      '/usr/bin/renet'
    );
    expect(serviceContent).toContain('--include-repo mail,nextcloud');
    expect(serviceContent).not.toContain('--exclude-repo');
  });

  it('includes --exclude-repo when strategy has exclude', async () => {
    const { _testing } = await import('../backup-schedule.js');
    const { serviceContent } = _testing.generateServiceUnit(
      'nightly',
      { schedule: '0 3 * * *', mode: 'cold', exclude: ['gitlab'], destinations: [] },
      [{ name: 'dest', storage: 'microsoft' }],
      new Map([['dest', { remote: ':onedrive:hostinger', params: [] }]]),
      '/mnt/rediacc',
      '/usr/bin/renet'
    );
    expect(serviceContent).toContain('--exclude-repo gitlab');
    expect(serviceContent).toContain('--mode cold');
  });

  it('omits mode flag when mode is undefined (defaults to hot)', async () => {
    const { _testing } = await import('../backup-schedule.js');
    const { serviceContent } = _testing.generateServiceUnit(
      'default',
      { schedule: '0 * * * *', destinations: [] },
      [{ name: 'dest', storage: 'microsoft' }],
      new Map([['dest', { remote: ':onedrive:hostinger', params: [] }]]),
      '/mnt/rediacc',
      '/usr/bin/renet'
    );
    expect(serviceContent).toContain('--mode hot');
  });

  it('generates multiple ExecStart lines for multiple destinations', async () => {
    const { _testing } = await import('../backup-schedule.js');
    const { serviceContent } = _testing.generateServiceUnit(
      'multi',
      { schedule: '0 3 * * *', destinations: [] },
      [
        { name: 'dest1', storage: 'microsoft' },
        { name: 'dest2', storage: 'r2' },
      ],
      new Map([
        ['dest1', { remote: ':onedrive:hostinger', params: [] }],
        ['dest2', { remote: ':s3:bucket', params: [] }],
      ]),
      '/mnt/rediacc',
      '/usr/bin/renet'
    );
    const execStartCount = (serviceContent.match(/ExecStart=/g) ?? []).length;
    expect(execStartCount).toBe(2);
    expect(serviceContent).toContain('--rclone-backend onedrive');
    expect(serviceContent).toContain('--rclone-backend s3');
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
    // TimeoutStartSec= must sit between Type=oneshot and the first ExecStart=
    // so systemd applies it to the actual run.
    const typeIdx = serviceContent.indexOf('Type=oneshot');
    const timeoutIdx = serviceContent.indexOf('TimeoutStartSec=infinity');
    const execIdx = serviceContent.indexOf('ExecStart=');
    expect(typeIdx).toBeGreaterThanOrEqual(0);
    expect(timeoutIdx).toBeGreaterThan(typeIdx);
    expect(execIdx).toBeGreaterThan(timeoutIdx);
  });

  it('omits EnvironmentFile= when no credentials are present', async () => {
    const { _testing } = await import('../backup-schedule.js');
    const { serviceContent, envVars } = _testing.generateServiceUnit(
      'no-creds',
      { schedule: '0 * * * *', destinations: [] },
      [{ name: 'dest', storage: 'microsoft' }],
      new Map([['dest', { remote: ':onedrive:hostinger', params: [] }]]),
      '/mnt/rediacc',
      '/usr/bin/renet'
    );
    expect(envVars).toEqual({});
    expect(serviceContent).not.toContain('EnvironmentFile=');
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
    // No access/refresh token or param flag should appear in the argv.
    expect(serviceContent).not.toContain('onedrive-token');
    expect(serviceContent).not.toContain('access_token');
    expect(serviceContent).not.toContain('refresh_token');
    expect(serviceContent).not.toContain('--rclone-param');
    expect(serviceContent).toContain('EnvironmentFile=/etc/rediacc/backup-nightly-cold.env');
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

  it('redacts --setenv values for sensitive RCLONE_ keys (quoted form)', async () => {
    const { sanitizeBackupOutput } = await import('../backup-schedule.js');
    const input =
      'systemd-run --unit=u --setenv=RCLONE_ONEDRIVE_TOKEN=\'{"access_token":"abc"}\' --setenv=RCLONE_BWLIMIT=\'6M\' --remain-after-exit';
    const out = sanitizeBackupOutput(input);
    expect(out).toContain("--setenv=RCLONE_ONEDRIVE_TOKEN='[REDACTED]'");
    expect(out).toContain("--setenv=RCLONE_BWLIMIT='6M'");
  });

  it('redacts --setenv values for sensitive RCLONE_ keys (bare form)', async () => {
    const { sanitizeBackupOutput } = await import('../backup-schedule.js');
    const input =
      'systemd-run --setenv=RCLONE_S3_SECRET_ACCESS_KEY=deadbeef --setenv=RCLONE_BWLIMIT=6M';
    const out = sanitizeBackupOutput(input);
    expect(out).toContain('--setenv=RCLONE_S3_SECRET_ACCESS_KEY=[REDACTED]');
    expect(out).toContain('--setenv=RCLONE_BWLIMIT=6M');
  });
});

describe('generateEnvFile', () => {
  it('quotes values and escapes backslashes and double quotes', async () => {
    const { _testing } = await import('../backup-schedule.js');
    const tokenJson = '{"access_token":"ab\\c","refresh_token":"x\\"y"}';
    const content = _testing.generateEnvFile({ RCLONE_ONEDRIVE_TOKEN: tokenJson });
    // Every value must be double-quoted; embedded " and \ escaped.
    expect(content).toBe(
      `RCLONE_ONEDRIVE_TOKEN="{\\"access_token\\":\\"ab\\\\c\\",\\"refresh_token\\":\\"x\\\\\\"y\\"}"\n`
    );
  });

  it('returns empty string for an empty map', async () => {
    const { _testing } = await import('../backup-schedule.js');
    expect(_testing.generateEnvFile({})).toBe('');
  });

  it('emits one line per key', async () => {
    const { _testing } = await import('../backup-schedule.js');
    const content = _testing.generateEnvFile({
      RCLONE_ONEDRIVE_TOKEN: 'tok',
      RCLONE_ONEDRIVE_DRIVE_ID: 'id',
      RCLONE_BWLIMIT: '6M',
    });
    const lines = content.trimEnd().split('\n');
    expect(lines).toHaveLength(3);
    expect(lines).toContain('RCLONE_ONEDRIVE_TOKEN="tok"');
    expect(lines).toContain('RCLONE_ONEDRIVE_DRIVE_ID="id"');
    expect(lines).toContain('RCLONE_BWLIMIT="6M"');
  });
});

describe('cronToOnCalendar', () => {
  // Regression: cron ranges like "0-2,4-23" must become systemd "0..2,4..23"
  // (double-dot, not hyphen). Single-dash output trips systemd's parser and
  // renders the timer unit "bad-setting", silently disabling the schedule.
  it('converts hyphen ranges and comma-lists to systemd ..-ranges', async () => {
    const { _testing } = await import('../backup-schedule.js');
    expect(_testing.cronToOnCalendar('0 0-2,4-23 * * *')).toBe(
      '*-*-* 00..02,04..23:00:00'
    );
    expect(_testing.cronToOnCalendar('0 */6 * * *')).toBe('*-*-* 00/6:00:00');
    expect(_testing.cronToOnCalendar('15 3 * * *')).toBe('*-*-* 03:15:00');
    expect(_testing.cronToOnCalendar('0 * * * *')).toBe('*-*-* *:00:00');
  });
});

describe('pushBackupSchedule', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mockExecStreaming.mockResolvedValue(0);

    mockGetLocalConfig.mockResolvedValue({
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
    });

    mockGetBackupStrategy.mockResolvedValue({
      schedule: '0 * * * *',
      mode: 'hot',
      destinations: [{ name: 'onedrive-hourly', storage: 'microsoft', enabled: true }],
    });

    mockGetStorage.mockResolvedValue({ vaultContent: { any: 'value' } });
    mockBuildRcloneArgs.mockReturnValue({
      remote: ':s3:rediacc/hostinger',
      params: ['--s3-region=auto'],
    });
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

  it('reads machine.backupStrategies and deploys one timer per strategy', async () => {
    const { pushBackupSchedule } = await import('../backup-schedule.js');

    await pushBackupSchedule('hostinger');

    // Should write service + timer + enable for the strategy
    const commands = mockExecStreaming.mock.calls.map(([cmd]) => cmd);
    expect(commands).toContain(
      'sudo tee /etc/systemd/system/rediacc-backup-hourly-hot.service > /dev/null'
    );
    expect(commands).toContain(
      'sudo tee /etc/systemd/system/rediacc-backup-hourly-hot.timer > /dev/null'
    );
    expect(commands).toContain('sudo systemctl enable --now rediacc-backup-hourly-hot.timer');
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

  it('writes env file with umask 077 before writing the service unit', async () => {
    mockBuildRcloneArgs.mockReturnValue({
      remote: ':onedrive:hostinger',
      params: ['--onedrive-token={"access_token":"a"}'],
    });

    const { pushBackupSchedule } = await import('../backup-schedule.js');
    await pushBackupSchedule('hostinger');

    const commands = mockExecStreaming.mock.calls.map(([cmd]) => cmd as string);

    const envFileIdx = commands.findIndex((c) =>
      c.includes(`umask 077 && cat > /etc/rediacc/backup-hourly-hot.env`)
    );
    const serviceIdx = commands.findIndex((c) =>
      c.includes('tee /etc/systemd/system/rediacc-backup-hourly-hot.service')
    );
    const mkdirIdx = commands.findIndex((c) =>
      c.includes('install -d -m 0755 -o root -g root /etc/rediacc')
    );

    expect(mkdirIdx).toBeGreaterThanOrEqual(0);
    expect(envFileIdx).toBeGreaterThan(mkdirIdx);
    expect(serviceIdx).toBeGreaterThan(envFileIdx);

    // Stdin for the env-file write must carry the token, not the service unit.
    const envStdin = mockExecStreaming.mock.calls[envFileIdx][1].stdin as string;
    expect(envStdin).toContain('RCLONE_ONEDRIVE_TOKEN=');
    expect(envStdin).toContain('access_token');

    // The service unit written to disk must NOT contain the token.
    const serviceStdin = mockExecStreaming.mock.calls[serviceIdx][1].stdin as string;
    expect(serviceStdin).not.toContain('access_token');
    expect(serviceStdin).not.toContain('--rclone-param');
    expect(serviceStdin).toContain('EnvironmentFile=/etc/rediacc/backup-hourly-hot.env');
  });

  it('cleanup removes stale env files alongside units', async () => {
    const { pushBackupSchedule } = await import('../backup-schedule.js');
    await pushBackupSchedule('hostinger');

    const commands = mockExecStreaming.mock.calls.map(([cmd]) => cmd as string);
    const cleanupCmd = commands.find((c) => c.startsWith('sudo rm -f'));
    expect(cleanupCmd).toBeDefined();
    expect(cleanupCmd).toContain('/etc/rediacc/backup-*.env');
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
