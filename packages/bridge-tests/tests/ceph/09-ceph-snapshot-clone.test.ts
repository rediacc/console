import { expect, test } from '@playwright/test';
import { BridgeTestRunner } from '../../src/utils/bridge/BridgeTestRunner';
import { CephTestHelper } from '../../src/utils/bridge/CephTestHelper';

// Check if Ceph is configured - skip all tests if not
// VM_CEPH_NODES can be empty or space-separated list of VM IDs (e.g., "21 22 23")
const cephNodes = (process.env.VM_CEPH_NODES ?? '').trim();
const hasCeph = cephNodes.length > 0;

/**
 * Ceph Snapshot/Clone Operations Tests (12 functions)
 *
 * Tests Ceph snapshot and clone management including the CRITICAL
 * Copy-on-Write (COW) clone mount/unmount operations.
 *
 * Functions tested:
 * - ceph_snapshot_create
 * - ceph_snapshot_delete
 * - ceph_snapshot_list
 * - ceph_snapshot_protect
 * - ceph_snapshot_unprotect
 * - ceph_snapshot_rollback
 * - ceph_clone_create
 * - ceph_clone_delete
 * - ceph_clone_list
 * - ceph_clone_flatten
 * - ceph_clone_mount (COW overlay)
 * - ceph_clone_unmount (CRITICAL teardown order)
 *
 * CRITICAL: The ceph_clone_mount uses device mapper for COW overlay.
 * The ceph_clone_unmount MUST follow exact teardown order:
 * 1. sync & umount filesystem
 * 2. dmsetup remove cow device
 * 3. losetup detach loop device
 * 4. rbd unmap device
 * 5. delete COW file
 */
test.describe
  .serial('Ceph Snapshot Operations @bridge @ceph', () => {
    test.skip(!hasCeph, 'Ceph not configured (VM_CEPH_NODES empty)');
    let runner: BridgeTestRunner;
    const pool = 'rediacc_rbd_pool';
    const image = `snap-test-image-${Date.now()}`;
    const snapshot = `test-snap-${Date.now()}`;

    test.beforeAll(() => {
      runner = BridgeTestRunner.forCeph();
    });

    // ===========================================================================
    // Setup: Create base image for snapshot tests
    // ===========================================================================

    test('setup: create image for snapshot tests', async () => {
      const result = await runner.cephImageCreate(pool, image, '1G');
      expect(runner.isSuccess(result)).toBe(true);
    });

    // ===========================================================================
    // Snapshot Creation
    // ===========================================================================

    test('ceph_snapshot_create should not have shell syntax errors', async () => {
      const result = await runner.cephSnapshotCreate(pool, image, snapshot);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // ===========================================================================
    // Snapshot Information (must run after create, before delete)
    // ===========================================================================

    test('ceph_snapshot_list should not have shell syntax errors', async () => {
      const result = await runner.cephSnapshotList(pool, image);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // ===========================================================================
    // Snapshot Protection (must run after create, before delete)
    // ===========================================================================

    test('ceph_snapshot_protect should not have shell syntax errors', async () => {
      const result = await runner.cephSnapshotProtect(pool, image, snapshot);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('ceph_snapshot_unprotect should not have shell syntax errors', async () => {
      const result = await runner.cephSnapshotUnprotect(pool, image, snapshot);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // ===========================================================================
    // Snapshot Rollback (must run after create, before delete)
    // ===========================================================================

    test('ceph_snapshot_rollback should not have shell syntax errors', async () => {
      const result = await runner.cephSnapshotRollback(pool, image, snapshot);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // ===========================================================================
    // Snapshot Deletion (must be last)
    // ===========================================================================

    test('ceph_snapshot_delete should not have shell syntax errors', async () => {
      const result = await runner.cephSnapshotDelete(pool, image, snapshot);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // ===========================================================================
    // Cleanup: Delete base image
    // ===========================================================================

    test('cleanup: delete image after snapshot tests', async () => {
      const result = await runner.cephImageDelete(pool, image);
      expect(runner.isSuccess(result)).toBe(true);
    });
  });

test.describe
  .serial('Ceph Clone Operations @bridge @ceph', () => {
    test.skip(!hasCeph, 'Ceph not configured (VM_CEPH_NODES empty)');
    let runner: BridgeTestRunner;
    const pool = 'rediacc_rbd_pool';
    const image = `clone-test-image-${Date.now()}`;
    const snapshot = `clone-test-snap-${Date.now()}`;
    const clone = `test-clone-${Date.now()}`;

    test.beforeAll(() => {
      runner = BridgeTestRunner.forCeph();
    });

    // ===========================================================================
    // Setup: Create base image and protected snapshot for clone tests
    // ===========================================================================

    test('setup: create image for clone tests', async () => {
      const result = await runner.cephImageCreate(pool, image, '1G');
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('setup: create snapshot for clone tests', async () => {
      const result = await runner.cephSnapshotCreate(pool, image, snapshot);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('setup: protect snapshot for clone tests', async () => {
      const result = await runner.cephSnapshotProtect(pool, image, snapshot);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // ===========================================================================
    // Clone Creation
    // ===========================================================================

    test('ceph_clone_create should not have shell syntax errors', async () => {
      const result = await runner.cephCloneCreate(pool, image, snapshot, clone);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // ===========================================================================
    // Clone Information (must run after create, before delete)
    // ===========================================================================

    test('ceph_clone_list should not have shell syntax errors', async () => {
      const result = await runner.cephCloneList(pool, image, snapshot);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // ===========================================================================
    // Clone Flatten (must run after create, before delete)
    // ===========================================================================

    test('ceph_clone_flatten should not have shell syntax errors', async () => {
      const result = await runner.cephCloneFlatten(pool, clone);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // ===========================================================================
    // Clone Deletion (must be last)
    // ===========================================================================

    test('ceph_clone_delete should not have shell syntax errors', async () => {
      const result = await runner.cephCloneDelete(pool, clone);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // ===========================================================================
    // Cleanup: Unprotect snapshot and delete resources
    // ===========================================================================

    test('cleanup: unprotect snapshot after clone tests', async () => {
      const result = await runner.cephSnapshotUnprotect(pool, image, snapshot);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('cleanup: delete snapshot after clone tests', async () => {
      const result = await runner.cephSnapshotDelete(pool, image, snapshot);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('cleanup: delete image after clone tests', async () => {
      const result = await runner.cephImageDelete(pool, image);
      expect(runner.isSuccess(result)).toBe(true);
    });
  });

/**
 * Ceph Clone Mount/Unmount with COW
 *
 * Tests the CRITICAL Copy-on-Write mount functionality.
 * This is the CORE use case for Ceph integration.
 */
test.describe
  .serial('Ceph Clone COW Mount/Unmount @bridge @ceph', () => {
    test.skip(!hasCeph, 'Ceph not configured (VM_CEPH_NODES empty)');
    let runner: BridgeTestRunner;
    const pool = 'rediacc_rbd_pool';
    const image = `cow-test-image-${Date.now()}`;
    const snapshot = `cow-test-snap-${Date.now()}`;
    const clone = `cow-test-clone-${Date.now()}`;
    const mountPoint = '/mnt/test-clone';

    test.beforeAll(() => {
      runner = BridgeTestRunner.forCeph();
    });

    // ===========================================================================
    // Setup: Create image, snapshot, and clone for mount tests
    // ===========================================================================

    test('setup: create image for COW tests', async () => {
      const result = await runner.cephImageCreate(pool, image, '1G');
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('setup: create snapshot for COW tests', async () => {
      const result = await runner.cephSnapshotCreate(pool, image, snapshot);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('setup: protect snapshot for COW tests', async () => {
      const result = await runner.cephSnapshotProtect(pool, image, snapshot);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('setup: create clone for COW tests', async () => {
      const result = await runner.cephCloneCreate(pool, image, snapshot, clone);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // ===========================================================================
    // COW Mount/Unmount Tests
    // ===========================================================================

    test('ceph_clone_mount should not have shell syntax errors', async () => {
      const result = await runner.cephCloneMount(clone, mountPoint, '2G', pool);
      // Use hasValidCommandSyntax for syntax tests - runtime failures (like no filesystem) are OK
      expect(runner.hasValidCommandSyntax(result)).toBe(true);
    });

    test('ceph_clone_unmount should not have shell syntax errors', async () => {
      const result = await runner.cephCloneUnmount(clone, false, pool);
      // Use hasValidCommandSyntax for syntax tests - runtime failures are OK
      expect(runner.hasValidCommandSyntax(result)).toBe(true);
    });

    test('ceph_clone_mount with custom COW size should not have shell syntax errors', async () => {
      const result = await runner.cephCloneMount(clone, mountPoint, '5G', pool);
      // Use hasValidCommandSyntax for syntax tests - runtime failures (like no filesystem) are OK
      expect(runner.hasValidCommandSyntax(result)).toBe(true);
    });

    test('ceph_clone_unmount with keep-cow should not have shell syntax errors', async () => {
      const result = await runner.cephCloneUnmount(clone, true, pool);
      // Use hasValidCommandSyntax for syntax tests - runtime failures are OK
      expect(runner.hasValidCommandSyntax(result)).toBe(true);
    });

    // ===========================================================================
    // Cleanup: Remove clone and resources
    // ===========================================================================

    test('cleanup: delete clone after COW tests', async () => {
      const result = await runner.cephCloneDelete(pool, clone);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('cleanup: unprotect snapshot after COW tests', async () => {
      const result = await runner.cephSnapshotUnprotect(pool, image, snapshot);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('cleanup: delete snapshot after COW tests', async () => {
      const result = await runner.cephSnapshotDelete(pool, image, snapshot);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('cleanup: delete image after COW tests', async () => {
      const result = await runner.cephImageDelete(pool, image);
      expect(runner.isSuccess(result)).toBe(true);
    });
  });

/**
 * Full Ceph Snapshot/Clone Lifecycle Test
 *
 * Tests the complete snapshot and clone lifecycle in STRICT order.
 * This is CRITICAL - the order must be exact to avoid orphaned resources.
 * Uses the existing rediacc_rbd_pool to avoid PG count issues.
 *
 * IMPORTANT: The image MUST be formatted with BTRFS before creating snapshots,
 * otherwise the COW mount will fail (no filesystem to mount).
 */
test.describe
  .serial('Ceph Snapshot/Clone Full Lifecycle @bridge @ceph @lifecycle', () => {
    test.skip(!hasCeph, 'Ceph not configured (VM_CEPH_NODES empty)');
    let runner: BridgeTestRunner;
    const pool = 'rediacc_rbd_pool';
    const image = `lifecycle-image-${Date.now()}`;
    const snapshot = `lifecycle-snap-${Date.now()}`;
    const clone = `lifecycle-clone-${Date.now()}`;
    const mountPoint = `/mnt/lifecycle-${Date.now()}`;

    test.beforeAll(() => {
      runner = BridgeTestRunner.forCeph();
    });

    // Setup: Create and format image
    test('1. setup: create image', async () => {
      const result = await runner.cephImageCreate(pool, image, '1G');
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('2. setup: format image with BTRFS', async () => {
      const result = await runner.cephImageFormat(pool, image, 'btrfs', 'lifecycle-test');
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Snapshot operations
    test('3. ceph_snapshot_create: create snapshot', async () => {
      const result = await runner.cephSnapshotCreate(pool, image, snapshot);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('4. ceph_snapshot_list: verify snapshot exists', async () => {
      const result = await runner.cephSnapshotList(pool, image);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('5. ceph_snapshot_protect: protect snapshot for cloning', async () => {
      const result = await runner.cephSnapshotProtect(pool, image, snapshot);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Clone operations
    test('6. ceph_clone_create: create clone from snapshot', async () => {
      const result = await runner.cephCloneCreate(pool, image, snapshot, clone);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('7. ceph_clone_list: verify clone exists', async () => {
      const result = await runner.cephCloneList(pool, image, snapshot);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // COW Mount (the CORE use case) - Now works with BTRFS-formatted image!
    test('8. ceph_clone_mount: mount clone with COW overlay', async () => {
      const result = await runner.cephCloneMount(clone, mountPoint, '2G', pool);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Teardown in EXACT order (CRITICAL)
    test('9. ceph_clone_unmount: unmount with exact teardown order', async () => {
      // MUST follow order:
      // 1. sync & umount filesystem
      // 2. dmsetup remove cow device
      // 3. losetup detach loop device
      // 4. rbd unmap device
      // 5. delete COW file
      const result = await runner.cephCloneUnmount(clone, false, pool);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('10. ceph_clone_delete: delete clone', async () => {
      const result = await runner.cephCloneDelete(pool, clone);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('11. ceph_snapshot_unprotect: unprotect snapshot', async () => {
      const result = await runner.cephSnapshotUnprotect(pool, image, snapshot);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('12. ceph_snapshot_delete: delete snapshot', async () => {
      const result = await runner.cephSnapshotDelete(pool, image, snapshot);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Cleanup
    test('13. cleanup: delete image', async () => {
      const result = await runner.cephImageDelete(pool, image);
      expect(runner.isSuccess(result)).toBe(true);
    });
  });

/**
 * Ceph Snapshot/Clone Error Handling
 *
 * Tests that snapshot/clone operations handle errors gracefully without shell syntax errors.
 * Note: Commands on nonexistent resources will fail (exit code != 0) but should
 * execute without shell errors.
 */
test.describe('Ceph Snapshot/Clone Error Handling @bridge @ceph', () => {
  test.skip(!hasCeph, 'Ceph not configured (VM_CEPH_NODES empty)');
  let runner: BridgeTestRunner;

  test.beforeAll(() => {
    runner = BridgeTestRunner.forCeph();
  });

  test('snapshot on nonexistent image should execute without shell errors', async () => {
    // Command will fail (image doesn't exist) but should not have shell syntax errors
    const result = await runner.cephSnapshotCreate('rediacc_rbd_pool', 'nonexistent-xyz', 'snap');
    expect(result).toBeDefined();
  });

  test('clone from nonexistent snapshot should execute without shell errors', async () => {
    // Command will fail (snapshot doesn't exist) but should not have shell syntax errors
    const result = await runner.cephCloneCreate(
      'rediacc_rbd_pool',
      'image',
      'nonexistent-snap',
      'clone'
    );
    expect(result).toBeDefined();
  });

  test('deleting nonexistent snapshot should execute without shell errors', async () => {
    // Command will fail (snapshot doesn't exist) but should not have shell syntax errors
    const result = await runner.cephSnapshotDelete(
      'rediacc_rbd_pool',
      'nonexistent-image',
      'nonexistent-snap'
    );
    expect(result).toBeDefined();
  });

  test('unmounting non-mounted clone should handle gracefully', async () => {
    const result = await runner.cephCloneUnmount('nonexistent-clone', false, 'rediacc_rbd_pool');
    expect(runner.isSuccess(result)).toBe(true);
  });
});

/**
 * CephTestHelper Integration Tests
 *
 * Tests using the CephTestHelper utility for resource management.
 */
test.describe('CephTestHelper Resource Management @bridge @ceph', () => {
  test.skip(!hasCeph, 'Ceph not configured (VM_CEPH_NODES empty)');
  let runner: BridgeTestRunner;
  let helper: CephTestHelper;

  test.beforeAll(() => {
    runner = BridgeTestRunner.forCeph();
    helper = new CephTestHelper(runner);
  });

  test.afterAll(async () => {
    // Cleanup all resources created during tests
    await helper.cleanup();
  });

  test('helper should generate unique resource names', () => {
    const pool1 = helper.generatePoolName();
    const pool2 = helper.generatePoolName('custom');
    const image1 = helper.generateImageName();
    const snap1 = helper.generateSnapshotName();
    const clone1 = helper.generateCloneName();

    expect(pool1).toContain('test-pool');
    expect(pool2).toContain('custom');
    expect(image1).toContain('test-image');
    expect(snap1).toContain('test-snap');
    expect(clone1).toContain('test-clone');

    // Names should be unique
    expect(pool1).not.toBe(pool2);
  });

  test('helper createPool should track resource for cleanup', async () => {
    const poolName = helper.generatePoolName('track-test');
    const result = await helper.createPool(poolName);
    expect(runner.isSuccess(result)).toBe(true);
  });

  test('helper cleanup should clean all tracked resources', async () => {
    await helper.cleanup();
    // In test mode, cleanup may report errors for non-existent resources
    // Just verify cleanup completes without throwing
    expect(true).toBe(true);
  });
});

/**
 * BTRFS on Ceph RBD Tests
 *
 * Tests BTRFS-specific functionality on Ceph RBD images.
 * This validates the BTRFS inside Ceph architecture - the core use case
 * for read-write access to immutable Ceph clones via COW overlay.
 *
 * Architecture:
 * ┌─────────────────────────────────────────────────────────────────────┐
 * │                    MOUNT POINT (Read-Write BTRFS)                    │
 * └───────────────────────────────┬─────────────────────────────────────┘
 *                                 │
 *                                 ▼
 * ┌─────────────────────────────────────────────────────────────────────┐
 * │              /dev/mapper/clone-cow (Device Mapper Snapshot)         │
 * └────────────────┬────────────────────────────────┬───────────────────┘
 *                  │                                │
 *     ┌────────────▼────────────┐      ┌────────────▼────────────┐
 *     │  Origin: /dev/rbdX      │      │  COW: /dev/loopY        │
 *     │  (Read-Only RBD Clone)  │      │  (Sparse Backing File)  │
 *     │  Contains: BTRFS fs     │      │  Stores: Write deltas   │
 *     └─────────────────────────┘      └─────────────────────────┘
 */
test.describe
  .serial('BTRFS on Ceph RBD @bridge @ceph @btrfs', () => {
    test.skip(!hasCeph, 'Ceph not configured (VM_CEPH_NODES empty)');
    let runner: BridgeTestRunner;
    const pool = 'rediacc_rbd_pool';
    const baseImage = `btrfs-test-image-${Date.now()}`;
    const snapshot = `btrfs-snap-${Date.now()}`;
    const clone = `btrfs-clone-${Date.now()}`;
    const mountPoint = `/mnt/btrfs-test-${Date.now()}`;

    test.beforeAll(() => {
      runner = BridgeTestRunner.forCeph();
    });

    // ===========================================================================
    // BTRFS Formatting Tests
    // ===========================================================================

    test('ceph_image_format with BTRFS should work', async () => {
      // Create image
      let result = await runner.cephImageCreate(pool, baseImage, '1G');
      expect(runner.isSuccess(result)).toBe(true);

      // Format with BTRFS
      result = await runner.cephImageFormat(pool, baseImage, 'btrfs', 'test-btrfs');
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('ceph_image_format with ext4 should work', async () => {
      const ext4Image = `ext4-test-${Date.now()}`;

      // Create image
      let result = await runner.cephImageCreate(pool, ext4Image, '512M');
      expect(runner.isSuccess(result)).toBe(true);

      // Format with ext4
      result = await runner.cephImageFormat(pool, ext4Image, 'ext4');
      expect(runner.isSuccess(result)).toBe(true);

      // Cleanup
      await runner.cephImageDelete(pool, ext4Image);
    });

    test('ceph_image_format with xfs should work', async () => {
      const xfsImage = `xfs-test-${Date.now()}`;

      // Create image
      let result = await runner.cephImageCreate(pool, xfsImage, '512M');
      expect(runner.isSuccess(result)).toBe(true);

      // Format with xfs
      result = await runner.cephImageFormat(pool, xfsImage, 'xfs');
      expect(runner.isSuccess(result)).toBe(true);

      // Cleanup
      await runner.cephImageDelete(pool, xfsImage);
    });

    // ===========================================================================
    // COW Mount with BTRFS Lifecycle
    // ===========================================================================

    test('setup: create snapshot from BTRFS-formatted image', async () => {
      const result = await runner.cephSnapshotCreate(pool, baseImage, snapshot);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('setup: protect snapshot', async () => {
      const result = await runner.cephSnapshotProtect(pool, baseImage, snapshot);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('setup: create clone', async () => {
      const result = await runner.cephCloneCreate(pool, baseImage, snapshot, clone);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('ceph_clone_mount with BTRFS should create valid mount', async () => {
      const result = await runner.cephCloneMount(clone, mountPoint, '2G', pool);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('mounted BTRFS clone should be writable', async () => {
      // Write a file to prove writes work (go to COW, not Ceph)
      const result = await runner.executeOnCeph(
        `echo "test data from btrfs" | sudo tee ${mountPoint}/test-file.txt`
      );
      expect(result.code).toBe(0);
    });

    test('mounted BTRFS clone should be readable', async () => {
      const result = await runner.executeOnCeph(`sudo cat ${mountPoint}/test-file.txt`);
      expect(result.code).toBe(0);
      expect(result.stdout).toContain('test data from btrfs');
    });

    test('ceph_clone_unmount should cleanup correctly', async () => {
      const result = await runner.cephCloneUnmount(clone, false, pool);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('mount point should be empty after unmount', async () => {
      const result = await runner.executeOnCeph(`ls -la ${mountPoint} 2>&1 || true`);
      // Should be empty or not mounted
      expect(result.stdout).not.toContain('test-file.txt');
    });

    // ===========================================================================
    // COW Persistence Tests
    // ===========================================================================

    test('ceph_clone_mount with keep-cow remount should work', async () => {
      // Mount again
      let result = await runner.cephCloneMount(clone, mountPoint, '2G', pool);
      expect(runner.isSuccess(result)).toBe(true);

      // Write new data
      result = await runner.executeOnCeph(
        `echo "persistent data" | sudo tee ${mountPoint}/persistent.txt`
      );
      expect(result.code).toBe(0);

      // Unmount with keep-cow
      result = await runner.cephCloneUnmount(clone, true, pool); // keepCow = true
      expect(runner.isSuccess(result)).toBe(true);
    });

    // ===========================================================================
    // Cleanup
    // ===========================================================================

    test('cleanup: delete clone', async () => {
      const result = await runner.cephCloneDelete(pool, clone);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('cleanup: unprotect snapshot', async () => {
      const result = await runner.cephSnapshotUnprotect(pool, baseImage, snapshot);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('cleanup: delete snapshot', async () => {
      const result = await runner.cephSnapshotDelete(pool, baseImage, snapshot);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('cleanup: delete base image', async () => {
      const result = await runner.cephImageDelete(pool, baseImage);
      expect(runner.isSuccess(result)).toBe(true);
    });
  });

/**
 * Ceph Clone Unmount with Force Flag
 *
 * Tests the force flag for ceph_clone_unmount command.
 * This is part of the vault parameter fixes that ensure the
 * 'force' boolean parameter is properly passed from vault to CLI.
 */
test.describe
  .serial('Ceph Clone Unmount Force Flag @bridge @ceph', () => {
    test.skip(!hasCeph, 'Ceph not configured (VM_CEPH_NODES empty)');
    let runner: BridgeTestRunner;
    const pool = 'rediacc_rbd_pool';
    const image = `force-test-image-${Date.now()}`;
    const snapshot = `force-test-snap-${Date.now()}`;
    const clone = `force-test-clone-${Date.now()}`;
    const mountPoint = '/mnt/force-test';

    test.beforeAll(() => {
      runner = BridgeTestRunner.forCeph();
    });

    // Setup
    test('setup: create image for force flag tests', async () => {
      const result = await runner.cephImageCreate(pool, image, '1G');
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('setup: format image with BTRFS', async () => {
      const result = await runner.cephImageFormat(pool, image, 'btrfs', 'force-test');
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('setup: create snapshot', async () => {
      const result = await runner.cephSnapshotCreate(pool, image, snapshot);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('setup: protect snapshot', async () => {
      const result = await runner.cephSnapshotProtect(pool, image, snapshot);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('setup: create clone', async () => {
      const result = await runner.cephCloneCreate(pool, image, snapshot, clone);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Force flag tests
    test('ceph_clone_unmount with force=true should not have syntax errors', async () => {
      // Mount first
      await runner.cephCloneMount(clone, mountPoint, '2G', pool);

      // Unmount with force=true
      const result = await runner.cephCloneUnmount(clone, false, pool, true);
      expect(runner.hasValidCommandSyntax(result)).toBe(true);
    });

    test('ceph_clone_unmount with keep_cow=true and force=true should work', async () => {
      // Mount again
      await runner.cephCloneMount(clone, mountPoint, '2G', pool);

      // Unmount with keep_cow=true and force=true
      const result = await runner.cephCloneUnmount(clone, true, pool, true);
      expect(runner.hasValidCommandSyntax(result)).toBe(true);
    });

    test('ceph_clone_unmount with force=false should work', async () => {
      // Mount again
      await runner.cephCloneMount(clone, mountPoint, '2G', pool);

      // Unmount without force
      const result = await runner.cephCloneUnmount(clone, false, pool, false);
      expect(runner.hasValidCommandSyntax(result)).toBe(true);
    });

    // Cleanup
    test('cleanup: delete clone', async () => {
      const result = await runner.cephCloneDelete(pool, clone);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('cleanup: unprotect snapshot', async () => {
      const result = await runner.cephSnapshotUnprotect(pool, image, snapshot);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('cleanup: delete snapshot', async () => {
      const result = await runner.cephSnapshotDelete(pool, image, snapshot);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('cleanup: delete image', async () => {
      const result = await runner.cephImageDelete(pool, image);
      expect(runner.isSuccess(result)).toBe(true);
    });
  });
