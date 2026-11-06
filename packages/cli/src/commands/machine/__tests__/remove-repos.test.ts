/**
 * `machine remove` and the repos placed on the machine (#f9759988): `--archive-repos` archives
 * them, `--force` names them with the way to archive them, and a machine without repos is unchanged.
 */

import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const h = vi.hoisted(() => ({
  config: undefined as unknown,
  archived: [] as string[][],
  removed: [] as string[],
  info: [] as string[],
  warn: [] as string[],
}));

vi.mock('../../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key} ${JSON.stringify(params)}` : key,
}));
vi.mock('../../../services/config/config-resources.js', () => ({
  configService: {
    getCurrent: () => Promise.resolve(h.config),
    listRepositories: () => {
      const repos = (h.config as { resources: { repositories: Record<string, unknown> } }).resources
        .repositories;
      return Promise.resolve(Object.entries(repos).map(([name, config]) => ({ name, config })));
    },
    removeMachine: (name: string) => {
      h.removed.push(name);
      return Promise.resolve();
    },
    archiveRepositories: (keys: string[]) => {
      h.archived.push(keys);
      return Promise.resolve(keys);
    },
  },
}));
vi.mock('../../../services/core/output.js', () => ({
  outputService: {
    info: (line: string) => h.info.push(line),
    warn: (line: string) => h.warn.push(line),
    success: vi.fn(),
  },
}));
vi.mock('../../../utils/errors.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../utils/errors.js')>()),
  handleError: (e: unknown) => {
    throw e;
  },
}));

const { registerMachineRegistrationCommands } = await import('../register.js');

function config(withRepos: boolean): unknown {
  return {
    resources: {
      machines: { 'obs-lab': {}, hostinger: {} },
      repositories: withRepos
        ? {
            obsram: {
              grand: 'latest',
              placement: { machine: 'obs-lab' },
              tags: { latest: { repositoryGuid: 'g1' }, t1: { repositoryGuid: 'g2' } },
            },
            shop: {
              grand: 'latest',
              placement: { machine: 'hostinger' },
              tags: { latest: { repositoryGuid: 'g3' } },
            },
          }
        : {},
    },
  };
}

async function run(...argv: string[]): Promise<void> {
  const program = new Command();
  program.exitOverride();
  registerMachineRegistrationCommands(program.command('machine'), program);
  await program.parseAsync(['machine', 'remove', 'obs-lab', '-y', ...argv], { from: 'user' });
}

beforeEach(() => {
  h.archived = [];
  h.removed = [];
  h.info = [];
  h.warn = [];
  h.config = config(true);
});

describe('machine remove: the machine repos', () => {
  it('archives the repos placed on the machine with --archive-repos, and only those', async () => {
    await run('--archive-repos');
    expect(h.removed).toEqual(['obs-lab']);
    expect(h.archived).toEqual([['obsram:latest', 'obsram:t1']]);
    expect(h.warn).toEqual([]);
  });

  it('refuses without a flag, naming --archive-repos, and removes nothing', async () => {
    await expect(run()).rejects.toMatchObject({ exitCode: 12 });
    expect(h.removed).toEqual([]);
    expect(h.archived).toEqual([]);
  });

  it('with --force names the repos and the archive commands, archiving nothing', async () => {
    await run('--force');
    expect(h.removed).toEqual(['obs-lab']);
    expect(h.archived).toEqual([]);
    expect(h.warn.join('\n')).toContain('obsram');
    expect(h.info.join('\n')).toContain('reposLeftHint');
  });

  it('is unchanged for a machine without repos', async () => {
    h.config = config(false);
    await run();
    expect(h.removed).toEqual(['obs-lab']);
    expect(h.archived).toEqual([]);
    expect([...h.info, ...h.warn]).toEqual([]);
  });
});
