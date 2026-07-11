import { expect, test } from '@playwright/test';
import { BridgeTestRunner } from '../../src/utils/bridge/BridgeTestRunner';
import type { ExecResult } from '../../src/utils/bridge/types';

// Suite 17 (`Bridge K8s Multinode` job): a multi-node k3s cluster + whole-cluster
// fork/migrate on the DATASTORE-CLUSTER model (redesign spec 06 §17). It ports
// the wave-7 proof off the DELETED per-namespace bring-up (`kube apply
// --ceph-pool`, `kube_namespace_*`) onto the surviving anchor+rejoin surface,
// while KEEPING the multinode fork/migrate PROOF SHAPE:
//
//   - MULTI-NODE bring-up: an anchor cluster (control plane inside a
//     cluster-labeled ceph control datastore on worker 1) + a real-NIC agent
//     join on worker 2. The kube repo rides the runtime-generic `repository up`
//     dispatch (kube arm) with a DECLARED-VOLUME manifest — NOT the removed
//     `kube apply --ceph-pool` / `kube_namespace_create`.
//   - WHOLE-CLUSTER FORK (anchor+rejoin, spec 04 §2 / P3-w1 orchestrator): ONE
//     atomic GROUP snapshot across the cluster's ceph datastores → clone each
//     member → attach on the fork nodes → `kube identity-rewrite --operation
//     fork` re-mints the control-plane PKI (F1-F8 + secret scrub + ROLE=fork,
//     the CT-01k/CT-04 half at cluster scope) → a FRESH agent joins the fork's
//     new CA (the anchor+rejoin difference from the old per-node rewrite). The
//     fork's kine diverges; the parent is untouched.
//   - CLUSTER MIGRATE (in-Ceph fenced remap, spec 04 §3): drain + detach + fenced
//     re-attach (`--force`) + `identity-rewrite --operation migrate` (CA
//     PRESERVED, networkID kept), with a measured cutover. Zero data copy.
//
// RED-UNTIL-LIVE-RUN (spec 06 authoring bar): authored to COMPILE + keep the
// coverage gate green; the BODY is not executed by this wave (needs the
// multi-VM ceph harness + a RAM window — carry-in 8 live-fencing-race folds in
// here). The live follow-up (P3 gate item 5) gates P3 when it passes locally.
//
// Gated on K8S_MODE=1 + a ceph topology (VM_CEPH_NODES) + TWO worker VMs.
const enabled = process.env.K8S_MODE === '1';
const cephNodes = (process.env.VM_CEPH_NODES ?? '').trim();
const workers = (process.env.VM_WORKERS ?? '').trim().split(/\s+/).filter(Boolean);
const canRun = enabled && cephNodes.length > 0 && workers.length >= 2;

const NET = process.env.VM_NET_BASE ?? '192.168.111';
const W1_IP = `${NET}.${workers[0] ?? '11'}`; // control plane (real private NIC)
const W2_IP = `${NET}.${workers[1] ?? '12'}`; // agent (real private NIC)
// Secondary IP the fork control plane relocates onto (S1 verdict 2: parent
// stopped while the fork runs — no two k3s in one host netns).
const W1_FORK_IP = `${NET}.211`;
const NIC = 'ens1';

const K3S = '/usr/local/bin/rediacc-k3s';
const CLUSTER = 'mnprod';
const CTRL_DS = `ds-control-${CLUSTER}`;
const CTRL_MOUNT = `/mnt/rediacc-ds/${CTRL_DS}`;
const SRV_NET = '3072';
const AGT_NET = '3136';
const DATA_DS = 'mnshop';
const DATA_MOUNT = `/mnt/rediacc-ds/${DATA_DS}`;
const POOL = `mn${Date.now().toString(36)}`;
const REPO = 'shop';
const REPO_NET = '3200';
const NS = REPO;
const SC = `rediacc-ds-${DATA_DS}`;
const KC = `${CTRL_MOUNT}/.rediacc/k3s/kubeconfig.yaml`;
const NODE1 = `rediacc${workers[0] ?? '11'}`;
const NODE2 = `rediacc${workers[1] ?? '12'}`;

// The fork (anchor+rejoin): `<parent>:f1` records, mounted at `<parent>-f1`.
const FORK_TAG = 'f1';
const SNAP = 'forksnap';
const FORK_CTRL_MOUNT = `${CTRL_MOUNT}-${FORK_TAG}`;
const FORK_NET = '3264';
const FKC = `${FORK_CTRL_MOUNT}/.rediacc/k3s/kubeconfig.yaml`;

// A ceph-backed kube repo: a ConfigMap that lives in kine (what a whole-cluster
// fork carries + diverges) + an annotated Service + a Deployment pinned to the
// AGENT node with a PVC naming the repo's rediacc ceph StorageClass. The declared
// volume drives ProvisionVolumes; the manifests/ deploy rides the Deploy phase.
const APP_MANIFEST = `apiVersion: v1
kind: ConfigMap
metadata:
  name: clusterstate
data:
  marker: parent-v1
---
apiVersion: v1
kind: Service
metadata:
  name: web
  annotations:
    rediacc.service_port: "80"
spec:
  selector:
    app: web
  ports:
    - port: 80
      targetPort: 80
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: data
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: ${SC}
  resources:
    requests:
      storage: 1Gi
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
spec:
  replicas: 1
  selector:
    matchLabels:
      app: web
  template:
    metadata:
      labels:
        app: web
    spec:
      nodeSelector:
        kubernetes.io/hostname: ${NODE2}
      securityContext:
        runAsNonRoot: true
        runAsUser: 65534
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: web
          image: busybox:1.36
          command: ["sh", "-c", "test -s /data/marker.txt || echo original-data > /data/marker.txt; exec tail -f /dev/null"]
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop: [ALL]
          volumeMounts:
            - name: data
              mountPath: /data
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: data
`;

const REDIACCFILE = `#!/usr/bin/env bash
up() { :; }
down() { :; }
health() { exit 0; }
`;

test.describe
  .serial('multi-node cluster fork + migrate (datastore-cluster) @bridge @kube @k8s @multinode', () => {
    test.skip(!canRun, 'Requires K8S_MODE=1, VM_CEPH_NODES, and TWO worker VMs');
    test.setTimeout(900_000);

    let w1: BridgeTestRunner; // control plane node
    let w2: BridgeTestRunner; // agent node
    let cephNode: BridgeTestRunner;

    const kubectlOn = async (
      runner: BridgeTestRunner,
      kc: string,
      args: string
    ): Promise<ExecResult> =>
      runner.executeViaBridge(`sudo ${K3S} kubectl --kubeconfig ${kc} ${args}`);

    const writeFileOn = async (
      runner: BridgeTestRunner,
      path: string,
      content: string
    ): Promise<void> => {
      const b64 = Buffer.from(content).toString('base64');
      const res = await runner.executeViaBridge(
        `echo ${b64} | base64 -d | sudo tee ${path} >/dev/null`
      );
      expect(res.code, `write ${path}`).toBe(0);
    };

    const poll = async (fn: () => Promise<boolean>, timeoutMs = 240_000, stepMs = 5_000) => {
      const attempts = Math.max(1, Math.ceil(timeoutMs / stepMs));
      for (let i = 0; i < attempts; i++) {
        if (await fn()) return true;
        await new Promise((res) => setTimeout(res, stepMs));
      }
      return fn();
    };

    const readyNodeCount = async (kc: string): Promise<number> => {
      const res = await kubectlOn(w1, kc, 'get nodes --no-headers');
      if (res.code !== 0) return -1;
      return res.stdout.split('\n').filter((l) => /^\S+\s+Ready\b/.test(l.trim())).length;
    };

    const internalIP = async (kc: string, node: string): Promise<string> => {
      const res = await kubectlOn(
        w1,
        kc,
        `get node ${node} -o jsonpath="{.status.addresses[?(@.type==\\"InternalIP\\")].address}"`
      );
      return res.stdout.trim();
    };

    const uncordon = async (kc: string, nodes: string[]): Promise<void> => {
      for (const n of nodes) await kubectlOn(w1, kc, `uncordon ${n}`);
    };

    const cmMarker = async (kc: string): Promise<string> => {
      const res = await kubectlOn(
        w1,
        kc,
        `-n ${NS} get configmap clusterstate -o jsonpath="{.data.marker}"`
      );
      return res.stdout.trim();
    };

    const podRunningOn = async (kc: string, node: string): Promise<boolean> => {
      const res = await kubectlOn(w1, kc, `-n ${NS} get pod -l app=web -o wide --no-headers`);
      return res.code === 0 && /\sRunning\s/.test(res.stdout) && res.stdout.includes(node);
    };

    const stageCephClient = async (runner: BridgeTestRunner): Promise<void> => {
      for (const f of ['ceph.conf', 'ceph.client.admin.keyring']) {
        const read = await cephNode.executeViaBridge(`sudo base64 -w0 /etc/ceph/${f}`);
        expect(read.code, `read /etc/ceph/${f}`).toBe(0);
        await runner.executeViaBridge('sudo mkdir -p /etc/ceph');
        await writeFileOn(
          runner,
          `/etc/ceph/${f}`,
          Buffer.from(read.stdout.trim(), 'base64').toString()
        );
      }
      await runner.executeViaBridge('sudo modprobe rbd || true');
    };

    // Author the kube repo-as-folder on the data datastore.
    const writeRepoFolder = async (): Promise<void> => {
      const repoPath = `${DATA_MOUNT}/repos/${REPO}`;
      await w1.executeViaBridge(`sudo mkdir -p ${repoPath}/manifests`);
      await writeFileOn(w1, `${repoPath}/manifests/app.yaml`, APP_MANIFEST);
      await writeFileOn(w1, `${repoPath}/Rediaccfile`, REDIACCFILE);
    };

    const teardownAll = async (): Promise<void> => {
      // Fork (secondary IP + fork records).
      await w1.executeViaBridge(
        `sudo renet kube uninstall --mount-path ${FORK_CTRL_MOUNT} --network-id ${FORK_NET} 2>/dev/null; true`
      );
      await w1.executeViaBridge(
        `sudo renet datastore detach --name ${CTRL_DS}:${FORK_TAG} --discard 2>/dev/null; true`
      );
      await w1.executeViaBridge(
        `sudo renet datastore detach --name ${DATA_DS}:${FORK_TAG} --discard 2>/dev/null; true`
      );
      await w1.executeViaBridge(`sudo ip addr del ${W1_FORK_IP}/24 dev ${NIC} 2>/dev/null; true`);
      // Agent + parent control.
      await w2.executeViaBridge(
        `sudo renet kube uninstall --mount-path ${CTRL_MOUNT} --network-id ${AGT_NET} 2>/dev/null; true`
      );
      await w1.executeViaBridge(
        `sudo renet kube uninstall --mount-path ${CTRL_MOUNT} --network-id ${SRV_NET} 2>/dev/null; true`
      );
      await w1.executeViaBridge(`sudo renet datastore detach --name ${DATA_DS} 2>/dev/null; true`);
      await w1.executeViaBridge(`sudo renet datastore delete --name ${DATA_DS} 2>/dev/null; true`);
      await w1.executeViaBridge(`sudo renet datastore detach --name ${CTRL_DS} 2>/dev/null; true`);
      await w1.executeViaBridge(`sudo renet datastore delete --name ${CTRL_DS} 2>/dev/null; true`);
    };

    test.beforeAll(async () => {
      w1 = BridgeTestRunner.forWorker(1);
      w2 = BridgeTestRunner.forWorker(2);
      cephNode = BridgeTestRunner.forCeph();
      await teardownAll();
    });

    test.afterAll(async () => {
      if (process.env.KEEP_CLUSTER === '1') return;
      await teardownAll().catch(() => undefined);
      await cephNode.cephPoolDelete(POOL).catch(() => undefined);
    });

    test('1. Ceph healthy, a dedicated pool, and rbd client staged on both workers', async () => {
      expect(cephNode.isSuccess(await cephNode.cephHealth())).toBe(true);
      expect(cephNode.isSuccess(await cephNode.cephPoolCreate(POOL))).toBe(true);
      const init = await cephNode.executeViaBridge(`sudo rbd pool init ${POOL}`);
      expect(init.code, init.stderr).toBe(0);
      await stageCephClient(w1);
      await stageCephClient(w2);
    });

    test('2. multi-node anchor cluster: control plane on w1 + real-NIC agent join on w2', async () => {
      // Anchor control plane inside a cluster-labeled ceph control datastore.
      expect(
        w1.isSuccess(
          await w1.datastoreCreate({
            name: CTRL_DS,
            backend: 'ceph',
            size: '10G',
            pool: POOL,
            cluster: CLUSTER,
          })
        )
      ).toBe(true);
      expect(w1.isSuccess(await w1.datastoreAttach({ name: CTRL_DS }))).toBe(true);
      const srvInstall = await w1.executeViaBridge(
        `sudo renet kube install --mount-path ${CTRL_MOUNT} --network-id ${SRV_NET} --role server --bind-ip ${W1_IP}`,
        540_000
      );
      expect(srvInstall.code, srvInstall.stderr).toBe(0);
      expect(await poll(() => readyNodeCount(KC).then((n) => n >= 1), 150_000)).toBe(true);
      expect(await internalIP(KC, NODE1)).toBe(W1_IP);

      // Agent joins from w2 on its real NIC. The agent attaches the cluster's
      // ceph control datastore to reach the embedded control plane.
      expect(w2.isSuccess(await w2.datastoreAttach({ name: CTRL_DS }))).toBe(true);
      const tokenRes = await w1.kubeJoinToken({ mountPath: CTRL_MOUNT, networkId: SRV_NET });
      const token = /K10\S+/.exec(tokenRes.stdout + tokenRes.stderr)?.[0];
      expect(token, 'join token').toBeTruthy();
      const join = await w2.executeViaBridge(
        `sudo renet kube join --mount-path ${CTRL_MOUNT} --network-id ${AGT_NET} --role agent ` +
          `--token ${token} --server https://${W1_IP}:6443 --bind-ip ${W2_IP}`,
        540_000
      );
      expect(join.code, join.stderr).toBe(0);
      expect(await poll(() => readyNodeCount(KC).then((n) => n >= 2), 150_000)).toBe(true);
      expect(await internalIP(KC, NODE2)).toBe(W2_IP);
    });

    test('3. kube repo up via the datastore dispatch: declared ceph volume + agent-pinned pod + kine state', async () => {
      // Ceph data datastore (cluster backref ⇒ KubeRuntime dispatch).
      expect(
        w1.isSuccess(
          await w1.datastoreCreate({
            name: DATA_DS,
            backend: 'ceph',
            size: '2G',
            pool: POOL,
            cluster: CLUSTER,
          })
        )
      ).toBe(true);
      expect(w1.isSuccess(await w1.datastoreAttach({ name: DATA_DS }))).toBe(true);
      await writeRepoFolder();

      // repository up (kube arm) — replaces the deleted `kube apply --ceph-pool`
      // + kube_namespace_create: ApplyIsolation → ProvisionVolumes → InjectSecrets
      // → Deploy, all from the declared-volume manifest.
      const up = await w1.executeViaBridge(
        `sudo renet repository up --name ${REPO} --datastore ${DATA_MOUNT} --network-id ${REPO_NET}`,
        300_000
      );
      expect(up.code, up.stderr).toBe(0);

      // repository status reports the repo up (runtime-generic verb).
      const status = await w1.repositoryStatus(REPO, DATA_MOUNT);
      expect(w1.isSuccess(status)).toBe(true);

      // The PVC binds, the pod runs on the AGENT node, kine carries the ConfigMap.
      expect(
        await poll(
          async () =>
            (await kubectlOn(w1, KC, `-n ${NS} get pvc data --no-headers`)).stdout.includes(
              'Bound'
            ),
          300_000
        )
      ).toBe(true);
      expect(await poll(() => podRunningOn(KC, NODE2), 180_000)).toBe(true);
      expect(await cmMarker(KC)).toBe('parent-v1');
    });

    test('4. whole-cluster fork (anchor+rejoin): group snap → clone → identity-rewrite fork → fresh agent join', async () => {
      const t0 = Date.now();

      // ONE atomic group snapshot across the cluster's ceph datastores — the
      // parent is NOT stopped for the snapshot (crash-consistent).
      expect(
        w1.isSuccess(await w1.datastoreSnapshotCreate({ group: CLUSTER, snapshot: SNAP }))
      ).toBe(true);
      for (const parent of [CTRL_DS, DATA_DS]) {
        expect(
          w1.isSuccess(
            await w1.datastoreFork({ parent, tag: FORK_TAG, snapshot: SNAP, group: CLUSTER })
          )
        ).toBe(true);
      }

      // S1 verdict 2: two k3s cannot co-tenant one host netns, so stop the parent
      // (drain both nodes) before the fork control plane comes up on w1's
      // secondary IP. carry-in 8 (live fencing race) is exercised here.
      const prep1 = await w1.kubePrepFork({
        mountPath: CTRL_MOUNT,
        networkId: SRV_NET,
        node: NODE1,
      });
      expect(w1.isSuccess(prep1), `prep-fork server: ${prep1.stderr}`).toBe(true);
      const prep2 = await w2.kubePrepFork({
        mountPath: CTRL_MOUNT,
        networkId: AGT_NET,
        node: NODE2,
      });
      expect(w2.isSuccess(prep2), `prep-fork agent: ${prep2.stderr}`).toBe(true);

      // Attach the fork clones on w1 with --writes local, relocate onto a
      // secondary IP.
      for (const parent of [CTRL_DS, DATA_DS]) {
        expect(
          w1.isSuccess(await w1.datastoreAttach({ name: `${parent}:${FORK_TAG}`, writes: 'local' }))
        ).toBe(true);
      }
      await w1.executeViaBridge(`sudo ip addr add ${W1_FORK_IP}/24 dev ${NIC} 2>/dev/null; true`);

      // identity-rewrite --operation fork on the fork control plane: F1-F8 PKI
      // re-mint + secret scrub + ROLE=fork (the CT-01k/CT-04 half at cluster
      // scope), retagged to the fork networkID.
      const idFork = await w1.kubeIdentityRewrite({
        mountPath: FORK_CTRL_MOUNT,
        operation: 'fork',
        mode: 'server',
        newNodeIp: W1_FORK_IP,
        newNetworkId: FORK_NET,
        role: 'fork',
        writes: 'local',
      });
      expect(w1.isSuccess(idFork), (idFork.stdout + idFork.stderr).slice(-800)).toBe(true);
      expect(await poll(() => readyNodeCount(FKC).then((n) => n >= 1), 150_000)).toBe(true);

      // Anchor+rejoin: the agent is a FRESH join to the fork's NEW CA (not a
      // per-node identity rewrite — the disposable-agent model, dest count free).
      const forkTok = await w1.kubeJoinToken({ mountPath: FORK_CTRL_MOUNT, networkId: FORK_NET });
      const token = /K10\S+/.exec(forkTok.stdout + forkTok.stderr)?.[0];
      expect(token, 'fork join token (fresh CA)').toBeTruthy();
      const join = await w2.executeViaBridge(
        `sudo renet kube join --mount-path ${FORK_CTRL_MOUNT} --network-id ${FORK_NET} --role agent ` +
          `--token ${token} --server https://${W1_FORK_IP}:6443 --bind-ip ${W2_IP}`,
        540_000
      );
      expect(join.code, `fresh agent join: ${join.stderr}`).toBe(0);
      expect(await poll(() => readyNodeCount(FKC).then((n) => n >= 2), 150_000)).toBe(true);
      await uncordon(FKC, [NODE1, NODE2]);
      process.stdout.write(
        `[suite17] whole-cluster anchor+rejoin fork wall-time: ${Date.now() - t0}ms\n`
      );

      // The whole cluster's kine state came across, then diverge it.
      expect(await cmMarker(FKC)).toBe('parent-v1');
      const patch = await kubectlOn(
        w1,
        FKC,
        `-n ${NS} patch configmap clusterstate --type merge -p '{"data":{"marker":"fork-v2"}}'`
      );
      expect(patch.code, patch.stderr).toBe(0);
      expect(await cmMarker(FKC)).toBe('fork-v2');
    });

    test('5. parent untouched: tear the fork down, restart the parent, its kine is unchanged', async () => {
      // Bring the fork DOWN before the parent UP (co-tenancy = NO).
      await w2.executeViaBridge(
        `sudo renet kube uninstall --mount-path ${FORK_CTRL_MOUNT} --network-id ${FORK_NET} 2>/dev/null; true`
      );
      await w1.executeViaBridge(
        `sudo renet kube uninstall --mount-path ${FORK_CTRL_MOUNT} --network-id ${FORK_NET} 2>/dev/null; true`
      );
      await w1.executeViaBridge(
        `sudo renet datastore detach --name ${CTRL_DS}:${FORK_TAG} --discard 2>/dev/null; true`
      );
      await w1.executeViaBridge(
        `sudo renet datastore detach --name ${DATA_DS}:${FORK_TAG} --discard 2>/dev/null; true`
      );
      await w1.executeViaBridge(`sudo ip addr del ${W1_FORK_IP}/24 dev ${NIC} 2>/dev/null; true`);

      // Restart the parent's k3s units (identity unchanged; its ceph datastore
      // was never modified by the fork — the clone diverged CoW).
      const startSrv = await w1.executeViaBridge(`sudo systemctl start rediacc-k3s-${SRV_NET}`);
      expect(startSrv.code, `restart parent server: ${startSrv.stderr}`).toBe(0);
      await w2.executeViaBridge(`sudo systemctl start rediacc-k3s-${AGT_NET}`);
      expect(await poll(() => readyNodeCount(KC).then((n) => n >= 2), 180_000)).toBe(true);
      await uncordon(KC, [NODE1, NODE2]);
      // The parent's ConfigMap is still parent-v1: the fork's write was isolated.
      expect(await cmMarker(KC)).toBe('parent-v1');
    });

    test('6. cluster migrate (in-Ceph fenced remap): detach → fenced re-attach → identity-rewrite migrate', async () => {
      // Tear the multi-node cluster down to a single control node to migrate.
      await w2.executeViaBridge(
        `sudo renet kube uninstall --mount-path ${CTRL_MOUNT} --network-id ${AGT_NET}`
      );
      await w2.executeViaBridge(`sudo renet datastore detach --name ${CTRL_DS} 2>/dev/null; true`);
      const cutStart = Date.now();

      // In-Ceph fenced remap (zero data copy): drain + stop the control plane,
      // detach (release the ceph lock), fenced re-attach (--force fences a stale
      // holder, same mount path = mount-path stability), then identity-rewrite
      // --operation migrate (CA PRESERVED, networkID kept, IP-only).
      const prep = await w1.kubePrepFork({
        mountPath: CTRL_MOUNT,
        networkId: SRV_NET,
        node: NODE1,
      });
      expect(w1.isSuccess(prep), `migrate prep: ${prep.stderr}`).toBe(true);
      expect(w1.isSuccess(await w1.datastoreDetach(CTRL_DS))).toBe(true);
      expect(w1.isSuccess(await w1.datastoreAttach({ name: CTRL_DS, force: true }))).toBe(true);
      const idMig = await w1.kubeIdentityRewrite({
        mountPath: CTRL_MOUNT,
        operation: 'migrate',
        mode: 'server',
        newNodeIp: W1_IP,
      });
      expect(w1.isSuccess(idMig), (idMig.stdout + idMig.stderr).slice(-400)).toBe(true);
      expect(await poll(() => readyNodeCount(KC).then((n) => n >= 1), 150_000)).toBe(true);
      await uncordon(KC, [NODE1]);
      process.stdout.write(
        `[suite17] cluster migrate cutover downtime: ${Date.now() - cutStart}ms\n`
      );

      // The relocated cluster is Ready with its kine state intact (CA preserved).
      expect(await cmMarker(KC)).toBe('parent-v1');
    });

    test('7. teardown leaves both workers clean', async () => {
      const down = await w1.executeViaBridge(
        `sudo renet repository down --name ${REPO} --datastore ${DATA_MOUNT} --network-id ${REPO_NET} 2>/dev/null; true`
      );
      expect(down.code).toBe(0);
      expect(
        w1.isSuccess(await w1.kubeUninstall({ mountPath: CTRL_MOUNT, networkId: SRV_NET }))
      ).toBe(true);
      expect(w1.isSuccess(await w1.datastoreDetach(DATA_DS))).toBe(true);
      expect(w1.isSuccess(await w1.datastoreDelete(DATA_DS))).toBe(true);
      expect(w1.isSuccess(await w1.datastoreDetach(CTRL_DS))).toBe(true);
      expect(w1.isSuccess(await w1.datastoreDelete(CTRL_DS))).toBe(true);
      const list = await w1.datastoreList();
      expect(w1.isSuccess(list)).toBe(true);
    });
  });
