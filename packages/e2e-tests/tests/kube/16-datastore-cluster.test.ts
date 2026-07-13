import { expect, test } from '@playwright/test';
import { BridgeTestRunner } from '../../src/utils/bridge/BridgeTestRunner';
import type { ExecResult } from '../../src/utils/bridge/types';

// Suite 16 (`Bridge Datastore Cluster` job, flagship): the datastore-cluster
// GROUP-SNAP FORK proof (redesign spec 06 §16; CONTRACT.md CT-01k/CT-02k). The
// old per-namespace ceph-csi/RADOS-namespace subject is DELETED — the NEW
// subject is a whole cluster-attached, ceph-group-backed datastore forked
// atomically:
//
//   cluster-attached rbd datastore(s)  ─ group snapshot ─▶ datastore_fork
//     ─ attach --writes {local|ceph} ─▶ kube identity-rewrite --operation fork
//
// It promotes the P2-A proven battery (scratchpad/p2a-fork-battery.sh, the
// live-run FOLLOW-UP #1) to a suite, KEEPING the multinode fork PROOF SHAPE:
//   - GROUP snapshot atomic across the cluster's ceph datastores; the parent is
//     NEVER stopped (a continuous liveness loop witnesses it).
//   - datastore_fork clones each member from the group snap (clone-format-2);
//     attach --writes selects the fork's write home (local dm-COW overlay vs a
//     durable ceph RW clone — the new axis).
//   - kube identity-rewrite --operation fork runs the F1-F8 PKI re-mint on the
//     fork's control-plane clone: the fork's kine carries NO parent CA (CT-01k,
//     a fail-loud fingerprint refusal makes a silent parent-CA fork impossible)
//     and NO parent secret material; the parent admin cert is REJECTED (401) by
//     the fork API but STILL WORKS (200) against the parent (CT-02k).
//   - a MIGRATE leg: an in-place CA-PRESERVING relocate (operation=migrate)
//     keeps the CA + secrets (the fork/migrate arm split, spec 05 §3).
//
// RED-UNTIL-LIVE-RUN (spec 06 authoring bar + P2 FOLLOW-UP #1): authored to
// COMPILE + keep the coverage gate green; the BODY is not executed by this wave
// (needs a RAM-adequate host + healthy ceph — the exact blocker that descoped
// the live P2-A run). The live follow-up must produce the full identity battery
// (parent-vs-fork CA fingerprints, old-cred 401/200, secret absence, ROLE=fork,
// kine/storage markers, continuous parent liveness, the migrate leg).
//
// Gated on K8S_MODE=1 + a ceph topology (VM_CEPH_NODES) + TWO worker VMs
// (control on worker 1, fork dest on worker 2 — S1 verdict 2 forbids two k3s in
// one host netns, so the fork server relocates to a second machine).
const enabled = process.env.K8S_MODE === '1';
const cephNodes = (process.env.VM_CEPH_NODES ?? '').trim();
const workers = (process.env.VM_WORKERS ?? '').trim().split(/\s+/).filter(Boolean);
const canRun = enabled && cephNodes.length > 0 && workers.length >= 2;

const K3S = '/usr/local/bin/rediacc-k3s';
const NET = process.env.VM_NET_BASE ?? '192.168.111';
const W1_IP = `${NET}.${workers[0] ?? '11'}`; // control plane (real private NIC)
const W2_IP = `${NET}.${workers[1] ?? '12'}`; // fork dest (real private NIC)

const CLUSTER = 'cephprod';
// The anchor control datastore + the data datastore, both ceph-group-backed so
// the whole cluster forks via ONE atomic group snapshot.
const CTRL_DS = `ds-control-${CLUSTER}`;
const CTRL_MOUNT = `/mnt/rediacc-ds/${CTRL_DS}`;
const CTRL_NET = '2944';
const DATA_DS = 'cephshop';
const DATA_MOUNT = `/mnt/rediacc-ds/${DATA_DS}`;
const POOL = `dsc${Date.now().toString(36)}`;
const KC = `${CTRL_MOUNT}/.rediacc/k3s/kubeconfig.yaml`;

// The fork: `<parent>:f1` records, mounted at `<parent>-f1` on the dest.
const FORK_TAG = 'f1';
const SNAP = 'forksnap';
const FORK_CTRL_MOUNT = `${CTRL_MOUNT}-${FORK_TAG}`;
const FORK_DATA_MOUNT = `${DATA_MOUNT}-${FORK_TAG}`;
const FORK_NET = '3008';
const FKC = `${FORK_CTRL_MOUNT}/.rediacc/k3s/kubeconfig.yaml`;

// A storage-level marker written into the data datastore: by construction it must
// ride the ceph clone into the fork (the PV-data isolation claim).
const DATA_MARKER = `${DATA_MOUNT}/repos/shop/volumes/data-marker`;
const FORK_DATA_MARKER = `${FORK_DATA_MOUNT}/repos/shop/volumes/data-marker`;
const APP_SECRET_VALUE = 's3cr3t-cephprod';

test.describe
  .serial('datastore-cluster group-snap fork @bridge @kube @k8s @ceph', () => {
    test.skip(!canRun, 'Requires K8S_MODE=1, VM_CEPH_NODES, and TWO worker VMs');
    test.setTimeout(900_000);

    let w1: BridgeTestRunner; // control plane host
    let w2: BridgeTestRunner; // fork dest host
    let cephNode: BridgeTestRunner;

    let parentCaFingerprint = '';

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

    const readyOn = async (runner: BridgeTestRunner, kc: string): Promise<boolean> => {
      const res = await kubectlOn(runner, kc, 'get nodes --no-headers');
      return res.code === 0 && /\sReady\b/.test(res.stdout);
    };

    // The k3s server-ca fingerprint identifies the cluster PKI. A fork MUST NOT
    // share it (F1); a migrate MUST preserve it.
    const caFingerprintOn = async (runner: BridgeTestRunner, mount: string): Promise<string> => {
      const res = await runner.executeViaBridge(
        `sudo openssl x509 -in ${mount}/.rediacc/k3s/data/server/tls/server-ca.crt -noout -fingerprint -sha256`
      );
      return res.stdout.trim();
    };

    // Stage the ceph admin keyring + ceph.conf on a worker (renet shells rbd for
    // clones), plus load krbd.
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

    // A k3s node leaves containerd/kubelet KERNEL submounts under the datastore
    // mount it ran on. `kube uninstall` removes the unit (cgroup-kill), but those
    // submounts survive, so the datastore release is then CORRECTLY refused by the
    // no-lazy-success guard (spec 03 §2b) with "target is busy" — the product
    // behaving right, not failing. The suite owns cleanup of what it created, so it
    // unwinds them itself. The missing product-side porcelain (a shared node-side
    // teardown that unwinds BEFORE any release verb) is gate finding #20; this is
    // its third witness (after FU#2 evict and the suite-15 reused-fleet mounts).
    // Shell form: executeViaBridge relays through THREE shells and escapeForNestedSSH
    // does NOT escape `$`, so the selection stays variable-free (a `$(...)` here would
    // be expanded on the LOCAL host). Holders = mountpoints strictly UNDER our mount
    // (kubelet pod volumes) + mountpoints OUTSIDE the datastore root whose line
    // references our mount (the /run/k3s containerd overlays, which hold it busy from
    // outside its path). Excluding `^<root>/` keeps a SIBLING datastore (the fork's
    // `<mount>-f1`, a prefix match) out of the list. Deepest-first, repeat 3×.
    const unwindSubmounts = async (runner: BridgeTestRunner, mount: string): Promise<void> => {
      const root = mount.replace(/\/[^/]+$/, '');
      const select =
        `{ cut -d" " -f2 /proc/mounts | grep "^${mount}/"; ` +
        `grep -F "${mount}" /proc/mounts | cut -d" " -f2 | grep -v "^${root}/"; } | sort -ru`;
      const res = await runner.executeViaBridge(
        `sudo bash -c 'for i in 1 2 3; do ${select} | xargs -r -n1 umount 2>/dev/null; ${select} | xargs -r -n1 umount -l 2>/dev/null; sleep 1; done; udevadm settle 2>/dev/null; ` +
          `sync; echo REMAINING_HOLDERS:; ${select}'; true`
      );
      process.stdout.write(
        `[suite16 unwind ${mount}] ${res.stdout.trim().replaceAll('\n', ' | ')}\n`
      );
    };

    // `renet kube install` auto-starts the node CSI units (rediacc-csi / -provisioner
    // / -snapshotter) as HOST daemons whose socket + state live INSIDE the datastore,
    // and NO verb ever stops them (`renet kube csi-node-down` exists with zero
    // callers) → every storage release hits EBUSY with no mount holder to find. Gate
    // finding #26. The suite stops what the product started.
    const csiNodeDown = async (runner: BridgeTestRunner): Promise<void> => {
      await runner.executeViaBridge('sudo renet kube csi-node-down 2>/dev/null; true');
    };

    // Names whatever still holds a datastore when the mount-level unwind reports
    // clean: the dm device's OPEN COUNT, any loop device backed by a file on the
    // datastore (the per-volume LUKS stack), leftover container-runtime processes,
    // and — the one /proc/mounts cannot see — a mount of it inside ANOTHER MOUNT
    // NAMESPACE, found by scanning every process's mountinfo. Variable-free shell
    // (executeViaBridge relays through three shells and does not escape `$`).
    const deepHolders = async (
      runner: BridgeTestRunner,
      mount: string,
      dmName: string
    ): Promise<void> => {
      const res = await runner.executeViaBridge(
        `sudo bash -c 'echo "DM_INFO:"; dmsetup info -c ${dmName} 2>/dev/null || echo none; ` +
          `echo "LOOPS:"; losetup -a | grep -F "${mount}" || echo none; ` +
          `echo "PROCS:"; ps -eo pid,args | grep -E "containerd-shim|csi-serve|csi-provisioner|csi-snapshotter|k3s" | grep -v grep || echo none; ` +
          `echo "MOUNTINFO_NS:"; grep -l -F "${mount}" /proc/[0-9]*/mountinfo 2>/dev/null || echo none'; true`
      );
      process.stdout.write(
        `[suite16 deepHolders ${mount}] ${res.stdout.trim().replaceAll('\n', ' | ')}\n`
      );
    };

    const teardownAll = async (): Promise<void> => {
      await csiNodeDown(w1);
      await csiNodeDown(w2);
      // Fork first (on the dest): discard the fork records + uninstall its k3s.
      await w2.executeViaBridge(
        `sudo renet kube uninstall --mount-path ${FORK_CTRL_MOUNT} --network-id ${FORK_NET} 2>/dev/null; true`
      );
      await w2.executeViaBridge(
        `sudo renet datastore detach --name ${CTRL_DS}:${FORK_TAG} --discard 2>/dev/null; true`
      );
      await w2.executeViaBridge(
        `sudo renet datastore detach --name ${DATA_DS}:${FORK_TAG} --discard 2>/dev/null; true`
      );
      // Parent (on the control host).
      await w1.executeViaBridge(
        `sudo renet kube uninstall --mount-path ${CTRL_MOUNT} --network-id ${CTRL_NET} 2>/dev/null; true`
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
      const check = await w2.executeViaBridge(`sudo rbd ls ${POOL} 2>&1; echo rc=$?`);
      expect(check.stdout, `worker-2 rbd access: ${check.stdout}`).toContain('rc=0');
    });

    test('2. anchor cluster on a ceph control datastore + a ceph data datastore', async () => {
      // The control plane lives inside a cluster-labeled CEPH control datastore
      // (so it joins the group snapshot). Real-NIC bind for cross-machine fork
      // reachability.
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
      const install = await w1.executeViaBridge(
        `sudo renet kube install --mount-path ${CTRL_MOUNT} --network-id ${CTRL_NET} --role server --bind-ip ${W1_IP}`,
        540_000
      );
      expect(install.code, install.stderr).toBe(0);
      expect(await poll(() => readyOn(w1, KC), 150_000)).toBe(true);

      // The data datastore: ceph-backed, same cluster backref (joins the group).
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
    });

    test('3. seed parent cluster state + storage marker; capture the parent CA', async () => {
      // Storage-level marker that must ride the ceph clone.
      await w1.executeViaBridge(`sudo mkdir -p ${DATA_MOUNT}/repos/shop/volumes`);
      await writeFileOn(w1, DATA_MARKER, 'cephprod-original');
      await w1.executeViaBridge('sync');

      // kine-resident parent state the fork scrub must act on: a repo namespace,
      // the ROLE ConfigMap (primary), a labeled rediacc-env Secret, a THIRD-PARTY
      // operator secret, and an app-data marker ConfigMap.
      const K = (args: string) => kubectlOn(w1, KC, args);
      await K('create namespace shop');
      await K(
        'label ns shop rediacc.io/injected=true rediacc.io/repo-namespace=true rediacc.io/repo=shop --overwrite'
      );
      await w1.executeViaBridge(
        `sudo ${K3S} kubectl --kubeconfig ${KC} -n shop create configmap rediacc-role ` +
          `--from-literal=REDIACC_ROLE=primary --from-literal=REDIACC_DATASTORE=${DATA_DS} --dry-run=client -o yaml | ` +
          `sudo ${K3S} kubectl --kubeconfig ${KC} apply -f -`
      );
      await K('-n shop label configmap rediacc-role rediacc.io/injected=true --overwrite');
      await w1.executeViaBridge(
        `sudo ${K3S} kubectl --kubeconfig ${KC} -n shop create secret generic rediacc-env ` +
          `--from-literal=APP_SECRET=${APP_SECRET_VALUE} --dry-run=client -o yaml | ` +
          `sudo ${K3S} kubectl --kubeconfig ${KC} apply -f -`
      );
      await K('-n shop label secret rediacc-env rediacc.io/injected=true --overwrite');
      await w1.executeViaBridge(
        `sudo ${K3S} kubectl --kubeconfig ${KC} -n shop create secret generic operator-db-pass ` +
          `--from-literal=PASSWORD=hunter2 --dry-run=client -o yaml | ` +
          `sudo ${K3S} kubectl --kubeconfig ${KC} apply -f -`
      );
      await w1.executeViaBridge(
        `sudo ${K3S} kubectl --kubeconfig ${KC} -n shop create configmap app-data ` +
          `--from-literal=marker=cephprod-original --dry-run=client -o yaml | ` +
          `sudo ${K3S} kubectl --kubeconfig ${KC} apply -f -`
      );

      // Extract the parent admin cert+key for the CT-02k 401/200 test.
      await w1.executeViaBridge(
        `sudo ${K3S} kubectl --kubeconfig ${KC} config view --raw ` +
          `-o jsonpath="{.users[0].user.client-certificate-data}" | base64 -d | sudo tee /tmp/old-admin.crt >/dev/null`
      );
      await w1.executeViaBridge(
        `sudo ${K3S} kubectl --kubeconfig ${KC} config view --raw ` +
          `-o jsonpath="{.users[0].user.client-key-data}" | base64 -d | sudo tee /tmp/old-admin.key >/dev/null`
      );

      parentCaFingerprint = await caFingerprintOn(w1, CTRL_MOUNT);
      expect(parentCaFingerprint).toMatch(/Fingerprint=/);

      // Flush the control node's kine SQLite (on the ceph control datastore mount)
      // to the RBD image BEFORE the crash-consistent group snapshot (test 4). The
      // snapshot never stops the parent, so a just-seeded-but-unsynced kine write
      // (the `shop` namespace + configmaps) would not ride the clone — a test race,
      // not a product gap (a real fork accepts the crash-consistent point-in-time).
      await w1.executeViaBridge('sync');
    });

    test('4. GROUP snapshot atomic across the cluster ceph datastores; parent never stopped', async () => {
      // Start a background parent-liveness loop: the group snapshot + clone must
      // NOT interrupt the parent API (crash-consistent, no stop).
      await w1.executeViaBridge(
        `sudo bash -c 'rm -f /tmp/live.stop; (while [ ! -f /tmp/live.stop ]; do ` +
          `${K3S} kubectl --kubeconfig ${KC} get --raw=/readyz >>/tmp/live.log 2>&1 || echo UNREACHABLE >>/tmp/live.log; ` +
          `sleep 2; done) >/dev/null 2>&1 &'`
      );

      const snap = await w1.datastoreSnapshotCreate({ group: CLUSTER, snapshot: SNAP });
      expect(w1.isSuccess(snap), (snap.stdout + snap.stderr).slice(-400)).toBe(true);
    });

    test('5. datastore_fork clones each member from the group snap (clone-format-2)', async () => {
      const t0 = Date.now();
      for (const parent of [CTRL_DS, DATA_DS]) {
        const fork = await w1.datastoreFork({
          parent,
          tag: FORK_TAG,
          snapshot: SNAP,
          group: CLUSTER,
        });
        expect(
          w1.isSuccess(fork),
          `fork ${parent}: ${(fork.stdout + fork.stderr).slice(-400)}`
        ).toBe(true);
      }
      process.stdout.write(`[suite16] group-snap clone wall-time: ${Date.now() - t0}ms\n`);
    });

    test('6. attach the clones on the dest with --writes local (ephemeral dm-COW overlay)', async () => {
      // Prep the fork DEST (w2) with the package set a fork of a DIFFERENT cluster
      // needs: ceph-common (`rbd`, which `datastore attach` shells) + sqlite3 (the
      // fork's `kube identity-rewrite` F2 kine-scrub shells `sqlite3`). The CLI
      // cluster-fork seeds this via prepareForkDest → kube_fork_dest_prep; the raw
      // primitive path must too, or identity-rewrite (test 7) fails "sqlite3 not
      // found on PATH".
      expect(w2.isSuccess(await w2.kubeForkDestPrep()), 'kube_fork_dest_prep on w2').toBe(true);

      // Free the dest host netns for the fork server: stop any k3s already on w2.
      await w2.executeViaBridge(
        `for u in $(systemctl list-units 'rediacc-k3s-*.service' --no-legend --plain 2>/dev/null | awk '{print $1}'); do sudo systemctl stop "$u" || true; done`
      );

      // Cross-node fork attach requires the fork's registry RECORD on the dest
      // first. datastore_fork registered each fork on w1 (the source) only; the
      // CLI cluster-fork ferries `datastore list --json` → base64 → datastore_adopt
      // on the dest before attaching (cluster-fork.ts). Replicate that here: w2's
      // registry has no `<parent>:f1` row until we adopt the ferried record.
      const listRes = await w1.executeViaBridge('sudo renet datastore list --json');
      const records = JSON.parse(listRes.stdout) as { name: string }[];
      for (const parent of [CTRL_DS, DATA_DS]) {
        const forkName = `${parent}:${FORK_TAG}`;
        const rec = records.find((r) => r.name === forkName);
        expect(rec, `fork record ${forkName} on w1: ${listRes.stdout}`).toBeTruthy();
        const b64 = Buffer.from(JSON.stringify(rec)).toString('base64');
        const adopt = await w2.executeViaBridge(
          `sudo renet datastore adopt --name ${forkName} --record-b64 ${b64}`
        );
        expect(adopt.code, `adopt ${forkName} on w2: ${adopt.stderr}`).toBe(0);
      }

      // --writes local: the fork's writes land in a local dm-COW overlay over the
      // RO clone (the ephemeral disposition — the new axis vs --writes ceph).
      for (const parent of [CTRL_DS, DATA_DS]) {
        const attach = await w2.datastoreAttach({ name: `${parent}:${FORK_TAG}`, writes: 'local' });
        expect(w2.isSuccess(attach), `attach ${parent}:${FORK_TAG}: ${attach.stderr}`).toBe(true);
      }
      // The fork's control-plane data-dir is present on the dest mount.
      const present = await w2.executeViaBridge(
        `sudo test -d ${FORK_CTRL_MOUNT}/.rediacc/k3s && echo OK || echo MISSING`
      );
      expect(present.stdout).toContain('OK');
    });

    test('7. identity-rewrite --operation fork: F1-F8 PKI re-mint on the fork control plane', async () => {
      const rewrite = await w2.kubeIdentityRewrite({
        mountPath: FORK_CTRL_MOUNT,
        operation: 'fork',
        mode: 'server',
        newNodeIp: W2_IP,
        newNetworkId: FORK_NET,
        role: 'fork',
        writes: 'local',
      });
      expect(w2.isSuccess(rewrite), (rewrite.stdout + rewrite.stderr).slice(-800)).toBe(true);
      expect(await poll(() => readyOn(w2, FKC), 150_000)).toBe(true);
    });

    test('8. CT-01k: the fork carries a FRESH CA + NO parent secret material; ROLE=fork', async () => {
      // (a) fork server-ca fingerprint MUST differ from the parent's (a fail-loud
      // fingerprint refusal makes a byte-identical CA impossible by construction).
      const forkCa = await caFingerprintOn(w2, FORK_CTRL_MOUNT);
      expect(forkCa).toMatch(/Fingerprint=/);
      expect(forkCa).not.toBe(parentCaFingerprint);

      const FK = (args: string) => kubectlOn(w2, FKC, args);
      // (b) labeled + third-party secrets scrubbed from the fork's kine.
      const labeled = await FK('get secrets -A -l rediacc.io/injected=true --no-headers');
      expect(labeled.stdout.trim()).toBe('');
      const shopSecrets = await FK('-n shop get secrets --no-headers');
      expect(shopSecrets.stdout).not.toContain('rediacc-env');
      expect(shopSecrets.stdout).not.toContain('operator-db-pass');

      // (c) ROLE ConfigMap rewritten to fork.
      const role = await FK(
        '-n shop get configmap rediacc-role -o jsonpath="{.data.REDIACC_ROLE}"'
      );
      expect(role.stdout.trim()).toBe('fork');

      // (d) kine app-data marker rode the fork (cluster state present).
      const kineMarker = await FK('-n shop get configmap app-data -o jsonpath="{.data.marker}"');
      expect(kineMarker.stdout.trim()).toBe('cephprod-original');

      // (e) the storage marker rode the ceph clone into the fork's data datastore.
      const storageMarker = await w2.executeViaBridge(`sudo cat ${FORK_DATA_MARKER}`);
      expect(storageMarker.stdout.trim()).toBe('cephprod-original');
    });

    test('9. CT-02k: the parent admin cert is REJECTED (401) by the fork but WORKS (200) on the parent', async () => {
      // Run from the control host (it has the old cert). The fork API is on the
      // dest's new IP with the new CA → 401; the parent API is unchanged → 200.
      const vsFork = await w1.executeViaBridge(
        `curl -sk --cert /tmp/old-admin.crt --key /tmp/old-admin.key https://${W2_IP}:6443/api/v1/nodes -o /dev/null -w '%{http_code}'`
      );
      expect(vsFork.stdout.trim()).toBe('401');
      const vsParent = await w1.executeViaBridge(
        `curl -sk --cert /tmp/old-admin.crt --key /tmp/old-admin.key https://${W1_IP}:6443/api/v1/nodes -o /dev/null -w '%{http_code}'`
      );
      expect(vsParent.stdout.trim()).toBe('200');
    });

    test('10. parent continuity: the liveness loop never dropped + the parent secret survives', async () => {
      await w1.executeViaBridge('sudo touch /tmp/live.stop; sleep 3');
      const live = await w1.executeViaBridge('cat /tmp/live.log');
      expect(live.stdout).not.toContain('UNREACHABLE');
      const stillReady = await w1.executeViaBridge(
        `sudo ${K3S} kubectl --kubeconfig ${KC} get --raw=/readyz`
      );
      expect(stillReady.stdout).toContain('ok');
      const parentSecret = await kubectlOn(w1, KC, '-n shop get secret rediacc-env -o name');
      expect(parentSecret.stdout).toContain('secret/rediacc-env');
    });

    test('11. MIGRATE leg: in-place CA-PRESERVING relocate keeps the CA + secrets', async () => {
      // The migrate arm (spec 05 §3): CA preserved, serving leaf regenerated for
      // the (same) IP, networkID kept, secrets STAY — the opposite of the fork arm.
      const before = await caFingerprintOn(w1, CTRL_MOUNT);
      const migrate = await w1.kubeIdentityRewrite({
        mountPath: CTRL_MOUNT,
        operation: 'migrate',
        mode: 'server',
        newNodeIp: W1_IP,
      });
      expect(w1.isSuccess(migrate), (migrate.stdout + migrate.stderr).slice(-400)).toBe(true);
      const after = await caFingerprintOn(w1, CTRL_MOUNT);
      expect(after).toBe(before); // CA preserved
      const secret = await kubectlOn(w1, KC, '-n shop get secret rediacc-env -o name');
      expect(secret.stdout).toContain('secret/rediacc-env');
      const role = await kubectlOn(
        w1,
        KC,
        '-n shop get configmap rediacc-role -o jsonpath="{.data.REDIACC_ROLE}"'
      );
      expect(role.stdout.trim()).toBe('primary');
    });

    test('12. teardown: discard the forks, uninstall, delete the datastores, drop the pool', async () => {
      expect(
        w2.isSuccess(await w2.kubeUninstall({ mountPath: FORK_CTRL_MOUNT, networkId: FORK_NET }))
      ).toBe(true);
      // Unwind the fork k3s's leftover containerd/kubelet submounts before release
      // (see unwindSubmounts / gate finding #20) — and the node CSI daemons the
      // product started and never stops (#26), which are the holder that actually
      // blocks the release.
      await csiNodeDown(w2);
      await unwindSubmounts(w2, FORK_CTRL_MOUNT);
      await unwindSubmounts(w2, FORK_DATA_MOUNT);
      // The fork's dm-COW device has been refusing `dmsetup remove` with EBUSY even
      // after the mounts are unwound, the CSI units are stopped and the retry (#27)
      // has run — so the holder is neither a host mount nor a known process. Name it:
      // the dm OPEN COUNT says whether anything still has the device open, and a scan
      // of EVERY process's mountinfo finds a mount of it inside another mount
      // NAMESPACE (a leftover container's private namespace is invisible in
      // /proc/mounts).
      //
      // The probe BEFORE the release is only a baseline — the datastore is still
      // ATTACHED here, so its mount is live and Open=1 means nothing. The probe that
      // matters runs AFTER a FAILED detach (below), when the product has unmounted the
      // filesystem and the dm removal has just been refused: whatever holds the device
      // THEN is the real holder of gate finding #29.
      await deepHolders(w2, FORK_CTRL_MOUNT, `${CTRL_DS}-${FORK_TAG}-cow`);
      // --discard removes the fork record (forks only).
      const forkDetach = await w2.datastoreDetach(`${CTRL_DS}:${FORK_TAG}`, true);
      if (!w2.isSuccess(forkDetach)) {
        // Post-mortem, captured at the only moment it is meaningful (fs unmounted, dm
        // removal just refused) so the next run of this suite — by CI or by whoever
        // picks up #29 — arrives with the holder named instead of another blind cycle.
        await deepHolders(w2, FORK_CTRL_MOUNT, `${CTRL_DS}-${FORK_TAG}-cow`);
      }
      expect(
        w2.isSuccess(forkDetach),
        `fork discard (#29): ${(forkDetach.stdout + forkDetach.stderr).slice(-400)}`
      ).toBe(true);
      expect(w2.isSuccess(await w2.datastoreDetach(`${DATA_DS}:${FORK_TAG}`, true))).toBe(true);
      expect(
        w1.isSuccess(await w1.kubeUninstall({ mountPath: CTRL_MOUNT, networkId: CTRL_NET }))
      ).toBe(true);
      // The parent node leaves the same two holders on its own datastore mounts.
      await csiNodeDown(w1);
      await unwindSubmounts(w1, CTRL_MOUNT);
      await unwindSubmounts(w1, DATA_MOUNT);
      expect(w1.isSuccess(await w1.datastoreDetach(DATA_DS))).toBe(true);
      expect(w1.isSuccess(await w1.datastoreDelete(DATA_DS))).toBe(true);
      expect(w1.isSuccess(await w1.datastoreDetach(CTRL_DS))).toBe(true);
      expect(w1.isSuccess(await w1.datastoreDelete(CTRL_DS))).toBe(true);
    });
  });
