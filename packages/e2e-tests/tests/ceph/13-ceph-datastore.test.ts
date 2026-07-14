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
 * TRANSLATED to the named-datastore registry. The datastore-centric redesign deleted
 * the image/path-addressed ceph verbs this suite drove; the SUBJECT is unchanged and
 * every assertion below survives — only the addressing does:
 *
 *   datastore_ceph_init   -> datastore_create --backend ceph  (then attach)
 *   datastore_ceph_fork   -> datastore_fork --parent <name> --tag <tag>
 *   datastore_ceph_unfork -> datastore_detach --discard  (fork removal)
 *
 * A named datastore is addressed by NAME, not by image + mount point: the mount path
 * is DERIVED, so the filesystem assertions resolve it with `datastore path` instead of
 * dictating it. That is the redesign's whole point — the caller stopped owning layout.
 *
 * Coverage (unchanged):
 *   - create + attach the RBD-backed datastore, backend reported as "ceph",
 *     datastore_expand grows it.
 *   - a repository created on the RBD datastore (repo lifecycle on RBD).
 *   - fork carries the source data (divergence baseline), writes to the fork stay in
 *     the fork's COW, writes to the source stay in the source.
 *   - fork teardown leaves no orphan RBD clone image or fork snapshot.
 */
test.describe
  .serial('Ceph RBD Datastore Lifecycle @bridge @ceph @datastore', () => {
    test.skip(!hasCephAndClient, 'Requires combined topology (VM_CEPH_NODES + VM_WORKERS)');

    let worker: BridgeTestRunner;
    let ceph: BridgeTestRunner;

    const id = Date.now().toString(36);
    const pool = `ds-pool-${id}`;
    const image = `ds-img-${id}`;
    const dsName = `ceph-ds-${id}`;
    const forkTag = 'fork1';
    const forkRef = `${dsName}:${forkTag}`;
    const repoName = `ds-repo-${id}`;
    const repoPassword = 'ceph-ds-test-pw';

    // Mount points are DERIVED by the datastore layer, not chosen by the caller.
    let dsPath = '';
    let forkPath = '';
    // Discovered at fork time (fork-<unix>), needed for the orphan checks.
    let forkSnapshot = '';

    /**
     * Resolve a datastore's mount path by ASKING THE REGISTRY that owns it.
     *
     * The first cut of this ran `renet datastore path <ref>` and took the last
     * whitespace-token of stdout. There is no such subcommand, so it scraped the last
     * word of the CLI's error text and "resolved" the mount path to the string
     * "command." — a parse that cannot fail loudly is worse than one that cannot parse.
     * `datastore list --json` emits the registry records, each carrying its own
     * mountPath; that is the layer that decides where a named datastore lives.
     */
    const pathOf = async (ref: string): Promise<string> => {
      const out = await worker.executeViaBridge('sudo renet datastore list --json');
      expect(out.code, `datastore list: ${out.stderr}`).toBe(0);
      const start = out.stdout.indexOf('[');
      expect(
        start,
        `datastore list --json emitted no JSON array: ${out.stdout}`
      ).toBeGreaterThanOrEqual(0);
      const records = JSON.parse(out.stdout.slice(start)) as {
        name?: string;
        mountPath?: string;
      }[];
      const hit = records.find((r) => r.name === ref);
      expect(hit, `datastore ${ref} is not in the registry: ${out.stdout}`).toBeTruthy();
      const resolved = hit?.mountPath ?? '';
      expect(resolved, `registry gave no mountPath for ${ref}`).toMatch(/^\//);
      return resolved;
    };

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

    test('3. datastore_create + attach materializes the RBD-backed datastore', async () => {
      const created = await worker.datastoreCreate({
        name: dsName,
        backend: 'ceph',
        size: '2G',
        pool,
        image,
      });
      expect(worker.isSuccess(created)).toBe(true);

      const attached = await worker.datastoreAttach({ name: dsName });
      expect(worker.isSuccess(attached)).toBe(true);

      // The RBD-backed BTRFS filesystem must be mounted at the DERIVED path.
      dsPath = await pathOf(dsName);
      const mounted = await worker.executeViaBridge(`mountpoint -q ${dsPath} && echo MOUNTED`);
      expect(mounted.stdout).toContain('MOUNTED');
    });

    test('4. datastore status reports the ceph backend', async () => {
      const status = await worker.executeViaBridge(`sudo renet datastore status ${dsName} --json`);
      expect(status.code).toBe(0);
      expect(status.stdout.toLowerCase()).toContain('ceph');
    });

    test('5. datastore_expand grows the RBD datastore', async () => {
      // The PATH is the subject: `datastore_expand` with no --datastore-path grows the
      // machine's BASE pool, not this ceph-backed datastore. Dropping it would not fail
      // loudly — it would expand the wrong datastore and assert nothing about RBD.
      const result = await worker.datastoreExpand('3G', dsPath);
      expect(worker.isSuccess(result)).toBe(true);
    });

    test('6. seed known data into the source datastore', async () => {
      const write = await worker.executeViaBridge(
        `echo source-base-${id} | sudo tee ${dsPath}/base.txt >/dev/null && sync`
      );
      expect(write.code).toBe(0);
    });

    test('7. datastore_fork forks the datastore (carries source data)', async () => {
      const result = await worker.datastoreFork({
        parent: dsName,
        tag: forkTag,
        cowSize: '2G',
      });
      expect(worker.isSuccess(result)).toBe(true);

      // A fork is DETACHED at birth: it must choose a write home before it mounts.
      const attached = await worker.datastoreAttach({ name: forkRef, writes: 'local' });
      expect(worker.isSuccess(attached)).toBe(true);
      forkPath = await pathOf(forkRef);

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

    test('9. datastore_detach --discard tears the fork down in order', async () => {
      const result = await worker.datastoreDetach(forkRef, true);
      expect(worker.isSuccess(result)).toBe(true);

      // Fork mount is gone.
      const stillMounted = await worker.executeViaBridge(
        `mountpoint -q ${forkPath} && echo MOUNTED || echo UNMOUNTED`
      );
      expect(stillMounted.stdout).toContain('UNMOUNTED');
    });

    test('10. no orphan RBD clone image or fork snapshot remain', async () => {
      // rbd ls / snap ls run on a worker (ceph nodes are cephadm-only, no host rbd).
      // The clone image name is DERIVED from the fork now, so assert on the tag it
      // must carry rather than on a name this test used to dictate.
      const images = await worker.executeViaBridge(`sudo rbd ls ${pool}`);
      expect(images.stdout).not.toContain(forkTag);

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
