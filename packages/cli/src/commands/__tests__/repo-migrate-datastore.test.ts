/**
 * `repo migrate` must declare the datastore its repo actually lives on (#74).
 *
 * renet resolves a repo's datastore from the MACHINE VAULT, never from the params
 * bag, so an execution that declares nothing runs against the machine's default
 * docker datastore. Migrate declared nothing on ANY of its five legs, so migrating
 * a repo out of a named datastore died on the first one:
 *
 *   Execution failed: stat /mnt/rediacc/repositories/<guid>: no such file or directory
 *
 * caught live by `./run.sh drill license --legs b` on 2026-08-04. These assertions
 * read the ExecuteOptions the command produced, not its output: a check on the
 * message would have passed against the broken build too.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const mockGetRepository = vi.hoisted(() => vi.fn());
const mockGetCurrent = vi.hoisted(() => vi.fn());
const mockGetLocalConfig = vi.hoisted(() => vi.fn());
const mockSetRepositoryPlacement = vi.hoisted(() => vi.fn());

vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getRepository: mockGetRepository,
    getCurrent: mockGetCurrent,
    getLocalConfig: mockGetLocalConfig,
    setRepositoryPlacement: mockSetRepositoryPlacement,
    ensureRepositoryNetworkId: vi.fn().mockResolvedValue(undefined),
  },
}));

const mockExecute = vi.hoisted(() => vi.fn());
vi.mock('../../services/executor/executor-factory.js', () => ({
  getExecutor: () => ({ execute: mockExecute }),
}));

vi.mock('../../services/repo/repo-key-deployment.js', () => ({
  deployRepoKeyIfNeeded: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('../repo-batch-utils.js', () => ({
  postRepoUpTasks: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('../repo-list-parser.js', () => ({
  parseRepositoryListOutput: () => [],
}));

vi.mock('../repo-push-stats.js', () => ({
  extractPushResult: () => undefined,
}));

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

vi.mock('../../services/core/output.js', () => ({
  outputService: { info: vi.fn(), success: vi.fn(), warn: vi.fn() },
}));

const { migrateRepo } = await import('../repo-migrate.js');

const NAMED_MOUNT = '/mnt/rediacc-ds/tier1';

/** Every ExecuteOptions the command produced, in call order. */
function calls(): { functionName: string; machineName: string; datastore?: string }[] {
  return mockExecute.mock.calls.map((c) => c[0]);
}

function callFor(functionName: string, machineName?: string) {
  return calls().find(
    (c) => c.functionName === functionName && (!machineName || c.machineName === machineName)
  );
}

/** A config placing the `app` family on the named datastore `tier1`. */
function placeOnNamedDatastore(): void {
  mockGetCurrent.mockResolvedValue({
    resources: {
      repositories: {
        app: { grand: 'latest', tags: { latest: {} }, placement: { datastore: 'tier1' } },
      },
    },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGetRepository.mockResolvedValue({
    repositoryGuid: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    tag: 'latest',
    networkId: 100,
  });
  mockGetLocalConfig.mockResolvedValue({
    machines: { 'src-machine': { ip: '10.0.0.1' }, 'dst-machine': { ip: '10.0.0.2' } },
  });
  mockSetRepositoryPlacement.mockResolvedValue(undefined);
  mockExecute.mockResolvedValue({ success: true, stdout: '', allSteps: [], steps: [] });
  mockGetCurrent.mockResolvedValue({
    resources: { repositories: { app: { grand: 'latest', tags: { latest: {} } } } },
  });
});

describe('repo migrate — source datastore declaration (#74)', () => {
  it('declares the named datastore on every SOURCE-side leg', async () => {
    placeOnNamedDatastore();

    await migrateRepo('app', { to: 'dst-machine', skipDns: true });

    // Phase 1 bulk push and phase 2 delta push both run on the source.
    const pushes = calls().filter((c) => c.functionName === 'backup_push');
    expect(pushes).toHaveLength(2);
    for (const push of pushes) {
      expect(push.machineName).toBe('src-machine');
      expect(push.datastore).toBe(NAMED_MOUNT);
    }

    // Phase 2 stops, then unmounts, the source.
    const downs = calls().filter((c) => c.functionName === 'repository_down');
    expect(downs).toHaveLength(2);
    for (const down of downs) {
      expect(down.machineName).toBe('src-machine');
      expect(down.datastore).toBe(NAMED_MOUNT);
    }
  });

  it('leaves the TARGET-side start on the machine default', async () => {
    placeOnNamedDatastore();

    await migrateRepo('app', { to: 'dst-machine', skipDns: true });

    // The push lands the image in the target's DEFAULT datastore, and placement is
    // rewritten to `{machine: to}` to match, so naming the source's mount here would
    // point renet at a path that does not exist on the target.
    const up = callFor('repository_up', 'dst-machine');
    expect(up).toBeDefined();
    expect(up?.datastore).toBeUndefined();
  });

  it('deletes the source image from the SOURCE datastore, after placement moved', async () => {
    placeOnNamedDatastore();
    // finalizeCutover rewrites placement BEFORE phase 3, so a derivation done at
    // delete time would answer for the target and hunt the image on the wrong mount.
    mockSetRepositoryPlacement.mockImplementation(() => {
      mockGetCurrent.mockResolvedValue({
        resources: {
          repositories: {
            app: { grand: 'latest', tags: { latest: {} }, placement: { machine: 'dst-machine' } },
          },
        },
      });
      // Stays thenable to match the mockResolvedValue baseline set in beforeEach.
      return Promise.resolve();
    });

    await migrateRepo('app', { to: 'dst-machine', skipDns: true });

    const del = callFor('repository_delete');
    expect(del).toBeDefined();
    expect(del?.machineName).toBe('src-machine');
    expect(del?.datastore).toBe(NAMED_MOUNT);
  });

  it('declares nothing when the repo lives on the machine default', async () => {
    await migrateRepo('app', { to: 'dst-machine', skipDns: true });

    expect(calls().length).toBeGreaterThan(0);
    for (const call of calls()) {
      expect(call.datastore).toBeUndefined();
    }
  });
});
