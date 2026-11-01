/**
 * `rdc backup restore <src> --as <name>` with no `--at` on a repo that has a
 * chunk-store lineage restores the NEWEST snapshot. It used to take the
 * machine-pull path and die on `stat repositories/<guid>: no such file`
 * (live run 2026-10-28). A repo with no snapshots keeps the pull.
 */
import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const SOURCE_GUID = vi.hoisted(() => '0a1b2c3d-0000-4000-8000-00000000a11c');

const mockAddRepository = vi.hoisted(() => vi.fn());
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
    removeRepository: vi.fn().mockResolvedValue(undefined),
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
vi.mock('../../utils/remote-resolve.js', () => ({
  resolveRemoteName: (name: string) => Promise.resolve({ type: 'machine', name }),
}));
vi.mock('../repo-backup-list.js', () => ({
  fetchBackupList: vi.fn().mockResolvedValue([]),
  renderBackupList: vi.fn(),
}));
// The pull route installs the minted GUID's licence first (ensureRestorePullLicense); here one is already installed, so it is skipped. backup-restore-pull-license.test.ts covers issuance.
vi.mock('../../services/machine/machine-connection.js', () => ({
  machineConnections: {
    acquire: vi.fn().mockResolvedValue({
      sftp: {},
      machine: { ip: '10.0.0.1', user: 'u' },
      sshPrivateKey: 'k',
      release: vi.fn(),
    }),
  },
}));
vi.mock('../../services/executor/repo-license-context.js', () => ({
  resolveRestoreLicenseContext: vi.fn().mockResolvedValue({
    repositoryGuid: 'g',
    grandGuid: 'g',
    kind: 'grand',
    datastoreMount: '/mnt/rediacc',
  }),
  restoreLicenseAlreadyInstalled: vi.fn().mockResolvedValue(true),
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

const { registerBackupCommands } = await import('../backup.js');
const { outputService } = await import('../../services/core/output.js');

async function run(argv: readonly string[]): Promise<void> {
  const program = new Command();
  program.exitOverride();
  registerBackupCommands(program);
  await program.parseAsync(['node', 'rdc', 'backup', ...argv]);
}

const fnCalls = () => mockExecute.mock.calls.map((c) => c[0].functionName);
const ARGS = ['restore', 'm1:src', '--as', 'copy', '-m', 'm1', '--any-stream'] as const;

beforeEach(() => {
  vi.clearAllMocks();
  mockSource.current = { repositoryGuid: SOURCE_GUID, tag: 'latest', credential: 'c' };
  mockAddRepository.mockResolvedValue(undefined);
  mockExecute.mockResolvedValue({ success: true, stdout: '', durationMs: 1 });
});

describe('backup restore without --at', () => {
  it('restores the newest snapshot of a lineage that has snapshots', async () => {
    mockFetch.mockResolvedValue({
      manifests: [
        { snapshotId: 'snap-old', streamId: 's', createdAt: '2020-01-01T00:00:00.000Z' },
        { snapshotId: 'snap-new', streamId: 's', createdAt: '2020-02-01T00:00:00.000Z' },
      ],
    });
    await run(ARGS);
    expect(fnCalls()).toContain('backup_restore');
    expect(fnCalls()).not.toContain('backup_pull');
    const call = mockExecute.mock.calls.find((c) => c[0].functionName === 'backup_restore')?.[0];
    expect(call.params.at).toBe('snap-new');
  });

  it('keeps the pull route when the lineage has no snapshots', async () => {
    mockFetch.mockResolvedValue({ manifests: [] });
    await run(ARGS);
    expect(fnCalls()).toContain('backup_pull');
    expect(fnCalls()).not.toContain('backup_restore');
  });

  it('keeps the pull route when the index cannot be read, and says so', async () => {
    mockFetch.mockRejectedValue(new Error('offline'));
    await run(ARGS);
    expect(fnCalls()).toContain('backup_pull');
    expect(outputService.warn).toHaveBeenCalledWith(
      'commands.backup.restore.snapshotIndexUnreadable:{"name":"m1:src","reason":"offline"}'
    );
  });

  it('says nothing about the index when it answered', async () => {
    mockFetch.mockResolvedValue({ manifests: [] });
    await run(ARGS);
    expect(outputService.warn).not.toHaveBeenCalledWith(
      expect.stringContaining('snapshotIndexUnreadable')
    );
  });
});

describe('backup restore --no-seed', () => {
  const snapshots = {
    manifests: [{ snapshotId: 'snap-new', streamId: 's', createdAt: '2020-02-01T00:00:00.000Z' }],
  };
  const restoreParams = () =>
    mockExecute.mock.calls.find((c) => c[0].functionName === 'backup_restore')?.[0].params;

  it('sends no_seed: true to backup_restore', async () => {
    mockFetch.mockResolvedValue(snapshots);
    await run([...ARGS, '--no-seed']);
    expect(restoreParams().no_seed).toBe(true);
  });

  it('sends no_seed: false without the flag', async () => {
    mockFetch.mockResolvedValue(snapshots);
    await run(ARGS);
    expect(restoreParams().no_seed).toBe(false);
  });

  it('refuses the flag before registering anything when there is no snapshot to restore', async () => {
    mockFetch.mockResolvedValue({ manifests: [] });
    await expect(run([...ARGS, '--no-seed'])).rejects.toThrow('noSeedNeedsSnapshot');
    expect(mockAddRepository).not.toHaveBeenCalled();
    expect(fnCalls()).toEqual([]);
  });
});
