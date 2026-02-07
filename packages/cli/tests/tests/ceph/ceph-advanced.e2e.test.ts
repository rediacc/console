import { expect, test } from '@playwright/test';
import { CliTestRunner } from '../../src/utils/CliTestRunner';
import { E2E } from '../../src/utils/e2e-constants';
import { getE2EConfig, setupE2EEnvironment } from '../../src/utils/local';
import { SSHValidator } from '../../src/utils/SSHValidator';

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
    let runner: CliTestRunner;
    const ctxName = `e2e-phase8-${Date.now()}`;

    const IMAGE_NAME = 'e2e-test-image';
    const SNAPSHOT_NAME = 'e2e-test-snap';
    const CLONE_NAME = 'e2e-test-clone';
    const MOUNT_POINT = '/mnt/e2e-ceph-test';
    const CLONE_MOUNT_POINT = '/mnt/e2e-ceph-clone';
    const POOL = 'rbd';
    const IMAGE_SIZE = '1G';
    const RESIZED_SIZE = '2G';

    /** Build ceph command args with common flags */
    const cephCmd = (group: string, cmd: string, flags: Record<string, string> = {}) => {
      const args = ['ceph', group, cmd, '--machine', E2E.MACHINE_VM1];
      for (const [key, value] of Object.entries(flags)) {
        args.push(`--${key}`, value);
      }
      return args;
    };

    test.beforeAll(async () => {
      test.skip(!config.enabled || !cephConfigured, 'E2E VMs or Ceph not configured');
      ssh1 = new SSHValidator(config.vm1Ip, config.sshUser, config.sshKeyPath);
      cleanup = await setupE2EEnvironment(ctxName);
      runner = CliTestRunner.withContext(ctxName);
    });

    test.afterAll(async () => {
      // Best-effort cleanup in reverse dependency order
      if (config.enabled && cephConfigured && runner) {
        const cleanupOps = [
          cephCmd('client', 'unmount', { image: IMAGE_NAME, pool: POOL }),
          cephCmd('clone', 'unmount', { clone: CLONE_NAME, 'mount-point': CLONE_MOUNT_POINT, pool: POOL }),
          cephCmd('clone', 'delete', { clone: CLONE_NAME, pool: POOL }),
          cephCmd('snapshot', 'unprotect', { image: IMAGE_NAME, snapshot: SNAPSHOT_NAME, pool: POOL }),
          cephCmd('snapshot', 'delete', { image: IMAGE_NAME, snapshot: SNAPSHOT_NAME, pool: POOL }),
          cephCmd('image', 'unmap', { image: IMAGE_NAME, pool: POOL }),
          cephCmd('image', 'delete', { image: IMAGE_NAME, pool: POOL }),
        ];
        for (const args of cleanupOps) {
          try {
            await runner.run(args, { timeout: 120_000 });
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

      const result = await runner.run(
        cephCmd('image', 'create', { image: IMAGE_NAME, size: IMAGE_SIZE, pool: POOL }),
        { timeout: E2E.TEST_TIMEOUT }
      );
      runner.expectSuccess(result);

      // SSH validation: image should appear in rbd ls
      const images = await ssh1.rbdList(POOL);
      expect(images).toContain(IMAGE_NAME);
    });

    test('ceph_image_list - should list RBD images', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runner.run(
        cephCmd('image', 'list', { pool: POOL }),
        { timeout: E2E.TEST_TIMEOUT }
      );
      runner.expectSuccess(result);

      const output = result.stdout + result.stderr;
      expect(output).toContain(IMAGE_NAME);
    });

    test('ceph_image_info - should show image details', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runner.run(
        cephCmd('image', 'info', { image: IMAGE_NAME, pool: POOL }),
        { timeout: E2E.TEST_TIMEOUT }
      );
      runner.expectSuccess(result);

      const output = result.stdout + result.stderr;
      expect(output.length).toBeGreaterThan(0);
    });

    test('ceph_image_resize - should resize RBD image', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runner.run(
        cephCmd('image', 'resize', { image: IMAGE_NAME, size: RESIZED_SIZE, pool: POOL }),
        { timeout: E2E.TEST_TIMEOUT }
      );
      runner.expectSuccess(result);

      // SSH validation: rbd info should show new size
      const info = await ssh1.rbdInfo(IMAGE_NAME, POOL);
      expect(info).toContain('2');
    });

    test('ceph_image_format - should format RBD image', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runner.run(
        cephCmd('image', 'format', { image: IMAGE_NAME, pool: POOL, filesystem: 'ext4' }),
        { timeout: E2E.TEST_TIMEOUT }
      );
      runner.expectSuccess(result);
    });

    // --- CephFS client operations ---

    test('ceph_client_mount - should mount RBD image via client', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runner.run(
        cephCmd('client', 'mount', { image: IMAGE_NAME, 'mount-point': MOUNT_POINT, pool: POOL }),
        { timeout: E2E.TEST_TIMEOUT }
      );
      runner.expectSuccess(result);

      expect(await ssh1.dirExists(MOUNT_POINT)).toBe(true);
      expect(await ssh1.mountExists(MOUNT_POINT)).toBe(true);
    });

    test('ceph_client_unmount - should unmount RBD image via client', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runner.run(
        cephCmd('client', 'unmount', { image: IMAGE_NAME, pool: POOL }),
        { timeout: E2E.TEST_TIMEOUT }
      );
      runner.expectSuccess(result);

      expect(await ssh1.mountExists(MOUNT_POINT)).toBe(false);
    });

    test('ceph_image_map - should map RBD image to block device', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runner.run(
        cephCmd('image', 'map', { image: IMAGE_NAME, pool: POOL }),
        { timeout: E2E.TEST_TIMEOUT }
      );
      runner.expectSuccess(result);

      const mapped = await ssh1.rbdShowMapped();
      expect(mapped).toContain(IMAGE_NAME);
    });

    // --- Snapshot operations ---

    test('ceph_snapshot_create - should create snapshot', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runner.run(
        cephCmd('snapshot', 'create', { image: IMAGE_NAME, snapshot: SNAPSHOT_NAME, pool: POOL }),
        { timeout: E2E.TEST_TIMEOUT }
      );
      runner.expectSuccess(result);

      const snaps = await ssh1.rbdSnapList(IMAGE_NAME, POOL);
      const hasSnapshot = snaps.some((s) => s.includes(SNAPSHOT_NAME));
      expect(hasSnapshot).toBe(true);
    });

    test('ceph_snapshot_list - should list snapshots', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runner.run(
        cephCmd('snapshot', 'list', { image: IMAGE_NAME, pool: POOL }),
        { timeout: E2E.TEST_TIMEOUT }
      );
      runner.expectSuccess(result);

      const output = result.stdout + result.stderr;
      expect(output).toContain(SNAPSHOT_NAME);
    });

    test('ceph_snapshot_protect - should protect snapshot', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runner.run(
        cephCmd('snapshot', 'protect', { image: IMAGE_NAME, snapshot: SNAPSHOT_NAME, pool: POOL }),
        { timeout: E2E.TEST_TIMEOUT }
      );
      runner.expectSuccess(result);

      const snaps = await ssh1.rbdSnapList(IMAGE_NAME, POOL);
      expect(snaps.length).toBeGreaterThan(0);
    });

    // --- Clone operations ---

    test('ceph_clone_image - should clone from snapshot', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runner.run(
        cephCmd('clone', 'image', {
          image: IMAGE_NAME,
          snapshot: SNAPSHOT_NAME,
          clone: CLONE_NAME,
          pool: POOL,
        }),
        { timeout: E2E.TEST_TIMEOUT }
      );
      runner.expectSuccess(result);

      const images = await ssh1.rbdList(POOL);
      expect(images).toContain(CLONE_NAME);
    });

    test('ceph_clone_list - should list clones', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runner.run(
        cephCmd('clone', 'list', { image: IMAGE_NAME, snapshot: SNAPSHOT_NAME, pool: POOL }),
        { timeout: E2E.TEST_TIMEOUT }
      );
      runner.expectSuccess(result);

      const output = result.stdout + result.stderr;
      expect(output).toContain(CLONE_NAME);
    });

    test('ceph_clone_mount - should mount clone', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runner.run(
        cephCmd('clone', 'mount', {
          clone: CLONE_NAME,
          'mount-point': CLONE_MOUNT_POINT,
          pool: POOL,
          filesystem: 'ext4',
        }),
        { timeout: E2E.TEST_TIMEOUT }
      );
      runner.expectSuccess(result);

      expect(await ssh1.dirExists(CLONE_MOUNT_POINT)).toBe(true);
      expect(await ssh1.mountExists(CLONE_MOUNT_POINT)).toBe(true);
    });

    test('ceph_clone_unmount - should unmount clone', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runner.run(
        cephCmd('clone', 'unmount', {
          clone: CLONE_NAME,
          'mount-point': CLONE_MOUNT_POINT,
          pool: POOL,
        }),
        { timeout: E2E.TEST_TIMEOUT }
      );
      runner.expectSuccess(result);

      expect(await ssh1.mountExists(CLONE_MOUNT_POINT)).toBe(false);
    });

    test('ceph_clone_flatten - should flatten clone (make independent)', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runner.run(
        cephCmd('clone', 'flatten', { clone: CLONE_NAME, pool: POOL }),
        { timeout: E2E.TEST_TIMEOUT }
      );
      runner.expectSuccess(result);

      const info = await ssh1.rbdInfo(CLONE_NAME, POOL);
      expect(info).not.toContain('parent');
    });

    test('ceph_clone_delete - should delete clone', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runner.run(
        cephCmd('clone', 'delete', { clone: CLONE_NAME, pool: POOL }),
        { timeout: E2E.TEST_TIMEOUT }
      );
      runner.expectSuccess(result);

      const images = await ssh1.rbdList(POOL);
      expect(images).not.toContain(CLONE_NAME);
    });

    // --- Continue snapshot operations (cleanup order) ---

    test('ceph_snapshot_unprotect - should unprotect snapshot', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runner.run(
        cephCmd('snapshot', 'unprotect', { image: IMAGE_NAME, snapshot: SNAPSHOT_NAME, pool: POOL }),
        { timeout: E2E.TEST_TIMEOUT }
      );
      runner.expectSuccess(result);
    });

    test('ceph_snapshot_rollback - should rollback image to snapshot', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runner.run(
        cephCmd('snapshot', 'rollback', { image: IMAGE_NAME, snapshot: SNAPSHOT_NAME, pool: POOL }),
        { timeout: E2E.TEST_TIMEOUT }
      );
      runner.expectSuccess(result);
    });

    test('ceph_snapshot_delete - should delete snapshot', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runner.run(
        cephCmd('snapshot', 'delete', { image: IMAGE_NAME, snapshot: SNAPSHOT_NAME, pool: POOL }),
        { timeout: E2E.TEST_TIMEOUT }
      );
      runner.expectSuccess(result);

      const snaps = await ssh1.rbdSnapList(IMAGE_NAME, POOL);
      const hasSnapshot = snaps.some((s) => s.includes(SNAPSHOT_NAME));
      expect(hasSnapshot).toBe(false);
    });

    // --- Image cleanup operations ---

    test('ceph_image_unmap - should unmap RBD image', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runner.run(
        cephCmd('image', 'unmap', { image: IMAGE_NAME, pool: POOL }),
        { timeout: E2E.TEST_TIMEOUT }
      );
      runner.expectSuccess(result);

      const mapped = await ssh1.rbdShowMapped();
      expect(mapped).not.toContain(IMAGE_NAME);
    });

    test('ceph_image_delete - should delete RBD image', async () => {
      test.skip(!config.enabled || !cephConfigured, 'Ceph not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runner.run(
        cephCmd('image', 'delete', { image: IMAGE_NAME, pool: POOL }),
        { timeout: E2E.TEST_TIMEOUT }
      );
      runner.expectSuccess(result);

      const images = await ssh1.rbdList(POOL);
      expect(images).not.toContain(IMAGE_NAME);
    });
  });
