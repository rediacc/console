import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockExecStreaming = vi.fn();
const mockConnect = vi.fn().mockResolvedValue(undefined);
const mockClose = vi.fn();
const mockBuildRcloneArgs = vi.fn();

const mockProvisionRenetToRemote = vi.fn().mockResolvedValue('/usr/bin/renet');
const mockReadSSHKey = vi.fn().mockResolvedValue('PRIVATE_KEY');

const mockGetBackupStrategy = vi.fn();
const mockGetLocalConfig = vi.fn();
const mockGetStorage = vi.fn();

const mockOutputInfo = vi.fn();
const mockOutputWarn = vi.fn();

vi.mock('@rediacc/shared-desktop/sftp', () => ({
  SFTPClient: vi.fn().mockImplementation(function MockSFTPClient() {
    return {
      connect: mockConnect,
      close: mockClose,
      execStreaming: mockExecStreaming,
    };
  }),
}));

vi.mock('@rediacc/shared/queue-vault', () => ({
  buildRcloneArgs: mockBuildRcloneArgs,
}));

vi.mock('../renet-execution.js', () => ({
  provisionRenetToRemote: mockProvisionRenetToRemote,
  readSSHKey: mockReadSSHKey,
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
        typeof cmd === 'string' && cmd.includes('sudo rm -f /etc/systemd/system/rediacc-backup*.service')
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
    expect(commands).not.toContain('sudo systemctl enable --now rediacc-backup-r2-cloudflare.timer');
  });
});
