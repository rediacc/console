import { describe, expect, it } from 'vitest';
import type { ListResult } from '@rediacc/shared/renet-contract/data/list-types.generated';
import type { RdcConfig } from '../../schema/schemas.js';
import {
  reconcileState,
  verifyRoutingHint,
  type ReconcileDeps,
} from '../config/config-reconcile.js';

const GRAND = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const FORK = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';

function baseConfig(): RdcConfig {
  return {
    schemaVersion: 3,
    id: '00000000-0000-4000-8000-000000000000',
    version: 4,
    resources: {
      machines: {
        'web-1': { ip: '10.0.0.1', user: 'deploy' },
        'web-2': { ip: '10.0.0.2', user: 'deploy' },
      },
      repositories: {
        shop: {
          grand: 'main',
          tags: {
            main: { repositoryGuid: GRAND },
            test: { repositoryGuid: FORK, grandGuid: GRAND },
          },
        },
      },
    },
  };
}

function listWithRepo(guid: string, mounted = true): ListResult {
  return {
    repositories: [
      { name: guid, repo_name: 'shop:main', mounted, mount_path: '/mnt/rediacc/mounts/x' },
    ],
  } as unknown as ListResult;
}

function emptyList(): ListResult {
  return { repositories: [] } as unknown as ListResult;
}

function makeDeps(
  config: RdcConfig,
  statuses: Record<string, ListResult | Error>
): { deps: ReconcileDeps; written: () => RdcConfig } {
  let current = config;
  const deps: ReconcileDeps = {
    loadConfig: () => Promise.resolve(current),
    fetchStatus: (m) => {
      const s = statuses[m];
      if (s instanceof Error) return Promise.reject(s);
      return Promise.resolve(s ?? emptyList());
    },
    writeState: (updater) => {
      current = updater(current);
      return Promise.resolve();
    },
  };
  return { deps, written: () => current };
}

describe('reconcileState', () => {
  it('fills missing placement by matching the grand GUID on one machine', async () => {
    const { deps, written } = makeDeps(baseConfig(), {
      'web-1': listWithRepo(GRAND),
      'web-2': emptyList(),
    });
    const report = await reconcileState(deps);

    expect(report.placementsFilled).toEqual([
      { repository: 'shop', placement: { machine: 'web-1' } },
    ]);
    expect(report.conflicts).toHaveLength(0);
    expect(written().resources?.repositories?.shop.placement).toEqual({ machine: 'web-1' });
    expect(written().state?.machines?.['web-1']?.lastSeenAt).toBeDefined();
    expect(written().state?.reconciledAt).toBe(report.reconciledAt);
  });

  it('never overwrites a declared placement; reports a spec-vs-observed conflict', async () => {
    const config = baseConfig();
    config.resources!.repositories!.shop.placement = { machine: 'web-1' };
    const { deps, written } = makeDeps(config, {
      'web-1': emptyList(),
      'web-2': listWithRepo(GRAND), // observed on the WRONG machine
    });
    const report = await reconcileState(deps);

    expect(report.placementsFilled).toHaveLength(0);
    expect(report.conflicts).toHaveLength(1);
    expect(report.conflicts[0].kind).toBe('placement');
    expect(report.conflicts[0].message).toContain('web-2');
    // Declaration is untouched.
    expect(written().resources?.repositories?.shop.placement).toEqual({ machine: 'web-1' });
  });

  it('reports a duplicate conflict when a GUID is observed on two machines', async () => {
    const { deps } = makeDeps(baseConfig(), {
      'web-1': listWithRepo(GRAND),
      'web-2': listWithRepo(GRAND),
    });
    const report = await reconcileState(deps);

    expect(report.placementsFilled).toHaveLength(0);
    expect(report.conflicts).toHaveLength(1);
    expect(report.conflicts[0].kind).toBe('duplicate');
  });

  it('records unreachable machines without failing the whole reconcile', async () => {
    const { deps } = makeDeps(baseConfig(), {
      'web-1': listWithRepo(GRAND),
      'web-2': new Error('ssh timeout'),
    });
    const report = await reconcileState(deps);

    expect(report.machinesSeen).toEqual(['web-1']);
    expect(report.machinesUnreachable).toEqual([{ machine: 'web-2', error: 'ssh timeout' }]);
    expect(report.placementsFilled).toHaveLength(1);
  });
});

describe('verifyRoutingHint', () => {
  it('passes when the datastore is mounted on the hinted machine', () => {
    expect(
      verifyRoutingHint({
        datastore: 'ds-alpha',
        hintedMachine: 'prod-2',
        observedMountedOn: 'prod-2',
      })
    ).toEqual({ ok: true });
  });

  it('fails closed naming both sides and the fix', () => {
    const v = verifyRoutingHint({
      datastore: 'ds-alpha',
      hintedMachine: 'prod-2',
      observedMountedOn: null,
    });
    expect(v.ok).toBe(false);
    expect(v.error).toContain('ds-alpha');
    expect(v.error).toContain('prod-2');
    expect(v.error).toContain('rdc config reconcile');
  });
});
