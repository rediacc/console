import { Command } from 'commander';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const ORPHAN = '260f0a05-1111-4222-8333-444455556666';
const KNOWN = 'b9521afd-0cbd-4481-92ed-f798268a69dd';

const mocks = vi.hoisted(() => ({
  format: 'json' as 'json' | 'table' | 'yaml',
  fail: false,
  repos: [] as Record<string, unknown>[],
  deletes: [] as string[],
}));

vi.mock('../../utils/errors.js', () => ({
  getOutputFormat: () => mocks.format,
  handleError: (error: unknown) => {
    throw error;
  },
}));
vi.mock('../_validate.js', () => ({ assertMachineExists: async () => undefined }));
vi.mock('../../services/executor/executor-factory.js', () => ({
  getExecutor: () => ({
    execute: (req: { functionName: string; params?: { repository?: string } }) => {
      if (req.functionName === 'repository_delete') {
        mocks.deletes.push(String(req.params?.repository));
      }
      if (mocks.fail) return Promise.resolve({ success: false, error: 'boom' });
      if (req.functionName === 'repository_prune') {
        return Promise.resolve({
          success: true,
          stdout: JSON.stringify({ stale_locks: null, auth_keys: [] }),
        });
      }
      return Promise.resolve({
        success: true,
        stdout: 'Nothing to prune. All networks have repositories.',
      });
    },
  }),
}));
vi.mock('../../utils/local-execution-failures.js', () => ({
  renderLocalExecutionFailure: vi.fn(),
}));
vi.mock('../../services/machine/machine-status.js', () => ({
  fetchMachineStatus: async () => ({ repositories: mocks.repos }),
}));
vi.mock('@rediacc/shared/renet-contract/data/list-types.generated', () => ({
  getRepositories: () => [{ name: KNOWN }, { name: ORPHAN }],
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getCurrent: async () => ({}),
    getCurrentName: () => 'dev',
    listRepositories: async () => [{ name: 'base', config: { repositoryGuid: KNOWN } }],
    listArchivedRepositories: async () => [],
    purgeExpiredArchives: async () => [],
  },
}));
vi.mock('../../adapters/config-file-storage.js', () => ({
  configFileStorage: { list: async () => ['dev'], load: async () => ({}) },
}));
vi.mock('../../remote/vscode/index.js', () => ({
  listSSHConfigEntries: () => [],
  removePersistedKeys: vi.fn(),
  removeSSHConfigEntry: vi.fn(),
}));

import { registerPruneCommand } from '../machine/prune.js';

let stdout = '';

beforeEach(() => {
  stdout = '';
  mocks.fail = false;
  mocks.repos = [];
  mocks.deletes = [];
  vi.spyOn(process.stdout, 'write').mockImplementation((chunk: string | Uint8Array) => {
    stdout += String(chunk);
    return true;
  });
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
});
afterEach(() => vi.restoreAllMocks());

async function run(...args: string[]): Promise<void> {
  const machine = new Command();
  registerPruneCommand(machine);
  await machine.parseAsync(['prune', 'ops-worker', ...args], { from: 'user' });
}

describe('machine prune output', () => {
  it('emits exactly one json document holding every phase', async () => {
    mocks.format = 'json';
    await run('--orphaned-repos', '--dry-run');
    const doc = JSON.parse(stdout);
    expect(doc.data.datastore).toEqual({ stale_locks: null, auth_keys: [] });
    expect(doc.data.units).toContain('Nothing to prune');
    expect(doc.data.dry_run).toBe(true);
    expect(doc.data.orphaned_repos).toEqual([{ guid: ORPHAN, reason: 'not in any config' }]);
    expect(doc.data.protected_repos).toEqual([{ guid: KNOWN, reason: 'active in dev' }]);
  });

  it('carries dry_run, orphaned_repos and protected_repos without --orphaned-repos', async () => {
    mocks.format = 'json';
    await run('--dry-run');
    const doc = JSON.parse(stdout);
    expect(doc.data.dry_run).toBe(true);
    expect(doc.data.orphaned_repos).toEqual([]);
    expect(doc.data.protected_repos).toEqual([]);
  });

  it('prints no data document in table output', async () => {
    mocks.format = 'table';
    await run('--orphaned-repos', '--dry-run');
    expect(stdout).not.toContain('orphaned_repos');
  });

  it('prints no data document when a phase failed', async () => {
    mocks.format = 'json';
    mocks.fail = true;
    await run('--orphaned-repos', '--dry-run');
    expect(stdout).not.toContain('orphaned_repos');
  });

  // docker_running is the repo's daemon answering, with or without containers.
  // A live daemon holding zero containers still protects an unmounted repo.
  it('refuses an unmounted unknown repo whose daemon answers with zero containers', async () => {
    mocks.format = 'json';
    mocks.repos = [{ name: ORPHAN, mounted: false, docker_running: true, container_count: 0 }];
    await run('--prune-unknown');
    expect(mocks.deletes).toEqual([]);
  });

  it('deletes that repo once --force-delete-mounted is passed', async () => {
    mocks.format = 'json';
    mocks.repos = [{ name: ORPHAN, mounted: false, docker_running: true, container_count: 0 }];
    await run('--prune-unknown', '--force-delete-mounted');
    expect(mocks.deletes).toEqual([ORPHAN]);
  });

  it('deletes an unmounted unknown repo whose daemon is down', async () => {
    mocks.format = 'json';
    mocks.repos = [{ name: ORPHAN, mounted: false, docker_running: false, container_count: 0 }];
    await run('--prune-unknown');
    expect(mocks.deletes).toEqual([ORPHAN]);
  });
});
