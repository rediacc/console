import { exec } from 'node:child_process';
import { promisify } from 'node:util';
import { expect, test } from '@playwright/test';
import { BridgeTestRunner } from '../../src/utils/bridge/BridgeTestRunner';
import { getOpsManager, getOpsManagerForGroup } from '../../src/utils/bridge/OpsManager';
import type { ExecResult } from '../../src/utils/bridge/types';

const execAsync = promisify(exec);

// Suite 18 (`Bridge Migrate` job): the free local rehearsal of the wave-L
// cross-DC demo. It boots a SECOND concurrent KVM group (renet12 / 192.168.112,
// disjoint VM IDs 5+51) beside the ambient group A (renet11 / 192.168.111) and
// migrates a running single-node k3s cluster from a group-A worker to a group-B
// worker across the two private LANs (the host routes between the renet11 and
// renet12 bridges, standing in for the WAN between two datacenters).
//
// The migrate MECHANISM itself is already proven cross-machine by suite 17
// (16.0s cutover); what suite 18 proves is the DUAL-GROUP HARNESS:
//   - group B is driven by its own per-group OpsManager (getOpsManagerForGroup)
//     whose `renet ops` subprocesses carry group B's VM_NET/DOCKER_REGISTRY and
//     never bleed group A's (guarded by the provisioning vitest);
//   - the migrate crosses the group boundary (A .11 -> B .51) with data intact,
//     a measured cutover downtime, and k3s serving-cert / kubeconfig resync;
//   - `ops down` of group B provably leaves group A's VMs intact, because the
//     two groups use DISJOINT VM ID sets (ops down destroys `rediacc<id>`
//     domains by ID, not by network).
//
// Gated on K8S_MODE=1 + DUAL_GROUP=1 (set by playwright.migrate.config.ts). The
// second group must already be up (the CI job / local runner boots it before
// invoking this config).
const enabled = process.env.K8S_MODE === '1' && process.env.DUAL_GROUP === '1';

// Group A (source) — ambient env.
const A_NET = process.env.VM_NET_BASE ?? '192.168.111';
const A_WORKER_ID = Number.parseInt((process.env.VM_WORKERS ?? '11 12').split(/\s+/)[0], 10) || 11;
const A_WORKER_IP = `${A_NET}.${A_WORKER_ID}`;
const A_NODE = `rediacc${A_WORKER_ID}`;

// Group B (destination) — the second KVM group. Disjoint IDs from group A.
const B_NET = process.env.GROUP_B_NET_BASE ?? '192.168.112';
const B_NET_NAME = process.env.GROUP_B_NET ?? 'renet12';
const B_BRIDGE_ID = Number.parseInt(process.env.GROUP_B_BRIDGE ?? '5', 10);
const B_WORKER_ID = Number.parseInt(process.env.GROUP_B_WORKER ?? '51', 10);
const B_WORKER_IP = `${B_NET}.${B_WORKER_ID}`;
const B_NODE = `rediacc${B_WORKER_ID}`;

const DATASTORE = '/mnt/rediacc';
const K3S = '/usr/local/bin/rediacc-k3s';
// Network IDs must be 2816 + n*64. Suites 15/16/17 use 2816-3328; suite 18 uses
// 3392 (source) and reuses it on the destination (the image carries its netID).
const MIG_NET = '3392';
const REPO = 'dgmig';
const MOUNT = `${DATASTORE}/mounts/${REPO}`;
const KC = `${MOUNT}/.rediacc/k3s/kubeconfig.yaml`;

test.describe
  .serial('dual-group k8s cluster migrate A->B @bridge @kube @dualgroup', () => {
    test.skip(!enabled, 'Requires K8S_MODE=1 and DUAL_GROUP=1 (a second KVM group booted)');
    test.setTimeout(900_000);

    let src: BridgeTestRunner; // group A worker .11 (source; two-hop via A's bridge)
    const opsA = getOpsManager();
    // Group B's non-singleton manager: its own groupEnv (VM_NET=renet12,
    // DOCKER_REGISTRY derived from .5), disjoint IDs — this is the wave-8 seam.
    const opsB = getOpsManagerForGroup({
      netName: B_NET_NAME,
      netBase: B_NET,
      bridgeId: B_BRIDGE_ID,
      workerIds: [B_WORKER_ID],
    });

    // Group A commands two-hop through group A's bridge (the proven path). Group
    // B commands SSH the host straight to .51 (host reaches both private LANs via
    // its two libvirt bridges; the shared ~/.renet key is trusted on both).
    const onA = (cmd: string, timeout?: number): Promise<ExecResult> =>
      src.executeViaBridge(cmd, timeout);
    const onB = (cmd: string, timeout?: number): Promise<ExecResult> =>
      src.executeOnVM(B_WORKER_IP, cmd, timeout);

    const poll = async (fn: () => Promise<boolean>, timeoutMs = 240_000, stepMs = 5_000) => {
      const attempts = Math.max(1, Math.ceil(timeoutMs / stepMs));
      for (let i = 0; i < attempts; i++) {
        if (await fn()) return true;
        await new Promise((res) => setTimeout(res, stepMs));
      }
      return fn();
    };

    // kubectl against a kubeconfig, run ON the node that currently hosts the
    // cluster (source before migrate, dest after).
    const kubectlOnB = async (args: string): Promise<ExecResult> =>
      onB(`sudo ${K3S} kubectl --kubeconfig ${KC} ${args}`);
    const kubectlOnA = async (args: string): Promise<ExecResult> =>
      onA(`sudo ${K3S} kubectl --kubeconfig ${KC} ${args}`);

    const readyCountA = async (): Promise<number> => {
      const res = await kubectlOnA('get nodes --no-headers');
      if (res.code !== 0) return -1;
      return res.stdout.split('\n').filter((l) => /^\S+\s+Ready\b/.test(l.trim())).length;
    };
    const readyCountB = async (): Promise<number> => {
      const res = await kubectlOnB('get nodes --no-headers');
      if (res.code !== 0) return -1;
      return res.stdout.split('\n').filter((l) => /^\S+\s+Ready\b/.test(l.trim())).length;
    };
    const migMarkerB = async (): Promise<string> => {
      const res = await kubectlOnB('get configmap migstate -o jsonpath="{.data.marker}"');
      return res.stdout.trim();
    };
    // NOTE: group B runs over a single-hop direct SSH (executeOnVM), whose
    // quoting differs from suite 17's two-hop executeViaBridge — a jsonpath
    // filter with embedded quotes (?(@.type=="InternalIP")) gets mangled in
    // transit. Read the INTERNAL-IP straight from the `-o wide` column instead
    // (NAME STATUS ROLES AGE VERSION INTERNAL-IP ...), no quotes required.
    const internalIPB = async (node: string): Promise<string> => {
      const res = await kubectlOnB(`get node ${node} -o wide --no-headers`);
      if (res.code !== 0) return '';
      return res.stdout.trim().split(/\s+/)[5] ?? '';
    };

    // Local (host) virsh — the two fleets are libvirt domains on this host.
    const runningDomains = async (): Promise<string[]> => {
      const { stdout } = await execAsync('sudo virsh list --state-running --name');
      return stdout
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean);
    };

    // The two groups sit on separate libvirt NAT networks whose default rules
    // reject NEW inter-network connections (LIBVIRT_FWI). The host is the router
    // between the two private LANs (the WAN stand-in for the cross-DC demo), so
    // open cross-subnet forwarding both ways. Idempotent; harmless leftover.
    const ensureCrossLanRoute = async (): Promise<void> => {
      for (const [src2, dst2] of [
        [`${A_NET}.0/24`, `${B_NET}.0/24`],
        [`${B_NET}.0/24`, `${A_NET}.0/24`],
      ]) {
        const { stdout } = await execAsync('sudo nft list chain ip filter LIBVIRT_FWI');
        if (!stdout.includes(`ip saddr ${src2} ip daddr ${dst2}`)) {
          await execAsync(
            `sudo nft insert rule ip filter LIBVIRT_FWI ip saddr ${src2} ip daddr ${dst2} counter accept`
          );
        }
      }
    };

    // Clean both nodes for network MIG_NET. The migrate leaves the SOURCE
    // unmounted-but-not-uninstalled (the cluster relocates to the dest), so a
    // re-run must also reap the source's leftover per-cluster k3s dummy
    // interface (rdk<netID>, holding 10.150.x.1) and its systemd unit — else
    // `kube install` fails with "Address already assigned". Fresh CI runners
    // never hit this; local re-runs do.
    const cleanNode = async (
      on: (cmd: string, timeout?: number) => Promise<ExecResult>
    ): Promise<void> => {
      await on(
        `sudo renet kube uninstall --mount-path ${MOUNT} --network-id ${MIG_NET} 2>/dev/null; true`
      );
      await on(
        `sudo systemctl disable --now rediacc-k3s-${MIG_NET} 2>/dev/null; sudo ip link del rdk${MIG_NET} 2>/dev/null; true`
      );
      await on(
        `sudo renet repository unmount --name ${REPO} --network-id ${MIG_NET} 2>/dev/null; true`
      );
      await on(`sudo renet repository delete --name ${REPO} --force 2>/dev/null; true`);
    };
    const teardownRepo = async (): Promise<void> => {
      await cleanNode(onA);
      await cleanNode(onB);
    };

    test.beforeAll(async () => {
      src = BridgeTestRunner.forWorker(1);

      // Host routes between the two private LANs (the WAN stand-in).
      await ensureCrossLanRoute();

      // The fresh group-B worker installs renet under /usr/lib/rediacc/renet/
      // but has no /usr/bin/renet on PATH yet (that symlink is a group-A
      // global-setup step). Add it so `renet ...` resolves like on group A.
      const link = await onB(
        'test -x /usr/bin/renet || sudo ln -sf /usr/lib/rediacc/renet/current/renet /usr/bin/renet; echo linked'
      );
      expect(link.stdout).toContain('linked');

      // The destination worker is fresh from `ops up`: give it a datastore.
      const dsB = await onB(
        `sudo renet functions once --test-mode --function datastore_init --datastore-path ${DATASTORE} --size 10G --force`,
        180_000
      );
      expect(dsB.code, `group B datastore_init: ${dsB.stderr}`).toBe(0);

      // Source datastore: only (re)init if /mnt/rediacc is not already a mount,
      // so we do not wipe a datastore group A's setup already provisioned.
      const dsMountedA = await onA(`mountpoint -q ${DATASTORE} && echo MOUNTED || echo NO`);
      if (!dsMountedA.stdout.includes('MOUNTED')) {
        const dsA = await onA(
          `sudo renet functions once --test-mode --function datastore_init --datastore-path ${DATASTORE} --size 10G --force`,
          180_000
        );
        expect(dsA.code, `group A datastore_init: ${dsA.stderr}`).toBe(0);
      }

      // Peer the two private clusters: authorize group A worker's mesh key on the
      // group B worker so the migrate's rsync (A .11 -> B .51, as $USER) can log
      // in. In a real cross-DC migrate you likewise establish trust between the
      // fleets; here the groups were provisioned by separate `ops up` runs.
      const aPub = await onA('cat ~/.ssh/id_rsa.pub');
      expect(aPub.code, 'read group A worker mesh pubkey').toBe(0);
      const pub = aPub.stdout.trim();
      expect(pub.startsWith('ssh-'), `group A pubkey looks valid: ${pub.slice(0, 20)}`).toBe(true);
      const b64 = Buffer.from(`${pub}\n`).toString('base64');
      const grant = await onB(
        `mkdir -p ~/.ssh && chmod 700 ~/.ssh && touch ~/.ssh/authorized_keys && ` +
          `( grep -qxF "${pub}" ~/.ssh/authorized_keys || echo ${b64} | base64 -d >> ~/.ssh/authorized_keys )`
      );
      expect(grant.code, `authorize group A key on group B: ${grant.stderr}`).toBe(0);

      await teardownRepo();
    });

    test.afterAll(async () => {
      if (process.env.KEEP_GROUPS === '1') return;
      await teardownRepo().catch(() => undefined);
    });

    test('1. both groups are up with DISJOINT VM IDs (ops down safety basis)', async () => {
      const idsA = opsA.getVMIds();
      const idsB = opsB.getVMIds();
      const setA = new Set<number>([idsA.bridge, ...idsA.workers, ...idsA.ceph]);
      const setB = new Set<number>([idsB.bridge, ...idsB.workers, ...idsB.ceph]);
      const overlap = [...setB].filter((id) => setA.has(id));
      expect(overlap, `group B IDs must be disjoint from group A (overlap: ${overlap})`).toEqual(
        []
      );

      // Group B is driven by its own env — this is the anti-bleed contract.
      expect(opsB.getGroupEnv().VM_NET).toBe(B_NET_NAME);
      expect(opsB.getGroupEnv().VM_NET_BASE).toBe(B_NET);

      // Both fleets' workers are live and running renet.
      expect(await opsA.isSSHReady(A_WORKER_IP)).toBe(true);
      expect(await opsB.isSSHReady(B_WORKER_IP)).toBe(true);
      const rv = await onB('renet version');
      expect(rv.code, `group B worker renet: ${rv.stderr}`).toBe(0);
    });

    test('2. cross-LAN peering: group A worker can reach group B worker', async () => {
      // The migrate ships the image A .11 -> B .51; prove the hop works first.
      const hop = await onA(
        `ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o BatchMode=yes -o ConnectTimeout=8 ${B_WORKER_IP} hostname`
      );
      expect(hop.code, `A(.${A_WORKER_ID}) -> B(.${B_WORKER_ID}) ssh: ${hop.stderr}`).toBe(0);
      expect(hop.stdout.trim()).toBe(B_NODE);
    });

    test('3. single-node k3s cluster on group A worker, with kine state', async () => {
      const create = await onA(
        `sudo renet repository create --name ${REPO} --network-id ${MIG_NET} --unencrypted --size 6G`
      );
      expect(create.code, `create source repo: ${create.stderr}`).toBe(0);
      // k3s uses Type=notify; `systemctl start` blocks until Ready, and a cold
      // containerd pull can be slow, so give it a generous budget.
      const install = await onA(
        `sudo renet kube install --mount-path ${MOUNT} --network-id ${MIG_NET} --role server --bind-ip ${A_WORKER_IP}`,
        540_000
      );
      expect(install.code, `kube install source: ${install.stderr}`).toBe(0);
      expect(await poll(() => readyCountA().then((n) => n >= 1), 200_000)).toBe(true);

      // Known data that rides the cluster image (kine): a ConfigMap the migrate
      // must carry across intact.
      const cm = await kubectlOnA('create configmap migstate --from-literal=marker=mig-v1');
      expect(cm.code, `create migstate: ${cm.stderr}`).toBe(0);
      const readBack = await kubectlOnA('get configmap migstate -o jsonpath="{.data.marker}"');
      expect(readBack.stdout.trim()).toBe('mig-v1');
    });

    test('4. cluster migrate A .11 -> B .51 across the LANs, measured cutover', async () => {
      const downStart = Date.now();

      // Drain + stop the source so its image is crash-consistent (S2 verdict 5).
      const prep = await onA(
        `sudo renet kube prep-fork --mount-path ${MOUNT} --network-id ${MIG_NET} --node ${A_NODE}`
      );
      expect(prep.code, `prep source: ${prep.stderr}`).toBe(0);
      const umount = await onA(
        `sudo renet repository unmount --name ${REPO} --network-id ${MIG_NET}`
      );
      expect(umount.code, `unmount source: ${umount.stderr}`).toBe(0);

      // Ship the control-plane image A .11 -> B .51 (per-image FIEMAP-delta block
      // transfer — the migrate data plane, runtime-agnostic; --dest-user inferred
      // from SUDO_USER). This is the actual cross-group, cross-LAN hop.
      const push = await onA(
        `sudo renet backup push --name ${REPO} --datastore ${DATASTORE} --target machine ` +
          `--dest-host ${B_WORKER_IP} --dest-path ${DATASTORE} --dest ${REPO} --strategy physical`,
        600_000
      );
      expect(push.code, `image transfer A->B: ${push.stderr}`).toBe(0);

      // Bring the cluster up on group B under its new identity: mount the image,
      // then identity-rewrite (regenerates the k3s serving cert with the new
      // --tls-san + rewrites the kubeconfig URL = the cert/DNS resync) and bind
      // .51. ensureBinary() extracts rediacc-k3s on the fresh dest node.
      const mount = await onB(
        `sudo renet repository mount --name ${REPO} --network-id ${MIG_NET} --start-docker=false`
      );
      expect(mount.code, `mount dest: ${mount.stderr}`).toBe(0);
      const idw = await onB(
        `sudo renet kube identity-rewrite --mount-path ${MOUNT} --network-id ${MIG_NET} --mode server --new-node-ip ${B_WORKER_IP}`,
        540_000
      );
      expect(idw.code, `identity-rewrite dest: ${idw.stderr}`).toBe(0);

      // The image moved to a host with a different hostname, so k3s re-registers
      // the node as rediacc51 (leaving a rediacc11 ghost from the source). Wait
      // for the dest node Ready on group B's IP.
      expect(await poll(async () => (await internalIPB(B_NODE)) === B_WORKER_IP, 200_000)).toBe(
        true
      );
      await kubectlOnB(`uncordon ${B_NODE}`);
      await kubectlOnB(`delete node ${A_NODE} --ignore-not-found`);

      const downtimeMs = Date.now() - downStart;
      process.stdout.write(
        `[suite18] dual-group cluster migrate A->B cold-cutover downtime: ${downtimeMs}ms\n`
      );

      // The relocated cluster is Ready on group B, serving its migrated kine
      // state (the fresh cert + rewritten kubeconfig prove the resync: kubectl
      // over TLS to https://.51:6443 only succeeds if the SAN was regenerated).
      expect(await readyCountB()).toBeGreaterThanOrEqual(1);
      expect(await migMarkerB()).toBe('mig-v1');
    });

    test('5. ops down of group B leaves group A intact (disjoint-ID safety, live)', async () => {
      const domainsOf = (ids: { bridge: number; workers: number[]; ceph: number[] }): string[] =>
        [ids.bridge, ...ids.workers, ...ids.ceph].map((id) => `rediacc${id}`);
      const groupADomains = domainsOf(opsA.getVMIds());
      const groupBDomains = domainsOf(opsB.getVMIds());

      const before = await runningDomains();
      const presentA = groupADomains.filter((d) => before.includes(d));
      // The env-configured group A VMs must be running now, and all survive.
      expect(presentA.length, `group A domains running before: ${presentA}`).toBeGreaterThan(0);
      for (const d of groupBDomains) {
        expect(before, `group B ${d} must be running before its teardown`).toContain(d);
      }

      // Tear group B down through ITS OWN manager (renet ops down carries group
      // B's env; it destroys group B's domains by ID, never group A's).
      const down = await opsB.stopVMs();
      expect(down.success, `ops down group B: ${down.stderr}`).toBe(true);

      const after = await runningDomains();
      // Group B's VMs are gone...
      for (const d of groupBDomains) {
        expect(after, `group B ${d} must be destroyed`).not.toContain(d);
      }
      // ...and every group A VM that was running still is (disjoint IDs).
      for (const d of presentA) {
        expect(after, `group A ${d} must survive group B teardown`).toContain(d);
      }
    });
  });
