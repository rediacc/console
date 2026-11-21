/**
 * `repo delete` of a repo whose machine left the config (#80f7476a): `rdc repo delete
 * obsram:latest -y` failed `Machine "obs-lab" not found. Available: hostinger`. The delete is now
 * config-only: the entry is archived and no machine step runs.
 */

import type { RdcConfig } from '@rediacc/shared/config-schema';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const h = vi.hoisted(() => ({
  config: undefined as unknown,
  archived: [] as string[],
  info: [] as string[],
  settled: [] as string[],
  machineCalls: 0,
}));

vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getCurrent: () => Promise.resolve(structuredClone(h.config)),
    resolveDestructiveTarget: (key: string) =>
      Promise.resolve({
        key: key.includes(':') ? key : `${key}:latest`,
        config: { repositoryGuid: '11111111-1111-4111-8111-111111111111' },
      }),
    archiveRepository: (key: string) => {
      h.archived.push(key);
      return Promise.resolve();
    },
  },
}));
vi.mock('../../utils/command-policy.js', () => ({
  assertCommandPolicy: () => Promise.resolve(),
  CMD: { REPO_DELETE: 'repo.delete' },
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: (line: string) => h.info.push(line),
    warn: () => undefined,
    error: () => undefined,
    success: () => undefined,
    print: () => undefined,
  },
}));
vi.mock('../repo-delete-settle.js', () => ({
  isFork: () => false,
  settleCloudBackups: (name: string) => {
    h.settled.push(`backups:${name}`);
    return Promise.resolve();
  },
  settleRepoLicense: (name: string) => {
    h.settled.push(`license:${name}`);
    return Promise.resolve();
  },
  settleConfigEntry: () => Promise.resolve(),
}));
// The machine-side path must not run for a gone machine.
vi.mock('../../utils/repo-target.js', () => ({
  resolveRepoRef: () => {
    h.machineCalls += 1;
    return Promise.reject(new Error('Machine "obs-lab" not found. Available: hostinger'));
  },
}));

import { handleRepoDelete } from '../repo-create-delete-teardown.js';
import { goneMachineOf } from '../repo-delete-machine-gone.js';

function config(machines: string[]): RdcConfig {
  return {
    schemaVersion: 3,
    id: '00000000-0000-0000-0000-000000000000',
    version: 1,
    resources: {
      machines: Object.fromEntries(machines.map((m) => [m, { ip: '1.2.3.4', user: 'root' }])),
      repositories: {
        obsram: {
          grand: 'latest',
          placement: { machine: 'obs-lab' },
          tags: { latest: { repositoryGuid: '11111111-1111-4111-8111-111111111111' } },
        },
      },
    },
  };
}

beforeEach(() => {
  h.archived = [];
  h.info = [];
  h.settled = [];
  h.machineCalls = 0;
});

describe('repo delete when the machine is gone', () => {
  it('names the gone machine, and nothing when the machine exists', async () => {
    h.config = config(['hostinger']);
    expect(await goneMachineOf('obsram:latest')).toBe('obs-lab');
    h.config = config(['hostinger', 'obs-lab']);
    expect(await goneMachineOf('obsram:latest')).toBeUndefined();
  });

  it('archives the config entry, says what it removed, and never reaches for the machine', async () => {
    h.config = config(['hostinger']);
    await handleRepoDelete('obsram:latest', { yes: true });

    expect(h.machineCalls).toBe(0);
    expect(h.archived).toEqual(['obsram:latest']);
    expect(h.info).toContainEqual(
      expect.stringMatching(/obsram:latest.*obs-lab|machineGoneArchived/)
    );
    expect(h.settled).toEqual(['backups:obsram:latest', 'license:obsram:latest']);
  });

  it('archives with --archive-config too, the flag that failed in the report', async () => {
    h.config = config(['hostinger']);
    await handleRepoDelete('obsram:latest', { yes: true, archiveConfig: true });
    expect(h.archived).toEqual(['obsram:latest']);
    expect(h.machineCalls).toBe(0);
  });

  it('writes nothing on --dry-run', async () => {
    h.config = config(['hostinger']);
    await handleRepoDelete('obsram:latest', { dryRun: true });
    expect(h.archived).toEqual([]);
  });

  it('takes the machine path when the machine exists', async () => {
    h.config = config(['hostinger', 'obs-lab']);
    const exit = vi.spyOn(process, 'exit').mockImplementation((() => undefined) as never);
    await handleRepoDelete('obsram:latest', { yes: true });
    exit.mockRestore();
    expect(h.machineCalls).toBe(1);
    expect(h.archived).toEqual([]);
  });
});
