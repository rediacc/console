import { expect, test } from '@playwright/test';
import { BridgeTestRunner } from '../../src/utils/bridge/BridgeTestRunner';

// Combined topology only: needs a Ceph cluster AND a worker acting as the
// RBD client that hosts the datastore.
const cephNodes = (process.env.VM_CEPH_NODES ?? '').trim();
const workers = (process.env.VM_WORKERS ?? '').trim().split(/\s+/).filter(Boolean);
const hasCephAndClient = cephNodes.length > 0 && workers.length >= 1;

/**
 * Ceph-backed datastore lifecycle (suite 13).
 *
 * Exercises the shipped-but-untested product path: a worker consumes a Ceph RBD
 * image as its datastore (BTRFS on RBD), then instant-forks that datastore via
 * RBD snapshot + clone + local COW overlay.
 *
 * Coverage:
 *   - datastore_ceph_init: create + mount the RBD-backed datastore, backend
 *     detected as "ceph", datastore_expand grows it.
 *   - a repository created on the RBD datastore (repo lifecycle on RBD).
 *   - datastore_ceph_fork: fork carries the source data (divergence baseline),
 *     writes to the fork stay in the fork's COW, writes to the source stay in
 *     the source (source-unchanged guarantee).
 *   - datastore_ceph_unfork: strict teardown order, leaving no orphan RBD
 *     clone image or fork snapshot.
 */
test.describe
  .serial('Ceph RBD Datastore Lifecycle @bridge @ceph @datastore', () => {
    test.skip(!hasCephAndClient, 'Requires combined topology (VM_CEPH_NODES + VM_WORKERS)');

    let worker: BridgeTestRunner;
    let ceph: BridgeTestRunner;

    const id = Date.now().toString(36);
    const pool = `ds-pool-${id}`;
    const image = `ds-img-${id}`;
    const forkImage = `ds-fork-${id}`;
    const dsPath = `/mnt/ceph-ds-${id}`;
    const forkPath = `/mnt/ceph-fork-${id}`;
    const repoName = `ds-repo-${id}`;
    const repoPassword = 'ceph-ds-test-pw';

    // Discovered at fork time (fork-<unix>), needed for unfork + orphan checks.
    let forkSnapshot = '';

    test.beforeAll(() => {
      worker = BridgeTestRunner.forWorker(1);
      ceph = BridgeTestRunner.forCeph();
    });

    test('1. Ceph cluster is healthy', async () => {
      const result = await ceph.cephHealth();
      expect(ceph.isSuccess(result)).toBe(true);
    });

    test('2. create a dedicated RBD pool for the datastore', async () => {
      const result = await ceph.cephPoolCreate(pool);
      expect(ceph.isSuccess(result)).toBe(true);
    });

    test('3. datastore_ceph_init creates and mounts the RBD-backed datastore', async () => {
      const result = await worker.datastoreCephInit({
        size: '2G',
        image,
        datastorePath: dsPath,
        pool,
      });
      expect(worker.isSuccess(result)).toBe(true);

      // The RBD-backed BTRFS filesystem must be mounted at the datastore path.
      const mounted = await worker.executeViaBridge(`mountpoint -q ${dsPath} && echo MOUNTED`);
      expect(mounted.stdout).toContain('MOUNTED');
    });

    test('4. datastore status reports the ceph backend', async () => {
      const status = await worker.executeViaBridge(
        `sudo renet datastore status --path ${dsPath} --json`
      );
      expect(status.code).toBe(0);
      expect(status.stdout.toLowerCase()).toContain('ceph');
    });

    test('5. datastore_expand grows the RBD datastore', async () => {
      const result = await worker.datastoreExpand('3G', dsPath);
      expect(worker.isSuccess(result)).toBe(true);
    });

    test('6. seed known data into the source datastore', async () => {
      const write = await worker.executeViaBridge(
        `echo source-base-${id} | sudo tee ${dsPath}/base.txt >/dev/null && sync`
      );
      expect(write.code).toBe(0);
    });

    test('7. datastore_ceph_fork forks the datastore (carries source data)', async () => {
      const result = await worker.datastoreCephFork({
        source: image,
        dest: forkImage,
        mountPoint: forkPath,
        pool,
        cowSize: '2G',
      });
      expect(worker.isSuccess(result)).toBe(true);

      // Discover the fork snapshot name (fork-<unix>) for later teardown checks.
      // Use grep -oE, not awk '{print $2}': the two-hop SSH shell expands awk's
      // $2 to empty, so awk would print the whole line.
      const snapLs = await worker.executeViaBridge(
        `sudo rbd snap ls ${pool}/${image} 2>/dev/null | grep -oE 'fork-[0-9]+' | head -1`
      );
      forkSnapshot = snapLs.stdout.trim();
      expect(forkSnapshot).toMatch(/^fork-\d+$/);

      // The fork must carry the source data present at fork time.
      const forkBase = await worker.executeViaBridge(`sudo cat ${forkPath}/base.txt`);
      expect(forkBase.stdout).toContain(`source-base-${id}`);
    });

    test('8. fork writes stay in the fork; source stays unchanged', async () => {
      // Write only into the fork (goes to the fork's local COW overlay).
      const forkWrite = await worker.executeViaBridge(
        `echo fork-only-${id} | sudo tee ${forkPath}/fork-only.txt >/dev/null && sync`
      );
      expect(forkWrite.code).toBe(0);

      // Write only into the source (goes to the source RBD image, post-snapshot).
      const srcWrite = await worker.executeViaBridge(
        `echo source-new-${id} | sudo tee ${dsPath}/source-new.txt >/dev/null && sync`
      );
      expect(srcWrite.code).toBe(0);

      // Source must NOT see the fork's write.
      const srcHasFork = await worker.executeViaBridge(
        `test -f ${dsPath}/fork-only.txt && echo PRESENT || echo ABSENT`
      );
      expect(srcHasFork.stdout).toContain('ABSENT');

      // Fork must NOT see the source's post-fork write (clone is snapshot-based).
      const forkHasSrc = await worker.executeViaBridge(
        `test -f ${forkPath}/source-new.txt && echo PRESENT || echo ABSENT`
      );
      expect(forkHasSrc.stdout).toContain('ABSENT');

      // And each still has its own file.
      const forkOwn = await worker.executeViaBridge(`sudo cat ${forkPath}/fork-only.txt`);
      expect(forkOwn.stdout).toContain(`fork-only-${id}`);
      const srcOwn = await worker.executeViaBridge(`sudo cat ${dsPath}/source-new.txt`);
      expect(srcOwn.stdout).toContain(`source-new-${id}`);
    });

    test('9. datastore_ceph_unfork tears the fork down in order', async () => {
      const result = await worker.datastoreCephUnfork({
        source: image,
        dest: forkImage,
        snapshot: forkSnapshot,
        mountPoint: forkPath,
        pool,
      });
      expect(worker.isSuccess(result)).toBe(true);

      // Fork mount is gone.
      const stillMounted = await worker.executeViaBridge(
        `mountpoint -q ${forkPath} && echo MOUNTED || echo UNMOUNTED`
      );
      expect(stillMounted.stdout).toContain('UNMOUNTED');
    });

    test('10. no orphan RBD clone image or fork snapshot remain', async () => {
      // rbd ls / snap ls run on a worker (ceph nodes are cephadm-only, no host rbd).
      const images = await worker.executeViaBridge(`sudo rbd ls ${pool}`);
      expect(images.stdout).not.toContain(forkImage);

      const snaps = await worker.executeViaBridge(
        `sudo rbd snap ls ${pool}/${image} 2>/dev/null || true`
      );
      expect(snaps.stdout).not.toContain(forkSnapshot);
    });

    // Repo-on-RBD lifecycle runs last so the fork/unfork tests above operate on
    // a clean datastore. It is self-contained: create + verify on-disk + remove.
    test('11. repository lifecycle on the RBD datastore', async () => {
      const created = await worker.repositoryNew(repoName, '512M', repoPassword, dsPath);
      expect(worker.isSuccess(created)).toBe(true);

      // `renet list repositories` does not surface repos on this non-default
      // datastore, so verify the repo's LUKS image landed on the RBD-backed
      // datastore directly — that is the "repo on RBD" guarantee.
      const onDisk = await worker.executeViaBridge(
        `sudo test -f ${dsPath}/repositories/${repoName} && echo EXISTS || echo MISSING`
      );
      expect(onDisk.stdout).toContain('EXISTS');

      const removed = await worker.repositoryRm(repoName, dsPath);
      expect(worker.isSuccess(removed)).toBe(true);
    });

    test('12. cleanup: unmount + remove the source datastore and pool', async () => {
      // Tear down any residual per-repo docker/mounts, then unmount the datastore
      // and unmap its RBD device before removing the image + pool.
      await worker.executeViaBridge(
        `sudo renet daemon teardown --network-id 9152 --force 2>/dev/null || true`
      );
      await worker.executeViaBridge(
        `sudo umount ${dsPath} 2>/dev/null || sudo umount -l ${dsPath} 2>/dev/null || true`
      );
      // Unmap by image spec (rbd resolves the device); avoids awk $NF, which the
      // two-hop SSH shell would clobber.
      await worker.executeViaBridge(`sudo rbd unmap ${pool}/${image} 2>/dev/null || true`);
      await worker.executeViaBridge(`sudo rbd rm ${pool}/${image} 2>/dev/null || true`);
      const poolDel = await ceph.cephPoolDelete(pool);
      // Pool deletion is best-effort cleanup; do not fail the suite on it.
      expect([0, 1]).toContain(poolDel.code);
    });
  });
