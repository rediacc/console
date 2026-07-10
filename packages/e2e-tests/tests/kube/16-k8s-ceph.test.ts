import { expect, test } from '@playwright/test';
import { BridgeTestRunner } from '../../src/utils/bridge/BridgeTestRunner';
import type { ExecResult } from '../../src/utils/bridge/types';

// Suite 16 (`Bridge K8s Ceph` job, flagship): a Ceph-backed k8s repo end to end.
// A single-node k3s cluster on worker .11 runs ceph-csi (RBD) against the Ceph
// cluster on .21-.23. It exercises wave 6:
//   - repo-on-ceph deploy: kube_namespace_create --ceph-pool installs ceph-csi
//     + a per-namespace StorageClass; a StatefulSet PVC binds to a dynamically
//     provisioned RBD image scoped into the repo's RADOS namespace.
//   - RBD namespace fork (kube_namespace_fork pv_backend=auto): the source RADOS
//     namespace's images are CoW-cloned into a NEW RADOS namespace, the fork's
//     PVCs pre-bind to the clones (RW), data diverges, the parent is untouched.
//   - teardown: deleting the namespaces removes the RADOS namespaces + RBD images
//     with no orphans.
//
// Gated on K8S_MODE=1 + a ceph topology (VM_CEPH_NODES) + at least one worker.
// A second worker is joined best-effort as an agent (the robust multi-node join
// is wave 7); the flagship ceph/fork assertions do not depend on it.
const enabled = process.env.K8S_MODE === '1';
const cephNodes = (process.env.VM_CEPH_NODES ?? '').trim();
const workers = (process.env.VM_WORKERS ?? '').trim().split(/\s+/).filter(Boolean);
const canRun = enabled && cephNodes.length > 0 && workers.length >= 1;
const canJoin = workers.length >= 2;

const K3S = '/usr/local/bin/rediacc-k3s';
const DATASTORE = '/mnt/rediacc';
const CLUSTER = 'cephprod';
// Network IDs must be 2816 + n*64. Suite 15 uses 2816/2880; suite 16 uses 2944
// for its k3s repo and 3008 for the best-effort agent, so they never collide.
const NETWORK_ID = '2944';
const AGENT_NETWORK_ID = '3008';
const REPO = 'k8sceph';
const MOUNT = `/mnt/rediacc/mounts/${REPO}`;
const NS = 'shop';
const FORK_NS = `${NS}-joseph`;
const KC = `${MOUNT}/.rediacc/k3s/kubeconfig.yaml`;
const POOL = `k8srbd${Date.now().toString(36)}`;

// The image + protected snapshot used to wedge a RADOS namespace on purpose in
// the teardown test, so the leak-reporting path runs deterministically.
const WEDGE_IMAGE = 'e2e-wedge';
const WEDGE_SNAP = 'pin';

// The `leaked` payload of kube_namespace_delete (renet NamespaceTeardownLeak).
interface NamespaceTeardownLeak {
  radosNamespace: string;
  /** Absent for a datastore-backed namespace, which has no ceph state to leak. */
  pool?: string;
  images?: string[];
  pvImageDir?: string;
  reason: string;
}

// A Ceph-backed k8s app: an annotated ClusterIP Service (routable) plus a
// StatefulSet whose volumeClaimTemplate requests the per-namespace RBD
// StorageClass (rediacc-rbd-<ns>). The pod writes a marker into the RBD volume so
// fork divergence is observable.
const APP_MANIFEST = `apiVersion: v1
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
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: web
spec:
  serviceName: web
  replicas: 1
  selector:
    matchLabels:
      app: web
  template:
    metadata:
      labels:
        app: web
    spec:
      # busybox 'tail' runs as PID 1 and ignores SIGTERM, so the default 30s
      # grace period would dominate teardown (delaying the CSI rbd unmap the
      # RADOS-namespace delete waits on). A short grace lets the pod die fast.
      terminationGracePeriodSeconds: 1
      containers:
        - name: web
          image: busybox:1.36
          command: ["sh", "-c", "test -s /data/marker.txt || echo original-data > /data/marker.txt; exec tail -f /dev/null"]
          volumeMounts:
            - name: data
              mountPath: /data
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes: [ReadWriteOnce]
        storageClassName: rediacc-rbd-${NS}
        resources:
          requests:
            storage: 1Gi
`;

test.describe
  .serial('k8s ceph repo end to end @bridge @kube @k8s @ceph', () => {
    test.skip(!canRun, 'Requires K8S_MODE=1, VM_CEPH_NODES, and a worker VM');
    test.setTimeout(900_000);

    let w1: BridgeTestRunner;
    let cephNode: BridgeTestRunner;

    // --- kubectl-over-SSH helpers (embedded k3s, no host kubectl) ---
    const kubectl = async (args: string): Promise<ExecResult> =>
      w1.executeViaBridge(`sudo ${K3S} kubectl --kubeconfig ${KC} ${args}`);

    // rbd/ceph queries run on the ceph node (admin keyring present there).
    const rbd = async (args: string): Promise<ExecResult> =>
      cephNode.executeViaBridge(`sudo rbd ${args}`);

    const writeFile = async (path: string, content: string): Promise<void> => {
      const b64 = Buffer.from(content).toString('base64');
      const res = await w1.executeViaBridge(
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

    const nodeReady = async (): Promise<boolean> => {
      const res = await kubectl('get nodes --no-headers');
      return res.code === 0 && /\sReady\s/.test(res.stdout);
    };

    const podRunning = async (ns: string): Promise<boolean> => {
      const res = await kubectl(`-n ${ns} get pod web-0 --no-headers`);
      return res.code === 0 && /\sRunning\s/.test(res.stdout);
    };

    const pvcBound = async (ns: string): Promise<boolean> => {
      const res = await kubectl(`-n ${ns} get pvc data-web-0 --no-headers`);
      return res.code === 0 && /\sBound\s/.test(res.stdout);
    };

    const marker = async (ns: string): Promise<string> => {
      const res = await kubectl(`-n ${ns} exec web-0 -- cat /data/marker.txt`);
      return res.stdout.trim();
    };

    const rbdImages = async (radosNs: string): Promise<string[] | null> => {
      const res = await rbd(`ls ${POOL} --namespace ${radosNs} --format json`);
      if (res.code !== 0) return null;
      try {
        return JSON.parse(res.stdout.trim() || '[]') as string[];
      } catch {
        return null;
      }
    };

    const rbdImageCount = async (radosNs: string): Promise<number> =>
      (await rbdImages(radosNs))?.length ?? -1;

    const radosNamespaceExists = async (radosNs: string): Promise<boolean> => {
      const res = await rbd(`namespace ls ${POOL} --format json`);
      if (res.code !== 0) return false;
      try {
        return (JSON.parse(res.stdout.trim() || '[]') as { name: string }[]).some(
          (e) => e.name === radosNs
        );
      } catch {
        return false;
      }
    };

    // The ceph marker renet persists beside the rendered manifests; it records
    // which pool backs the namespace so a later delete or `auto` fork finds it.
    const markerExists = async (radosNs: string): Promise<boolean> => {
      const path = `${DATASTORE}/manifests/${CLUSTER}/${radosNs}/.rbd-backend.json`;
      const res = await w1.executeViaBridge(`sudo test -f ${path}`);
      return res.code === 0;
    };

    // wedgeNamespace pins an image in the RADOS namespace so no sweep can clear
    // it: `rbd rm` refuses while a snapshot exists, and `rbd snap rm` refuses
    // while that snapshot is protected. Deterministic, unlike the reclaim race.
    const wedgeNamespace = async (radosNs: string): Promise<void> => {
      const ns = `--pool ${POOL} --namespace ${radosNs}`;
      expect((await rbd(`create ${ns} --size 8 ${WEDGE_IMAGE}`)).code).toBe(0);
      expect((await rbd(`snap create ${ns} ${WEDGE_IMAGE}@${WEDGE_SNAP}`)).code).toBe(0);
      expect((await rbd(`snap protect ${ns} ${WEDGE_IMAGE}@${WEDGE_SNAP}`)).code).toBe(0);
    };

    // Best-effort inverse of wedgeNamespace. Safe to call when nothing is wedged:
    // every step tolerates an already-absent object, so it doubles as the cleanup
    // net for a test that failed midway (a protected snapshot left behind would
    // wedge the namespace for every later run against a reused pool).
    const unwedgeNamespace = async (radosNs: string): Promise<void> => {
      const ns = `--pool ${POOL} --namespace ${radosNs}`;
      await rbd(`snap unprotect ${ns} ${WEDGE_IMAGE}@${WEDGE_SNAP}`);
      await rbd(`snap rm ${ns} ${WEDGE_IMAGE}@${WEDGE_SNAP}`);
      await rbd(`rm ${ns} ${WEDGE_IMAGE}`);
    };

    // `renet functions once` re-emits each line of the child command's stdout as
    // a logfmt record: `time=... level=info msg="[kube_namespace_delete] <line>"`.
    // Recover the child's own stdout by pulling each msg value (logfmt quotes it
    // exactly like a JSON string) and stripping the function-name prefix.
    const unwrapFunctionOutput = (stdout: string): string => {
      const lines: string[] = [];
      for (const record of stdout.split('\n')) {
        const quoted = /\bmsg="((?:[^"\\]|\\.)*)"/.exec(record);
        if (!quoted) continue;
        let msg: string;
        try {
          msg = JSON.parse(`"${quoted[1]}"`) as string;
        } catch {
          continue;
        }
        const inner = /^\[[a-z_]+\] ([\s\S]*)$/.exec(msg);
        if (inner) lines.push(inner[1]);
      }
      return lines.length > 0 ? lines.join('\n') : stdout;
    };

    // kube_namespace_delete emits a pretty-printed `{namespace, leaked?}` object.
    // json.MarshalIndent puts the outer braces at column 0 and indents everything
    // nested, so a line-anchored match isolates the object once unwrapped.
    //
    // Read both streams: renet's logger writes the re-emitted child output to
    // stderr, so the payload never appears on stdout.
    const parseLeak = (res: ExecResult): NamespaceTeardownLeak | null => {
      const stdout = unwrapFunctionOutput(`${res.stdout}\n${res.stderr}`);
      const objects = [...stdout.matchAll(/^\{[\s\S]*?^\}/gm)].map((m) => m[0]);
      for (const raw of objects.reverse()) {
        try {
          const obj = JSON.parse(raw) as { namespace?: string; leaked?: NamespaceTeardownLeak };
          if (obj.namespace !== undefined) return obj.leaked ?? null;
        } catch {
          // Not the delete payload; keep looking.
        }
      }
      return null;
    };

    // kube_namespace_delete takes no --ceph-pool: it recovers the pool from the
    // persisted ceph marker, which a leaked teardown now leaves in place.
    //
    // A wedged namespace cannot drain, so the delete spends its whole internal
    // retry budget (2 minutes) before it can report the leak. That is longer
    // than the default BRIDGE_TIMEOUT of 120s locally, so the wedged call needs
    // its own timeout or the harness kills it before it prints the payload.
    const deleteBase = async (timeout?: number): Promise<ExecResult> =>
      w1.kubeNamespaceDelete({
        mountPath: MOUNT,
        networkId: NETWORK_ID,
        namespace: NS,
        cluster: CLUSTER,
        datastore: DATASTORE,
        timeout,
      });

    const WEDGED_DELETE_TIMEOUT_MS = 300_000;

    const teardownNode = async (): Promise<void> => {
      await w1.executeViaBridge(
        `sudo renet kube uninstall --mount-path ${MOUNT} --network-id ${NETWORK_ID}`
      );
      await w1.executeViaBridge(`sudo renet repository delete --name ${REPO} --force`);
      await w1.executeViaBridge(`sudo ip link del rdk${NETWORK_ID} 2>/dev/null; true`);
    };

    test.beforeAll(async () => {
      w1 = BridgeTestRunner.forWorker(1);
      cephNode = BridgeTestRunner.forCeph();

      // Idempotent teardown of any prior run (fixed networkID). POOL is unique
      // per run, so no pre-existing pool to drop here.
      await teardownNode();

      // Fresh k3s repo image on worker 1.
      const created = await w1.executeViaBridge(
        `sudo renet repository create --name ${REPO} --network-id ${NETWORK_ID} --unencrypted --size 6G`
      );
      expect(created.code, 'create repo image').toBe(0);
    });

    test.afterAll(async () => {
      // KEEP_CLUSTER=1 leaves the k3s repo + ceph-csi + RADOS namespaces up on a
      // failure so the live state can be inspected (provisioner logs, PVC events).
      if (process.env.KEEP_CLUSTER === '1') return;
      // Best-effort namespace/backend cleanup, then node teardown + pool drop.
      // The wedge is dropped first: a protected snapshot blocks every sweep, so
      // a test that failed while wedged would otherwise stall this teardown.
      await unwedgeNamespace(NS).catch(() => undefined);
      await w1
        .kubeNamespaceDelete({
          mountPath: MOUNT,
          networkId: NETWORK_ID,
          namespace: FORK_NS,
          cluster: CLUSTER,
          datastore: DATASTORE,
        })
        .catch(() => undefined);
      await w1
        .kubeNamespaceDelete({
          mountPath: MOUNT,
          networkId: NETWORK_ID,
          namespace: NS,
          cluster: CLUSTER,
          datastore: DATASTORE,
        })
        .catch(() => undefined);
      await teardownNode();
      // ceph_pool_delete removes the dedicated pool (needs mon_allow_pool_delete,
      // which the ceph test profile enables). Best-effort.
      await cephNode.cephPoolDelete(POOL).catch(() => undefined);
    });

    test('1. Ceph is healthy and a dedicated RBD pool is initialized', async () => {
      expect(cephNode.isSuccess(await cephNode.cephHealth())).toBe(true);
      expect(cephNode.isSuccess(await cephNode.cephPoolCreate(POOL))).toBe(true);
      // ceph-csi requires the pool have the rbd application enabled.
      const init = await cephNode.executeViaBridge(`sudo rbd pool init ${POOL}`);
      expect(init.code, init.stderr).toBe(0);
    });

    test('2. stage ceph client config on the worker and load the rbd module', async () => {
      // The worker runs `renet kube` (which shells ceph/rbd for facts + clones),
      // so it needs the admin keyring + ceph.conf. Copy them from the ceph node.
      for (const f of ['ceph.conf', 'ceph.client.admin.keyring']) {
        const read = await cephNode.executeViaBridge(`sudo base64 -w0 /etc/ceph/${f}`);
        expect(read.code, `read /etc/ceph/${f}`).toBe(0);
        await w1.executeViaBridge('sudo mkdir -p /etc/ceph');
        await writeFile(`/etc/ceph/${f}`, Buffer.from(read.stdout.trim(), 'base64').toString());
      }
      // krbd is how ceph-csi maps volumes on the node.
      await w1.executeViaBridge('sudo modprobe rbd || true');
      const check = await w1.executeViaBridge(`sudo rbd ls ${POOL} 2>&1; echo rc=$?`);
      expect(check.stdout, `worker rbd access: ${check.stdout}`).toContain('rc=0');
    });

    test('3. kube_install brings up a single-node k3s server (non-loopback node IP)', async () => {
      expect(
        w1.isSuccess(
          await w1.kubeInstall({ mountPath: MOUNT, networkId: NETWORK_ID, role: 'server' })
        )
      ).toBe(true);
      expect(await poll(() => nodeReady(), 120_000)).toBe(true);
      const ip = await kubectl(
        'get nodes -o jsonpath="{.items[0].status.addresses[?(@.type==\\"InternalIP\\")].address}"'
      );
      expect(ip.stdout.trim()).toMatch(/^10\.150\.\d+\.1$/);

      // Best-effort second-worker join (robust multi-node = wave 7). Never fails
      // the suite: the flagship ceph/fork assertions run on the server node.
      if (canJoin) {
        try {
          const w2 = BridgeTestRunner.forWorker(2);
          const tokenRes = await w1.kubeJoinToken({ mountPath: MOUNT, networkId: NETWORK_ID });
          const token = /K10\S+|[A-Fa-f0-9]{64}/.exec(tokenRes.stdout + tokenRes.stderr)?.[0];
          const nodeIp = ip.stdout.trim();
          if (token && nodeIp) {
            await w2.executeViaBridge(
              `sudo renet repository create --name ${REPO} --network-id ${AGENT_NETWORK_ID} --unencrypted --size 6G`
            );
            const joined = await w2.kubeJoin({
              mountPath: `/mnt/rediacc/mounts/${REPO}`,
              networkId: AGENT_NETWORK_ID,
              role: 'agent',
              token,
              endpoint: `https://${nodeIp}:6443`,
            });
            const nodes = await kubectl('get nodes --no-headers');
            const ready = (nodes.stdout.match(/\sReady\s/g) ?? []).length;
            process.stdout.write(
              `[suite16] agent join success=${w2.isSuccess(joined)} ready-nodes=${ready}\n`
            );
          }
        } catch (e) {
          process.stdout.write(`[suite16] agent join skipped (wave-7 territory): ${String(e)}\n`);
        }
      }
    });

    test('4. deploy: ceph-csi installs, a StatefulSet PVC binds to an RBD image in the RADOS namespace', async () => {
      // kube_namespace_create --ceph-pool installs the cluster-wide ceph-csi
      // driver, this namespace's StorageClass, and the RADOS namespace.
      expect(
        w1.isSuccess(
          await w1.kubeNamespaceCreate({
            mountPath: MOUNT,
            networkId: NETWORK_ID,
            namespace: NS,
            cluster: CLUSTER,
            datastore: DATASTORE,
            cephPool: POOL,
          })
        )
      ).toBe(true);

      // The RADOS namespace scoping the repo's images exists on the pool.
      expect(await radosNamespaceExists(NS)).toBe(true);
      // The per-namespace StorageClass is present.
      const sc = await kubectl(`get storageclass rediacc-rbd-${NS} --no-headers`);
      expect(sc.code, sc.stderr).toBe(0);

      // Deploy the StatefulSet (Rediaccfile up() path). Its PVC dynamically
      // provisions an RBD image via ceph-csi into the RADOS namespace.
      await writeFile('/tmp/shop-ceph.yaml', APP_MANIFEST);
      const applied = await w1.executeViaBridge(
        `sudo renet kube apply --mount-path ${MOUNT} --namespace ${NS} --cluster ${CLUSTER} --datastore ${DATASTORE} --ceph-pool ${POOL} -f /tmp/shop-ceph.yaml`
      );
      expect(applied.code, applied.stderr).toBe(0);

      // The exposed Service is router-stamped with the cluster (routing contract).
      const ann = await kubectl(
        `-n ${NS} get svc web -o jsonpath="{.metadata.annotations.rediacc\\.cluster}"`
      );
      expect(ann.stdout.trim()).toBe(CLUSTER);

      // PVC Bound (RBD provisioned) + pod Running with its marker; generous
      // timeout for the first-time ceph-csi image pulls.
      expect(await poll(() => pvcBound(NS), 300_000)).toBe(true);
      expect(await poll(() => podRunning(NS), 180_000)).toBe(true);
      expect(await marker(NS)).toBe('original-data');

      // The bound PV's backing image lives in the repo's RADOS namespace.
      // Not an exact-count check: under slow IO the external-provisioner's
      // CreateVolume retries can journal-orphan an extra csi-vol image
      // (observed on CI: PVC Pending ~80s, then bound + one orphan). The fork
      // clones only PVC-backed images, and teardown reaps whole namespaces,
      // so step 6's end-state no-orphan assertion is the real gate.
      const volumeName = (
        await kubectl(`-n ${NS} get pvc data-web-0 -o jsonpath="{.spec.volumeName}"`)
      ).stdout.trim();
      const imageName = (
        await kubectl(`get pv ${volumeName} -o jsonpath="{.spec.csi.volumeAttributes.imageName}"`)
      ).stdout.trim();
      expect(imageName, `PV ${volumeName} has no csi imageName`).not.toBe('');
      const images = await rbdImages(NS);
      expect(images, 'rbd ls failed').not.toBeNull();
      expect(images).toContain(imageName);
      if (images && images.length !== 1) {
        process.stdout.write(
          `[suite16] provisioner retry left ${images.length - 1} orphan image(s): ` +
            `${images.filter((i) => i !== imageName).join(', ')} (teardown must reap them)\n`
        );
      }
    });

    test('5. RBD namespace fork: images CoW-clone into a NEW RADOS namespace, data diverges, parent untouched', async () => {
      const t0 = Date.now();
      const res = await w1.kubeNamespaceFork({
        mountPath: MOUNT,
        networkId: NETWORK_ID,
        namespace: NS,
        tag: 'joseph',
        pvBackend: 'auto', // resolves to rbd via the persisted ceph marker
        cluster: CLUSTER,
        datastore: DATASTORE,
        cephPool: POOL,
      });
      const forkMs = Date.now() - t0;
      expect(w1.isSuccess(res), (res.stdout + res.stderr).slice(-800)).toBe(true);
      process.stdout.write(`[suite16] rbd namespace fork wall-time: ${forkMs}ms\n`);

      // The fork's RADOS namespace exists and carries a CoW clone (RW).
      expect(await radosNamespaceExists(FORK_NS)).toBe(true);
      expect(await rbdImageCount(FORK_NS)).toBe(1);

      // Fork pod comes up bound to the clone, carrying the parent's data.
      expect(await poll(() => pvcBound(FORK_NS), 240_000)).toBe(true);
      expect(await poll(() => podRunning(FORK_NS), 180_000)).toBe(true);
      expect(await marker(FORK_NS)).toBe('original-data');

      // Divergence: writing to the fork does not touch the parent.
      const wrote = await kubectl(
        `-n ${FORK_NS} exec web-0 -- sh -c "echo forked-data > /data/marker.txt; sync"`
      );
      expect(wrote.code).toBe(0);
      expect(await marker(FORK_NS)).toBe('forked-data');
      expect(await marker(NS)).toBe('original-data');
    });

    test('6. teardown removes both RADOS namespaces + RBD images with no orphans', async () => {
      // Delete the fork first: its static (Retain) PVs + the clone image + the
      // fork RADOS namespace must all go.
      expect(
        w1.isSuccess(
          await w1.kubeNamespaceDelete({
            mountPath: MOUNT,
            networkId: NETWORK_ID,
            namespace: FORK_NS,
            cluster: CLUSTER,
            datastore: DATASTORE,
          })
        )
      ).toBe(true);
      expect(await poll(() => radosNamespaceExists(FORK_NS).then((e) => !e), 60_000, 3_000)).toBe(
        true
      );

      // A protected snapshot makes `rbd snap rm` (and so the whole namespace
      // sweep) fail for as long as it exists. That wedges the base namespace on
      // purpose, which is the only way to exercise the leak path deterministically:
      // the real trigger is an async ceph-mgr trash task outliving the delete's
      // retry budget on a loaded runner, and that races rather than reproduces.
      await wedgeNamespace(NS);
      try {
        // The wedged delete SUCCEEDS (the k8s namespace is gone; there is nothing
        // the caller can retry differently) but must report exactly what it leaked
        // rather than swallowing it into a log line.
        const wedged = await deleteBase(WEDGED_DELETE_TIMEOUT_MS);
        expect(w1.isSuccess(wedged), `wedged delete: ${wedged.stderr || wedged.stdout}`).toBe(true);
        const leaked = parseLeak(wedged);
        expect(
          leaked,
          `delete must report the leak; output=${wedged.stdout}${wedged.stderr}`
        ).not.toBeNull();
        expect(leaked?.radosNamespace).toBe(NS);
        expect(leaked?.images).toContain(WEDGE_IMAGE);
        expect(await radosNamespaceExists(NS)).toBe(true);

        // The ceph marker names the pool backing this namespace. A leaked teardown
        // that deleted it would strand the surviving RADOS namespace, since the
        // next delete could no longer resolve the pool.
        expect(await markerExists(NS), 'ceph marker must survive a leaked teardown').toBe(true);
      } finally {
        await unwedgeNamespace(NS);
      }

      // Redrive: the surviving marker is what lets this delete rediscover the
      // pool. ceph-csi can still be finishing DeleteVolume through an async
      // ceph-mgr trash task, so the idempotent delete is re-invoked until the
      // RADOS namespace clears.
      const baseGone = () => radosNamespaceExists(NS).then((e) => !e);
      const redriven = await deleteBase();
      expect(w1.isSuccess(redriven)).toBe(true);
      expect(parseLeak(redriven), 'an unwedged teardown must report no leak').toBeNull();
      let cleared = await poll(baseGone, 60_000, 3_000);
      for (let redrive = 0; !cleared && redrive < 3; redrive++) {
        process.stdout.write(
          `[suite16] base namespace still present; redriving delete (#${redrive + 1})\n`
        );
        await deleteBase();
        cleared = await poll(baseGone, 60_000, 3_000);
      }
      expect(cleared).toBe(true);

      // A clean teardown reports no leak and drops the marker with the namespace.
      expect(await markerExists(NS)).toBe(false);

      // No orphan RADOS namespaces remain on the pool.
      const nsList = await rbd(`namespace ls ${POOL} --format json`);
      expect(nsList.stdout.trim() === '[]' || nsList.stdout.trim() === '').toBe(true);
    });

    test('7. teardown removes the node and the dummy interface', async () => {
      expect(
        w1.isSuccess(await w1.kubeUninstall({ mountPath: MOUNT, networkId: NETWORK_ID }))
      ).toBe(true);
      const iface = await w1.executeViaBridge(
        `ip link show rdk${NETWORK_ID} 2>/dev/null && echo PRESENT || echo GONE`
      );
      expect(iface.stdout).toContain('GONE');
    });
  });
