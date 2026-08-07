import { afterEach, describe, expect, it, vi } from 'vitest';
import type { RdcConfig } from '../../../types/index.js';
import { configService } from '../../config/config-resources.js';
import { outputService } from '../../core/output.js';
import { localExecutorService } from '../../executor/local-executor.js';
import {
  forgetReplicaSet,
  getReplicaSet,
  listReplicaSets,
  provisionReplicaDatastores,
  type ReplicaRenderInput,
  recordReplicaSet,
  renderReplicaSet,
} from '../repo-replicate.js';

// The machine-slot pre-flight reaches the account server. Stub it: a unit test
// must not depend on whether the box running it happens to hold a live
// subscription token. Its own behaviour is covered in
// services/__tests__/license-preflight.test.ts.
vi.mock('../../account/license-preflight.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../account/license-preflight.js')>()),
  assertMachineSlotsAvailable: vi.fn().mockResolvedValue(undefined),
}));

afterEach(() => vi.restoreAllMocks());

const renderInput: ReplicaRenderInput = {
  repo: 'sqldb',
  repoGuid: 'guid-sqldb',
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
    // ★ #93 (storage speaks GUID, k8s objects speak name): the PV path into the
    // fork mount is GUID-keyed — the fork is a byte-clone of the parent, whose
    // volumes-open/CSI mount at mounts/volumes/<guid>/<vol>. A NAME-keyed path
    // points at a directory that does not exist and the replica comes up EMPTY,
    // so a regression back to the name must turn this red.
    expect(yaml).toContain(
      'path: /mnt/rediacc-ds/ds-data-sqldb-replicas-r1/mounts/volumes/guid-sqldb/data'
    );
    expect(yaml).not.toContain('mounts/volumes/sqldb/');
    // ...while the k8s OBJECTS keep the name: namespace + Services stay `sqldb`.
    expect(yaml).toContain('namespace: sqldb');
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
  // datastore_fork is captured (--json) so provisionOneReplica can ferry the
  // record to an off-control node via datastore_adopt (finding #36); every
  // other step just needs success.
  return vi
    .spyOn(localExecutorService, 'execute')
    .mockImplementation((opts) =>
      Promise.resolve(
        (opts.functionName === 'datastore_fork'
          ? { success: true, stdout: '{"fork":{"cloneImage":"clone"}}' }
          : { success: true }) as never
      )
    );
}

describe('provisionReplicaDatastores (datastore plane: snapshot + N fork-attach)', () => {
  const base = {
    repo: 'sqldb',
    repoGuid: 'guid-sqldb',
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

  it('ferries the fork record via datastore_adopt off-control, and skips adopt on the control node (finding #36)', async () => {
    vi.spyOn(outputService, 'warn').mockReturnValue(undefined);
    const exec = execMock();
    // nodes = [control cp1, worker w1] — mirrors the live b1src layout where
    // replica 1 lands on the control node and replica 2 on an agent node.
    await provisionReplicaDatastores({
      ...base,
      replicas: 2,
      nodes: [
        { machine: 'cp1', ip: '10.0.0.1' }, // == controlMachine: record already local
        { machine: 'w1', ip: '10.0.0.2' }, // off-control: needs the adopt ferry
      ],
    });
    const calls = exec.mock.calls.map((c) => c[0]);
    // datastore_fork always runs on the control machine, captured for the ferry.
    expect(
      calls.filter((c) => c.functionName === 'datastore_fork').every((c) => c.machineName === 'cp1')
    ).toBe(true);
    // Only the OFF-control replica adopts; the on-control one skips it.
    const adopts = calls.filter((c) => c.functionName === 'datastore_adopt');
    expect(adopts.map((c) => c.machineName)).toEqual(['w1']);
    expect(adopts[0].params?.name).toBe('ds-data:set1-r2');
    expect(typeof adopts[0].params?.record_b64).toBe('string');
    // The adopt must PRECEDE the attach on that node (attach fails otherwise —
    // "not registered on this machine", the live bug this fixes).
    const w1Seq = calls
      .filter(
        (c) =>
          c.machineName === 'w1' &&
          (c.functionName === 'datastore_adopt' || c.functionName === 'datastore_attach')
      )
      .map((c) => c.functionName);
    expect(w1Seq).toEqual(['datastore_adopt', 'datastore_attach']);
    // #40: after the off-control attach, the control's vestigial fork record is
    // forgotten (registry-only) so a later re-fork of the same tag (refresh)
    // does not collide. ONLY the off-control replica; on-control skips it.
    const forgets = calls.filter((c) => c.functionName === 'datastore_forget');
    expect(forgets.map((c) => c.machineName)).toEqual(['cp1']);
    expect(forgets[0].params?.name).toBe('ds-data:set1-r2');
    // Order: forget runs AFTER the off-control attach (fork→adopt→attach→forget).
    const attachIdx = calls.findIndex(
      (c) => c.functionName === 'datastore_attach' && c.machineName === 'w1'
    );
    const forgetIdx = calls.findIndex((c) => c.functionName === 'datastore_forget');
    expect(forgetIdx).toBeGreaterThan(attachIdx);
  });

  it('refuses when the cluster has no nodes', async () => {
    execMock();
    await expect(provisionReplicaDatastores({ ...base, replicas: 2, nodes: [] })).rejects.toThrow(
      /no nodes/
    );
  });

  // ── bug #49: the per-volume LUKS images, and the trap ─────────────────────

  // A datastore fork is a BLOCK-layer clone: it carries the ciphertext
  // repos/<repo>/volumes/<pvc>.img AND the empty directory that image was mounted
  // over. The replica's PV points at that directory. If nothing re-opens the image,
  // the replica mounts the empty dir and comes up healthy, Ready, and EMPTY — the
  // failure has NO symptom except missing data, which is why it must be pinned here
  // rather than left to a live suite.
  it('opens the repo volumes on each fork, AFTER attach and BEFORE the node label', async () => {
    vi.spyOn(outputService, 'warn').mockReturnValue(undefined);
    const exec = execMock();

    await provisionReplicaDatastores({
      ...base,
      replicas: 2,
      nodes: [
        { machine: 'n1', ip: '10.0.0.1' },
        { machine: 'n2', ip: '10.0.0.2' },
      ],
    });

    const calls = exec.mock.calls.map((c) => c[0]);
    const opens = calls.filter((c) => c.functionName === 'datastore_volumes_open');
    expect(opens.length).toBe(2);
    // Scoped to the fork AND the repo: the images live in one repo's folder, and an
    // unscoped open would silently open nothing.
    expect(opens.map((c) => c.params?.name)).toEqual(['ds-data:set1-r1', 'ds-data:set1-r2']);
    // ★ #93 MUTATION CONTROL (found live by B1): the folder on the fork is
    // repos/<GUID> (#83), so the open must speak the GUID — a NAME-based
    // dispatch stats repos/<name>, which does not exist, and aborts every
    // replicate of a real kube repo. Both assertions must hold: reverting to
    // the name turns this red.
    expect(opens.every((c) => c.params?.repo === 'guid-sqldb')).toBe(true);
    expect(opens.some((c) => c.params?.repo === 'sqldb')).toBe(false);
    // Each open runs on the node that HOLDS the fork, not on the control plane.
    expect(opens.map((c) => c.machineName)).toEqual(['n1', 'n2']);

    // The ordering is the safety property. The node label is the PV's nodeAffinity
    // key and therefore the scheduling gate: opening BEFORE the label means a pod
    // can never be scheduled onto a volume that is not yet mounted. Attaching before
    // the open is likewise required — there is no mount to open the image on until
    // the datastore is attached.
    const names = calls.map((c) => c.functionName);
    for (const [i, fork] of ['ds-data:set1-r1', 'ds-data:set1-r2'].entries()) {
      const attachAt = calls.findIndex(
        (c) => c.functionName === 'datastore_attach' && c.params?.name === fork
      );
      const openAt = calls.findIndex(
        (c) => c.functionName === 'datastore_volumes_open' && c.params?.name === fork
      );
      const labelAt = names.indexOf('kube_node_label', attachAt);
      expect(attachAt, `replica ${i + 1}: attach must precede open`).toBeLessThan(openAt);
      expect(openAt, `replica ${i + 1}: open must precede the node label`).toBeLessThan(labelAt);
    }
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
