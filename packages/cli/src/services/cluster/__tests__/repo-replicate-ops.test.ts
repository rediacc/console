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
  getCluster: vi.fn(() =>
    Promise.resolve({
      provider: 'kvm',
      pools: [{ name: 'w', role: 'hyperconverged', count: 2 }],
    })
  ),
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
    // datastore_fork is captured (--json) so the record can be adopted onto an
    // off-control replica node before attach (finding #36).
    if (functionName === 'datastore_fork') {
      return Promise.resolve({
        success: true,
        stdout: '{"fork":{"cloneImage":"clone"}}',
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
  it('provisions from the ref-supplied datastore, applies the overlay, records state', async () => {
    mockState();
    const exec = mockExec();

    await replicateRepo({
      repo: 'sqldb',
      cluster: 'prod',
      datastore: 'ds-data',
      replicas: 2,
      image: 'postgres:16',
      port: 5432,
      refresh: '1h',
    });

    const calls = exec.mock.calls.map((c) => c[0]);
    const names = calls.map((c) => c.functionName);
    // The REF supplies the datastore (spec §2.3), so there is no datastore_list
    // inference round-trip any more: ONE snapshot -> (fork, attach, OPEN, label) x2
    // -> apply. Replicas land on off-control nodes (prod-w-1/2), so each fork's
    // record is adopted onto the hosting node before the attach (finding #36).
    //
    // datastore_volumes_open is bug #49's fix and its position is load-bearing: it
    // must follow the attach (there is no mount to open the image on before that)
    // and precede kube_node_label (the label is the PV's nodeAffinity key, i.e. the
    // scheduling gate, so opening first means no pod can ever be scheduled onto a
    // volume that is not yet mounted). Without it the replica bind-mounts the empty
    // directory the block clone carried and comes up healthy, Ready, and EMPTY.
    expect(names).toEqual([
      'datastore_snapshot_create',
      'datastore_fork',
      'datastore_adopt',
      'datastore_attach',
      'datastore_forget',
      'datastore_volumes_open',
      'kube_node_label',
      'datastore_fork',
      'datastore_adopt',
      'datastore_attach',
      'datastore_forget',
      'datastore_volumes_open',
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

  it('refuses a second replica set for the same repo (ONE set per repo, §4.4)', async () => {
    mockState({ 'sqldb-replicas': seededSet });
    mockExec();
    await expect(
      replicateRepo({
        repo: 'sqldb',
        cluster: 'prod',
        datastore: 'ds-data',
        replicas: 2,
        image: 'x',
        port: 1,
      })
    ).rejects.toThrow(/already has a replica set/);
  });

  it('derives the set name from the repo ref, colon and all', async () => {
    mockState();
    const exec = mockExec();
    await replicateRepo({
      repo: 'sqldb:test',
      cluster: 'prod',
      datastore: 'ds-data',
      replicas: 1,
      image: 'x',
      port: 1,
    });
    // A k8s object name and a datastore fork tag both reject `:`, so the ref is
    // slugged for every derived name; the state key follows the same rule.
    expect(Object.keys(stored ?? {})).toEqual(['sqldb-test-replicas']);
    const forks = exec.mock.calls
      .map((c) => c[0])
      .filter((c) => c.functionName === 'datastore_fork');
    expect(forks[0].params?.tag).toBe('sqldb-test-replicas-r1');
  });
});

describe('removeReplicaSet (teardown orchestrator)', () => {
  it('deletes overlay, strips labels, discards forks, drops snapshot, forgets state', async () => {
    mockState({ 'sqldb-replicas': seededSet });
    const exec = mockExec();

    await removeReplicaSet('sqldb');

    const calls = exec.mock.calls.map((c) => c[0]);
    // Each fork's per-volume LUKS images are closed BEFORE its discard-detach (bug
    // #49's mirror): a fork holding a live LUKS mapping and its loop device is BUSY,
    // so a detach that skipped the close would simply fail.
    expect(calls.map((c) => c.functionName)).toEqual([
      'kube_delete',
      'kube_node_label',
      'kube_node_label',
      'datastore_volumes_close',
      'datastore_detach',
      'datastore_volumes_close',
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
    expect(calls.at(-1)?.params).toMatchObject({
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
    await removeReplicaSet('sqldb');
    expect(stored).toEqual({});
  });
});

describe('refreshReplicaSet (rolling one-at-a-time)', () => {
  it('snapshots once, then per replica: HOLD -> bounce -> discard -> re-fork -> re-open', async () => {
    mockState({ 'sqldb-replicas': seededSet });
    const exec = mockExec();

    await refreshReplicaSet('sqldb');

    const calls = exec.mock.calls.map((c) => c[0]);
    expect(calls.map((c) => c.functionName)).toEqual([
      'datastore_snapshot_create',
      // Replica 1 fully, then replica 2 (N-1 keep serving). ★ BUG #41: the node
      // label is STRIPPED FIRST (kube_node_label remove) so the bounced pod is
      // unschedulable and cannot re-mount the OLD fork before the discard-detach
      // wins; provisionOneReplica's trailing kube_node_label re-opens the gate.
      // Each re-fork's record is re-adopted onto the off-control node (#36).
      // ★ BUG #49: the OLD fork's volumes are closed before its discard-detach (a
      // live LUKS mapping makes the fork BUSY, so the detach would burn its retries
      // and throw), and the NEW fork's volumes are opened after its attach and
      // before the label re-opens the scheduling gate. A refresh that re-forked
      // without re-opening would roll the whole set to EMPTY replicas.
      'kube_node_label',
      'kube_delete',
      'datastore_volumes_close',
      'datastore_detach',
      'datastore_fork',
      'datastore_adopt',
      'datastore_attach',
      'datastore_forget',
      'datastore_volumes_open',
      'kube_node_label',
      'kube_node_label',
      'kube_delete',
      'datastore_volumes_close',
      'datastore_detach',
      'datastore_fork',
      'datastore_adopt',
      'datastore_attach',
      'datastore_forget',
      'datastore_volumes_open',
      'kube_node_label',
      'datastore_snapshot_delete',
    ]);
    // The hold: strip BEFORE the bounce, re-stamp AFTER the re-attach.
    const holds = calls.filter((c) => c.functionName === 'kube_node_label');
    expect(holds[0].params).toMatchObject({
      datastore: 'ds-data-sqldb-replicas-r1',
      remove: true,
    });
    expect(holds[1].params?.remove).toBeUndefined();
    expect(calls.indexOf(holds[0])).toBeLessThan(
      calls.findIndex((c) => c.functionName === 'kube_delete')
    );
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
      if (functionName === 'datastore_fork') {
        return Promise.resolve({ success: true, stdout: '{"fork":{}}' }) as never;
      }
      return Promise.resolve({ success: true }) as never;
    });
    const delays: number[] = [];
    __setReplicateDelay((ms) => {
      delays.push(ms);
      return Promise.resolve();
    });

    await refreshReplicaSet('sqldb');

    expect(detachAttempts).toBe(3);
    expect(delays).toEqual([2000, 2000]);
  });
});
