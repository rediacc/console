/**
 * `machine deprovision` and the repos placed on the machine (#80f7476a): `--archive-repos` archives
 * them; without it they are named with the commands that archive them, never left unsaid.
 */

import type { RdcConfig } from '@rediacc/shared/config-schema';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const h = vi.hoisted(() => ({
  archived: [] as string[][],
  info: [] as string[],
  warn: [] as string[],
}));

vi.mock('../../../services/config/config-resources.js', () => ({
  configService: {
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
  },
}));

import { repoKeysPlacedOn } from '../../../services/config/machine-gone-repos.js';
import { settleMachineRepos } from '../provision.js';

beforeEach(() => {
  h.archived = [];
  h.info = [];
  h.warn = [];
});

describe('machine deprovision: the machine repos', () => {
  it('lists every tag placed on the machine, directly or through an attached datastore', () => {
    const cfg = {
      schemaVersion: 3,
      id: 'x',
      version: 1,
      resources: {
        repositories: {
          obsram: {
            grand: 'latest',
            placement: { machine: 'obs-lab' },
            tags: { latest: { repositoryGuid: 'g1' }, t1: { repositoryGuid: 'g2' } },
          },
          sockfix: {
            grand: 'latest',
            placement: { datastore: 'pool' },
            tags: { latest: { repositoryGuid: 'g3' } },
          },
          shop: {
            grand: 'latest',
            placement: { machine: 'hostinger' },
            tags: { latest: { repositoryGuid: 'g4' } },
          },
        },
      },
      state: { datastores: { pool: { attachedTo: 'obs-lab' } } },
    } as unknown as RdcConfig;
    expect(repoKeysPlacedOn(cfg, 'obs-lab')).toEqual([
      'obsram:latest',
      'obsram:t1',
      'sockfix:latest',
    ]);
  });

  it('archives them with --archive-repos', async () => {
    await settleMachineRepos('obs-lab', ['obsram:latest', 'sockfix09b:latest'], true);
    expect(h.archived).toEqual([['obsram:latest', 'sockfix09b:latest']]);
    expect(h.warn).toEqual([]);
    expect(h.info.join('\n')).toContain(
      'Archived 2 repository entry/entries placed on obs-lab: obsram:latest, sockfix09b:latest'
    );
  });

  it('names them and the way to archive them without the flag, and archives nothing', async () => {
    await settleMachineRepos('obs-lab', ['obsram:latest'], false);
    expect(h.archived).toEqual([]);
    expect(h.warn.join('\n')).toContain(
      '1 repository entry/entries still name obs-lab, which is no longer in this config: obsram:latest'
    );
    expect(h.info.join('\n')).toContain('rdc config prune --gone-machine-repos');
  });

  it('says nothing when no repo was placed on the machine', async () => {
    await settleMachineRepos('obs-lab', [], true);
    expect(h.archived).toEqual([]);
    expect([...h.info, ...h.warn]).toEqual([]);
  });
});
