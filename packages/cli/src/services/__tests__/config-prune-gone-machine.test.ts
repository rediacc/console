/**
 * `config prune` and references to a machine the config no longer has (#80f7476a): after
 * `machine deprovision obs-lab`, repos obsram/sockfix09b still pointed at obs-lab and nothing
 * removed them. The config is an in-memory document behind mocked configService/updateSyncedConfig;
 * the prune logic is real.
 */

import type { RdcConfig } from '@rediacc/shared/config-schema';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const h = vi.hoisted(() => ({ disk: undefined as unknown }));
const clone = <T>(v: T): T => structuredClone(v);

vi.mock('../config/config-resources.js', () => ({
  configService: {
    getCurrent: () => Promise.resolve(clone(h.disk)),
    getEffectiveConfigName: () => 'cfg',
  },
}));
vi.mock('../config/synced-write.js', () => ({
  updateSyncedConfig: (_name: string, edit: (c: RdcConfig) => RdcConfig) => {
    h.disk = clone(edit(clone(h.disk) as RdcConfig));
    return Promise.resolve();
  },
}));

import { analyzeConfigPrune, applyConfigPrune } from '../config/config-prune.js';

const PUSH = { lastPushAt: '2026-11-01T00:00:00.000Z', method: 'rsync' as const };

function config(): RdcConfig {
  return {
    schemaVersion: 3,
    id: '00000000-0000-0000-0000-000000000000',
    version: 1,
    resources: {
      machines: { hostinger: { ip: '1.2.3.4', user: 'root' } },
      repositories: {
        obsram: {
          grand: 'latest',
          placement: { machine: 'obs-lab' },
          tags: {
            latest: { repositoryGuid: '11111111-1111-4111-8111-111111111111' },
            t1: {
              repositoryGuid: '22222222-2222-4222-8222-222222222222',
              grandGuid: '11111111-1111-4111-8111-111111111111',
            },
          },
        },
        shop: {
          grand: 'latest',
          placement: { machine: 'hostinger' },
          tags: { latest: { repositoryGuid: '33333333-3333-4333-8333-333333333333' } },
        },
      },
    },
    state: {
      licenseRefresh: { hostinger: 1, 'obs-lab': 2 },
      repos: {
        obsram: { latest: { networkId: 2816 } },
        shop: { latest: { networkId: 2880, pushState: { hostinger: PUSH, 'obs-lab': PUSH } } },
      },
    },
  };
}

const disk = () => h.disk as RdcConfig;

beforeEach(() => {
  h.disk = config();
});

describe('config prune: references to a machine no longer in the config', () => {
  it('reports repos on the gone machine without touching them, and drops gone-machine state', async () => {
    const analysis = await applyConfigPrune({});

    expect(analysis.goneMachineRepos).toEqual([
      { name: 'obsram', machine: 'obs-lab', guid: '11111111-1111-4111-8111-111111111111' },
    ]);
    expect(disk().resources?.repositories).toHaveProperty('obsram');
    expect(analysis.goneMachineState.sort((a, b) => a.localeCompare(b))).toEqual([
      'state.licenseRefresh.obs-lab',
      'state.repos.shop.latest.pushState.obs-lab',
    ]);
    expect(disk().state?.licenseRefresh).toEqual({ hostinger: 1 });
    expect(disk().state?.repos?.shop.latest.pushState).toEqual({ hostinger: PUSH });
  });

  it('archives every tag of a gone-machine repo with --gone-machine-repos, credentials kept', async () => {
    const analysis = await applyConfigPrune({ goneMachineRepos: true });

    expect(analysis.goneMachineRepos.map((r) => r.name)).toEqual(['obsram']);
    expect(Object.keys(disk().resources?.repositories ?? {})).toEqual(['shop']);
    const archived = disk().resources?.deletedRepositories ?? [];
    expect(archived.map((a) => `${a.name}:${a.tag}`).sort((a, b) => a.localeCompare(b))).toEqual([
      'obsram:latest',
      'obsram:t1',
    ]);
    expect(archived.map((a) => a.repositoryGuid).sort((a, b) => a.localeCompare(b))).toEqual([
      '11111111-1111-4111-8111-111111111111',
      '22222222-2222-4222-8222-222222222222',
    ]);
    expect(disk().state?.repos).not.toHaveProperty('obsram');
    // A fresh archive is in grace, never purged by the same run.
    expect(analysis.expiredArchives).toEqual([]);
  });

  it('changes nothing on a dry run', async () => {
    const analysis = await analyzeConfigPrune({ goneMachineRepos: true });
    expect(analysis.goneMachineRepos).toHaveLength(1);
    expect(analysis.goneMachineState).toHaveLength(2);
    expect(disk()).toEqual(config());
  });

  it('archives a datastore-placed repo whose datastore is attached to a gone machine', async () => {
    const cfg = config();
    cfg.resources!.repositories!.obsram.placement = { datastore: 'pool' };
    cfg.state!.datastores = { pool: { attachedTo: 'obs-lab' } } as never;
    h.disk = cfg;

    const analysis = await applyConfigPrune({ goneMachineRepos: true });
    expect(analysis.goneMachineRepos.map((r) => r.machine)).toEqual(['obs-lab']);
    expect(disk().resources?.repositories).not.toHaveProperty('obsram');
  });
});
