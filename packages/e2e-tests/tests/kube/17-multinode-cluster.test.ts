import { expect, test } from '@playwright/test';
import { BridgeTestRunner } from '../../src/utils/bridge/BridgeTestRunner';
import type { ExecResult } from '../../src/utils/bridge/types';

// Suite 17 (`Bridge K8s Multinode` job): a 2-node k3s cluster + whole-cluster
// fork/migrate (wave 7, S2 verdicts). It exercises the multi-node mechanisms the
// single-node suites (15/16) do not:
//   - MULTI-NODE bring-up (V1): server on worker 1 + agent on worker 2, both
//     bound to their real private NICs (not the host-local dummy), flannel VXLAN
//     over the NIC, an agent-hosted Ceph RBD PV consumed by a pod.
//   - WHOLE-CLUSTER FORK (V2/V3/V5): drain + prep every node (so kubelet mounts
//     do not block the reflink), CoW-reflink the control-plane image FIRST then
//     the agent image, rewrite each node's identity (server first, then agents,
//     reusing the CA-derived token) onto secondary IPs. The fork's cluster state
//     (kine) diverges CoW-isolated from the parent; the parent is untouched.
//   - WHOLE-CLUSTER MIGRATE (V4): relocate a single-node cluster's image to
//     another machine via the per-image FIEMAP delta + identity rewrite, with a
//     measured cutover downtime.
//
// Gated on K8S_MODE=1 + a ceph topology (VM_CEPH_NODES) + TWO worker VMs.
const enabled = process.env.K8S_MODE === '1';
const cephNodes = (process.env.VM_CEPH_NODES ?? '').trim();
const workers = (process.env.VM_WORKERS ?? '').trim().split(/\s+/).filter(Boolean);
const canRun = enabled && cephNodes.length > 0 && workers.length >= 2;

const NET = process.env.VM_NET_BASE ?? '192.168.111';
const W1_IP = `${NET}.${workers[0] ?? '11'}`; // k3s server (real private NIC)
const W2_IP = `${NET}.${workers[1] ?? '12'}`; // k3s agent (real private NIC)
// Secondary IPs the fork/migrate relocate onto (co-tenancy: parent stopped while
// the fork runs — S1 verdict 2 forbids two k3s in one host netns).
const W1_FORK_IP = `${NET}.211`;
const W2_FORK_IP = `${NET}.212`;
const NIC = 'ens1';

const K3S = '/usr/local/bin/rediacc-k3s';
const DATASTORE = '/mnt/rediacc';
const CLUSTER = 'mnprod';
// Network IDs must be 2816 + n*64. Suites 15/16 use 2816-3008; suite 17 uses
// 3072/3136 (parent server/agent), 3200/3264 (fork server/agent), 3328 (migrate).
const SRV_NET = '3072';
const AGT_NET = '3136';
const FORK_SRV_NET = '3200';
const FORK_AGT_NET = '3264';
const REPO = 'k8smn';
const FORK_REPO = 'k8smnf';
const SRV_MOUNT = `/mnt/rediacc/mounts/${REPO}`;
const FORK_MOUNT = `/mnt/rediacc/mounts/${FORK_REPO}`;
const KC = `${SRV_MOUNT}/.rediacc/k3s/kubeconfig.yaml`;
const FORK_KC = `${FORK_MOUNT}/.rediacc/k3s/kubeconfig.yaml`;
const NS = 'shop';
const POOL = `k8smn${Date.now().toString(36)}`;
const NODE1 = `rediacc${workers[0] ?? '11'}`;
const NODE2 = `rediacc${workers[1] ?? '12'}`;
// Single-node cluster relocated cross-machine in the migrate test.
const MIG_NET = '3328';
const MIG_REPO = 'k8smig';
const MIG_MOUNT = `/mnt/rediacc/mounts/${MIG_REPO}`;
const MIG_KC = `${MIG_MOUNT}/.rediacc/k3s/kubeconfig.yaml`;

// A Ceph-backed app pinned to the AGENT node (S2 verdict 1: multi-node PVs must
// be Ceph — a local PV would escape the forkable image). Plus a ConfigMap that
// lives in kine (the control-plane image), which is what a whole-cluster fork
// carries + diverges.
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
      nodeSelector:
        kubernetes.io/hostname: ${NODE2}
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
  .serial('multi-node k8s cluster fork + migrate @bridge @kube @k8s @multinode', () => {
    test.skip(!canRun, 'Requires K8S_MODE=1, VM_CEPH_NODES, and TWO worker VMs');
    test.setTimeout(900_000);

    let w1: BridgeTestRunner; // k3s server node (.11)
    let w2: BridgeTestRunner; // k3s agent node (.12)
    let cephNode: BridgeTestRunner;

    // kubectl against a given kubeconfig, run on the server node.
    const kubectlOn = async (
      runner: BridgeTestRunner,
      kc: string,
      args: string
    ): Promise<ExecResult> =>
      runner.executeViaBridge(`sudo ${K3S} kubectl --kubeconfig ${kc} ${args}`);

    const rbd = async (args: string): Promise<ExecResult> =>
      cephNode.executeViaBridge(`sudo rbd ${args}`);

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

    // Count Ready nodes as seen by a given kubeconfig, queried from a given node.
    // A node's STATUS column is "Ready" or "Ready,SchedulingDisabled" (when
    // cordoned by a drain) — both count as Ready; "NotReady" must not.
    const readyNodeCountOn = async (runner: BridgeTestRunner, kc: string): Promise<number> => {
      const res = await kubectlOn(runner, kc, 'get nodes --no-headers');
      if (res.code !== 0) return -1;
      return res.stdout.split('\n').filter((l) => /^\S+\s+Ready\b/.test(l.trim())).length;
    };
    const readyNodeCount = async (kc: string): Promise<number> => readyNodeCountOn(w1, kc);

    // Undo the prep-fork drain (which cordoned the nodes) so the relocated cluster
    // is fully schedulable again.
    const uncordon = async (
      runner: BridgeTestRunner,
      kc: string,
      nodes: string[]
    ): Promise<void> => {
      for (const n of nodes) {
        await kubectlOn(runner, kc, `uncordon ${n}`);
      }
    };

    const internalIPOn = async (
      runner: BridgeTestRunner,
      kc: string,
      node: string
    ): Promise<string> => {
      const res = await kubectlOn(
        runner,
        kc,
        `get node ${node} -o jsonpath="{.status.addresses[?(@.type==\\"InternalIP\\")].address}"`
      );
      return res.stdout.trim();
    };
    const internalIP = async (kc: string, node: string): Promise<string> =>
      internalIPOn(w1, kc, node);

    // migstate ConfigMap marker (the migrate test's kine-resident data), read via
    // the node currently hosting the cluster.
    const migMarker = async (runner: BridgeTestRunner): Promise<string> => {
      const res = await kubectlOn(
        runner,
        MIG_KC,
        'get configmap migstate -o jsonpath="{.data.marker}"'
      );
      return res.stdout.trim();
    };

    const cmMarker = async (kc: string): Promise<string> => {
      const res = await kubectlOn(
        w1,
        kc,
        `-n ${NS} get configmap clusterstate -o jsonpath="{.data.marker}"`
      );
      return res.stdout.trim();
    };

    const pvcBound = async (kc: string): Promise<boolean> => {
      const res = await kubectlOn(w1, kc, `-n ${NS} get pvc data-web-0 --no-headers`);
      return res.code === 0 && /\sBound\s/.test(res.stdout);
    };

    const podRunningOn = async (kc: string, node: string): Promise<boolean> => {
      const res = await kubectlOn(w1, kc, `-n ${NS} get pod web-0 -o wide --no-headers`);
      return res.code === 0 && /\sRunning\s/.test(res.stdout) && res.stdout.includes(node);
    };

    const marker = async (kc: string): Promise<string> => {
      const res = await kubectlOn(w1, kc, `-n ${NS} exec web-0 -- cat /data/marker.txt`);
      return res.stdout.trim();
    };

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

    // Stage the ceph admin keyring + ceph.conf on a worker (renet kube shells
    // ceph/rbd for csi facts + clones), plus load krbd.
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

    // Teardown a node's k3s + repo image (+ its fork image + dummy/secondary IPs).
    const teardownAll = async (): Promise<void> => {
      // Fork first (may be up on secondary IPs).
      await w1.executeViaBridge(
        `sudo renet kube uninstall --mount-path ${FORK_MOUNT} --network-id ${FORK_SRV_NET} 2>/dev/null; true`
      );
      await w2.executeViaBridge(
        `sudo renet kube uninstall --mount-path /mnt/rediacc/mounts/${FORK_REPO} --network-id ${FORK_AGT_NET} 2>/dev/null; true`
      );
      await w1.executeViaBridge(
        `sudo renet repository delete --name ${FORK_REPO} --force 2>/dev/null; true`
      );
      await w2.executeViaBridge(
        `sudo renet repository delete --name ${FORK_REPO} --force 2>/dev/null; true`
      );
      await w1.executeViaBridge(`sudo ip addr del ${W1_FORK_IP}/24 dev ${NIC} 2>/dev/null; true`);
      await w2.executeViaBridge(`sudo ip addr del ${W2_FORK_IP}/24 dev ${NIC} 2>/dev/null; true`);
      // Parent nodes.
      await w1.executeViaBridge(
        `sudo renet kube uninstall --mount-path ${SRV_MOUNT} --network-id ${SRV_NET} 2>/dev/null; true`
      );
      await w2.executeViaBridge(
        `sudo renet kube uninstall --mount-path /mnt/rediacc/mounts/${REPO} --network-id ${AGT_NET} 2>/dev/null; true`
      );
      await w1.executeViaBridge(
        `sudo renet repository delete --name ${REPO} --force 2>/dev/null; true`
      );
      await w2.executeViaBridge(
        `sudo renet repository delete --name ${REPO} --force 2>/dev/null; true`
      );
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

    test('1. Ceph is healthy and a dedicated RBD pool is initialized', async () => {
      expect(cephNode.isSuccess(await cephNode.cephHealth())).toBe(true);
      expect(cephNode.isSuccess(await cephNode.cephPoolCreate(POOL))).toBe(true);
      const init = await cephNode.executeViaBridge(`sudo rbd pool init ${POOL}`);
      expect(init.code, init.stderr).toBe(0);
    });

    test('2. stage ceph client config on both workers and load the rbd module', async () => {
      await stageCephClient(w1);
      await stageCephClient(w2);
      const check = await w2.executeViaBridge(`sudo rbd ls ${POOL} 2>&1; echo rc=$?`);
      expect(check.stdout, `worker-2 rbd access: ${check.stdout}`).toContain('rc=0');
    });

    test('3. multi-node bring-up: server + agent both bound to their real private NICs', async () => {
      // Server on worker 1, bound to the real NIC (wave-7 multi-node bind).
      const srvCreate = await w1.executeViaBridge(
        `sudo renet repository create --name ${REPO} --network-id ${SRV_NET} --unencrypted --size 6G`
      );
      expect(srvCreate.code, srvCreate.stderr).toBe(0);
      // k3s uses Type=notify, so `systemctl start` (inside install/join) blocks
      // until the node is fully up — a cold containerd image pull can push that
      // past the default 120s command timeout, so give these a generous budget.
      const srvInstall = await w1.executeViaBridge(
        `sudo renet kube install --mount-path ${SRV_MOUNT} --network-id ${SRV_NET} --role server --bind-ip ${W1_IP}`,
        540_000
      );
      expect(srvInstall.code, srvInstall.stderr).toBe(0);
      expect(await poll(() => readyNodeCount(KC).then((n) => n >= 1), 150_000)).toBe(true);
      // The server advertises its REAL NIC, not the host-local dummy.
      expect(await internalIP(KC, NODE1)).toBe(W1_IP);

      // Agent on worker 2, joined with the wave-7 real-NIC bind (V1 fix).
      const agtCreate = await w2.executeViaBridge(
        `sudo renet repository create --name ${REPO} --network-id ${AGT_NET} --unencrypted --size 6G`
      );
      expect(agtCreate.code, agtCreate.stderr).toBe(0);
      const tokenRes = await w1.executeViaBridge(
        `sudo renet kube join-token --mount-path ${SRV_MOUNT} --network-id ${SRV_NET}`
      );
      const token = /K10\S+/.exec(tokenRes.stdout + tokenRes.stderr)?.[0];
      expect(token, 'join token').toBeTruthy();
      const agtJoin = await w2.executeViaBridge(
        `sudo renet kube join --mount-path /mnt/rediacc/mounts/${REPO} --network-id ${AGT_NET} --role agent --token ${token} --server https://${W1_IP}:6443 --bind-ip ${W2_IP}`,
        540_000
      );
      expect(agtJoin.code, agtJoin.stderr).toBe(0);

      // Both nodes Ready, each advertising its own real NIC.
      expect(await poll(() => readyNodeCount(KC).then((n) => n >= 2), 150_000)).toBe(true);
      expect(await internalIP(KC, NODE1)).toBe(W1_IP);
      expect(await internalIP(KC, NODE2)).toBe(W2_IP);
    });

    test('4. ceph PV consumed by an agent-hosted pod + cluster state in kine', async () => {
      // ceph-csi + the per-namespace StorageClass + RADOS namespace.
      expect(
        w1.isSuccess(
          await w1.kubeNamespaceCreate({
            mountPath: SRV_MOUNT,
            networkId: SRV_NET,
            namespace: NS,
            cluster: CLUSTER,
            datastore: DATASTORE,
            cephPool: POOL,
          })
        )
      ).toBe(true);
      expect(await radosNamespaceExists(NS)).toBe(true);

      // Deploy the app (StatefulSet pinned to the AGENT node + ConfigMap in kine).
      await writeFileOn(w1, '/tmp/mn-app.yaml', APP_MANIFEST);
      const applied = await w1.executeViaBridge(
        `sudo renet kube apply --mount-path ${SRV_MOUNT} --namespace ${NS} --cluster ${CLUSTER} --datastore ${DATASTORE} --ceph-pool ${POOL} -f /tmp/mn-app.yaml`
      );
      expect(applied.code, applied.stderr).toBe(0);

      expect(await poll(() => pvcBound(KC), 300_000)).toBe(true);
      expect(await poll(() => podRunningOn(KC, NODE2), 180_000)).toBe(true);
      expect(await marker(KC)).toBe('original-data');
      expect(await cmMarker(KC)).toBe('parent-v1');
    });

    test('5. whole-cluster fork: coordinated CoW + per-node identity rewrite onto new IPs', async () => {
      const t0 = Date.now();

      // S2 verdict 5: drain + prep EVERY node so leaked kubelet/containerd mounts
      // do not block the reflink. Draining also releases the agent's krbd map.
      const prep1 = await w1.executeViaBridge(
        `sudo renet kube prep-fork --mount-path ${SRV_MOUNT} --network-id ${SRV_NET} --node ${NODE1}`
      );
      expect(prep1.code, `prep-fork server: ${prep1.stderr}`).toBe(0);
      const prep2 = await w2.executeViaBridge(
        `sudo renet kube prep-fork --mount-path /mnt/rediacc/mounts/${REPO} --network-id ${AGT_NET} --node ${NODE2}`
      );
      expect(prep2.code, `prep-fork agent: ${prep2.stderr}`).toBe(0);

      // S2 verdict 2: coordinated CoW — control-plane image FIRST, then the agent.
      const forkSrv = await w1.executeViaBridge(
        `sudo renet repository fork --name ${REPO} --tag ${FORK_REPO} --network-id ${FORK_SRV_NET}`
      );
      expect(forkSrv.code, `fork control image: ${forkSrv.stderr}`).toBe(0);
      const forkAgt = await w2.executeViaBridge(
        `sudo renet repository fork --name ${REPO} --tag ${FORK_REPO} --network-id ${FORK_AGT_NET}`
      );
      expect(forkAgt.code, `fork agent image: ${forkAgt.stderr}`).toBe(0);

      // Mount the fork images (no docker; k8s repo).
      const mnt1 = await w1.executeViaBridge(
        `sudo renet repository mount --name ${FORK_REPO} --network-id ${FORK_SRV_NET} --start-docker=false`
      );
      expect(mnt1.code, `mount fork control: ${mnt1.stderr}`).toBe(0);
      const mnt2 = await w2.executeViaBridge(
        `sudo renet repository mount --name ${FORK_REPO} --network-id ${FORK_AGT_NET} --start-docker=false`
      );
      expect(mnt2.code, `mount fork agent: ${mnt2.stderr}`).toBe(0);

      // Assign the fork's secondary IPs to the real NIC (co-tenancy: parent is
      // stopped, so the fork relocates onto new IPs on the same machines).
      await w1.executeViaBridge(`sudo ip addr add ${W1_FORK_IP}/24 dev ${NIC} 2>/dev/null; true`);
      await w2.executeViaBridge(`sudo ip addr add ${W2_FORK_IP}/24 dev ${NIC} 2>/dev/null; true`);

      // S2 verdict 3: SERVER identity rewrite first (regen serving cert keeping CA,
      // bind the new IP), wait Ready, THEN the agent (reuse the CA-derived token).
      const idSrv = await w1.executeViaBridge(
        `sudo renet kube identity-rewrite --mount-path ${FORK_MOUNT} --network-id ${SRV_NET} --mode server --new-node-ip ${W1_FORK_IP} --new-network-id ${FORK_SRV_NET}`,
        540_000
      );
      expect(idSrv.code, `identity-rewrite server: ${idSrv.stderr}`).toBe(0);
      expect(await poll(() => readyNodeCount(FORK_KC).then((n) => n >= 1), 150_000)).toBe(true);

      const forkTok = await w1.executeViaBridge(
        `sudo renet kube join-token --mount-path ${FORK_MOUNT} --network-id ${FORK_SRV_NET}`
      );
      const token = /K10\S+/.exec(forkTok.stdout + forkTok.stderr)?.[0];
      expect(token, 'fork join token (CA preserved)').toBeTruthy();
      const idAgt = await w2.executeViaBridge(
        `sudo renet kube identity-rewrite --mount-path /mnt/rediacc/mounts/${FORK_REPO} --network-id ${AGT_NET} --mode agent --new-node-ip ${W2_FORK_IP} --new-network-id ${FORK_AGT_NET} --server https://${W1_FORK_IP}:6443 --token ${token}`,
        540_000
      );
      expect(idAgt.code, `identity-rewrite agent: ${idAgt.stderr}`).toBe(0);

      // Both fork nodes Ready on the NEW IPs.
      expect(await poll(() => readyNodeCount(FORK_KC).then((n) => n >= 2), 150_000)).toBe(true);
      await uncordon(w1, FORK_KC, [NODE1, NODE2]);
      const forkMs = Date.now() - t0;
      process.stdout.write(`[suite17] whole-cluster fork wall-time: ${forkMs}ms\n`);
      // The server self-heals its InternalIP immediately; the agent's kubelet
      // patches its Node to the new NIC a few seconds after reconnecting, so poll.
      expect(
        await poll(async () => (await internalIP(FORK_KC, NODE1)) === W1_FORK_IP, 90_000)
      ).toBe(true);
      expect(
        await poll(async () => (await internalIP(FORK_KC, NODE2)) === W2_FORK_IP, 90_000)
      ).toBe(true);

      // The whole cluster's state (kine) came across into the fork.
      expect(await cmMarker(FORK_KC)).toBe('parent-v1');

      // Diverge the fork's state — the parent's CoW image must stay untouched.
      const patch = await kubectlOn(
        w1,
        FORK_KC,
        `-n ${NS} patch configmap clusterstate --type merge -p '{"data":{"marker":"fork-v2"}}'`
      );
      expect(patch.code, patch.stderr).toBe(0);
      expect(await cmMarker(FORK_KC)).toBe('fork-v2');
    });

    test('6. parent untouched: tear the fork down, restart the parent, its state is unchanged', async () => {
      // S1 verdict 2 (co-tenancy = NO): bring the fork DOWN before the parent UP.
      await w2.executeViaBridge(
        `sudo renet kube uninstall --mount-path /mnt/rediacc/mounts/${FORK_REPO} --network-id ${FORK_AGT_NET}`
      );
      await w1.executeViaBridge(
        `sudo renet kube uninstall --mount-path ${FORK_MOUNT} --network-id ${FORK_SRV_NET}`
      );
      await w1.executeViaBridge(`sudo ip addr del ${W1_FORK_IP}/24 dev ${NIC} 2>/dev/null; true`);
      await w2.executeViaBridge(`sudo ip addr del ${W2_FORK_IP}/24 dev ${NIC} 2>/dev/null; true`);

      // Restart the parent's k3s units (identity unchanged; its image was never
      // modified by the fork — CoW). Server first, then agent.
      const startSrv = await w1.executeViaBridge(`sudo systemctl start rediacc-k3s-${SRV_NET}`);
      expect(startSrv.code, `restart parent server: ${startSrv.stderr}`).toBe(0);
      await w2.executeViaBridge(`sudo systemctl start rediacc-k3s-${AGT_NET}`);
      expect(await poll(() => readyNodeCount(KC).then((n) => n >= 2), 180_000)).toBe(true);
      await uncordon(w1, KC, [NODE1, NODE2]);

      // The parent's ConfigMap is still parent-v1: the fork's fork-v2 write was
      // CoW-isolated, so the parent is untouched.
      expect(await cmMarker(KC)).toBe('parent-v1');
    });

    test('7. set up a single-node cluster to migrate cross-machine', async () => {
      // The multi-node parent occupies both workers; a cross-machine migrate needs
      // a free destination, so tear the parent down first and stand up a fresh
      // single-node cluster on worker 1.
      await teardownAll();
      const create = await w1.executeViaBridge(
        `sudo renet repository create --name ${MIG_REPO} --network-id ${MIG_NET} --unencrypted --size 6G`
      );
      expect(create.code, create.stderr).toBe(0);
      const install = await w1.executeViaBridge(
        `sudo renet kube install --mount-path ${MIG_MOUNT} --network-id ${MIG_NET} --role server --bind-ip ${W1_IP}`,
        540_000
      );
      expect(install.code, install.stderr).toBe(0);
      expect(await poll(() => readyNodeCountOn(w1, MIG_KC).then((n) => n >= 1), 150_000)).toBe(
        true
      );

      // Cluster state in kine: a ConfigMap the migrate must carry across.
      const cm = await kubectlOn(
        w1,
        MIG_KC,
        'create configmap migstate --from-literal=marker=mig-v1'
      );
      expect(cm.code, cm.stderr).toBe(0);
      expect(await migMarker(w1)).toBe('mig-v1');
    });

    test('8. cluster migrate worker1 -> worker2 with a measured cutover downtime', async () => {
      // Cold cutover: stop the source, ship the control-plane image, rewrite its
      // identity onto worker 2, start. Downtime = source-stop -> destination-Ready.
      const downStart = Date.now();

      // Drain + stop the source so its image is consistent (S2 verdict 5).
      const prep = await w1.executeViaBridge(
        `sudo renet kube prep-fork --mount-path ${MIG_MOUNT} --network-id ${MIG_NET} --node ${NODE1}`
      );
      expect(prep.code, `migrate prep source: ${prep.stderr}`).toBe(0);
      const umount = await w1.executeViaBridge(
        `sudo renet repository unmount --name ${MIG_REPO} --network-id ${MIG_NET}`
      );
      expect(umount.code, `migrate unmount source: ${umount.stderr}`).toBe(0);

      // Ship the control-plane image worker1 -> worker2 (per-image block transfer,
      // the migrate data plane; --dest-user inferred from SUDO_USER).
      const push = await w1.executeViaBridge(
        `sudo renet backup push --name ${MIG_REPO} --datastore ${DATASTORE} --target machine --dest-host ${W2_IP} --dest-path ${DATASTORE} --dest ${MIG_REPO} --strategy physical`
      );
      expect(push.code, `migrate image transfer: ${push.stderr}`).toBe(0);

      // Bring the cluster up on worker 2 under its new identity (same networkID,
      // new NIC; kine — including migstate — rides the image).
      const mount = await w2.executeViaBridge(
        `sudo renet repository mount --name ${MIG_REPO} --network-id ${MIG_NET} --start-docker=false`
      );
      expect(mount.code, `migrate mount dest: ${mount.stderr}`).toBe(0);
      const idw = await w2.executeViaBridge(
        `sudo renet kube identity-rewrite --mount-path ${MIG_MOUNT} --network-id ${MIG_NET} --mode server --new-node-ip ${W2_IP}`,
        540_000
      );
      expect(idw.code, `migrate identity-rewrite dest: ${idw.stderr}`).toBe(0);
      // The image moved to a machine with a different hostname, so k3s
      // re-registers the node as NODE2 (leaving a stale NODE1 ghost from the
      // source). Wait for NODE2 to be Ready with worker 2's IP.
      expect(
        await poll(async () => (await internalIPOn(w2, MIG_KC, NODE2)) === W2_IP, 150_000)
      ).toBe(true);
      await uncordon(w2, MIG_KC, [NODE2]);
      // Reap the source-hostname ghost node (cross-hostname relocation, S2 exp 3).
      await kubectlOn(w2, MIG_KC, `delete node ${NODE1} --ignore-not-found`);

      const downtimeMs = Date.now() - downStart;
      process.stdout.write(`[suite17] cluster migrate cold-cutover downtime: ${downtimeMs}ms\n`);

      // The relocated cluster is Ready on worker 2 with its kine state intact.
      expect(await readyNodeCountOn(w2, MIG_KC)).toBeGreaterThanOrEqual(1);
      expect(await migMarker(w2)).toBe('mig-v1');
    });

    test('9. teardown leaves both workers clean', async () => {
      await w2.executeViaBridge(
        `sudo renet kube uninstall --mount-path ${MIG_MOUNT} --network-id ${MIG_NET}`
      );
      await w2.executeViaBridge(`sudo renet repository delete --name ${MIG_REPO} --force`);
      await w1.executeViaBridge(
        `sudo renet repository delete --name ${MIG_REPO} --force 2>/dev/null; true`
      );
      const repos1 = await w1.executeViaBridge('sudo renet list repositories --json');
      const repos2 = await w2.executeViaBridge('sudo renet list repositories --json');
      expect(repos1.stdout.trim() === '[]' || repos1.stdout.includes('[]')).toBe(true);
      expect(repos2.stdout.trim() === '[]' || repos2.stdout.includes('[]')).toBe(true);
    });
  });
