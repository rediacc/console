import type { ReplicaSet } from '@rediacc/shared/config-schema';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { configService } from '../../config/config-resources.js';
import { outputService } from '../../core/output.js';
import { localExecutorService } from '../../executor/local-executor.js';
import {
  __setReplicateClock,
  __setReplicateDelay,
  refreshReplicaSet,
  removeReplicaSet,
  replicateRepo,
} from '../repo-replicate-ops.js';

vi.mock('../cluster-target.js', () => ({
  resolveExecutionTarget: vi.fn(() => Promise.resolve({ machineName: 'cp1', cluster: 'prod' })),
}));
vi.mock('../../config/config-cluster-ops.js', () => ({
  getCluster: vi.fn(() => Promise.resolve({
    provider: 'kvm',
    pools: [{ name: 'w', role: 'hyperconverged', count: 2 }],
  })),
}));

/** In-memory replica-set state + a scripted executor. */
let stored: Record<string, ReplicaSet> | undefined;

function mockState(initial?: Record<string, ReplicaSet>): void {
  stored = initial;
  vi.spyOn(configService, 'getCurrent').mockImplementation(
    () => Promise.resolve({ state: { replicaSets: stored } }) as never
  );
  vi.spyOn(configService, 'setStateBucket').mockImplementation((_key, sets) => {
    stored = sets as Record<string, ReplicaSet>;
    return Promise.resolve();
  });
  vi.spyOn(configService, 'getLocalMachine').mockImplementation(
    (name: string) => Promise.resolve({ ip: `10.0.0.${name.slice(-1)}` }) as never
  );
}

function mockExec() {
  return vi.spyOn(localExecutorService, 'execute').mockImplementation(({ functionName }) => {
    if (functionName === 'datastore_list') {
      return Promise.resolve({
        success: true,
        stdout: JSON.stringify([
          { name: 'ds-control-prod', cluster: 'prod' },
          { name: 'ds-data', cluster: 'prod' },
          { name: 'ds-data:other-r1', cluster: 'prod', fork: {} },
          { name: 'default', implicit: true },
        ]),
      }) as never;
    }
    return Promise.resolve({ success: true }) as never;
  });
}

beforeEach(() => {
  vi.spyOn(outputService, 'info').mockReturnValue(undefined);
  vi.spyOn(outputService, 'warn').mockReturnValue(undefined);
  vi.spyOn(outputService, 'success').mockReturnValue(undefined);
  __setReplicateClock(() => 1_800_000_000_000);
  __setReplicateDelay(() => Promise.resolve());
});
afterEach(() => vi.restoreAllMocks());

const seededSet: ReplicaSet = {
  repo: 'sqldb',
  datastore: 'ds-data',
  cluster: 'prod',
  snapshot: 'replicate-sqldb-replicas',
  createdAt: '2026-07-11T00:00:00Z',
  replicas: [
    { index: 1, fork: 'ds-data:sqldb-replicas-r1', node: 'prod-w-1' },
    { index: 2, fork: 'ds-data:sqldb-replicas-r2', node: 'prod-w-2' },
  ],
};

describe('replicateRepo (create orchestrator)', () => {
  it('infers the datastore, provisions, applies the overlay, records state', async () => {
    mockState();
    const exec = mockExec();

    await replicateRepo({
      repo: 'sqldb',
      cluster: 'prod',
      replicas: 2,
      image: 'postgres:16',
      port: 5432,
      refresh: '1h',
    });

    const calls = exec.mock.calls.map((c) => c[0]);
    const names = calls.map((c) => c.functionName);
    // datastore inference -> ONE snapshot -> (fork, attach, label) x2 -> apply.
    expect(names).toEqual([
      'datastore_list',
      'datastore_snapshot_create',
      'datastore_fork',
      'datastore_attach',
      'kube_node_label',
      'datastore_fork',
      'datastore_attach',
      'kube_node_label',
      'kube_apply',
    ]);
    // The overlay goes through kube_apply on the control node, stdin-fed,
    // persisted under a stable per-set basename.
    const apply = calls.find((c) => c.functionName === 'kube_apply');
    expect(apply).toMatchObject({
      machineName: 'cp1',
      params: {
        mount_path: '/mnt/rediacc-ds/ds-control-prod',
        namespace: 'sqldb',
        name: 'replicate-sqldb-replicas.yaml',
        cluster: 'prod',
        datastore: '/mnt/rediacc-ds/ds-data',
      },
    });
    expect(apply?.params?.manifest).toContain('name: sqldb-ro');
    expect(apply?.params?.manifest).toContain('kind: StatefulSet');
    // Managed state recorded from birth (R2-F17), snapshot + refresh included.
    expect(stored?.['sqldb-replicas']).toMatchObject({
      repo: 'sqldb',
      datastore: 'ds-data',
      cluster: 'prod',
      snapshot: 'replicate-sqldb-replicas',
      refresh: '1h',
      replicas: [
        { index: 1, fork: 'ds-data:sqldb-replicas-r1', node: 'prod-w-1' },
        { index: 2, fork: 'ds-data:sqldb-replicas-r2', node: 'prod-w-2' },
      ],
    });
  });

  it('refuses a duplicate set name', async () => {
    mockState({ 'sqldb-replicas': seededSet });
    mockExec();
    await expect(
      replicateRepo({ repo: 'sqldb', cluster: 'prod', replicas: 2, image: 'x', port: 1 })
    ).rejects.toThrow(/already exists/);
  });

  it('refuses an ambiguous datastore instead of guessing', async () => {
    mockState();
    vi.spyOn(localExecutorService, 'execute').mockResolvedValue({
      success: true,
      stdout: JSON.stringify([
        { name: 'ds-a', cluster: 'prod' },
        { name: 'ds-b', cluster: 'prod' },
      ]),
    } as never);
    await expect(
      replicateRepo({ repo: 'sqldb', cluster: 'prod', replicas: 1, image: 'x', port: 1 })
    ).rejects.toThrow(/2 data datastores \(ds-a, ds-b\)/);
  });
});

describe('removeReplicaSet (teardown orchestrator)', () => {
  it('deletes overlay, strips labels, discards forks, drops snapshot, forgets state', async () => {
    mockState({ 'sqldb-replicas': seededSet });
    const exec = mockExec();

    await removeReplicaSet('sqldb-replicas');

    const calls = exec.mock.calls.map((c) => c[0]);
    expect(calls.map((c) => c.functionName)).toEqual([
      'kube_delete',
      'kube_node_label',
      'kube_node_label',
      'datastore_detach',
      'datastore_detach',
      'datastore_snapshot_delete',
    ]);
    // The overlay delete is replica-set scoped (whole-overlay form, no ordinal).
    expect(calls[0]).toMatchObject({
      machineName: 'cp1',
      params: { namespace: 'sqldb', replica_set: 'sqldb-replicas' },
    });
    expect(calls[0].params?.pod_ordinal).toBeUndefined();
    // Labels are stripped per fork (mount-style datastore name).
    expect(calls[1].params).toMatchObject({ datastore: 'ds-data-sqldb-replicas-r1', remove: true });
    // The set's snapshot is dropped after the clones are discarded.
    expect(calls[5].params).toMatchObject({
      name: 'ds-data',
      snapshot: 'replicate-sqldb-replicas',
    });
    expect(stored).toEqual({});
  });

  it('continues past infra failures so remove converges, then forgets state', async () => {
    mockState({ 'sqldb-replicas': seededSet });
    vi.spyOn(localExecutorService, 'execute').mockResolvedValue({
      success: false,
      error: 'cluster gone',
    } as never);
    await removeReplicaSet('sqldb-replicas');
    expect(stored).toEqual({});
  });
});

describe('refreshReplicaSet (rolling one-at-a-time)', () => {
  it('snapshots once, then per replica: pod bounce -> discard -> re-fork -> re-attach -> label', async () => {
    mockState({ 'sqldb-replicas': seededSet });
    const exec = mockExec();

    await refreshReplicaSet('sqldb-replicas');

    const calls = exec.mock.calls.map((c) => c[0]);
    expect(calls.map((c) => c.functionName)).toEqual([
      'datastore_snapshot_create',
      // replica 1 fully, then replica 2 (N-1 keep serving).
      'kube_delete',
      'datastore_detach',
      'datastore_fork',
      'datastore_attach',
      'kube_node_label',
      'kube_delete',
      'datastore_detach',
      'datastore_fork',
      'datastore_attach',
      'kube_node_label',
      'datastore_snapshot_delete',
    ]);
    // Pod bounce targets the 0-based ordinal of each replica index.
    const bounces = calls.filter((c) => c.functionName === 'kube_delete');
    expect(bounces.map((c) => c.params?.pod_ordinal)).toEqual([0, 1]);
    // New forks clone the NEW snapshot; same tag, so the PV path never changes.
    const newSnap = 'replicate-sqldb-replicas-1800000000000';
    const forks = calls.filter((c) => c.functionName === 'datastore_fork');
    expect(forks.every((c) => c.params?.snapshot === newSnap)).toBe(true);
    expect(forks.map((c) => c.params?.tag)).toEqual(['sqldb-replicas-r1', 'sqldb-replicas-r2']);
    // The OLD snapshot is deleted once every replica clones the new one.
    expect(calls.at(-1)?.params).toMatchObject({ snapshot: 'replicate-sqldb-replicas' });
    // State now points at the new snapshot with a refresh timestamp.
    expect(stored?.['sqldb-replicas']).toMatchObject({
      snapshot: newSnap,
      refreshedAt: new Date(1_800_000_000_000).toISOString(),
    });
  });

  it('retries a busy detach while the terminating pod releases the mount', async () => {
    mockState({
      'sqldb-replicas': { ...seededSet, replicas: [seededSet.replicas[0]] },
    });
    let detachAttempts = 0;
    vi.spyOn(localExecutorService, 'execute').mockImplementation(({ functionName }) => {
      if (functionName === 'datastore_detach' && ++detachAttempts < 3) {
        return Promise.resolve({ success: false, error: 'busy' }) as never;
      }
      return Promise.resolve({ success: true }) as never;
    });
    const delays: number[] = [];
    __setReplicateDelay((ms) => {
      delays.push(ms);
      return Promise.resolve();
    });

    await refreshReplicaSet('sqldb-replicas');

    expect(detachAttempts).toBe(3);
    expect(delays).toEqual([2000, 2000]);
  });
});
