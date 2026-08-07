/**
 * `repo gc` and `repo fsck` must enumerate EVERY datastore the config places
 * repos on, not just the machine's default (#74).
 *
 * `repository_list` lists exactly one datastore — there is no `--all-datastores`
 * on it the way there is on the licence verbs (private/renet/cmd/renet/
 * license_scope.go:23 registers that flag for `repository license-status` and
 * `license-scan` only). Both commands compare that one listing against the WHOLE
 * config, so a repo family living on a named datastore was invisible: fsck
 * reported its refs as dangling, and gc could never collect its unreachable
 * commits. Asking each recorded mount in turn needs no new renet surface.
 */
import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const mockGetCurrent = vi.hoisted(() => vi.fn());
const mockListRepositories = vi.hoisted(() => vi.fn());

vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getCurrent: mockGetCurrent,
    listRepositories: mockListRepositories,
  },
}));

const mockExecute = vi.hoisted(() => vi.fn());
vi.mock('../../services/executor/executor-factory.js', () => ({
  getExecutor: () => ({ execute: mockExecute }),
}));

vi.mock('../repo-list-parser.js', () => ({
  parseRepositoryListOutput: (raw: string) => JSON.parse(raw),
}));

vi.mock('../../services/core/output.js', () => ({
  outputService: { info: vi.fn(), success: vi.fn(), warn: vi.fn(), error: vi.fn(), print: vi.fn() },
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

const { registerRepoMaintenanceCommands } = await import('../repo-maintenance.js');

const NAMED_MOUNT = '/mnt/rediacc-ds/tier1';
const ORPHAN_GUID = 'dddddddd-dddd-dddd-dddd-dddddddddddd';

/**
 * One family on a named datastore holding an unreachable, unmounted, immutable
 * commit — a gc candidate that only exists in that datastore's listing.
 */
function configWithNamedDatastore(): void {
  mockGetCurrent.mockResolvedValue({
    resources: { repositories: { app: { placement: { datastore: 'tier1' } } } },
  });
  mockListRepositories.mockResolvedValue([
    { name: 'app', config: { repositoryGuid: 'guid-app', tag: 'latest', head: 'guid-app' } },
    { name: 'app', config: { repositoryGuid: ORPHAN_GUID, tag: 'old', immutable: true } },
  ]);
}

async function run(argv: string[]): Promise<void> {
  const program = new Command();
  program.exitOverride();
  const repo = program.command('repo');
  // fsck lives under `repo admin` (§5.4); gc is a direct repo verb.
  const admin = repo.command('admin');
  registerRepoMaintenanceCommands(repo, admin);
  await program.parseAsync(['node', 'rdc', 'repo', ...argv]);
}

function listedDatastores(): (string | undefined)[] {
  return mockExecute.mock.calls
    .filter((c) => c[0].functionName === 'repository_list')
    .map((c) => c[0].datastore);
}

beforeEach(() => {
  vi.clearAllMocks();
  configWithNamedDatastore();
  mockExecute.mockImplementation(({ functionName, datastore }) => {
    if (functionName !== 'repository_list') return Promise.resolve({ success: true, stdout: '' });
    // The orphan exists ONLY in the named datastore. A run that enumerates just
    // the default finds nothing to collect.
    return Promise.resolve({
      success: true,
      stdout:
        datastore === NAMED_MOUNT
          ? JSON.stringify([{ name: ORPHAN_GUID, mounted: false }])
          : JSON.stringify([]),
    });
  });
});

describe('repo gc / fsck enumerate every recorded datastore (#74)', () => {
  it('lists the machine default AND each named mount', async () => {
    await run(['gc', '-m', 'm1']);

    expect(listedDatastores()).toEqual([undefined, NAMED_MOUNT]);
  });

  it('finds a gc candidate that lives only in the named datastore', async () => {
    await run(['gc', '-m', 'm1', '--apply']);

    const del = mockExecute.mock.calls.find((c) => c[0].functionName === 'repository_delete');
    expect(del, 'the orphan in the named datastore was never collected').toBeDefined();
    expect(del?.[0].params.repository).toBe(ORPHAN_GUID);
  });

  it('deletes the candidate from the datastore it was found in, not the default', async () => {
    await run(['gc', '-m', 'm1', '--apply']);

    const del = mockExecute.mock.calls.find((c) => c[0].functionName === 'repository_delete');
    expect(del?.[0].datastore).toBe(NAMED_MOUNT);
  });

  it('enumerates only the default when nothing is placed on a named datastore', async () => {
    mockGetCurrent.mockResolvedValue({ resources: { repositories: { app: {} } } });

    await run(['admin', 'fsck', '-m', 'm1']);

    expect(listedDatastores()).toEqual([undefined]);
  });
});
