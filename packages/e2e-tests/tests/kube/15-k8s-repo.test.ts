import { expect, test } from '@playwright/test';
import { BridgeTestRunner } from '../../src/utils/bridge/BridgeTestRunner';
import type { ExecResult } from '../../src/utils/bridge/types';

// Suite 15 (`E2E K8s` job): a k8s repo end to end on a single-node k3s cluster
// living inside a datastore-backed repo image (design D6 v3). It exercises the
// wave-5 S1 parameters live: the dedicated non-loopback node IP, the router
// annotation contract, PV-per-CoW-image provisioning, and the flagship
// namespace fork (instant CoW, data divergence, parent unchanged).
//
// Gated on K8S_MODE=1 + at least one worker VM. The cross-cluster migrate test
// additionally needs a second worker (skipped otherwise) and prints the
// measured cutover downtime.
const enabled = process.env.K8S_MODE === '1';
const workers = (process.env.VM_WORKERS ?? '').trim().split(/\s+/).filter(Boolean);
const canRun = enabled && workers.length >= 1;
const canMigrate = enabled && workers.length >= 2;

const K3S = '/usr/local/bin/rediacc-k3s';
const DATASTORE = '/mnt/rediacc';
const CLUSTER = 'prod';
const NETWORK_ID = '2816';
const REPO = 'k8slive';
const MOUNT = `/mnt/rediacc/mounts/${REPO}`;
const NS = 'shop';
const KC = `${MOUNT}/.rediacc/k3s/kubeconfig.yaml`;

// The repo's k8s app: an annotated Service (routable), a rediacc-datastore PVC
// (CoW-forkable), and a Deployment that writes a marker into the PV so fork
// divergence is observable.
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
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: data
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: rediacc-datastore
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
      containers:
        - name: web
          image: busybox:1.36
          command: ["sh", "-c", "test -s /data/marker.txt || echo original-data > /data/marker.txt; exec tail -f /dev/null"]
          volumeMounts:
            - name: data
              mountPath: /data
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: data
`;

// A manifest the linter must reject (S1 verdicts 3 + 5): NodePort exposes the
// real NIC and defeats the router-mediated ClusterIP model.
const NODEPORT_MANIFEST = `apiVersion: v1
kind: Service
metadata:
  name: bad
  annotations:
    rediacc.service_port: "80"
spec:
  type: NodePort
  selector:
    app: web
  ports:
    - port: 80
      nodePort: 31888
`;

test.describe
  .serial('k8s repo end to end @bridge @kube @k8s', () => {
    test.skip(!canRun, 'Requires K8S_MODE=1 and a worker VM');
    test.setTimeout(600_000);

    let w1: BridgeTestRunner;

    // --- kubectl-over-SSH helpers (no host kubectl; use the embedded k3s) ---
    const kubectl = async (r: BridgeTestRunner, kc: string, args: string): Promise<ExecResult> =>
      r.executeViaBridge(`sudo ${K3S} kubectl --kubeconfig ${kc} ${args}`);

    const writeFile = async (r: BridgeTestRunner, path: string, content: string): Promise<void> => {
      const b64 = Buffer.from(content).toString('base64');
      const res = await r.executeViaBridge(`echo ${b64} | base64 -d | sudo tee ${path} >/dev/null`);
      expect(res.code, `write ${path}`).toBe(0);
    };

    const poll = async (
      fn: () => Promise<boolean>,
      timeoutMs = 120_000,
      stepMs = 5_000
    ): Promise<boolean> => {
      const attempts = Math.max(1, Math.ceil(timeoutMs / stepMs));
      for (let i = 0; i < attempts; i++) {
        if (await fn()) return true;
        await new Promise((res) => setTimeout(res, stepMs));
      }
      return fn();
    };

    const nodeReady = async (r: BridgeTestRunner, kc: string): Promise<boolean> => {
      const res = await kubectl(r, kc, 'get nodes --no-headers');
      return res.code === 0 && /\sReady\s/.test(res.stdout);
    };

    const podRunning = async (r: BridgeTestRunner, kc: string, ns: string): Promise<boolean> => {
      const res = await kubectl(r, kc, `-n ${ns} get pods -l app=web --no-headers`);
      return res.code === 0 && /\sRunning\s/.test(res.stdout);
    };

    const marker = async (r: BridgeTestRunner, kc: string, ns: string): Promise<string> => {
      const res = await kubectl(r, kc, `-n ${ns} exec deploy/web -- cat /data/marker.txt`);
      return res.stdout.trim();
    };

    const teardownNode = async (
      r: BridgeTestRunner,
      mount: string,
      networkId: string
    ): Promise<void> => {
      await r.executeViaBridge(
        `sudo renet kube uninstall --mount-path ${mount} --network-id ${networkId}`
      );
      await r.executeViaBridge(`sudo renet repository delete --name ${REPO} --force`);
      await r.executeViaBridge(`sudo ip link del rdk${networkId} 2>/dev/null; true`);
    };

    test.beforeAll(async () => {
      w1 = BridgeTestRunner.forWorker(1);
      // Idempotent teardown: this suite uses a fixed networkID, so a prior run's
      // k3s / repo / dummy interface must be cleared before a fresh install.
      await teardownNode(w1, MOUNT, NETWORK_ID);
      const created = await w1.executeViaBridge(
        `sudo renet repository create --name ${REPO} --network-id ${NETWORK_ID} --unencrypted --size 6G`
      );
      expect(created.code, 'create repo image').toBe(0);
    });

    test.afterAll(async () => {
      await teardownNode(w1, MOUNT, NETWORK_ID);
    });

    test('1. kube_install brings up a single-node k3s server on a non-loopback node IP', async () => {
      const res = await w1.kubeInstall({ mountPath: MOUNT, networkId: NETWORK_ID, role: 'server' });
      expect(w1.isSuccess(res)).toBe(true);

      expect(await poll(() => nodeReady(w1, KC), 120_000)).toBe(true);
      // S1 verdict 1: the node's InternalIP must be the dedicated non-loopback IP
      // (10.150.x.1), NOT a 127/8 loopback.
      const ip = await kubectl(
        w1,
        KC,
        'get nodes -o jsonpath="{.items[0].status.addresses[?(@.type==\\"InternalIP\\")].address}"'
      );
      expect(ip.stdout.trim()).toMatch(/^10\.150\.\d+\.1$/);
    });

    test('2. kube_health reports the API server ready', async () => {
      expect(w1.isSuccess(await w1.kubeHealth({ mountPath: MOUNT, networkId: NETWORK_ID }))).toBe(
        true
      );
    });

    test('3. kube_kubeconfig emits a kubeconfig whose server URL is the reachable node IP', async () => {
      const res = await w1.kubeKubeconfig({ mountPath: MOUNT, networkId: NETWORK_ID });
      expect(w1.isSuccess(res)).toBe(true);
      // The rewritten server URL must be reachable (not k3s's 127.0.0.1 default).
      // The bridge-once test-mode executor surfaces function output through the
      // renet logger (stderr), so match the combined stream (as tests 7/8 do).
      expect(res.stdout + res.stderr).toMatch(/server:\s*https:\/\/10\.150\.\d+\.1:6443/);
    });

    test('4. deploy: PVs materialize, the Service is router-stamped, the pod runs with its data', async () => {
      expect(
        w1.isSuccess(
          await w1.kubeNamespaceCreate({
            mountPath: MOUNT,
            networkId: NETWORK_ID,
            namespace: NS,
            cluster: CLUSTER,
            datastore: DATASTORE,
          })
        )
      ).toBe(true);

      // A standalone PV provision (kube_pv_provision) creates a datastore image.
      expect(
        w1.isSuccess(
          await w1.kubePvProvision({
            datastore: DATASTORE,
            cluster: CLUSTER,
            namespace: NS,
            pvc: 'scratch',
            size: '1Gi',
          })
        )
      ).toBe(true);
      const img = await w1.executeViaBridge(
        `sudo test -f ${DATASTORE}/pv/${CLUSTER}/${NS}/scratch.img && echo OK`
      );
      expect(img.stdout).toContain('OK');

      // Initial deploy is the Rediaccfile up() path: `renet kube apply -f` renders
      // (namespace stamp + router annotation contract + PVC materialize) + persists.
      await writeFile(w1, '/tmp/shop-app.yaml', APP_MANIFEST);
      const applied = await w1.executeViaBridge(
        `sudo renet kube apply --mount-path ${MOUNT} --namespace ${NS} --cluster ${CLUSTER} --datastore ${DATASTORE} -f /tmp/shop-app.yaml`
      );
      expect(applied.code, applied.stderr).toBe(0);

      // Router contract: the exposed Service carries rediacc.cluster (else the
      // route is silently dropped, S1 verdict 5).
      const ann = await kubectl(
        w1,
        KC,
        `-n ${NS} get svc web -o jsonpath="{.metadata.annotations.rediacc\\.cluster}"`
      );
      expect(ann.stdout.trim()).toBe(CLUSTER);

      // PVC bound + pod running with the marker written into the CoW PV.
      const pvc = await kubectl(w1, KC, `-n ${NS} get pvc data --no-headers`);
      expect(pvc.stdout).toMatch(/\sBound\s/);
      expect(await poll(() => podRunning(w1, KC, NS), 120_000)).toBe(true);
      expect(await marker(w1, KC, NS)).toBe('original-data');

      // kube_deploy re-applies the persisted manifest (idempotent redeploy path).
      expect(
        w1.isSuccess(
          await w1.kubeDeploy({
            mountPath: MOUNT,
            networkId: NETWORK_ID,
            namespace: NS,
            cluster: CLUSTER,
            datastore: DATASTORE,
          })
        )
      ).toBe(true);
    });

    test('5. namespace fork is instant CoW: data diverges, parent unchanged, URL under parent wildcard', async () => {
      const forkNs = `${NS}-joseph`;
      const t0 = Date.now();
      const res = await w1.kubeNamespaceFork({
        mountPath: MOUNT,
        networkId: NETWORK_ID,
        namespace: NS,
        tag: 'joseph',
        pvBackend: 'datastore',
        cluster: CLUSTER,
        datastore: DATASTORE,
      });
      const forkMs = Date.now() - t0;
      expect(w1.isSuccess(res)).toBe(true);
      // Constant-time CoW: forking a repo with data is near-instant regardless of
      // size (reflink), not a full copy. Generous ceiling for a busy CI runner.
      process.stdout.write(`[suite15] namespace fork wall-time: ${forkMs}ms\n`);
      expect(forkMs).toBeLessThan(60_000);

      // Fork Service carries the same cluster stamp -> its URL lands under the
      // parent's per-cluster wildcard (zero new certs on fork).
      const forkAnn = await kubectl(
        w1,
        KC,
        `-n ${forkNs} get svc web -o jsonpath="{.metadata.annotations.rediacc\\.cluster}"`
      );
      expect(forkAnn.stdout.trim()).toBe(CLUSTER);

      // Fork pod comes up carrying the parent's data (CoW clone).
      expect(await poll(() => podRunning(w1, KC, forkNs), 120_000)).toBe(true);
      expect(await marker(w1, KC, forkNs)).toBe('original-data');

      // Divergence: write to the fork, then assert the parent is untouched.
      const wrote = await kubectl(
        w1,
        KC,
        `-n ${forkNs} exec deploy/web -- sh -c "echo forked-data > /data/marker.txt"`
      );
      expect(wrote.code).toBe(0);
      expect(await marker(w1, KC, forkNs)).toBe('forked-data');
      expect(await marker(w1, KC, NS)).toBe('original-data');
    });

    test('6. kube_pv_clone / kube_pv_delete operate on standalone PV images', async () => {
      const clone = await w1.kubePvClone({
        datastore: DATASTORE,
        cluster: CLUSTER,
        srcPv: `${DATASTORE}/pv/${CLUSTER}/${NS}/data.img`,
        dstNamespace: `${NS}-copy`,
      });
      expect(w1.isSuccess(clone)).toBe(true);
      const cloned = `${DATASTORE}/pv/${CLUSTER}/${NS}-copy/data.img`;
      expect((await w1.executeViaBridge(`sudo test -f ${cloned} && echo OK`)).stdout).toContain(
        'OK'
      );

      expect(w1.isSuccess(await w1.kubePvDelete(cloned))).toBe(true);
      expect((await w1.executeViaBridge(`sudo test -f ${cloned} || echo GONE`)).stdout).toContain(
        'GONE'
      );
    });

    test('7. the kube linter rejects node-exposing manifests (NodePort)', async () => {
      await writeFile(w1, '/tmp/bad.yaml', NODEPORT_MANIFEST);
      const applied = await w1.executeViaBridge(
        `sudo renet kube apply --mount-path ${MOUNT} --namespace ${NS} --cluster ${CLUSTER} --datastore ${DATASTORE} -f /tmp/bad.yaml`
      );
      expect(applied.code, 'NodePort apply must fail').not.toBe(0);
      expect(applied.stdout + applied.stderr).toMatch(/NodePort|reject/i);
    });

    test('8. an external (non-embeddable) distro refuses install cleanly', async () => {
      const res = await w1.executeViaBridge(
        `sudo renet kube install --mount-path /tmp/extc --network-id ${NETWORK_ID} --distro external`
      );
      expect(res.code, 'external install must refuse').not.toBe(0);
      expect(res.stdout + res.stderr).toMatch(/not applicable/i);
    });

    test('9. cross-cluster migrate moves the namespace with a measured, seconds-level downtime', async () => {
      test.skip(!canMigrate, 'Requires a second worker VM');
      const w2 = BridgeTestRunner.forWorker(2);
      const cluster2 = 'prod2';
      const netId2 = '2880';
      const mount2 = `/mnt/rediacc/mounts/${REPO}`;
      const kc2 = `${mount2}/.rediacc/k3s/kubeconfig.yaml`;

      // Fresh destination cluster on worker 2.
      await w2.executeViaBridge(
        `sudo renet kube uninstall --mount-path ${mount2} --network-id ${netId2}`
      );
      await w2.executeViaBridge(`sudo renet repository delete --name ${REPO} --force`);
      await w2.executeViaBridge(`sudo ip link del rdk${netId2} 2>/dev/null; true`);
      expect(
        (
          await w2.executeViaBridge(
            `sudo renet repository create --name ${REPO} --network-id ${netId2} --unencrypted --size 6G`
          )
        ).code
      ).toBe(0);
      expect(
        w2.isSuccess(await w2.kubeInstall({ mountPath: mount2, networkId: netId2, role: 'server' }))
      ).toBe(true);
      expect(await poll(() => nodeReady(w2, kc2), 120_000)).toBe(true);

      // Transfer the namespace's persisted manifest + PV image worker1 -> worker2,
      // relocated under the destination cluster's datastore layout. The bridge VM
      // (mesh SSH to every worker) relays the copy: workers do not trust each
      // other directly, but both trust the bridge.
      const srcImg = `${DATASTORE}/pv/${CLUSTER}/${NS}/data.img`;
      const dstImgDir = `${DATASTORE}/pv/${cluster2}/${NS}`;
      const srcMan = `${DATASTORE}/manifests/${CLUSTER}/${NS}`;
      const dstManDir = `${DATASTORE}/manifests/${cluster2}/${NS}`;
      const [w1ip, w2ip] = w1.getWorkerVMs();
      const user = process.env.USER;
      const scp = '-o StrictHostKeyChecking=no -o BatchMode=yes';
      const relay = async (srcPath: string, dstPath: string): Promise<void> => {
        const relayTmp = `/tmp/mig-${Date.now()}`;
        const cmd =
          `scp ${scp} ${user}@${w1ip}:${srcPath} ${relayTmp} && ` +
          `scp ${scp} ${relayTmp} ${user}@${w2ip}:${dstPath} && rm -f ${relayTmp}`;
        const res = await w1.executeOnVM(w1.getBridgeVM(), cmd);
        expect(res.code, `relay ${srcPath} -> ${dstPath}: ${res.stderr}`).toBe(0);
      };

      // World-readable staging copies on both ends so the mesh SSH user can read
      // the sudo-owned datastore files and write into /tmp on worker2.
      const manFiles = await w1.executeViaBridge(`sudo ls ${srcMan}`);
      const manName = manFiles.stdout.trim().split(/\s+/)[0];
      await w1.executeViaBridge(
        `sudo cp ${srcImg} /tmp/mig-data.img && sudo cp ${srcMan}/${manName} /tmp/mig-man.yaml && sudo chmod 644 /tmp/mig-data.img /tmp/mig-man.yaml`
      );
      await relay('/tmp/mig-data.img', '/tmp/mig-data.img');
      await relay('/tmp/mig-man.yaml', '/tmp/mig-man.yaml');
      await w2.executeViaBridge(
        `sudo mkdir -p ${dstImgDir} ${dstManDir} && sudo cp /tmp/mig-data.img ${dstImgDir}/data.img && sudo cp /tmp/mig-man.yaml ${dstManDir}/${manName}`
      );

      // Cutover: stop the source workload, then deploy on the destination.
      const cutStart = Date.now();
      await kubectl(w1, KC, `-n ${NS} scale deploy/web --replicas=0`);
      expect(
        w2.isSuccess(
          await w2.kubeNamespaceCreate({
            mountPath: mount2,
            networkId: netId2,
            namespace: NS,
            cluster: cluster2,
            datastore: DATASTORE,
          })
        )
      ).toBe(true);
      expect(
        w2.isSuccess(
          await w2.kubeDeploy({
            mountPath: mount2,
            networkId: netId2,
            namespace: NS,
            cluster: cluster2,
            datastore: DATASTORE,
          })
        )
      ).toBe(true);
      expect(await poll(() => podRunning(w2, kc2, NS), 180_000)).toBe(true);
      const downtimeSec = ((Date.now() - cutStart) / 1000).toFixed(1);
      process.stdout.write(`[suite15] cross-cluster migrate downtime: ${downtimeSec}s\n`);

      // Data intact on the destination.
      expect(await marker(w2, kc2, NS)).toBe('original-data');

      // Cleanup destination.
      await w2.executeViaBridge(
        `sudo renet kube uninstall --mount-path ${mount2} --network-id ${netId2}`
      );
      await w2.executeViaBridge(`sudo renet repository delete --name ${REPO} --force`);
      await w2.executeViaBridge(`sudo ip link del rdk${netId2} 2>/dev/null; true`);
    });

    test('10. teardown removes the namespace, the node, and the dummy interface', async () => {
      expect(
        w1.isSuccess(
          await w1.kubeNamespaceDelete({
            mountPath: MOUNT,
            networkId: NETWORK_ID,
            namespace: NS,
            cluster: CLUSTER,
            datastore: DATASTORE,
          })
        )
      ).toBe(true);
      expect(
        w1.isSuccess(await w1.kubeUninstall({ mountPath: MOUNT, networkId: NETWORK_ID }))
      ).toBe(true);
      // S1 verdict 1 teardown: the per-cluster dummy interface is removed.
      const iface = await w1.executeViaBridge(
        `ip link show rdk${NETWORK_ID} 2>/dev/null && echo PRESENT || echo GONE`
      );
      expect(iface.stdout).toContain('GONE');
    });
  });
