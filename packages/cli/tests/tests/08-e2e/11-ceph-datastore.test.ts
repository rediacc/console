import { expect, test } from '@playwright/test';
import { E2E } from '../../src/utils/e2e-constants';
import {
  assertSuccess,
  getE2EConfig,
  runLocalFunction,
  setupE2EEnvironment,
} from '../../src/utils/local';
import { SSHValidator } from '../../src/utils/SSHValidator';

/**
 * Phase 10: Ceph Datastore Fork/Unfork (7 ops)
 *
 * Conditional: only runs when E2E_CEPH_NODES is set (ceph VMs provisioned).
 *
 * Tests the full ceph datastore lifecycle including fork operations:
 *   1. Init ceph-backed datastore (rbd create + mkfs.btrfs + mount)
 *   2. Verify directory structure and mount
 *   3. Write test data to datastore
 *   4. Fork datastore (snapshot + clone + COW mount on target)
 *   5. Verify fork data readable on target, writes go to COW
 *   6. Unfork (cleanup clone, snapshot, COW)
 *   7. Cleanup datastore
 *
 * Requires two worker VMs (vm1 = source, vm2 = fork target).
 */
test.describe
  .serial('Phase 10: Ceph Datastore Fork/Unfork @e2e', () => {
    const config = getE2EConfig();
    const cephConfigured = !!process.env.E2E_CEPH_NODES;
    let ssh1: SSHValidator;
    let ssh2: SSHValidator;
    let cleanup: (() => Promise<void>) | null = null;
    const ctxName = `e2e-phase10-${Date.now()}`;

    const DS_IMAGE = 'e2e-ds-test';
    const DS_FORK = 'e2e-ds-fork';
    const DS_SIZE = '10G';
    const POOL = 'rbd';
    const MOUNT_POINT = '/mnt/rediacc';
    const FORK_MOUNT_POINT = '/mnt/rediacc';

    // Will be set after fork
    let snapshotName = '';

    test.beforeAll(async () => {
      test.skip(!config.enabled || !cephConfigured, 'E2E VMs or Ceph not configured');
      ssh1 = new SSHValidator(config.vm1Ip, config.sshUser, config.sshKeyPath);
      ssh2 = new SSHValidator(config.vm2Ip, config.sshUser, config.sshKeyPath);
      cleanup = await setupE2EEnvironment(ctxName);
    });

    /** Run cleanup operations via renet functions (best-effort). */
    async function cleanupViaRenet(): Promise<void> {
      const ops = [
        ...(snapshotName
          ? [
              {
                fn: 'datastore_ceph_unfork',
                machine: E2E.MACHINE_VM2,
                params: {
                  source: DS_IMAGE,
                  dest: DS_FORK,
                  snapshot: snapshotName,
                  pool: POOL,
                  mount_point: FORK_MOUNT_POINT,
                  force: 'true',
                },
              },
            ]
          : []),
        {
          fn: 'datastore_ceph_init',
          machine: E2E.MACHINE_VM1,
          params: { image: DS_IMAGE, pool: POOL },
        },
      ];

      for (const op of ops) {
        try {
          await runLocalFunction(op.fn, op.machine, {
            contextName: ctxName,
            params: op.params,
            timeout: 120_000,
          });
        } catch {
          // ignore cleanup errors
        }
      }
    }

    /** Direct SSH cleanup as fallback. */
    async function cleanupViaSsh(): Promise<void> {
      await ssh1.run(`sudo umount ${MOUNT_POINT} 2>/dev/null || true`);
      await ssh1.run(`sudo rbd unmap /dev/rbd0 2>/dev/null || true`);
      await ssh1.run(`sudo rbd rm ${POOL}/${DS_IMAGE} 2>/dev/null || true`);
      await ssh2.run(`sudo umount ${FORK_MOUNT_POINT} 2>/dev/null || true`);
      await ssh2.run(`sudo rbd rm ${POOL}/${DS_FORK} 2>/dev/null || true`);
    }

    test.afterAll(async () => {
      if (config.enabled && cephConfigured) {
        await cleanupViaRenet();
        try {
          await cleanupViaSsh();
        } catch {
          // ignore
        }
      }

      await cleanup?.();
    });

    // --- Datastore Init ---

    test('datastore_ceph_init - should initialize ceph-backed datastore', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.SETUP_TIMEOUT);

      const result = await runLocalFunction('datastore_ceph_init', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: {
          size: DS_SIZE,
          image: DS_IMAGE,
          pool: POOL,
        },
        timeout: E2E.SETUP_TIMEOUT,
      });
      assertSuccess(result);

      // SSH validation: RBD image should exist
      const images = await ssh1.rbdList(POOL);
      expect(images).toContain(DS_IMAGE);

      // SSH validation: BTRFS should be mounted
      expect(await ssh1.mountExists(MOUNT_POINT)).toBe(true);

      // SSH validation: Directory structure should exist
      expect(await ssh1.dirExists(`${MOUNT_POINT}/repositories`)).toBe(true);
    });

    test('datastore_status - should show ceph backend info', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('datastore_status', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: {},
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);

      const output = result.stdout + result.stderr;
      expect(output).toContain('ceph');
    });

    test('write test data to datastore', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      // Write a marker file to verify fork can read it
      await ssh1.run(
        `echo "fork-test-data-${Date.now()}" | sudo tee ${MOUNT_POINT}/repositories/fork-marker.txt`
      );

      // Verify it exists
      const content = await ssh1.run(`cat ${MOUNT_POINT}/repositories/fork-marker.txt`);
      expect(content).toContain('fork-test-data');
    });

    // --- Fork ---

    test('datastore_ceph_fork - should create instant fork', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.SETUP_TIMEOUT);

      const result = await runLocalFunction('datastore_ceph_fork', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: {
          source: DS_IMAGE,
          dest: DS_FORK,
          pool: POOL,
          mount_point: FORK_MOUNT_POINT,
        },
        timeout: E2E.SETUP_TIMEOUT,
      });
      assertSuccess(result);

      // Extract snapshot name from output
      const output = result.stdout + result.stderr;
      const snapMatch = output.match(/fork-\d+/);
      if (snapMatch) {
        snapshotName = snapMatch[0];
      }

      // SSH validation on target (vm2): fork should be mounted
      expect(await ssh2.mountExists(FORK_MOUNT_POINT)).toBe(true);

      // SSH validation: test data should be readable on fork
      const content = await ssh2.run(`cat ${FORK_MOUNT_POINT}/repositories/fork-marker.txt`);
      expect(content).toContain('fork-test-data');
    });

    test('fork isolation - writes on fork should not affect source', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      // Write to fork
      await ssh2.run(
        `echo "fork-only-data" | sudo tee ${FORK_MOUNT_POINT}/repositories/fork-write.txt`
      );

      // Verify write exists on fork
      const forkContent = await ssh2.run(`cat ${FORK_MOUNT_POINT}/repositories/fork-write.txt`);
      expect(forkContent).toContain('fork-only-data');

      // Verify write does NOT exist on source
      const sourceResult = await ssh1.run(
        `test -f ${MOUNT_POINT}/repositories/fork-write.txt && echo "exists" || echo "not-found"`
      );
      expect(sourceResult).toContain('not-found');
    });

    // --- Unfork ---

    test('datastore_ceph_unfork - should clean up fork', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.skip(!snapshotName, 'Fork did not produce a snapshot name');
      test.setTimeout(E2E.SETUP_TIMEOUT);

      const result = await runLocalFunction('datastore_ceph_unfork', E2E.MACHINE_VM2, {
        contextName: ctxName,
        params: {
          source: DS_IMAGE,
          dest: DS_FORK,
          snapshot: snapshotName,
          pool: POOL,
          mount_point: FORK_MOUNT_POINT,
          force: 'true',
        },
        timeout: E2E.SETUP_TIMEOUT,
      });
      assertSuccess(result);

      // SSH validation: fork mount should be gone
      expect(await ssh2.mountExists(FORK_MOUNT_POINT)).toBe(false);

      // SSH validation: clone image should be removed
      const images = await ssh2.rbdList(POOL);
      expect(images).not.toContain(DS_FORK);

      // SSH validation: snapshot should be removed
      const snaps = await ssh1.rbdSnapList(DS_IMAGE, POOL);
      const hasSnapshot = snaps.some((s) => s.includes(snapshotName));
      expect(hasSnapshot).toBe(false);
    });

    // --- Cleanup ---

    test('cleanup - should remove ceph datastore', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.SETUP_TIMEOUT);

      // Unmount and clean up via SSH (no dedicated cleanup bridge function yet)
      await ssh1.run(`sudo umount ${MOUNT_POINT} || true`);

      // Find and unmap RBD device
      await ssh1.run(`
        DEV=$(rbd showmapped | grep ${DS_IMAGE} | awk '{print $5}')
        if [ -n "$DEV" ]; then
          sudo rbd unmap "$DEV"
        fi
      `);

      // Remove RBD image
      await ssh1.run(`sudo rbd rm ${POOL}/${DS_IMAGE}`);

      // SSH validation: image should be gone
      const images = await ssh1.rbdList(POOL);
      expect(images).not.toContain(DS_IMAGE);
    });
  });
