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
  // The repo's storage identity (#93): replicate resolves the GUID up front and
  // speaks it to every datastore verb; k8s objects keep the name.
  vi.spyOn(configService, 'getRepository').mockImplementation((repoKey: string) =>
    Promise.resolve({ repositoryGuid: `guid-${repoKey.replaceAll(':', '-')}` })
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
    // ★ #93 (storage speaks GUID): the orchestrator resolves the repo's GUID
    // from config and every storage-facing step speaks it — a create that
    // passes the NAME through (skipping resolution) turns this red.
    const opens = calls.filter((c) => c.functionName === 'datastore_volumes_open');
    expect(opens.every((c) => c.params?.repo === 'guid-sqldb')).toBe(true);
    expect(opens.some((c) => c.params?.repo === 'sqldb')).toBe(false);

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
  it('deletes overlay, discards forks (close before detach), strips labels, drops snapshot, VERIFIES, then forgets', async () => {
    mockState({ 'sqldb-replicas': seededSet });
    const exec = mockExec();

    await removeReplicaSet('sqldb');

    const calls = exec.mock.calls.map((c) => c[0]);
    // ORDER is the safety property (bug #95): delete the WHOLE overlay FIRST so the
    // replica pods terminate and release their fork mounts, THEN per fork close its
    // LUKS volumes (#49 mirror) and detach --discard, THEN strip the labels, drop
    // the snapshot, and VERIFY each fork is gone (datastore_list per node) before
    // forgetting state. The old order stripped labels first and detached with a
    // warn-and-continue swallow — the false-success the fix kills.
    expect(calls.map((c) => c.functionName)).toEqual([
      'kube_delete',
      'datastore_volumes_close',
      'datastore_detach',
      'datastore_volumes_close',
      'datastore_detach',
      'kube_node_label',
      'kube_node_label',
      'datastore_snapshot_delete',
      'datastore_list',
      'datastore_list',
    ]);
    // The overlay delete is replica-set scoped (whole-overlay form, no ordinal) and
    // CAPTURED — a failure surfaces what it actually deleted (bug #95 mechanism b).
    expect(calls[0]).toMatchObject({
      machineName: 'cp1',
      captureOutput: true,
      params: { namespace: 'sqldb', replica_set: 'sqldb-replicas' },
    });
    expect(calls[0].params?.pod_ordinal).toBeUndefined();
    // Per fork: close precedes detach --discard (a live LUKS mapping is BUSY).
    for (const fork of ['ds-data:sqldb-replicas-r1', 'ds-data:sqldb-replicas-r2']) {
      const closeAt = calls.findIndex(
        (c) => c.functionName === 'datastore_volumes_close' && c.params?.name === fork
      );
      const detachAt = calls.findIndex(
        (c) => c.functionName === 'datastore_detach' && c.params?.name === fork
      );
      expect(closeAt).toBeGreaterThanOrEqual(0);
      expect(closeAt, `${fork}: close must precede detach --discard`).toBeLessThan(detachAt);
      expect(calls[detachAt].params?.discard).toBe(true);
    }
    // Labels stripped per fork (mount-style datastore name), on the control node.
    const labels = calls.filter((c) => c.functionName === 'kube_node_label');
    expect(labels.map((c) => c.params?.datastore)).toEqual([
      'ds-data-sqldb-replicas-r1',
      'ds-data-sqldb-replicas-r2',
    ]);
    expect(labels.every((c) => c.params?.remove === true)).toBe(true);
    // The set's snapshot is dropped after the clones are discarded.
    const snap = calls.find((c) => c.functionName === 'datastore_snapshot_delete');
    expect(snap?.params).toMatchObject({ name: 'ds-data', snapshot: 'replicate-sqldb-replicas' });
    // Verification queries each replica node; the mock list holds neither fork.
    const lists = calls.filter((c) => c.functionName === 'datastore_list');
    expect(lists.map((c) => c.machineName)).toEqual(['prod-w-1', 'prod-w-2']);
    // State forgotten LAST, only after the verified teardown.
    expect(stored).toEqual({});
  });

  it('REJECTS and PRESERVES state when a fork detach stays busy (bug #95 — no false success)', async () => {
    mockState({ 'sqldb-replicas': seededSet });
    // The replica pod outlived the detach, so datastore_detach never clears. The
    // OLD teardown swallowed this (tryStep warn-and-continue) and forgot state
    // anyway — the false success. Now the discard is HARD: it must propagate and
    // NEVER reach the state-forget.
    const forget = vi.spyOn(configService, 'setStateBucket');
    vi.spyOn(localExecutorService, 'execute').mockImplementation(({ functionName }) => {
      if (functionName === 'datastore_detach') {
        return Promise.resolve({
          success: false,
          error: 'device-mapper: remove ioctl ... Device or resource busy',
        }) as never;
      }
      return Promise.resolve({ success: true }) as never;
    });

    await expect(removeReplicaSet('sqldb')).rejects.toThrow(/NOT removed.*could not be discarded/s);

    // The state-forget (the only setStateBucket call remove makes) never fired —
    // reverting the discard to a swallow makes this go red (state cleared).
    expect(forget).not.toHaveBeenCalled();
    expect(stored).toEqual({ 'sqldb-replicas': seededSet });
  });

  it('REJECTS naming the survivor when a fork is still attached after the discard', async () => {
    mockState({ 'sqldb-replicas': seededSet });
    const forget = vi.spyOn(configService, 'setStateBucket');
    // Every teardown step SUCCEEDS, but datastore_list still enumerates r1's fork:
    // the discard succeeded-but-did-nothing. Verify-before-forget catches it and
    // fails loud naming the survivor, leaving state intact for the retry.
    vi.spyOn(localExecutorService, 'execute').mockImplementation(
      ({ functionName, machineName }) => {
        if (functionName === 'datastore_list') {
          const forks = machineName === 'prod-w-1' ? [{ name: 'ds-data:sqldb-replicas-r1' }] : [];
          return Promise.resolve({ success: true, stdout: JSON.stringify(forks) }) as never;
        }
        return Promise.resolve({ success: true }) as never;
      }
    );

    await expect(removeReplicaSet('sqldb')).rejects.toThrow(
      /still attached: ds-data:sqldb-replicas-r1 on prod-w-1/
    );
    expect(forget).not.toHaveBeenCalled();
    expect(stored).toEqual({ 'sqldb-replicas': seededSet });
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
