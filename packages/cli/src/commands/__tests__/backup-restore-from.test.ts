/**
 * `rdc backup restore --from <storeId>` and the store pick (multi-target C3).
 *
 * A lineage can hold a snapshot in several stores. Without `--from` the restore reads the account's best-ranked store
 * and falls back to the next one when a store fails for its own reasons (a 5xx, a refused grant); a missing snapshot
 * is the snapshot's own fault and is never retried elsewhere; an explicit `--from` never falls back. Each case drives
 * the real command and reads the `backup_restore` calls the executor received.
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

const mockPick = vi.hoisted(() => vi.fn());
vi.mock('../../services/backup/backup-store-pick.js', async () => {
  const actual = await vi.importActual<typeof import('../../services/backup/backup-store-pick.js')>(
    '../../services/backup/backup-store-pick.js'
  );
  return { ...actual, pickStores: mockPick };
});

const RANKED = { stores: ['eu-west', 'home'], explicit: false };
const ARGS = [
  'restore',
  'observability:lab@obs-lab',
  '--as',
  'obsram',
  '-m',
  'obs-lab',
  '--any-stream',
] as const;

/** What the executor answers for `backup_restore`, one entry per call; the last repeats. */
const restoreAnswers = vi.hoisted(() => [] as Record<string, unknown>[]);

beforeEach(() => {
  vi.clearAllMocks();
  restoreAnswers.length = 0;
  for (const key of Object.keys(repos)) delete repos[key];
  repos.observability = { repositoryGuid: GRAND_GUID, tag: 'latest', credential: 'c' };
  repos['observability:lab'] = {
    repositoryGuid: FORK_GUID,
    grandGuid: GRAND_GUID,
    tag: 'lab',
    credential: 'c',
  };
  mockGetRepository.mockImplementation((ref: string) => Promise.resolve(repos[ref]));
  mockAddRepository.mockResolvedValue(undefined);
  mockRemoveRepository.mockResolvedValue(undefined);
  mockDeployKey.mockResolvedValue(undefined);
  mockSftpExec.mockImplementation(() => Promise.resolve('absent\n'));
  mockPick.mockImplementation((_lineage: string, from?: string) =>
    Promise.resolve(from === undefined ? RANKED : { stores: [from], explicit: true })
  );
  mockFetch.mockImplementation((path: string) =>
    Promise.resolve(
      path.includes('/snapshots/resolve')
        ? { snapshotId: 'snap-new', streamId: 's', createdAt: '2026-11-05T00:00:00.000Z' }
        : { manifests: [{ snapshotId: 'snap-new', streamId: 's', createdAt: '2026-11-05' }] }
    )
  );
  mockExecute.mockImplementation((opts: { functionName: string }) => {
    if (opts.functionName !== 'backup_restore') {
      return Promise.resolve({ success: true, stdout: '', durationMs: 1 });
    }
    const answer = restoreAnswers.length > 1 ? restoreAnswers.shift() : restoreAnswers[0];
    return Promise.resolve(answer ?? { success: true, stdout: '', durationMs: 1 });
  });
});

const OK = { success: true, exitCode: 0, stdout: '', durationMs: 1 };
const failed = (error: string) => ({
  success: false,
  exitCode: 1,
  error,
  stdout: '',
  durationMs: 1,
});
const stores = () => calls('backup_restore').map((c) => c[0].params.store);

describe('backup restore --from', () => {
  it('reads the named store and passes it to renet', async () => {
    restoreAnswers.push(OK);
    await run([...ARGS, '--from', 'eu-west']);
    expect(mockPick).toHaveBeenCalledWith(GRAND_GUID, 'eu-west');
    expect(stores()).toEqual(['eu-west']);
  });

  it('never falls back from a named store, even on a 5xx', async () => {
    restoreAnswers.push(failed('HTTP 502 bad gateway'));
    await expect(run([...ARGS, '--from', 'eu-west'])).rejects.toThrow('process exited');
    expect(stores()).toEqual(['eu-west']);
    expect(outputService.warn).not.toHaveBeenCalledWith(
      expect.stringContaining('commands.backup.restore.storeFallback')
    );
  });

  it('is refused on the pull route, which has no store', async () => {
    mockSftpExec.mockImplementation(() => Promise.resolve('present\n'));
    await expect(run([...ARGS, '--from', 'eu-west'])).rejects.toThrow(
      'commands.backup.restore.fromNeedsSnapshot'
    );
    expect(calls('backup_pull')).toHaveLength(0);
  });
});

describe('backup restore default pick', () => {
  it('reads the best-ranked store and says which one served', async () => {
    restoreAnswers.push(OK);
    await run([...ARGS]);
    expect(stores()).toEqual(['eu-west']);
    expect(outputService.info).toHaveBeenCalledWith(
      `commands.backup.restore.storeServed:${JSON.stringify({ store: 'eu-west' })}`
    );
  });

  it('omits the store param for home', async () => {
    mockPick.mockResolvedValue({ stores: ['home'], explicit: false });
    restoreAnswers.push(OK);
    await run([...ARGS]);
    expect(calls('backup_restore')[0][0].params).not.toHaveProperty('store');
  });

  it('falls back to the next store when the first answers a 5xx, and registers the target again', async () => {
    restoreAnswers.push(failed('HTTP 502 bad gateway'), OK);
    await run([...ARGS]);
    expect(stores()).toEqual(['eu-west', undefined]);
    expect(mockAddRepository).toHaveBeenCalledTimes(2);
    expect(outputService.warn).toHaveBeenCalledWith(
      `commands.backup.restore.storeFallback:${JSON.stringify({ failed: 'eu-west', next: 'home' })}`
    );
    expect(outputService.info).toHaveBeenCalledWith(
      `commands.backup.restore.storeServed:${JSON.stringify({ store: 'home' })}`
    );
  });

  it('does not fall back when the snapshot itself is missing', async () => {
    restoreAnswers.push(failed('snapshot snap-new not found in the manifest index'));
    await expect(run([...ARGS])).rejects.toThrow('process exited');
    expect(stores()).toEqual(['eu-west']);
  });

  it('renders the last store failure when every store fails', async () => {
    restoreAnswers.push(failed('HTTP 503 service unavailable'));
    await expect(run([...ARGS])).rejects.toThrow('process exited');
    expect(stores()).toEqual(['eu-west', undefined]);
  });
});

describe('backup restore --at <time> resolves inside each store (item #acd03b8a)', () => {
  const AT = '2026-11-04T00:00:00Z';
  const IN_STORE: Record<string, string | undefined> = {
    'eu-west': 'snap-eu',
    home: 'snap-home',
  };
  const storeOf = (path: string) => new URL(path, 'https://x').searchParams.get('storeId');
  const resolvedIn = () =>
    mockFetch.mock.calls
      .map((c) => c[0] as string)
      .filter((p) => p.includes('/snapshots/resolve'))
      .map(storeOf);
  const restored = () => calls('backup_restore').map((c) => c[0].params.at);

  function holding(table: Record<string, string | undefined>): void {
    mockFetch.mockImplementation((path: string) => {
      if (!path.includes('/snapshots/resolve')) return Promise.resolve({ manifests: [] });
      const snapshotId = table[storeOf(path) ?? ''];
      return snapshotId
        ? Promise.resolve({ snapshotId, streamId: 's', createdAt: '2026-11-03T00:00:00.000Z' })
        : Promise.reject(Object.assign(new Error('not found'), { status: 404 }));
    });
  }

  it('with --from, resolves inside that store only', async () => {
    holding(IN_STORE);
    restoreAnswers.push(OK);
    await run([...ARGS, '--at', AT, '--from', 'eu-west']);
    expect(resolvedIn()).toEqual(['eu-west']);
    expect(restored()).toEqual(['snap-eu']);
  });

  it('on a fallback, restores the snapshot the next store resolves the time to', async () => {
    holding(IN_STORE);
    restoreAnswers.push(failed('HTTP 502 bad gateway'), OK);
    await run([...ARGS, '--at', AT]);
    expect(resolvedIn()).toEqual(['eu-west', 'home']);
    expect(restored()).toEqual(['snap-eu', 'snap-home']);
  });

  it('passes over a store holding nothing at that time, registering nothing for it', async () => {
    holding({ home: 'snap-home' });
    restoreAnswers.push(OK);
    await run([...ARGS, '--at', AT]);
    expect(stores()).toEqual([undefined]);
    expect(restored()).toEqual(['snap-home']);
    expect(mockAddRepository).toHaveBeenCalledTimes(1);
  });

  it('refuses a --from store holding nothing at that time before registering anything', async () => {
    holding({ home: 'snap-home' });
    await expect(run([...ARGS, '--at', AT, '--from', 'eu-west'])).rejects.toThrow(
      'commands.backup.restore.atNoSnapshot'
    );
    expect(mockAddRepository).not.toHaveBeenCalled();
    expect(calls('backup_restore')).toHaveLength(0);
  });

  it('renders a store failure when no later store holds the time, rather than deferring it', async () => {
    holding({ 'eu-west': 'snap-eu' });
    restoreAnswers.push(failed('HTTP 502 bad gateway'));
    await expect(run([...ARGS, '--at', AT])).rejects.toThrow('process exited');
    expect(stores()).toEqual(['eu-west']);
    expect(mockRenderFailure).toHaveBeenCalled();
  });
});
