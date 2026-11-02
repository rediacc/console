/** `--bwlimit` on push/pull: renet parses bytes/second or a rate (`12.5M`, `100Mbps`); the CLI refuses a bad one before any SSH and carries a good one through untouched. */
import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const mockGetCurrent = vi.hoisted(() => vi.fn());

vi.mock('../../services/config/network-id-discovery.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../services/config/network-id-discovery.js')>()),
  ensureRepositoryNetworkId: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getCurrent: mockGetCurrent,
    getRepository: vi
      .fn()
      .mockResolvedValue({ repositoryGuid: 'guid-app', tag: 'latest', networkId: 100 }),
    listRepositories: vi.fn().mockResolvedValue([]),
  },
}));

const mockExecute = vi.hoisted(() => vi.fn());
vi.mock('../../services/executor/executor-factory.js', () => ({
  getExecutor: () => ({ execute: mockExecute }),
}));

vi.mock('../../utils/repo-target.js', () => ({
  resolveRepoRef: () =>
    Promise.resolve({ name: 'app', repoKey: 'app', machineName: 'src-machine', tag: 'latest' }),
  resolveRepoTarget: () => Promise.resolve({ machineName: 'src-machine' }),
}));
vi.mock('../../utils/remote-resolve.js', () => ({
  resolveRemoteName: (name: string) => Promise.resolve({ type: 'machine', name }),
}));
vi.mock('../../services/account/subscription-auth.js', () => ({
  getSubscriptionTokenState: () => ({ kind: 'ready' }),
}));
vi.mock('../../services/config/config-cluster-ops.js', () => ({
  resolveControlNode: (n: string) => Promise.resolve(n),
}));
vi.mock('../../services/repo/repo-key-deployment.js', () => ({
  deployRepoKeyIfNeeded: vi.fn().mockResolvedValue(undefined),
  deployAllRepoKeys: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('../function-params.js', () => ({
  coerceCliParams: (_f: string, p: Record<string, unknown>) => p,
  validateFunctionParams: vi.fn(),
  parseParamOptions: () => ({}),
}));
vi.mock('../repo-delta.js', () => ({
  applyPullDeltaParams: vi.fn(),
  applyPushDeltaParams: vi.fn(),
  finalizePush: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('../repo-push-stats.js', () => ({
  reportPushStats: vi.fn(),
  extractPushResult: () => undefined,
}));
vi.mock('../../utils/command-policy.js', () => ({
  assertCommandPolicy: vi.fn().mockResolvedValue(undefined),
  CMD: new Proxy({}, { get: (_t, p) => String(p) }),
}));
vi.mock('../../utils/local-execution-failures.js', () => ({
  renderLocalExecutionFailure: vi.fn(),
}));
// repo-batch-utils extras, for the `repo list --datastore` half.
vi.mock('../../services/config/config-datastores.js', () => ({
  getDatastore: () => Promise.resolve({ cluster: undefined }),
  requireDatastoreHost: () => Promise.resolve('ds-holder'),
}));
vi.mock('../../services/telemetry/telemetry.js', () => ({
  telemetryService: { recordCommand: vi.fn(), flush: vi.fn() },
}));
vi.mock('../../utils/guid-resolver.js', () => ({
  createRepoNameResolver: () => (g: string) => g,
  loadGuidMap: () => Promise.resolve(new Map()),
}));
vi.mock('../repo-list-parser.js', () => ({ parseRepositoryListOutput: () => [] }));
vi.mock('@rediacc/shared/services/machine', () => ({ getMachineContainers: vi.fn() }));
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

const { registerRepoBackupCommands } = await import('../repo-backup.js');

async function run(argv: string[]): Promise<void> {
  const program = new Command();
  program.exitOverride();
  const repo = program.command('repo');
  registerRepoBackupCommands(repo);
  await program.parseAsync(['node', 'rdc', 'repo', ...argv]);
}

function callFor(fn: string) {
  return mockExecute.mock.calls.find((c) => c[0].functionName === fn)?.[0];
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGetCurrent.mockResolvedValue({ resources: { repositories: { app: {} } } });
  mockExecute.mockResolvedValue({ success: true, stdout: '', durationMs: 1 });
});

describe('repo push/pull --bwlimit', () => {
  it('push carries 100Mbps through to backup_push', async () => {
    await run(['push', 'app', '--to', 'dst-machine', '--bwlimit', '100Mbps']);
    expect(callFor('backup_push')?.params.bwlimit).toBe('100Mbps');
  });

  it('pull carries 12.5M through to backup_pull', async () => {
    await run(['pull', 'app', '--from', 'src2', '--bwlimit', '12.5M']);
    expect(callFor('backup_pull')?.params.bwlimit).toBe('12.5M');
  });

  it('push refuses a megabit-or-megabyte guess before any execution', async () => {
    await expect(run(['push', 'app', '--to', 'dst-machine', '--bwlimit', '100Mb'])).rejects.toThrow(
      /bwlimitInvalid|unconvertible/i
    );
    expect(mockExecute).not.toHaveBeenCalled();
  });

  it('push refuses a blank --bwlimit instead of ignoring it', async () => {
    await expect(run(['push', 'app', '--to', 'dst-machine', '--bwlimit', ''])).rejects.toThrow(
      /bwlimitInvalid/
    );
    await expect(run(['pull', 'app', '--from', 'src2', '--bwlimit', '  '])).rejects.toThrow(
      /bwlimitInvalid/
    );
    expect(mockExecute).not.toHaveBeenCalled();
  });

  it('push without --bwlimit sends none', async () => {
    await run(['push', 'app', '--to', 'dst-machine']);
    expect(callFor('backup_push')?.params.bwlimit).toBeUndefined();
  });
});
