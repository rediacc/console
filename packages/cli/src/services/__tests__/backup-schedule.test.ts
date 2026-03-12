import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockExecStreaming = vi.fn();
const mockConnect = vi.fn().mockResolvedValue(undefined);
const mockClose = vi.fn();
const mockBuildRcloneArgs = vi.fn();

const mockProvisionRenetToRemote = vi.fn().mockResolvedValue('/usr/bin/renet');
const mockReadSSHKey = vi.fn().mockResolvedValue('PRIVATE_KEY');
const mockRefreshRepoLicensesBatch = vi.fn();

const mockGetBackupStrategy = vi.fn();
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

describe('pushBackupSchedule', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mockExecStreaming.mockResolvedValue(0);

    mockGetBackupStrategy.mockResolvedValue({
      enabled: true,
      schedule: '0 2 * * *',
      destinations: [
        { storage: 'microsoft', enabled: true },
        { storage: 'r2-cloudflare', enabled: true },
      ],
    });

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
        },
      },
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

  it('cleans up all existing backup units before redeploying destination timers', async () => {
    const { pushBackupSchedule } = await import('../backup-schedule.js');

    await pushBackupSchedule('hostinger');

    expect(mockExecStreaming).toHaveBeenCalledWith(
      expect.stringContaining('sudo rm -f /etc/systemd/system/rediacc-backup*.service'),
      expect.any(Object)
    );
    expect(mockExecStreaming).toHaveBeenCalledWith(
      'sudo systemctl daemon-reload',
      expect.any(Object)
    );
    expect(mockExecStreaming).toHaveBeenCalledWith(
      'sudo systemctl reset-failed',
      expect.any(Object)
    );

    const cleanupIndex = mockExecStreaming.mock.calls.findIndex(
      ([cmd]) =>
        typeof cmd === 'string' &&
        cmd.includes('sudo rm -f /etc/systemd/system/rediacc-backup*.service')
    );
    const writeMicrosoftIndex = mockExecStreaming.mock.calls.findIndex(
      ([cmd]) =>
        typeof cmd === 'string' &&
        cmd === 'sudo tee /etc/systemd/system/rediacc-backup-microsoft.service > /dev/null'
    );

    expect(cleanupIndex).toBeGreaterThanOrEqual(0);
    expect(writeMicrosoftIndex).toBeGreaterThan(cleanupIndex);
  });

  it('only deploys enabled destinations after cleanup', async () => {
    mockGetBackupStrategy.mockResolvedValue({
      enabled: true,
      schedule: '0 2 * * *',
      destinations: [
        { storage: 'microsoft', enabled: true },
        { storage: 'r2-cloudflare', enabled: false },
      ],
    });

    const { pushBackupSchedule } = await import('../backup-schedule.js');

    await pushBackupSchedule('hostinger');

    const commands = mockExecStreaming.mock.calls.map(([cmd]) => cmd);

    expect(commands).toContain(
      'sudo tee /etc/systemd/system/rediacc-backup-microsoft.service > /dev/null'
    );
    expect(commands).not.toContain(
      'sudo tee /etc/systemd/system/rediacc-backup-r2-cloudflare.service > /dev/null'
    );
    expect(commands).not.toContain(
      'sudo systemctl enable --now rediacc-backup-r2-cloudflare.timer'
    );
  });

  it('aborts deploy when repo batch refresh yields zero valid repos', async () => {
    mockRefreshRepoLicensesBatch.mockResolvedValueOnce({
      scanned: 2,
      issued: 0,
      refreshed: 0,
      unchanged: 0,
      failed: 2,
      valid: 0,
      failures: [
        { repositoryGuid: 'a', error: 'expired' },
        { repositoryGuid: 'b', error: 'expired' },
      ],
    });

    const { pushBackupSchedule } = await import('../backup-schedule.js');

    await expect(pushBackupSchedule('hostinger')).rejects.toThrow('no valid repo licenses');
  });
});
