import { afterEach, describe, expect, it, vi } from 'vitest';
import type { RdcConfig } from '../../../types/index.js';
import { configService } from '../../config/config-resources.js';
import { outputService } from '../../core/output.js';
import { localExecutorService } from '../../executor/local-executor.js';
import {
  discardReplicaDatastores,
  forgetReplicaSet,
  getReplicaSet,
  listReplicaSets,
  provisionReplicaDatastores,
  recordReplicaSet,
  type ReplicaRenderInput,
  renderReplicaSet,
} from '../repo-replicate.js';

afterEach(() => vi.restoreAllMocks());

const renderInput: ReplicaRenderInput = {
  repo: 'sqldb',
  setName: 'sqldb-replicas',
  datastore: 'ds-data',
  primaryApp: 'sqldb-primary',
  image: 'postgres:16',
  port: 5432,
  pvc: 'data',
  headless: false,
  replicas: [
    {
      index: 1,
      datastoreLabel: 'rediacc.io/ds-ds-data-sqldb-replicas-r1',
      mountPath: '/mnt/rediacc-ds/ds-data-sqldb-replicas-r1',
    },
    {
      index: 2,
      datastoreLabel: 'rediacc.io/ds-ds-data-sqldb-replicas-r2',
      mountPath: '/mnt/rediacc-ds/ds-data-sqldb-replicas-r2',
    },
  ],
};

describe('renderReplicaSet (spec 05 §1 manifest plumbing)', () => {
  it('renders one nodeAffinity-pinned local PV per replica + StatefulSet + two Services', () => {
    const yaml = renderReplicaSet(renderInput);
    // One PV per replica, each pinned to that replica's node datastore label.
    expect(yaml).toContain('name: sqldb-replicas-1-data');
    expect(yaml).toContain('name: sqldb-replicas-2-data');
    expect(yaml).toContain('key: rediacc.io/ds-ds-data-sqldb-replicas-r1');
    expect(yaml).toContain(
      'path: /mnt/rediacc-ds/ds-data-sqldb-replicas-r1/mounts/volumes/sqldb/data'
    );
    // StatefulSet: N replicas, anti-affinity, REDIACC_ROLE=replica.
    expect(yaml).toContain('kind: StatefulSet');
    expect(yaml).toContain('replicas: 2');
    expect(yaml).toContain('podAntiAffinity');
    expect(yaml).toContain('value: replica');
    // claimRef pre-binds each PV to the PVC kubectl will mint from the
    // volumeClaimTemplate: <template>-<sts>-<0-based ordinal>.
    expect(yaml).toContain('name: data-sqldb-replicas-0');
    expect(yaml).toContain('name: data-sqldb-replicas-1');
    // Two Services: -rw -> the PRIMARY app, -ro -> the replica-set label.
    expect(yaml).toContain('name: sqldb-rw');
    expect(yaml).toContain('app: sqldb-primary');
    expect(yaml).toContain('name: sqldb-ro');
    expect(yaml).toContain('rediacc.io/replica-set: sqldb-replicas');
  });

  it('--headless makes the read Service headless (clusterIP: None)', () => {
    const yaml = renderReplicaSet({ ...renderInput, headless: true });
    expect(yaml).toContain('clusterIP: None');
  });
});

function execMock() {
  return vi.spyOn(localExecutorService, 'execute').mockResolvedValue({ success: true } as never);
}

describe('provisionReplicaDatastores (datastore plane: snapshot + N fork-attach)', () => {
  const base = {
    repo: 'sqldb',
    setName: 'set1',
    datastore: 'ds-data',
    snapshot: 'replicate-set1',
    controlMachine: 'cp1',
    controlMount: '/mnt/rediacc-ds/ds-control-prod',
  };

  it('takes ONE snapshot then forks+attaches+labels N replicas spread round-robin', async () => {
    vi.spyOn(outputService, 'warn').mockReturnValue(undefined);
    const exec = execMock();

    const { placements, forks } = await provisionReplicaDatastores({
      ...base,
      replicas: 3,
      nodes: [
        { machine: 'n1', ip: '10.0.0.1' },
        { machine: 'n2', ip: '10.0.0.2' },
      ],
    });

    const calls = exec.mock.calls.map((c) => c[0]);
    const names = calls.map((c) => c.functionName);
    // ONE snapshot, then fork+attach+node-label per replica.
    expect(names.filter((n) => n === 'datastore_snapshot_create').length).toBe(1);
    expect(names.filter((n) => n === 'datastore_fork').length).toBe(3);
    expect(names.filter((n) => n === 'datastore_attach').length).toBe(3);
    expect(names.filter((n) => n === 'kube_node_label').length).toBe(3);
    // Snapshot + forks run on the control machine; all forks clone the ONE snapshot.
    const snap = calls.find((c) => c.functionName === 'datastore_snapshot_create');
    expect(snap).toMatchObject({
      machineName: 'cp1',
      params: { name: 'ds-data', snapshot: 'replicate-set1' },
    });
    const forkCalls = calls.filter((c) => c.functionName === 'datastore_fork');
    expect(forkCalls.every((c) => c.params?.snapshot === 'replicate-set1')).toBe(true);
    // Attaches are --writes local, spread round-robin across the 2 nodes (n1,n2,n1).
    const attaches = calls.filter((c) => c.functionName === 'datastore_attach');
    expect(attaches.every((c) => c.params?.writes === 'local')).toBe(true);
    expect(attaches.map((c) => c.machineName)).toEqual(['n1', 'n2', 'n1']);
    // Each hosting node gets the FORK's own datastore label (PV pin key, F3),
    // stamped through the control plane by InternalIP.
    const labels = calls.filter((c) => c.functionName === 'kube_node_label');
    expect(labels.every((c) => c.machineName === 'cp1')).toBe(true);
    expect(labels.map((c) => c.params?.node_ip)).toEqual(['10.0.0.1', '10.0.0.2', '10.0.0.1']);
    expect(labels.map((c) => c.params?.datastore)).toEqual([
      'ds-data-set1-r1',
      'ds-data-set1-r2',
      'ds-data-set1-r3',
    ]);
    // Placements pin each PV to the fork's label + mount; forks record key + node.
    expect(placements.map((p) => p.mountPath)).toEqual([
      '/mnt/rediacc-ds/ds-data-set1-r1',
      '/mnt/rediacc-ds/ds-data-set1-r2',
      '/mnt/rediacc-ds/ds-data-set1-r3',
    ]);
    expect(placements.map((p) => p.datastoreLabel)).toEqual([
      'rediacc.io/ds-ds-data-set1-r1',
      'rediacc.io/ds-ds-data-set1-r2',
      'rediacc.io/ds-ds-data-set1-r3',
    ]);
    expect(forks).toEqual([
      { index: 1, fork: 'ds-data:set1-r1', node: 'n1' },
      { index: 2, fork: 'ds-data:set1-r2', node: 'n2' },
      { index: 3, fork: 'ds-data:set1-r3', node: 'n1' },
    ]);
  });

  it('refuses when the cluster has no nodes', async () => {
    execMock();
    await expect(provisionReplicaDatastores({ ...base, replicas: 2, nodes: [] })).rejects.toThrow(
      /no nodes/
    );
  });

  it('discardReplicaDatastores detaches --discard every fork (best-effort)', async () => {
    vi.spyOn(outputService, 'warn').mockReturnValue(undefined);
    const exec = execMock();
    await discardReplicaDatastores({
      repo: 'sqldb',
      datastore: 'ds-data',
      cluster: 'prod',
      createdAt: 'now',
      replicas: [
        { index: 1, fork: 'ds-data:set1-r1', node: 'n1' },
        { index: 2, fork: 'ds-data:set1-r2', node: 'n2' },
      ],
    });
    const detaches = exec.mock.calls
      .map((c) => c[0])
      .filter((c) => c.functionName === 'datastore_detach' && c.params?.discard === true);
    expect(detaches.map((c) => c.params?.name)).toEqual(['ds-data:set1-r1', 'ds-data:set1-r2']);
  });
});

describe('replica-set managed state (R2-F17 CRUD)', () => {
  it('record → list → get → forget round-trips through config state', async () => {
    let stored: Record<string, unknown> | undefined;
    vi.spyOn(configService, 'getCurrent').mockImplementation(
      () => Promise.resolve({ state: { replicaSets: stored } }) as never
    );
    vi.spyOn(configService, 'setStateBucket').mockImplementation((_key, sets) => {
      stored = sets as Record<string, unknown>;
      return Promise.resolve();
    });

    const set = {
      repo: 'sqldb',
      datastore: 'ds-data',
      cluster: 'prod',
      createdAt: '2026-07-11T00:00:00Z',
      replicas: [{ index: 1, fork: 'ds-data:s-r1', node: 'n1' }],
    };
    await recordReplicaSet('s', set);
    expect(await listReplicaSets()).toEqual({ s: set });
    expect(await getReplicaSet('s')).toEqual(set);
    await forgetReplicaSet('s');
    expect(await getReplicaSet('s')).toBeUndefined();
  });
});

// Ensure the RdcConfig type import is exercised (state shape).
const _typecheck: RdcConfig | undefined = undefined;
void _typecheck;
