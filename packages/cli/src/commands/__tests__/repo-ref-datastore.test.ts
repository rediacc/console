/**
 * The repo verbs must declare the datastore their ref is RECORDED on (#74).
 *
 * renet resolves a repo's image from the MACHINE VAULT, never from the params
 * bag, so a dispatch that declares nothing runs against the machine's default
 * docker datastore. Every verb outside `executeRepoFunction` declared nothing,
 * so on a repo living in a named datastore they addressed a path the repo has
 * never been at — `stat /mnt/rediacc/repositories/<guid>: no such file or
 * directory` where the verb errored at all, and silently wrong answers where it
 * did not (`repo log` on an empty listing looks like "no commits").
 *
 * One representative per fix shape rather than one per site: these four cover a
 * read verb, a container verb, a mutating branching verb, and the ref-vs-machine
 * split that `trim` and `policy` share. The assertions read the ExecuteOptions
 * the command produced — a check on output would pass against the broken build.
 */
import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const mockGetCurrent = vi.hoisted(() => vi.fn());
const mockGetRepository = vi.hoisted(() => vi.fn());

vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getCurrent: mockGetCurrent,
    getRepository: mockGetRepository,
    ensureRepositoryNetworkId: vi.fn().mockResolvedValue(undefined),
    getRepositoryKey: (ref: string) => Promise.resolve(ref),
    setRepositoryState: vi.fn().mockResolvedValue(undefined),
    addRepository: vi.fn().mockResolvedValue(undefined),
    listRepositories: vi.fn().mockResolvedValue([]),
  },
}));

const mockExecute = vi.hoisted(() => vi.fn());
vi.mock('../../services/executor/executor-factory.js', () => ({
  getExecutor: () => ({ execute: mockExecute }),
}));

vi.mock('../../utils/repo-target.js', () => ({
  resolveRepoRef: () =>
    Promise.resolve({ name: 'app', repoKey: 'app', machineName: 'm1', tag: 'latest' }),
  resolveRepoTarget: () => Promise.resolve({ machineName: 'm1' }),
  resolveRepoRefLocal: () =>
    Promise.resolve({ name: 'app', repoKey: 'app', machineName: 'm1', tag: 'latest' }),
}));

vi.mock('../../utils/command-policy.js', () => ({
  assertCommandPolicy: vi.fn().mockResolvedValue(undefined),
  CMD: new Proxy({}, { get: (_t, p) => String(p) }),
}));

vi.mock('../_validate.js', () => ({ assertMachineExists: vi.fn().mockResolvedValue(undefined) }));
vi.mock('../repo-fork.js', () => ({ handleForkAction: vi.fn().mockResolvedValue(undefined) }));
vi.mock('../datastore-prune-parser.js', () => ({ parseDatastorePruneOutput: () => ({}) }));
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

const { registerRepoDiffCommand } = await import('../repo-diff.js');
const { registerRepoContainerCommands } = await import('../repo-container.js');
const { registerRepoBranchingCommands } = await import('../repo-branching.js');
const { registerRepoTrimCommand } = await import('../repo-trim.js');

const NAMED_MOUNT = '/mnt/rediacc-ds/tier1';

/** A config whose `app` family is placed on the named datastore `tier1`. */
function placeOnNamedDatastore(): void {
  mockGetCurrent.mockResolvedValue({
    resources: { repositories: { app: { placement: { datastore: 'tier1' } } } },
  });
}

async function run(argv: string[]): Promise<void> {
  const program = new Command();
  program.exitOverride();
  const repo = program.command('repo');
  registerRepoDiffCommand(repo);
  registerRepoContainerCommands(repo);
  registerRepoBranchingCommands(repo);
  registerRepoTrimCommand(repo);
  await program.parseAsync(['node', 'rdc', 'repo', ...argv]);
}

/** The datastore declared on the last dispatch. */
function lastDatastore(): string | undefined {
  const calls = mockExecute.mock.calls;
  return calls[calls.length - 1][0].datastore;
}

beforeEach(() => {
  vi.clearAllMocks();
  // Default: the repo lives on the machine's implicit default datastore.
  mockGetCurrent.mockResolvedValue({ resources: { repositories: { app: {} } } });
  // Keyed on the ref so `diff` gets two distinct GUIDs (it refuses base===target).
  mockGetRepository.mockImplementation((ref: string) =>
    Promise.resolve({
      repositoryGuid: `guid-${ref}`,
      tag: 'latest',
      networkId: 100,
      headCommit: `commit-${ref}`,
    })
  );
  mockExecute.mockResolvedValue({ success: true, stdout: '{"entries":[]}', durationMs: 1 });
});

describe('repo verbs declare the recorded datastore (#74)', () => {
  it.each([
    ['diff', ['diff', 'app', '--base', 'previous'], 'repository_diff'],
    ['logs', ['logs', 'app'], 'container_logs'],
    ['commit', ['commit', 'app', '--message', 'wip'], 'repository_commit'],
    ['log', ['log', 'app'], 'repository_log'],
    ['trim (ref arm)', ['trim', 'app'], 'repository_trim'],
  ])('%s dispatches against the named datastore', async (_label, argv, fn) => {
    placeOnNamedDatastore();

    await run(argv);

    const call = mockExecute.mock.calls.find((c) => c[0].functionName === fn);
    expect(call, `no ${fn} dispatch`).toBeDefined();
    expect(call?.[0].datastore).toBe(NAMED_MOUNT);
  });

  it('declares nothing when the repo lives on the machine default', async () => {
    await run(['logs', 'app']);

    expect(mockExecute).toHaveBeenCalled();
    expect(lastDatastore()).toBeUndefined();
  });

  // The machine-wide arm of trim (and, identically, policy) addresses the
  // machine's OWN default datastore by definition. Declaring the repo's mount
  // there would be wrong, not merely unnecessary — which is why the ref arm and
  // the machine arm are pinned separately.
  it('trim --machine stays on the machine default even when a repo is placed elsewhere', async () => {
    placeOnNamedDatastore();

    await run(['trim', '-m', 'm1']);

    const call = mockExecute.mock.calls.find((c) => c[0].functionName === 'repository_trim');
    expect(call).toBeDefined();
    expect(call?.[0].datastore).toBeUndefined();
  });
});
