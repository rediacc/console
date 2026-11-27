import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const EU = 'https://eu.rediacc.cloud';
const BENCH = 'https://bench.rediacc.cloud';

beforeAll(async () => {
  await import('../backup-schedule.js');
}, 30000);

const mockAcquireFor = vi.fn();
const mockRelease = vi.fn();
const mockExecStreaming = vi.fn();
const mockAcquireRemoteRenet = vi.fn();
const mockRunCommandJob = vi.fn();
const mockRefreshRepoLicensesBatch = vi.fn();
const mockGetLocalConfig = vi.fn();
const mockGetCurrent = vi.fn();
const mockGetBackupStrategy = vi.fn();
const mockWarn = vi.fn();
const mockOrigin = vi.fn();

vi.mock('../../machine/machine-connection.js', () => ({
  machineConnections: { acquireFor: mockAcquireFor },
}));
vi.mock('../../renet/renet-execution.js', () => ({
  acquireRemoteRenet: mockAcquireRemoteRenet,
  readSSHKey: vi.fn().mockResolvedValue('KEY'),
}));
vi.mock('../../jobs/command-job.js', () => ({
  runCommandJob: mockRunCommandJob,
  pendingExitCode: () => undefined,
}));
vi.mock('../../account/license.js', () => ({
  refreshRepoLicensesBatch: mockRefreshRepoLicensesBatch,
}));
vi.mock('../../config/config-resources.js', () => ({
  configService: {
    getBackupStrategy: mockGetBackupStrategy,
    listBackupStrategies: vi.fn(() => Promise.resolve({})),
    getLocalConfig: mockGetLocalConfig,
    getCurrent: mockGetCurrent,
  },
}));
vi.mock('../../core/output.js', () => ({
  outputService: { info: vi.fn(), warn: mockWarn },
}));
vi.mock('../backup-store-universe.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../backup-store-universe.js')>()),
  expectedAccountServerOrigin: mockOrigin,
}));

const GUID = 'aaaaaaaa-0000-4000-8000-000000000001';
const MACHINE = {
  ip: '72.61.137.225',
  user: 'muhammed',
  port: 22,
  datastore: WK_DATASTORE_PATH,
  backupStrategies: ['hourly-hot'],
};

/** What the machine's units record: the `grep -o` of the expect-account-server flag, one match per unit. */
function deployedOrigin(origin: string | undefined): void {
  mockExecStreaming.mockImplementation(
    (cmd: string, opts?: { onStdout?: (data: Buffer) => void }): Promise<number> => {
      if (cmd.includes('rediacc-backup-*.service') && cmd.includes('grep') && origin) {
        opts?.onStdout?.(Buffer.from(`--expect-account-server ${origin}\n`.repeat(6)));
      }
      if (cmd === 'nproc') opts?.onStdout?.(Buffer.from('8\n'));
      if (cmd.includes('backup snapshot --help')) {
        opts?.onStdout?.(Buffer.from('  --expect-account-server string   x\n'));
      }
      return Promise.resolve(0);
    }
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockAcquireFor.mockResolvedValue({
    sftp: { execStreaming: mockExecStreaming },
    release: mockRelease,
  });
  mockAcquireRemoteRenet.mockResolvedValue({ remotePath: '/usr/bin/renet', uploaded: false });
  mockRunCommandJob.mockResolvedValue({
    kind: 'finished',
    result: { success: true, exitCode: 0, durationMs: 1, state: 'succeeded' },
  });
  mockRefreshRepoLicensesBatch.mockResolvedValue({
    scanned: 0,
    issued: 0,
    refreshed: 0,
    unchanged: 0,
    failed: 0,
    valid: 0,
    failures: [],
  });
  mockGetLocalConfig.mockResolvedValue({
    renetPath: '/local/renet',
    sshPrivateKey: 'KEY',
    ssh: { privateKeyPath: '/tmp/key' },
    machines: { hostinger: MACHINE },
  });
  mockGetCurrent.mockResolvedValue({
    resources: {
      machines: { hostinger: { ip: MACHINE.ip, user: MACHINE.user, datastore: WK_DATASTORE_PATH } },
      datastores: {},
      repositories: {
        mail: {
          placement: { machine: 'hostinger' },
          grand: 'latest',
          tags: { latest: { repositoryGuid: GUID } },
        },
      },
    },
  });
  mockGetBackupStrategy.mockResolvedValue({
    schedule: '0 * * * *',
    mode: 'hot',
    destinations: [{ kind: 'hosted-service', name: 'chunks-hourly', enabled: true }],
  });
  mockOrigin.mockReturnValue(BENCH);
});

describe('a push never silently re-points deployed units at another account server', () => {
  it('refuses, naming both origins and the machine, and writes nothing', async () => {
    deployedOrigin(EU);
    const { pushBackupSchedule } = await import('../backup-schedule.js');
    const error = await pushBackupSchedule('hostinger').then(
      () => undefined,
      (e: Error) => e
    );
    expect(error?.message).toContain('hostinger');
    expect(error?.message).toContain(EU);
    expect(error?.message).toContain(BENCH);
    expect(error?.message).toContain('--adopt-origin');
    expect(mockAcquireRemoteRenet).not.toHaveBeenCalled();
    expect(mockRefreshRepoLicensesBatch).not.toHaveBeenCalled();
    expect(mockRunCommandJob).not.toHaveBeenCalled();
  });

  it('pushes when --adopt-origin asks for the move', async () => {
    deployedOrigin(EU);
    const { pushBackupSchedule } = await import('../backup-schedule.js');
    await expect(pushBackupSchedule('hostinger', { adoptOrigin: true })).resolves.toBe('applied');
    expect(mockRunCommandJob).toHaveBeenCalledTimes(1);
    const payload = (mockRunCommandJob.mock.calls[0][1] as { commandKind: { payload: string } })
      .commandKind.payload;
    expect(payload).toContain(`--expect-account-server ${BENCH}`);
    expect(payload).not.toContain(EU);
  });

  it('pushes when the deployed units already name this config origin', async () => {
    deployedOrigin(BENCH);
    const { pushBackupSchedule } = await import('../backup-schedule.js');
    await expect(pushBackupSchedule('hostinger')).resolves.toBe('applied');
  });

  it('pushes to a machine whose units record no origin (none deployed, or an older renet)', async () => {
    deployedOrigin(undefined);
    const { pushBackupSchedule } = await import('../backup-schedule.js');
    await expect(pushBackupSchedule('hostinger')).resolves.toBe('applied');
  });

  it('a repo-change re-render under the same mismatch skips without writing', async () => {
    deployedOrigin(EU);
    const { reconcileSchedulesAfterRepoChange } = await import('../backup-schedule.js');
    await expect(reconcileSchedulesAfterRepoChange('hostinger')).resolves.toBe(false);
    expect(mockWarn).toHaveBeenCalledWith(expect.stringContaining(EU));
    expect(mockAcquireRemoteRenet).not.toHaveBeenCalled();
    expect(mockRunCommandJob).not.toHaveBeenCalled();
  });
});
