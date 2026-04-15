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
  it('includes mode and bwlimit in ExecStart', async () => {
    const { _testing } = await import('../backup-schedule.js');
    const content = _testing.generateServiceUnit(
      'hourly-hot',
      { schedule: '0 * * * *', mode: 'hot', bandwidthLimit: '6M', destinations: [] },
      [{ name: 'onedrive', storage: 'microsoft' }],
      new Map([['onedrive', { remote: ':onedrive:hostinger', params: [] }]]),
      '/mnt/rediacc',
      '/usr/bin/renet'
    );
    expect(content).toContain('--mode hot');
    expect(content).toContain("--rclone-param 'bwlimit=6M'");
  });

  it('per-dest bwlimit overrides strategy bwlimit', async () => {
    const { _testing } = await import('../backup-schedule.js');
    const content = _testing.generateServiceUnit(
      'test',
      { schedule: '0 * * * *', bandwidthLimit: '6M', destinations: [] },
      [{ name: 'fast-dest', storage: 'microsoft', bandwidthLimit: '50M' }],
      new Map([['fast-dest', { remote: ':s3:bucket', params: [] }]]),
      '/mnt/rediacc',
      '/usr/bin/renet'
    );
    expect(content).toContain('bwlimit=50M');
    expect(content).not.toContain('bwlimit=6M');
  });

  it('includes --include-repo when strategy has include', async () => {
    const { _testing } = await import('../backup-schedule.js');
    const content = _testing.generateServiceUnit(
      'critical',
      { schedule: '0 * * * *', include: ['mail', 'nextcloud'], destinations: [] },
      [{ name: 'dest', storage: 'microsoft' }],
      new Map([['dest', { remote: ':onedrive:hostinger', params: [] }]]),
      '/mnt/rediacc',
      '/usr/bin/renet'
    );
    expect(content).toContain('--include-repo mail,nextcloud');
    expect(content).not.toContain('--exclude-repo');
  });

  it('includes --exclude-repo when strategy has exclude', async () => {
    const { _testing } = await import('../backup-schedule.js');
    const content = _testing.generateServiceUnit(
      'nightly',
      { schedule: '0 3 * * *', mode: 'cold', exclude: ['gitlab'], destinations: [] },
      [{ name: 'dest', storage: 'microsoft' }],
      new Map([['dest', { remote: ':onedrive:hostinger', params: [] }]]),
      '/mnt/rediacc',
      '/usr/bin/renet'
    );
    expect(content).toContain('--exclude-repo gitlab');
    expect(content).toContain('--mode cold');
  });

  it('omits mode flag when mode is undefined (defaults to hot)', async () => {
    const { _testing } = await import('../backup-schedule.js');
    const content = _testing.generateServiceUnit(
      'default',
      { schedule: '0 * * * *', destinations: [] },
      [{ name: 'dest', storage: 'microsoft' }],
      new Map([['dest', { remote: ':onedrive:hostinger', params: [] }]]),
      '/mnt/rediacc',
      '/usr/bin/renet'
    );
    expect(content).toContain('--mode hot');
  });

  it('generates multiple ExecStart lines for multiple destinations', async () => {
    const { _testing } = await import('../backup-schedule.js');
    const content = _testing.generateServiceUnit(
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
    const execStartCount = (content.match(/ExecStart=/g) ?? []).length;
    expect(execStartCount).toBe(2);
    expect(content).toContain('--rclone-backend onedrive');
    expect(content).toContain('--rclone-backend s3');
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
