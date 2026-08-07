/**
 * `repo push` / `repo pull` / `repo list --datastore` and the datastore they
 * address (#74).
 *
 * The subtle half of this class is that a transfer has TWO sides and only one of
 * them is the repo's recorded placement:
 *
 *   - the SOURCE of a push is the repo's own mount, and declaring nothing there
 *     sent renet hunting for the image under the machine's default;
 *   - the TARGET of a push is NOT. `resolveExtraMachines` builds `--dest-path`
 *     from the target machine's own vault record, so the image lands there, and
 *     the post-push `repository_up` must declare nothing — naming the source's
 *     mount would name a path that need not exist on that host at all.
 *
 * Both directions are pinned, because a fix that "threads the datastore
 * everywhere" breaks the second one while looking correct.
 */
import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const mockGetCurrent = vi.hoisted(() => vi.fn());

vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getCurrent: mockGetCurrent,
    getRepository: vi
      .fn()
      .mockResolvedValue({ repositoryGuid: 'guid-app', tag: 'latest', networkId: 100 }),
    ensureRepositoryNetworkId: vi.fn().mockResolvedValue(undefined),
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

const { registerRepoBackupCommands, postPushDeploy } = await import('../repo-backup.js');
const { handleRepoList } = await import('../repo-batch-utils.js');

const NAMED_MOUNT = '/mnt/rediacc-ds/tier1';

function placeOnNamedDatastore(): void {
  mockGetCurrent.mockResolvedValue({
    resources: { repositories: { app: { placement: { datastore: 'tier1' } } } },
  });
}

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

describe('repo push / pull declare the SOURCE datastore (#74)', () => {
  it('push reads the image from the repo own recorded mount', async () => {
    placeOnNamedDatastore();

    await run(['push', 'app', '--to', 'dst-machine']);

    expect(callFor('backup_push')?.datastore).toBe(NAMED_MOUNT);
  });

  it('pull writes into the repo own recorded mount', async () => {
    placeOnNamedDatastore();

    await run(['pull', 'app', '--from', 'src2']);

    expect(callFor('backup_pull')?.datastore).toBe(NAMED_MOUNT);
  });

  it('declares nothing when the repo lives on the machine default', async () => {
    await run(['push', 'app', '--to', 'dst-machine']);

    expect(callFor('backup_push')?.datastore).toBeUndefined();
  });

  // The control for the three above: the post-push deploy runs on the TARGET, and
  // it must NOT inherit the source's mount even though the same options object is
  // in scope carrying it.
  it('post-push deploy on the target declares nothing, even with a named source', async () => {
    placeOnNamedDatastore();

    await postPushDeploy('app', 'dst-machine', { datastore: NAMED_MOUNT });

    expect(callFor('repository_up')?.machineName).toBe('dst-machine');
    expect(callFor('repository_up')?.datastore).toBeUndefined();
  });
});

// `repo list --datastore <name>` resolved the datastore's HOLDER machine and then
// listed that machine's DEFAULT pool — dispatching at the right host and answering
// about the one place the operator did not ask about.
describe('repo list --datastore lists that datastore (#74)', () => {
  it('names the datastore mount it was asked about', async () => {
    await handleRepoList({ datastore: 'tier1' });

    expect(callFor('repository_list')?.machineName).toBe('ds-holder');
    expect(callFor('repository_list')?.datastore).toBe(NAMED_MOUNT);
  });

  it('stays on the machine default with no --datastore', async () => {
    await handleRepoList({ machine: 'src-machine' });

    expect(callFor('repository_list')?.datastore).toBeUndefined();
  });
});
