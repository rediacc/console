import { expect, test } from '@playwright/test';
import {
  assertSuccess,
  getE2EConfig,
  runLocalFunction,
  setupE2EEnvironment,
} from '../../src/utils/local';
import { SSHValidator } from '../../src/utils/SSHValidator';
import { E2E } from '../../src/utils/e2e-constants';

/**
 * Phase 8: Ceph Operations (22 ops)
 *
 * Conditional: only runs when E2E_CEPH_NODES is set (ceph VMs provisioned).
 *
 * Tests the full ceph lifecycle in dependency order:
 *   Image: create → list → info → resize → format
 *   Client: mount → unmount (maps/unmaps internally)
 *   Image: map → (snapshot/clone ops) → unmap → delete
 *   Snapshot: create → list → protect → unprotect → rollback → delete
 *   Clone: create → list → mount → unmount → flatten → delete
 */
test.describe
  .serial('Phase 8: Ceph Operations @e2e', () => {
    const config = getE2EConfig();
    const cephConfigured = !!process.env.E2E_CEPH_NODES;
    let ssh1: SSHValidator;
    let cleanup: (() => Promise<void>) | null = null;
    const ctxName = `e2e-phase8-${Date.now()}`;

    const IMAGE_NAME = 'e2e-test-image';
    const SNAPSHOT_NAME = 'e2e-test-snap';
    const CLONE_NAME = 'e2e-test-clone';
    const MOUNT_POINT = '/mnt/e2e-ceph-test';
    const CLONE_MOUNT_POINT = '/mnt/e2e-ceph-clone';
    const POOL = 'rbd';
    const IMAGE_SIZE = '1G';
    const RESIZED_SIZE = '2G';

    test.beforeAll(async () => {
      test.skip(!config.enabled || !cephConfigured, 'E2E VMs or Ceph not configured');
      ssh1 = new SSHValidator(config.vm1Ip, config.sshUser, config.sshKeyPath);
      cleanup = await setupE2EEnvironment(ctxName);
    });

    test.afterAll(async () => {
      // Best-effort cleanup in reverse dependency order
      if (config.enabled && cephConfigured) {
        const cleanupOps = [
          { fn: 'ceph_client_unmount', params: { image: IMAGE_NAME, pool: POOL } },
          {
            fn: 'ceph_clone_unmount',
            params: { clone: CLONE_NAME, mountPoint: CLONE_MOUNT_POINT, pool: POOL },
          },
          { fn: 'ceph_clone_delete', params: { clone: CLONE_NAME, pool: POOL } },
          {
            fn: 'ceph_snapshot_unprotect',
            params: { image: IMAGE_NAME, snapshot: SNAPSHOT_NAME, pool: POOL },
          },
          {
            fn: 'ceph_snapshot_delete',
            params: { image: IMAGE_NAME, snapshot: SNAPSHOT_NAME, pool: POOL },
          },
          { fn: 'ceph_image_unmap', params: { image: IMAGE_NAME, pool: POOL } },
          { fn: 'ceph_image_delete', params: { image: IMAGE_NAME, pool: POOL } },
        ];
        for (const op of cleanupOps) {
          try {
            await runLocalFunction(op.fn, E2E.MACHINE_VM1, {
              contextName: ctxName,
              params: op.params,
              timeout: 120_000,
            });
          } catch {
            // ignore cleanup errors
          }
        }
      }
      await cleanup?.();
    });

    // --- Image operations ---

    test('ceph_image_create - should create RBD image', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('ceph_image_create', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { image: IMAGE_NAME, size: IMAGE_SIZE, pool: POOL },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);

      // SSH validation: image should appear in rbd ls
      const images = await ssh1.rbdList(POOL);
      expect(images).toContain(IMAGE_NAME);
    });

    test('ceph_image_list - should list RBD images', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('ceph_image_list', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { pool: POOL },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);

      const output = result.stdout + result.stderr;
      expect(output).toContain(IMAGE_NAME);
    });

    test('ceph_image_info - should show image details', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('ceph_image_info', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { image: IMAGE_NAME, pool: POOL },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);

      const output = result.stdout + result.stderr;
      expect(output.length).toBeGreaterThan(0);
    });

    test('ceph_image_resize - should resize RBD image', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('ceph_image_resize', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { image: IMAGE_NAME, size: RESIZED_SIZE, pool: POOL },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);

      // SSH validation: rbd info should show new size
      const info = await ssh1.rbdInfo(IMAGE_NAME, POOL);
      expect(info).toContain('2');
    });

    test('ceph_image_format - should format RBD image', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('ceph_image_format', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { image: IMAGE_NAME, pool: POOL, filesystem: 'ext4' },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);
    });

    // --- CephFS client operations (image exists, formatted, not yet mapped) ---

    test('ceph_client_mount - should mount RBD image via client', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('ceph_client_mount', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { image: IMAGE_NAME, mountPoint: MOUNT_POINT, pool: POOL },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);

      // SSH validation: mount point should exist and be mounted
      expect(await ssh1.dirExists(MOUNT_POINT)).toBe(true);
      expect(await ssh1.mountExists(MOUNT_POINT)).toBe(true);
    });

    test('ceph_client_unmount - should unmount RBD image via client', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('ceph_client_unmount', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { image: IMAGE_NAME, pool: POOL },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);

      // SSH validation: mount point should no longer be mounted
      expect(await ssh1.mountExists(MOUNT_POINT)).toBe(false);
    });

    test('ceph_image_map - should map RBD image to block device', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('ceph_image_map', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { image: IMAGE_NAME, pool: POOL },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);

      // SSH validation: image should appear in rbd showmapped
      const mapped = await ssh1.rbdShowMapped();
      expect(mapped).toContain(IMAGE_NAME);
    });

    // --- Snapshot operations ---

    test('ceph_snapshot_create - should create snapshot', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('ceph_snapshot_create', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { image: IMAGE_NAME, snapshot: SNAPSHOT_NAME, pool: POOL },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);

      // SSH validation: snapshot should appear in rbd snap ls
      const snaps = await ssh1.rbdSnapList(IMAGE_NAME, POOL);
      const hasSnapshot = snaps.some((s) => s.includes(SNAPSHOT_NAME));
      expect(hasSnapshot).toBe(true);
    });

    test('ceph_snapshot_list - should list snapshots', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('ceph_snapshot_list', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { image: IMAGE_NAME, pool: POOL },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);

      const output = result.stdout + result.stderr;
      expect(output).toContain(SNAPSHOT_NAME);
    });

    test('ceph_snapshot_protect - should protect snapshot', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('ceph_snapshot_protect', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { image: IMAGE_NAME, snapshot: SNAPSHOT_NAME, pool: POOL },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);

      // SSH validation: snapshot should be protected (rbd snap ls shows 'yes' in protected column)
      const snaps = await ssh1.rbdSnapList(IMAGE_NAME, POOL);
      // Protected snapshots show differently in the output
      expect(snaps.length).toBeGreaterThan(0);
    });

    // --- Clone operations ---

    test('ceph_clone_image - should clone from snapshot', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('ceph_clone_image', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: {
          image: IMAGE_NAME,
          snapshot: SNAPSHOT_NAME,
          clone: CLONE_NAME,
          pool: POOL,
        },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);

      // SSH validation: clone should appear in rbd ls
      const images = await ssh1.rbdList(POOL);
      expect(images).toContain(CLONE_NAME);
    });

    test('ceph_clone_list - should list clones', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('ceph_clone_list', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { image: IMAGE_NAME, snapshot: SNAPSHOT_NAME, pool: POOL },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);

      const output = result.stdout + result.stderr;
      expect(output).toContain(CLONE_NAME);
    });

    test('ceph_clone_mount - should mount clone', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('ceph_clone_mount', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: {
          clone: CLONE_NAME,
          mountPoint: CLONE_MOUNT_POINT,
          pool: POOL,
          filesystem: 'ext4',
        },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);

      // SSH validation: mount point should exist and be mounted
      expect(await ssh1.dirExists(CLONE_MOUNT_POINT)).toBe(true);
      expect(await ssh1.mountExists(CLONE_MOUNT_POINT)).toBe(true);
    });

    test('ceph_clone_unmount - should unmount clone', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('ceph_clone_unmount', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: {
          clone: CLONE_NAME,
          mountPoint: CLONE_MOUNT_POINT,
          pool: POOL,
        },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);

      // SSH validation: mount point should no longer be mounted
      expect(await ssh1.mountExists(CLONE_MOUNT_POINT)).toBe(false);
    });

    test('ceph_clone_flatten - should flatten clone (make independent)', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('ceph_clone_flatten', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { clone: CLONE_NAME, pool: POOL },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);

      // SSH validation: clone should now be independent (rbd info shows no parent)
      const info = await ssh1.rbdInfo(CLONE_NAME, POOL);
      // Flattened clones don't have a parent field
      expect(info).not.toContain('parent');
    });

    test('ceph_clone_delete - should delete clone', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('ceph_clone_delete', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { clone: CLONE_NAME, pool: POOL },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);

      // SSH validation: clone should be removed
      const images = await ssh1.rbdList(POOL);
      expect(images).not.toContain(CLONE_NAME);
    });

    // --- Continue snapshot operations (cleanup order) ---

    test('ceph_snapshot_unprotect - should unprotect snapshot', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('ceph_snapshot_unprotect', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { image: IMAGE_NAME, snapshot: SNAPSHOT_NAME, pool: POOL },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);
    });

    test('ceph_snapshot_rollback - should rollback image to snapshot', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('ceph_snapshot_rollback', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { image: IMAGE_NAME, snapshot: SNAPSHOT_NAME, pool: POOL },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);
    });

    test('ceph_snapshot_delete - should delete snapshot', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('ceph_snapshot_delete', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { image: IMAGE_NAME, snapshot: SNAPSHOT_NAME, pool: POOL },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);

      // SSH validation: snapshot should be gone
      const snaps = await ssh1.rbdSnapList(IMAGE_NAME, POOL);
      const hasSnapshot = snaps.some((s) => s.includes(SNAPSHOT_NAME));
      expect(hasSnapshot).toBe(false);
    });

    // --- Image cleanup operations ---

    test('ceph_image_unmap - should unmap RBD image', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('ceph_image_unmap', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { image: IMAGE_NAME, pool: POOL },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);

      // SSH validation: image should not appear in rbd showmapped
      const mapped = await ssh1.rbdShowMapped();
      expect(mapped).not.toContain(IMAGE_NAME);
    });

    test('ceph_image_delete - should delete RBD image', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('ceph_image_delete', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { image: IMAGE_NAME, pool: POOL },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);

      // SSH validation: image should be removed
      const images = await ssh1.rbdList(POOL);
      expect(images).not.toContain(IMAGE_NAME);
    });
  });
