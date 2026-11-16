import { Command } from 'commander';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const ORPHAN = 'e9304ffc-0c96-47f2-a2fb-6076c1df6f52';
const KNOWN = 'b9521afd-0cbd-4481-92ed-f798268a69dd';
const GRAND = '260f0a05-1111-4222-8333-444455556666';
const FORK = '7a1c0e55-2222-4333-8444-555566667777';

const mocks = vi.hoisted(() => ({
  repos: [] as Record<string, unknown>[],
  calls: [] as { functionName: string; repository?: string }[],
  agent: false,
  confirm: true,
  deleteFails: false,
  others: {} as Record<string, unknown>,
}));

vi.mock('../../utils/errors.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../utils/errors.js')>()),
  getOutputFormat: () => 'json',
  handleError: (error: unknown) => {
    throw error;
  },
}));
vi.mock('../_validate.js', () => ({ assertMachineExists: async () => undefined }));
vi.mock('../../services/executor/executor-factory.js', () => ({
  getExecutor: () => ({
    execute: (req: { functionName: string; params?: { repository?: string } }) => {
      mocks.calls.push({ functionName: req.functionName, repository: req.params?.repository });
      if (mocks.deleteFails) return Promise.resolve({ success: false, error: 'renet refused' });
      return Promise.resolve({ success: true, stdout: '', stderr: '', exitCode: 0 });
    },
  }),
}));
vi.mock('../../services/machine/machine-status.js', () => ({
  fetchMachineStatus: async () => {
    mocks.calls.push({ functionName: 'list_all' });
    return { repositories: mocks.repos };
  },
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getCurrent: async () => ({}),
    getCurrentName: () => 'dev',
    listRepositories: async () => [
      { name: 'base', config: { repositoryGuid: KNOWN } },
      { name: 'app:dev', config: { repositoryGuid: FORK, grandGuid: GRAND } },
    ],
    listArchivedRepositories: async () => [],
  },
}));
vi.mock('../../adapters/config-file-storage.js', () => ({
  configFileStorage: {
    list: async () => ['dev', ...Object.keys(mocks.others)],
    load: async (name: string) => mocks.others[name] ?? {},
  },
}));
vi.mock('../../utils/agent-guard.js', () => ({ isAgentEnvironment: () => mocks.agent }));
vi.mock('../../utils/ops-vm.js', () => ({
  isOpsVmMachine: async () => false,
  isOpsVmPlacement: async () => false,
}));
vi.mock('../../utils/prompt.js', () => ({ askConfirm: async () => mocks.confirm }));
vi.mock('../../utils/local-execution-failures.js', () => ({
  renderLocalExecutionFailure: () => {
    process.exitCode = 1;
  },
}));

import { registerRepoAdminOrphan } from '../repo-admin-orphan.js';

const stopped = (name: string, extra: Record<string, unknown> = {}) => ({
  name,
  mounted: false,
  docker_running: false,
  containers_running: false,
  container_count: 0,
  size_human: '4.0G',
  modified_human: '2d ago',
  ...extra,
});

let stdout = '';

beforeEach(() => {
  stdout = '';
  mocks.repos = [stopped(KNOWN), stopped(ORPHAN), stopped(GRAND)];
  mocks.calls = [];
  mocks.agent = false;
  mocks.confirm = true;
  mocks.deleteFails = false;
  mocks.others = {};
  process.exitCode = undefined;
  vi.spyOn(process.stdout, 'write').mockImplementation((chunk: string | Uint8Array) => {
    stdout += String(chunk);
    return true;
  });
  vi.spyOn(process.stderr, 'write').mockImplementation(() => true);
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
  vi.spyOn(console, 'log').mockImplementation(() => undefined);
});
afterEach(() => {
  process.exitCode = undefined;
  vi.restoreAllMocks();
});

async function run(...args: string[]): Promise<void> {
  const admin = new Command();
  admin.exitOverride();
  registerRepoAdminOrphan(admin);
  await admin.parseAsync(['orphan', ...args], { from: 'user' });
}

const deletes = () => mocks.calls.filter((c) => c.functionName === 'repository_delete');

describe('repo admin orphan list', () => {
  it('marks only the GUID no config names as an orphan', async () => {
    await run('list', 'hostinger');
    const rows = JSON.parse(stdout.slice(stdout.indexOf('{'))).data as {
      guid: string;
      verdict: string;
      reason: string;
    }[];
    const byGuid = Object.fromEntries(rows.map((r) => [r.guid, r]));
    expect(byGuid[ORPHAN]?.verdict).toBe('orphaned');
    expect(byGuid[KNOWN]).toMatchObject({ verdict: 'protected', reason: 'active in dev' });
    // A configured fork's grand lineage is named by the config even though no entry carries it as its own GUID.
    expect(byGuid[GRAND]).toMatchObject({
      verdict: 'protected',
      reason: 'grand lineage of a configured fork',
    });
    expect(deletes()).toEqual([]);
  });
});

describe('repo admin orphan delete', () => {
  it('deletes an orphan through renet repository_delete with its GUID', async () => {
    await run('delete', `${ORPHAN.toUpperCase()}@hostinger`, '--yes');
    expect(deletes()).toEqual([{ functionName: 'repository_delete', repository: ORPHAN }]);
    expect(process.exitCode).toBeUndefined();
  });

  it('refuses a GUID the config names, before any delete', async () => {
    await expect(run('delete', `${KNOWN}@hostinger`, '--yes')).rejects.toThrow(/active in dev/);
    expect(deletes()).toEqual([]);
  });

  it('names no --force when another config holds the GUID, since delete has no such option', async () => {
    mocks.others = {
      'eu-bench': {
        resources: { repositories: { spike: { tags: { latest: { repositoryGuid: ORPHAN } } } } },
      },
    };
    const refusal = run('delete', `${ORPHAN}@hostinger`, '--yes');
    await expect(refusal).rejects.toThrow(/exists in eu-bench/);
    await expect(refusal).rejects.not.toThrow(/--force\b(?!-)/);
    expect(deletes()).toEqual([]);
  });

  it('refuses the grand lineage of a configured fork', async () => {
    await expect(run('delete', `${GRAND}@hostinger`, '--yes')).rejects.toThrow(
      /grand lineage of a configured fork/
    );
    expect(deletes()).toEqual([]);
  });

  it('refuses a running orphan', async () => {
    mocks.repos = [stopped(ORPHAN, { docker_running: true, container_count: 1 })];
    await expect(run('delete', `${ORPHAN}@hostinger`, '--yes')).rejects.toThrow(
      /--force-delete-mounted/
    );
    expect(deletes()).toEqual([]);
  });

  it('refuses a mounted orphan', async () => {
    mocks.repos = [stopped(ORPHAN, { mounted: true })];
    await expect(run('delete', `${ORPHAN}@hostinger`, '--yes')).rejects.toThrow(
      /--force-delete-mounted/
    );
    expect(deletes()).toEqual([]);
  });

  it('deletes a mounted, running orphan with --force-delete-mounted', async () => {
    mocks.repos = [stopped(ORPHAN, { mounted: true, docker_running: true, container_count: 1 })];
    await run('delete', `${ORPHAN}@hostinger`, '--yes', '--force-delete-mounted');
    expect(deletes()).toEqual([{ functionName: 'repository_delete', repository: ORPHAN }]);
  });

  it('calls nothing destructive on --dry-run', async () => {
    await run('delete', `${ORPHAN}@hostinger`, '--dry-run');
    expect(deletes()).toEqual([]);
    expect(JSON.parse(stdout.slice(stdout.indexOf('{'))).data).toMatchObject({
      dryRun: true,
      guid: ORPHAN,
      machine: 'hostinger',
    });
  });

  it('deletes nothing when the confirmation is declined', async () => {
    mocks.confirm = false;
    await run('delete', `${ORPHAN}@hostinger`);
    expect(deletes()).toEqual([]);
  });

  it('answers NOT_FOUND for a GUID the machine does not hold', async () => {
    mocks.repos = [stopped(KNOWN)];
    await expect(run('delete', `${ORPHAN}@hostinger`, '--yes')).rejects.toMatchObject({
      code: 'NOT_FOUND',
    });
    expect(deletes()).toEqual([]);
  });

  it.each(['not-a-guid@hostinger', ORPHAN, `${ORPHAN}@`, `@hostinger`])(
    'refuses the malformed ref %s before reading the machine',
    async (ref) => {
      await expect(run('delete', ref, '--yes')).rejects.toThrow(/<guid>@<machine>/);
      expect(mocks.calls).toEqual([]);
    }
  );

  it('exits non-zero when renet refuses the delete', async () => {
    mocks.deleteFails = true;
    await run('delete', `${ORPHAN}@hostinger`, '--yes');
    expect(deletes()).toHaveLength(1);
    expect(process.exitCode).toBe(1);
  });

  describe('agent grand guard', () => {
    const saved = process.env.REDIACC_ALLOW_GRAND_REPO;
    afterEach(() => {
      if (saved === undefined) delete process.env.REDIACC_ALLOW_GRAND_REPO;
      else process.env.REDIACC_ALLOW_GRAND_REPO = saved;
    });

    it('refuses an agent deleting an orphan the machine does not mark as a fork', async () => {
      mocks.agent = true;
      delete process.env.REDIACC_ALLOW_GRAND_REPO;
      await expect(run('delete', `${ORPHAN}@hostinger`, '--yes')).rejects.toThrow(
        /grand \(production\) repository/
      );
      expect(deletes()).toEqual([]);
    });

    it('refuses an agent on --dry-run too, as repo delete does', async () => {
      mocks.agent = true;
      delete process.env.REDIACC_ALLOW_GRAND_REPO;
      await expect(run('delete', `${ORPHAN}@hostinger`, '--dry-run')).rejects.toThrow(
        /grand \(production\) repository/
      );
    });

    it('lets an agent delete an orphan the machine marks as a fork', async () => {
      mocks.agent = true;
      delete process.env.REDIACC_ALLOW_GRAND_REPO;
      mocks.repos = [stopped(ORPHAN, { is_fork: true })];
      await run('delete', `${ORPHAN}@hostinger`, '--yes');
      expect(deletes()).toEqual([{ functionName: 'repository_delete', repository: ORPHAN }]);
    });
  });
});
