import { Command } from 'commander';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const ORPHAN = '260f0a05-1111-4222-8333-444455556666';
const KNOWN = 'b9521afd-0cbd-4481-92ed-f798268a69dd';

const mocks = vi.hoisted(() => ({
  format: 'json' as 'json' | 'table' | 'yaml',
  fail: false,
  repos: [] as Record<string, unknown>[],
  deletes: [] as string[],
  deployed: [] as string[],
  events: [] as string[],
  sshEntries: [] as string[],
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
        mocks.events.push(`delete:${String(req.params?.repository)}`);
      }
      return Promise.resolve({ success: true });
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
  getRepositories: () => mocks.deployed.map((name) => ({ name })),
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getCurrent: async () => ({}),
    getCurrentName: () => 'dev',
    applyDefaults: async () => ({}),
    listRepositories: async () => [{ name: 'base', config: { repositoryGuid: KNOWN } }],
    listArchivedRepositories: async () => [],
    purgeExpiredArchives: async () => [],
  },
}));
vi.mock('../../adapters/config-file-storage.js', () => ({
  configFileStorage: { list: async () => ['dev'], load: async () => ({}) },
}));
vi.mock('../../remote/vscode/index.js', () => ({
  listSSHConfigEntries: () => mocks.sshEntries,
  removePersistedKeys: (_team: string, _machine: string, repo: string) => {
    mocks.events.push(`keys:${repo}`);
  },
  removeSSHConfigEntry: (entry: string) => {
    mocks.events.push(`ssh:${entry}`);
  },
}));

import { registerPruneCommand, splitPrunePhases } from '../machine/prune.js';
import { installJobDeps } from './job-deps.js';

/** The one machine_prune job's stdout: each phase behind its marker line. */
const PRUNE_STDOUT = [
  '{"prune_phase":"datastore"}',
  JSON.stringify({ stale_locks: null, auth_keys: [] }),
  '{"prune_phase":"units"}',
  'Nothing to prune. All networks have repositories.',
].join('\n');

let restoreJobDeps: () => void;

let stdout = '';

beforeEach(() => {
  restoreJobDeps = installJobDeps(() =>
    Promise.resolve(
      mocks.fail
        ? { success: false, exitCode: 1, durationMs: 1, state: 'failed' as const, error: 'boom' }
        : {
            success: true,
            exitCode: 0,
            durationMs: 1,
            state: 'succeeded' as const,
            stdout: PRUNE_STDOUT,
          }
    )
  );
  stdout = '';
  mocks.fail = false;
  mocks.repos = [];
  mocks.deletes = [];
  mocks.deployed = [KNOWN, ORPHAN];
  mocks.events = [];
  mocks.sshEntries = [];
  vi.spyOn(process.stdout, 'write').mockImplementation((chunk: string | Uint8Array) => {
    stdout += String(chunk);
    return true;
  });
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
});
afterEach(() => {
  restoreJobDeps();
  vi.restoreAllMocks();
});

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

  // The SSH-config cleanup runs client-side after a real orphan deletion, and only then.
  describe('ssh artifact cleanup', () => {
    const STALE = 'rediacc--ops-worker-gone';
    const LIVE = 'rediacc--ops-worker-base';

    it('removes the stale entry and its keys after the orphan is deleted, and keeps a configured repo', async () => {
      mocks.format = 'json';
      mocks.sshEntries = [STALE, LIVE, 'rediacc--other-machine-gone'];
      await run('--orphaned-repos');
      expect(mocks.events).toEqual([`delete:${ORPHAN}`, `ssh:${STALE}`, 'keys:gone']);
    });

    it('touches no ssh entry on a dry run', async () => {
      mocks.format = 'json';
      mocks.sshEntries = [STALE];
      await run('--orphaned-repos', '--dry-run');
      expect(mocks.events).toEqual([]);
    });

    it('touches no ssh entry when nothing is orphaned', async () => {
      mocks.format = 'json';
      mocks.deployed = [KNOWN];
      mocks.sshEntries = [STALE];
      await run('--orphaned-repos');
      expect(mocks.events).toEqual([]);
    });
  });
});

describe('splitPrunePhases', () => {
  it('splits the two phases at their markers', () => {
    expect(splitPrunePhases(PRUNE_STDOUT)).toEqual({
      datastore: JSON.stringify({ stale_locks: null, auth_keys: [] }),
      units: 'Nothing to prune. All networks have repositories.',
    });
  });

  it.each(['constructor', '__proto__', 'toString'])(
    'skips the lines of an unknown marker named %s instead of throwing',
    (name) => {
      const out = [
        '{"prune_phase":"datastore"}',
        '{"a":1}',
        `{"prune_phase":"${name}"}`,
        'stray',
      ].join('\n');
      expect(splitPrunePhases(out)).toEqual({ datastore: '{"a":1}', units: '' });
    }
  );
});
