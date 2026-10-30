/**
 * G4: every verb that changes the repository set re-renders the machine's backup schedule.
 *
 * fork and migrate are driven for real with the hook mocked. create, delete, promote and
 * `backup restore --as` sit behind executors and prompts the unit tests cannot reach cheaply, so
 * their wiring is asserted on the source: the hook call exists and follows the config mutation.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const mockReconcile = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
vi.mock('../../services/backup/repo-change-hook.js', () => ({
  reconcileBackupSchedules: mockReconcile,
}));

const mockGetRepository = vi.hoisted(() => vi.fn());
const mockAddRepository = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
const mockGetCurrent = vi.hoisted(() => vi.fn());
const mockGetLocalConfig = vi.hoisted(() => vi.fn());
const mockSetRepositoryPlacement = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getRepository: mockGetRepository,
    addRepository: mockAddRepository,
    allocateNetworkId: vi.fn().mockResolvedValue(99999),
    removeRepository: vi.fn(),
    getLocalMachine: vi.fn().mockResolvedValue({ ip: '127.0.0.1', user: 'root' }),
    getCurrent: mockGetCurrent,
    getLocalConfig: mockGetLocalConfig,
    setRepositoryPlacement: mockSetRepositoryPlacement,
  },
}));

const mockExecute = vi.hoisted(() =>
  vi.fn().mockResolvedValue({ success: true, stdout: '', allSteps: [], steps: [] })
);
vi.mock('../../services/executor/local-executor.js', () => ({
  localExecutorService: {
    execute: mockExecute,
    refreshIdentityFor: vi.fn().mockResolvedValue(undefined),
  },
}));
vi.mock('../../services/executor/executor-factory.js', () => ({
  getExecutor: () => ({ execute: mockExecute }),
}));

vi.mock('../../services/machine/machine-connection.js', () => ({
  machineConnections: {
    acquire: vi.fn().mockResolvedValue({
      sftp: {},
      machine: { ip: '127.0.0.1', user: 'root' },
      sshPrivateKey: 'k',
      ensure: vi.fn().mockResolvedValue({}),
      release: vi.fn(),
    }),
  },
}));

vi.mock('../../services/repo-migrate-license.js', () => ({
  ensureTargetRepoLicense: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('../../services/repo/repo-key-deployment.js', () => ({
  deployRepoKeyIfNeeded: vi.fn().mockResolvedValue(undefined),
  removeRepoKeyIfDeployed: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('../repo-batch-utils.js', () => ({
  postRepoUpTasks: vi.fn().mockResolvedValue(undefined),
  ensureDns: vi.fn().mockResolvedValue('example.com'),
}));
vi.mock('../../utils/ssh-keygen.js', () => ({
  generateSSHKeyPair: () => ({ privateKey: 'priv', publicKey: 'pub' }),
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: vi.fn(),
    success: vi.fn(),
    warn: vi.fn(),
    print: vi.fn(),
    setTimelineRendered: vi.fn(),
  },
}));
vi.mock('../../utils/local-execution-failures.js', () => ({
  renderLocalExecutionFailure: vi.fn(),
}));
vi.mock('../../utils/errors.js', async () => {
  const actual =
    await vi.importActual<typeof import('../../utils/errors.js')>('../../utils/errors.js');
  return {
    ...actual,
    handleError: (e: unknown) => {
      throw e;
    },
  };
});
vi.mock('../../services/config/network-id-discovery.js', async (orig) => ({
  ...(await orig<typeof import('../../services/config/network-id-discovery.js')>()),
  targetFloor: vi.fn().mockResolvedValue([]),
  ensureRepositoryNetworkId: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('../repo-list-parser.js', () => ({ parseRepositoryListOutput: () => [] }));
vi.mock('../repo-push-stats.js', () => ({ extractPushResult: () => undefined }));
vi.mock('../repo-backup.js', () => ({
  autoProvisionTarget: vi.fn().mockResolvedValue(undefined),
  buildPushParams: (repo: string, guid: string, type: string, to: string) => ({
    params: { repository: repo, dest: guid, destinationType: type, to },
    dest: guid,
  }),
}));
vi.mock('../../utils/command-policy.js', () => ({
  assertCommandPolicy: vi.fn().mockResolvedValue(undefined),
  CMD: { REPO_PUSH: 'repo push' },
}));
vi.mock('../../utils/remote-resolve.js', () => ({
  resolveRemoteName: (name: string) => Promise.resolve({ type: 'machine', name }),
}));
vi.mock('../../utils/repo-target.js', () => ({
  resolveRepoRef: () =>
    Promise.resolve({ name: 'app', repoKey: 'app', machineName: 'src-machine', tag: 'latest' }),
}));
vi.mock('../../utils/spinner.js', () => ({
  withSpinner: <T>(_label: string, fn: () => Promise<T>) => fn(),
}));

const { handleForkAction } = await import('../repo-fork.js');
const { migrateRepo } = await import('../repo-migrate.js');

const PARENT = {
  repositoryGuid: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  tag: 'latest',
  credential: 'luks-pass',
  networkId: 100,
};

beforeEach(() => {
  vi.clearAllMocks();
  mockReconcile.mockResolvedValue(undefined);
  mockExecute.mockResolvedValue({ success: true, stdout: '', allSteps: [], steps: [] });
  mockGetRepository.mockImplementation((ref: string) =>
    Promise.resolve(ref === 'app' ? PARENT : undefined)
  );
  mockGetCurrent.mockResolvedValue({
    resources: { repositories: { app: { grand: 'latest', tags: { latest: {} } } } },
  });
  mockGetLocalConfig.mockResolvedValue({
    machines: { 'src-machine': { ip: '10.0.0.1' }, 'dst-machine': { ip: '10.0.0.2' } },
  });
});

describe('G4 wiring: the repo set changes, the schedule re-renders', () => {
  it('fork reconciles the machine after registering the fork', async () => {
    await handleForkAction('app', 'staging', { machine: 'hostinger' });
    expect(mockAddRepository).toHaveBeenCalled();
    expect(mockReconcile).toHaveBeenCalledExactlyOnceWith('hostinger');
    expect(mockAddRepository.mock.invocationCallOrder[0]).toBeLessThan(
      mockReconcile.mock.invocationCallOrder[0]
    );
  });

  it('migrate reconciles both the target and the source after the cutover', async () => {
    // The source job (PLAN-detached-jobs J4) ends with the cutover marker the placement rewrite waits on.
    mockExecute.mockImplementation((options: { functionName: string }) =>
      Promise.resolve({
        success: true,
        stdout: '',
        allSteps: [],
        steps:
          options.functionName === 'repository_migrate'
            ? [{ name: 'cutover_complete', duration_ms: 1 }]
            : [],
      })
    );
    await migrateRepo('app', { to: 'dst-machine', skipDns: true });
    expect(mockSetRepositoryPlacement).toHaveBeenCalledWith('app', { machine: 'dst-machine' });
    expect(mockReconcile.mock.calls.map((c) => c[0]).sort()).toEqual([
      'dst-machine',
      'src-machine',
    ]);
    expect(mockSetRepositoryPlacement.mock.invocationCallOrder[0]).toBeLessThan(
      mockReconcile.mock.invocationCallOrder[0]
    );
  });

  it('migrate does not reconcile when the cutover throws before returning', async () => {
    mockExecute.mockResolvedValue({ success: false, stdout: '', allSteps: [], steps: [] });
    // The failure must be the cutover's own, or the no-reconcile claim proves nothing.
    await expect(migrateRepo('app', { to: 'dst-machine', skipDns: true })).rejects.toThrow(
      / failed: /
    );
    expect(mockExecute).toHaveBeenCalled();
    expect(mockReconcile).not.toHaveBeenCalled();
  });
});

/** The text of a command source from `anchor` on, so an order check reads one verb. */
function sourceFrom(file: string, anchor: string): string {
  const src = readFileSync(resolve(__dirname, '..', file), 'utf-8');
  const at = src.indexOf(anchor);
  expect(at, `${anchor} in ${file}`).toBeGreaterThan(-1);
  return src.slice(at);
}

describe('G4 wiring (source): verbs behind executors and prompts', () => {
  it('create reconciles the machine on a successful result, before the rollback arm', () => {
    const body = sourceFrom('repo-create-delete.ts', 'async function renderCreateResult');
    const hook = body.indexOf('await reconcileBackupSchedules(machine)');
    expect(hook).toBeGreaterThan(-1);
    expect(hook).toBeLessThan(body.indexOf('rollbackCreateRepo(name, guid)'));
  });

  it('delete reconciles the machine after the config entry settles', () => {
    const body = sourceFrom('repo-create-delete.ts', 'async function handleDeleteSuccess');
    const settle = body.indexOf('await settleConfigEntry(');
    const hook = body.indexOf('await reconcileBackupSchedules(machineName)');
    expect(settle).toBeGreaterThan(-1);
    expect(hook).toBeGreaterThan(settle);
  });

  it('promote reconciles the machine after the fork ref is renamed', () => {
    const body = sourceFrom('repo-promote.ts', 'repository_promote');
    const rename = body.indexOf('await configService.removeRepository(forkRef)');
    const hook = body.indexOf('await reconcileBackupSchedules(machineName)');
    expect(rename).toBeGreaterThan(-1);
    expect(hook).toBeGreaterThan(rename);
  });

  it('restore --as plans the target machine reconcile as a success step, before the --up deploy', () => {
    // PLAN-detached-jobs J4: the reconcile rides the restore job's ticket as a success step, so it runs once the restore succeeded, and the step order puts it before the deploy.
    const body = sourceFrom('backup.ts', 'function restoreTailSteps(');
    const hook = body.indexOf("planStep('reconcileBackupSchedules', { machine: targetMachine })");
    const up = body.indexOf("planStep('restoreDeploy'");
    expect(hook).toBeGreaterThan(-1);
    expect(hook).toBeLessThan(up);
  });
});
