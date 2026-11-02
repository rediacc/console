import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
/**
 * `rdc backup restore <src> --as <name>` on the pull route mints a fresh GUID
 * (restoredIdentity), and `backup_pull` is full-tier: renet validates the
 * licence for that DESTINATION GUID, which no machine holds. The executor's
 * recovery runs the image-scanning batch refresh, which cannot license an image
 * that does not exist yet, so the restore died LICENSE_REQUIRED. The CLI now
 * issues the minted GUID's licence on the target before the pull.
 */
import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const SOURCE_GUID = vi.hoisted(() => '0a1b2c3d-0000-4000-8000-00000000a11c');

const mockAddRepository = vi.hoisted(() => vi.fn());
const mockRemoveRepository = vi.hoisted(() => vi.fn());
const mockSource = vi.hoisted(() => ({
  current: {
    repositoryGuid: '',
    tag: 'latest',
    credential: '',
  } as { repositoryGuid: string; tag: string; credential: string; grandGuid?: string },
}));

vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getCurrent: vi.fn().mockResolvedValue({ state: {}, resources: { repositories: {} } }),
    addRepository: mockAddRepository,
    removeRepository: mockRemoveRepository,
    allocateNetworkId: vi.fn().mockResolvedValue(4242),
    getRepository: (ref: string) => Promise.resolve(ref === 'src' ? mockSource.current : undefined),
    listRepositories: vi.fn().mockResolvedValue([]),
  },
}));

const mockExecute = vi.hoisted(() => vi.fn());
vi.mock('../../services/executor/executor-factory.js', () => ({
  getExecutor: () => ({ execute: mockExecute }),
}));
const mockFetch = vi.hoisted(() => vi.fn());
// These verbs read the hosted backup plane, which needs a login (PLAN-free-license R13); a logged-in operator is the case under test.
vi.mock('../../services/account/subscription-auth.js', () => ({
  getSubscriptionTokenState: () => ({
    kind: 'ready',
    token: { token: 't' },
    serverUrl: 'https://acct.example',
  }),
  getSubscriptionServerUrl: () => 'https://acct.example',
}));
vi.mock('../../services/account/account-client.js', () => ({ accountServerFetch: mockFetch }));
vi.mock('../../services/backup/backup-runs-state.js', () => ({
  recordBackupRun: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('../../services/backup/dr-nudge.js', () => ({
  warnIfConfigStorageUnenrolled: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('../../services/addressing/ref-parser.js', () => ({
  parseRef: (raw: string) => ({ place: raw.split(':')[0], name: raw.split(':')[1] ?? 'src' }),
}));
const mockPlaceType = vi.hoisted(() => ({ current: 'machine' as 'machine' | 'cluster' }));
vi.mock('../../utils/remote-resolve.js', () => ({
  resolveRemoteName: (name: string) => Promise.resolve({ type: mockPlaceType.current, name }),
}));
vi.mock('../repo-backup-list.js', () => ({
  fetchBackupList: vi.fn().mockResolvedValue([]),
  renderBackupList: vi.fn(),
}));
vi.mock('../../services/repo/repo-key-deployment.js', () => ({
  deployRepoKeyIfNeeded: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('../../utils/agent-guard.js', () => ({
  assertAgentRepoCreate: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('../../utils/command-policy.js', () => ({
  assertCommandPolicy: vi.fn().mockResolvedValue(undefined),
  CMD: new Proxy({}, { get: (_t, p) => String(p) }),
}));
vi.mock('../_validate.js', () => ({ assertMachineExists: vi.fn().mockResolvedValue(undefined) }));
vi.mock('../backup-ops.js', () => ({ registerBackupOpsCommands: vi.fn() }));
vi.mock('../backup-strategy.js', () => ({ registerBackupStrategyCommands: vi.fn() }));
vi.mock('../../utils/local-execution-failures.js', () => ({
  renderLocalExecutionFailure: vi.fn(),
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: { info: vi.fn(), success: vi.fn(), warn: vi.fn(), error: vi.fn(), print: vi.fn() },
}));
vi.mock('../../utils/errors.js', async () => {
  const actual =
    await vi.importActual<typeof import('../../utils/errors.js')>('../../utils/errors.js');
  return {
    ...actual,
    getOutputFormat: () => 'table',
    handleError: (e: unknown) => {
      throw e;
    },
  };
});

const mockAcquire = vi.hoisted(() => vi.fn());
const mockRelease = vi.hoisted(() => vi.fn());
vi.mock('../../services/machine/machine-connection.js', () => ({
  machineConnections: { acquire: mockAcquire },
}));
const mockResolveCtx = vi.hoisted(() => vi.fn());
const mockAlreadyInstalled = vi.hoisted(() => vi.fn());
vi.mock('../../services/executor/repo-license-context.js', () => ({
  resolveRestoreLicenseContext: mockResolveCtx,
  restoreLicenseAlreadyInstalled: mockAlreadyInstalled,
}));
const mockAuthority = vi.hoisted(() => vi.fn());
const mockIssueFree = vi.hoisted(() => vi.fn());
vi.mock('../../services/account/free-license.js', () => ({
  resolveLicenseAuthority: mockAuthority,
  issueFreeRepoLicense: mockIssueFree,
}));
const mockIssueRepo = vi.hoisted(() => vi.fn());
vi.mock('../../services/account/license.js', () => ({ issueRepoLicense: mockIssueRepo }));
const mockMeasure = vi.hoisted(() => vi.fn());
vi.mock('../../services/account/license-machine.js', () => ({
  DEFAULT_DATASTORE: WK_DATASTORE_PATH,
  measureRepoSizeGb: mockMeasure,
}));
vi.mock('../../services/account/subscription-device-auth.js', () => ({
  authorizeSubscriptionViaDeviceCode: vi.fn(),
}));

const { registerBackupCommands } = await import('../backup.js');

async function run(argv: readonly string[]): Promise<void> {
  const program = new Command();
  program.exitOverride();
  registerBackupCommands(program);
  await program.parseAsync(['node', 'rdc', 'backup', ...argv]);
}

const ARGS = ['restore', 'm1:src', '--as', 'copy', '-m', 'm2', '--yes'] as const;
const mintedGuid = (): string => mockAddRepository.mock.calls[0][1].repositoryGuid;
const fnCalls = () => mockExecute.mock.calls.map((c) => c[0].functionName);

beforeEach(() => {
  vi.clearAllMocks();
  mockPlaceType.current = 'machine';
  mockSource.current = { repositoryGuid: SOURCE_GUID, tag: 'latest', credential: 'c' };
  mockAddRepository.mockResolvedValue(undefined);
  mockRemoveRepository.mockResolvedValue(undefined);
  // No snapshots in the index: the pull route.
  mockFetch.mockResolvedValue({ manifests: [] });
  mockExecute.mockResolvedValue({ success: true, stdout: '', durationMs: 1 });
  mockAcquire.mockImplementation((name: string) =>
    Promise.resolve({
      sftp: { name },
      machine: { name, ip: '10.0.0.1', user: 'u', datastore: `/mnt/${name}` },
      sshPrivateKey: 'k',
      release: mockRelease,
    })
  );
  // The context is built from the registered record: the minted GUID.
  mockResolveCtx.mockImplementation(() =>
    Promise.resolve({
      repositoryGuid: mintedGuid(),
      grandGuid: SOURCE_GUID,
      kind: 'fork',
      datastoreMount: '/mnt/m2',
    })
  );
  mockAlreadyInstalled.mockResolvedValue(false);
  mockAuthority.mockResolvedValue('token');
  mockIssueRepo.mockResolvedValue(true);
  mockIssueFree.mockResolvedValue(undefined);
  mockMeasure.mockResolvedValue(7);
});

describe('backup restore (pull route) licenses the minted GUID before backup_pull', () => {
  it('issues for the NEW GUID on the target, sized from the source image, before the pull runs', async () => {
    await run(ARGS);

    expect(mockIssueRepo).toHaveBeenCalledTimes(1);
    const [machine, , params] = mockIssueRepo.mock.calls[0];
    expect(machine.name).toBe('m2');
    expect(params.repositoryGuid).toBe(mintedGuid());
    expect(params.repositoryGuid).not.toBe(SOURCE_GUID);
    expect(params.requestedSizeGb).toBe(7);
    // Measured on the SOURCE machine, for the SOURCE image.
    expect(mockMeasure).toHaveBeenCalledWith({ name: 'm1' }, SOURCE_GUID, [undefined, '/mnt/m1']);
    const pullAt = fnCalls().indexOf('backup_pull');
    expect(mockIssueRepo.mock.invocationCallOrder[0]).toBeLessThan(
      mockExecute.mock.invocationCallOrder[pullAt]
    );
    expect(fnCalls().filter((f) => f === 'backup_pull')).toHaveLength(1);
    expect(mockRelease).toHaveBeenCalledTimes(2);
  });

  it('skips issuance when the target already holds a valid licence for the GUID', async () => {
    mockAlreadyInstalled.mockResolvedValue(true);
    await run(ARGS);
    expect(mockIssueRepo).not.toHaveBeenCalled();
    expect(mockIssueFree).not.toHaveBeenCalled();
    expect(fnCalls().filter((f) => f === 'backup_pull')).toHaveLength(1);
  });

  it('takes the FREE licence when there is no login', async () => {
    mockAuthority.mockResolvedValue('free');
    await run(ARGS);
    expect(mockIssueRepo).not.toHaveBeenCalled();
    expect(mockIssueFree).toHaveBeenCalledTimes(1);
    expect(mockIssueFree.mock.calls[0][2]).toMatchObject({
      repositoryGuid: mintedGuid(),
      requestedSizeGb: 7,
    });
  });

  it('requests the floor for a cluster source, which names no machine to measure on', async () => {
    mockPlaceType.current = 'cluster';
    await run(ARGS);
    expect(mockMeasure).not.toHaveBeenCalled();
    expect(mockIssueRepo.mock.calls[0][2].requestedSizeGb).toBe(1);
  });

  it('a failed issuance runs no pull and drops the registration, so a retry is not blocked', async () => {
    mockIssueRepo.mockResolvedValue(false);
    await expect(run(ARGS)).rejects.toThrow(/activationFailed/);
    expect(fnCalls()).not.toContain('backup_pull');
    expect(mockRemoveRepository).toHaveBeenCalledWith('copy:latest');
    expect(mockRelease).toHaveBeenCalled();
  });
});
