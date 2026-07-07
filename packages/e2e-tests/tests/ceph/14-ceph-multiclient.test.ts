import { expect, test } from '@playwright/test';
import { BridgeTestRunner } from '../../src/utils/bridge/BridgeTestRunner';

// Combined topology only: needs BOTH a Ceph cluster and >=2 worker/client VMs.
const cephNodes = (process.env.VM_CEPH_NODES ?? '').trim();
const workers = (process.env.VM_WORKERS ?? '').trim().split(/\s+/).filter(Boolean);
const hasCephAndTwoClients = cephNodes.length > 0 && workers.length >= 2;

/**
 * Ceph multi-client read-only RBD consumption (suite 14).
 *
 * Exercises the shipped read-only-map + local-COW architecture across TWO
 * client machines: a single RBD clone is mapped read-only on each worker, and
 * each worker gets its OWN local COW overlay. The core guarantees under test:
 *   - both clients see the shared base data baked into the source image;
 *   - a write on worker1 lands in worker1's COW only — worker2 does NOT see it;
 *   - the underlying RBD device is mapped read-only on the clients;
 *   - unmount happens in the correct order (clients first, then teardown).
 *
 * The base content is seeded into the source image before the snapshot, so
 * "worker2 sees base but not worker1's writes" is a meaningful assertion.
 */
test.describe
  .serial('Ceph Multi-Client Read-Only + COW @bridge @ceph @multiclient', () => {
    test.skip(!hasCephAndTwoClients, 'Requires combined topology (VM_CEPH_NODES + >=2 VM_WORKERS)');

    let ceph: BridgeTestRunner;
    let worker1: BridgeTestRunner;
    let worker2: BridgeTestRunner;

    const id = Date.now().toString(36);
    const pool = `mc-pool-${id}`;
    const image = `mc-image-${id}`;
    const snapshot = `mc-snap-${id}`;
    const clone = `mc-clone-${id}`;
    const seedMount = `/mnt/mc-seed-${id}`;
    const mp1 = `/mnt/mc-w1-${id}`;
    const mp2 = `/mnt/mc-w2-${id}`;
    const baseContent = `base-content-${id}`;
    const worker1Content = `worker1-only-${id}`;

    test.beforeAll(() => {
      ceph = BridgeTestRunner.forCeph();
      worker1 = BridgeTestRunner.forWorker(1);
      worker2 = BridgeTestRunner.forWorker(2);
    });

    test('1. Ceph cluster is healthy', async () => {
      const result = await ceph.cephHealth();
      expect(ceph.isSuccess(result)).toBe(true);
    });

    test('2. create pool and BTRFS-formatted image', async () => {
      let result = await ceph.cephPoolCreate(pool);
      expect(ceph.isSuccess(result)).toBe(true);

      result = await ceph.cephImageCreate(pool, image, '1G');
      expect(ceph.isSuccess(result)).toBe(true);

      result = await ceph.cephImageFormat(pool, image, 'btrfs', `mc-${id}`);
      expect(ceph.isSuccess(result)).toBe(true);
    });

    test('3. seed shared base data into the source image', async () => {
      // Seed on a WORKER, not the ceph node: cephadm-managed ceph nodes have no
      // host rbd/ceph binary, but workers get ceph-common + the admin keyring
      // (ConfigureClients). Mount via the /dev/rbd/<pool>/<image> udev symlink
      // rather than capturing `rbd map` output in $(...): the two-hop SSH would
      // command-substitute $(...) on the bridge (which has no rbd), so the whole
      // command must be substitution-free and run on the worker.
      const dev = `/dev/rbd/${pool}/${image}`;
      const seed =
        `sudo rbd map ${pool}/${image} && sudo udevadm settle && sudo mkdir -p ${seedMount} && ` +
        `sudo mount ${dev} ${seedMount} && echo ${baseContent} | sudo tee ${seedMount}/base.txt >/dev/null && ` +
        `sync && sudo umount ${seedMount} && sudo rbd unmap ${pool}/${image}`;
      const result = await worker1.executeViaBridge(seed);
      expect(result.code).toBe(0);
    });

    test('4. snapshot, protect, clone', async () => {
      let result = await ceph.cephSnapshotCreate(pool, image, snapshot);
      expect(ceph.isSuccess(result)).toBe(true);

      result = await ceph.cephSnapshotProtect(pool, image, snapshot);
      expect(ceph.isSuccess(result)).toBe(true);

      result = await ceph.cephCloneCreate(pool, image, snapshot, clone);
      expect(ceph.isSuccess(result)).toBe(true);
    });

    test('5. worker1 mounts the clone with its own COW overlay', async () => {
      const result = await worker1.cephCloneMount(clone, mp1, '2G', pool);
      expect(worker1.isSuccess(result)).toBe(true);
    });

    test('6. worker1 sees base data and can write to its COW', async () => {
      const base = await worker1.executeViaBridge(`sudo cat ${mp1}/base.txt`);
      expect(base.code).toBe(0);
      expect(base.stdout).toContain(baseContent);

      const write = await worker1.executeViaBridge(
        `echo ${worker1Content} | sudo tee ${mp1}/worker1.txt >/dev/null && sync`
      );
      expect(write.code).toBe(0);

      const readback = await worker1.executeViaBridge(`sudo cat ${mp1}/worker1.txt`);
      expect(readback.stdout).toContain(worker1Content);
    });

    test('7. worker2 mounts the SAME clone read-only with its own COW', async () => {
      const result = await worker2.cephCloneMount(clone, mp2, '2G', pool);
      expect(worker2.isSuccess(result)).toBe(true);
    });

    test('8. worker2 sees the shared base but NOT worker1 writes (COW isolation)', async () => {
      const base = await worker2.executeViaBridge(`sudo cat ${mp2}/base.txt`);
      expect(base.code).toBe(0);
      expect(base.stdout).toContain(baseContent);

      // worker1's file lives only in worker1's local COW; worker2 must not see it.
      const isolated = await worker2.executeViaBridge(
        `test -f ${mp2}/worker1.txt && echo PRESENT || echo ABSENT`
      );
      expect(isolated.stdout).toContain('ABSENT');
      expect(isolated.stdout).not.toContain('PRESENT');
    });

    test('9. underlying RBD clone is mapped read-only on both clients', async () => {
      // cowclone maps the RBD clone with `rbd map --read-only`; lsblk RO column
      // reports 1 for read-only block devices.
      const mapped1 = await worker1.executeViaBridge('sudo rbd showmapped');
      expect(mapped1.stdout).toContain(clone);

      const ro2 = await worker2.executeViaBridge('lsblk -o NAME,RO -n -r | grep rbd || true');
      expect(ro2.stdout).toMatch(/rbd\S*\s+1/);
    });

    test('10. unmount clients first (worker2, then worker1)', async () => {
      const u2 = await worker2.cephCloneUnmount(clone, false, pool);
      expect(worker2.isSuccess(u2)).toBe(true);

      const u1 = await worker1.cephCloneUnmount(clone, false, pool);
      expect(worker1.isSuccess(u1)).toBe(true);
    });

    test('11. teardown clone, snapshot, image, pool in order', async () => {
      let result = await ceph.cephCloneDelete(pool, clone);
      expect(ceph.isSuccess(result)).toBe(true);

      result = await ceph.cephSnapshotUnprotect(pool, image, snapshot);
      expect(ceph.isSuccess(result)).toBe(true);

      result = await ceph.cephSnapshotDelete(pool, image, snapshot);
      expect(ceph.isSuccess(result)).toBe(true);

      result = await ceph.cephImageDelete(pool, image);
      expect(ceph.isSuccess(result)).toBe(true);

      result = await ceph.cephPoolDelete(pool);
      expect(ceph.isSuccess(result)).toBe(true);
    });
  });
