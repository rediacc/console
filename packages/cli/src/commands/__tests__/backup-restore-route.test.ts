/**
 * `rdc backup restore <name>:<tag>@<machine>` from a `repo push` artifact (live 2026-11-05).
 *
 * `rdc repo push observability:lab@hostinger --to obs-lab` left the lab fork's image on obs-lab
 * under the fork's GUID. `rdc backup restore observability:lab@obs-lab --as obsram -m obs-lab`
 * then:
 *  - looked the source up by its bare NAME, which resolves to the family's grand, so every GUID
 *    after that (the pull's `src`, the stream probe's repository) was the grand's;
 *  - routed to the chunk store because the LINEAGE (shared by the whole family) had snapshots
 *    taken on another machine, although obs-lab held the very image the ref names;
 *  - ran the stream probe (`backup_verify`) for the grand on obs-lab, which has no backup there,
 *    and rendered that failure as a command failure: the record stayed in captured stdout, and
 *    in agent mode the rendering exits the process;
 *  - had already registered the target, so the exit left a config entry with no image.
 *
 * Each `it` below fails on that code.
 */
import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const GRAND_GUID = '34dc6da3-b844-4b36-bb00-00df42df8f03';
const FORK_GUID = '5e587ce8-c437-4bd4-b5e6-cbaa48d311b6';

const repos = vi.hoisted(
  () =>
    ({}) as Record<
      string,
      { repositoryGuid: string; grandGuid?: string; tag: string; credential: string }
    >
);
const mockAddRepository = vi.hoisted(() => vi.fn());
const mockRemoveRepository = vi.hoisted(() => vi.fn());
const mockGetRepository = vi.hoisted(() => vi.fn());

vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getCurrent: vi.fn().mockResolvedValue({ state: {}, resources: { repositories: {} } }),
    addRepository: mockAddRepository,
    removeRepository: mockRemoveRepository,
    allocateNetworkId: vi.fn().mockResolvedValue(4242),
    getRepository: mockGetRepository,
    listRepositories: vi.fn().mockResolvedValue([]),
  },
}));
vi.mock('../../services/config/network-id-discovery.js', () => ({
  ensureRepositoryNetworkId: vi.fn().mockResolvedValue(4242),
  targetFloor: vi.fn().mockResolvedValue(undefined),
  parseNetworkIdConflict: vi.fn(),
  networkIdConflictMessage: vi.fn(),
}));

const mockExecute = vi.hoisted(() => vi.fn());
vi.mock('../../services/executor/executor-factory.js', () => ({
  getExecutor: () => ({ execute: mockExecute }),
}));
const mockFetch = vi.hoisted(() => vi.fn());
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
vi.mock('../../utils/remote-resolve.js', () => ({
  resolveRemoteName: (name: string) => Promise.resolve({ type: 'machine', name }),
}));
vi.mock('../repo-backup-list.js', () => ({ renderBackupList: vi.fn() }));

/** What `test -e repositories/<guid>` answers on the place machine. */
const imageProbe = vi.hoisted(() => ({ answer: 'absent' as string }));
const mockSftpExec = vi.hoisted(() => vi.fn());
const mockRelease = vi.hoisted(() => vi.fn());
vi.mock('../../services/machine/machine-connection.js', () => ({
  machineConnections: {
    acquire: vi.fn().mockImplementation(() =>
      Promise.resolve({
        sftp: { exec: mockSftpExec },
        machine: { ip: '10.0.0.1', user: 'u', datastore: WK_DATASTORE_PATH },
        sshPrivateKey: 'k',
        release: mockRelease,
      })
    ),
  },
}));
vi.mock('../../services/executor/repo-license-context.js', () => ({
  resolveRestoreLicenseContext: vi.fn().mockResolvedValue({
    repositoryGuid: 'g',
    grandGuid: 'g',
    kind: 'fork',
    datastoreMount: WK_DATASTORE_PATH,
  }),
  restoreLicenseAlreadyInstalled: vi.fn().mockResolvedValue(true),
}));
const mockDeployKey = vi.hoisted(() => vi.fn());
vi.mock('../../services/repo/repo-key-deployment.js', () => ({
  deployRepoKeyIfNeeded: mockDeployKey,
}));
vi.mock('../../utils/agent-guard.js', () => ({
  assertAgentRepoCreate: vi.fn().mockResolvedValue(undefined),
  isAgentEnvironment: () => true,
}));
vi.mock('../../utils/command-policy.js', () => ({
  assertCommandPolicy: vi.fn().mockResolvedValue(undefined),
  CMD: new Proxy({}, { get: (_t, p) => String(p) }),
}));
vi.mock('../_validate.js', () => ({ assertMachineExists: vi.fn().mockResolvedValue(undefined) }));
vi.mock('../backup-ops.js', () => ({ registerBackupOpsCommands: vi.fn() }));
vi.mock('../backup-strategy.js', () => ({ registerBackupStrategyCommands: vi.fn() }));
// In agent mode the real rendering exits the process; nothing after it runs.
const mockRenderFailure = vi.hoisted(() =>
  vi.fn(() => {
    throw new Error('process exited (agent mode)');
  })
);
vi.mock('../../utils/local-execution-failures.js', () => ({
  renderLocalExecutionFailure: mockRenderFailure,
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: vi.fn(),
    success: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    print: vi.fn(),
    setTimelineRendered: vi.fn(),
  },
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

const calls = (fn: string) => mockExecute.mock.calls.filter((c) => c[0].functionName === fn);
const ARGS = ['restore', 'observability:lab@obs-lab', '--as', 'obsram', '-m', 'obs-lab'] as const;
const NO_BACKUP_RECORD = JSON.stringify({
  guid: GRAND_GUID,
  level: 'spot',
  status: 'no-backup',
  reason: 'no committed snapshot recorded on this machine',
});

beforeEach(() => {
  vi.clearAllMocks();
  for (const key of Object.keys(repos)) delete repos[key];
  // The bare name resolves to the grand, as configService.getRepository does for a family.
  repos.observability = { repositoryGuid: GRAND_GUID, tag: 'latest', credential: 'c' };
  repos['observability:lab'] = {
    repositoryGuid: FORK_GUID,
    grandGuid: GRAND_GUID,
    tag: 'lab',
    credential: 'c',
  };
  mockGetRepository.mockImplementation((ref: string) => Promise.resolve(repos[ref]));
  mockAddRepository.mockImplementation((key: string, record: { repositoryGuid: string }) => {
    repos[key.replace(/:latest$/, '')] = { ...record, tag: 'latest', credential: 'c' };
    return Promise.resolve();
  });
  mockRemoveRepository.mockResolvedValue(undefined);
  mockDeployKey.mockResolvedValue(undefined);
  imageProbe.answer = 'absent';
  mockSftpExec.mockImplementation(() => Promise.resolve(`${imageProbe.answer}\n`));
  // The grand is backed up elsewhere, so the LINEAGE has snapshots.
  mockFetch.mockImplementation((path: string) =>
    Promise.resolve(
      path.includes('/snapshots/resolve')
        ? { snapshotId: 'snap-new', streamId: 's', createdAt: '2026-11-05T00:00:00.000Z' }
        : { manifests: [{ snapshotId: 'snap-new', streamId: 's', createdAt: '2026-11-05' }] }
    )
  );
  mockExecute.mockImplementation((opts: { functionName: string }) =>
    Promise.resolve(
      opts.functionName === 'backup_verify'
        ? { success: false, exitCode: 1, stdout: `${NO_BACKUP_RECORD}\n`, durationMs: 1 }
        : { success: true, stdout: '', durationMs: 1 }
    )
  );
});

describe('backup restore from a repo push artifact', () => {
  it('pulls the image the place machine holds, under the FORK guid, with no chunk-store probe', async () => {
    imageProbe.answer = 'present';
    await run(ARGS);
    expect(calls('backup_verify')).toHaveLength(0);
    expect(calls('backup_restore')).toHaveLength(0);
    expect(calls('backup_pull')).toHaveLength(1);
    expect(calls('backup_pull')[0][0].params.src).toBe(FORK_GUID);
    expect(calls('backup_pull')[0][0].params.from).toBe('obs-lab');
    // The probe asked about the fork's image, not the grand's.
    expect(String(mockSftpExec.mock.calls[0][0])).toContain(`repositories/${FORK_GUID}`);
    expect(mockRelease).toHaveBeenCalled();
  });

  it('keeps the tag when it resolves the source', async () => {
    imageProbe.answer = 'present';
    await run(ARGS);
    expect(mockGetRepository).toHaveBeenCalledWith('observability:lab');
    expect(mockGetRepository).not.toHaveBeenCalledWith('observability');
  });

  it('a lineage with snapshots still restores the newest one when the place has no image', async () => {
    await run([...ARGS, '--any-stream']);
    expect(calls('backup_pull')).toHaveLength(0);
    expect(calls('backup_restore')).toHaveLength(1);
    expect(calls('backup_restore')[0][0].params.at).toBe('snap-new');
  });

  it('an unanswerable probe falls back to the index decision', async () => {
    imageProbe.answer = 'sudo: a password is required';
    await run([...ARGS, '--any-stream']);
    expect(calls('backup_restore')).toHaveLength(1);
  });
});

describe('backup restore stream probe failure', () => {
  it('probes the tagged source, prints the verify record, refuses, and registers nothing', async () => {
    await expect(run(ARGS)).rejects.toThrow('commands.backup.restore.streamUnknown');
    expect(calls('backup_verify')).toHaveLength(1);
    expect(calls('backup_verify')[0][0].params.repository).toBe('observability:lab');
    // The record reaches the operator instead of renet's "see records above".
    expect(outputService.warn).toHaveBeenCalledWith(expect.stringContaining('"no-backup"'));
    // Not rendered as a command failure, which exits the process in agent mode.
    expect(mockRenderFailure).not.toHaveBeenCalled();
    // Refused before the target was registered: no orphan config entry.
    expect(mockAddRepository).not.toHaveBeenCalled();
    expect(repos.obsram).toBeUndefined();
    expect(calls('backup_restore')).toHaveLength(0);
  });
});

describe('backup restore rollback before the job starts', () => {
  it('drops the chunk-route registration when the key deploy fails', async () => {
    mockDeployKey.mockRejectedValue(new Error('key deploy failed'));
    await expect(run([...ARGS, '--any-stream'])).rejects.toThrow('key deploy failed');
    expect(mockAddRepository).toHaveBeenCalledTimes(1);
    expect(mockRemoveRepository).toHaveBeenCalledWith('obsram:latest');
    expect(calls('backup_restore')).toHaveLength(0);
  });
});
