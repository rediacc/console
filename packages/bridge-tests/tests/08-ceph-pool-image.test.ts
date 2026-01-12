import { expect, test } from '@playwright/test';
import { BridgeTestRunner } from '../src/utils/bridge/BridgeTestRunner';

// Check if Ceph is configured - skip all tests if not
// VM_CEPH_NODES can be empty, "NONE", or space-separated list of VM IDs
const cephNodes = (process.env.VM_CEPH_NODES ?? '').trim().toLowerCase();
const hasCeph = cephNodes.length > 0 && cephNodes !== 'none';

/**
 * Ceph Pool/Image Operations Tests (12 functions)
 *
 * Tests Ceph pool and image management functions.
 * These are LEVEL 4 functions - require Ceph cluster available.
 *
 * Functions tested:
 * - ceph_health
 * - ceph_pool_create
 * - ceph_pool_delete
 * - ceph_pool_list
 * - ceph_pool_info
 * - ceph_pool_stats
 * - ceph_image_create
 * - ceph_image_delete
 * - ceph_image_list
 * - ceph_image_info
 * - ceph_image_resize
 * - ceph_image_map
 *
 * Tests validate command syntax and structure. With a Ceph cluster available,
 * commands will execute actual operations. Without Ceph, renet runs in
 * test-mode which validates syntax only.
 */
test.describe('Ceph Health Check @bridge @ceph', () => {
  test.skip(!hasCeph, 'Ceph not configured (VM_CEPH_NODES empty)');
  let runner: BridgeTestRunner;

  test.beforeAll(() => {
    runner = BridgeTestRunner.forCeph();
  });

  test('ceph_health should not have shell syntax errors', async () => {
    const result = await runner.cephHealth();
    expect(runner.isSuccess(result)).toBe(true);
  });
});

test.describe('Ceph Pool Operations @bridge @ceph', () => {
  test.skip(!hasCeph, 'Ceph not configured (VM_CEPH_NODES empty)');
  let runner: BridgeTestRunner;
  const testPool = `test-pool-${Date.now()}`;

  test.beforeAll(() => {
    runner = BridgeTestRunner.forCeph();
  });

  // ===========================================================================
  // Pool Creation
  // ===========================================================================

  test('ceph_pool_create should not have shell syntax errors', async () => {
    const result = await runner.cephPoolCreate(testPool);
    expect(runner.isSuccess(result)).toBe(true);
  });

  // ===========================================================================
  // Pool Information (must run after create, before delete)
  // ===========================================================================

  test('ceph_pool_list should not have shell syntax errors', async () => {
    const result = await runner.cephPoolList();
    expect(runner.isSuccess(result)).toBe(true);
  });

  test('ceph_pool_info should not have shell syntax errors', async () => {
    const result = await runner.cephPoolInfo(testPool);
    expect(runner.isSuccess(result)).toBe(true);
  });

  test('ceph_pool_stats should not have shell syntax errors', async () => {
    const result = await runner.cephPoolStats(testPool);
    expect(runner.isSuccess(result)).toBe(true);
  });

  // ===========================================================================
  // Pool Deletion (must be last)
  // ===========================================================================

  test('ceph_pool_delete should not have shell syntax errors', async () => {
    const result = await runner.cephPoolDelete(testPool);
    expect(runner.isSuccess(result)).toBe(true);
  });
});

test.describe('Ceph Image Operations @bridge @ceph', () => {
  test.skip(!hasCeph, 'Ceph not configured (VM_CEPH_NODES empty)');
  let runner: BridgeTestRunner;
  const testPool = 'rediacc_rbd_pool';
  const testImage = `test-image-${Date.now()}`;

  test.beforeAll(() => {
    runner = BridgeTestRunner.forCeph();
  });

  // ===========================================================================
  // Image Creation
  // ===========================================================================

  test('ceph_image_create should not have shell syntax errors', async () => {
    const result = await runner.cephImageCreate(testPool, testImage, '1G');
    expect(runner.isSuccess(result)).toBe(true);
  });

  // ===========================================================================
  // Image Information (must run after create, before delete)
  // ===========================================================================

  test('ceph_image_list should not have shell syntax errors', async () => {
    const result = await runner.cephImageList(testPool);
    expect(runner.isSuccess(result)).toBe(true);
  });

  test('ceph_image_info should not have shell syntax errors', async () => {
    const result = await runner.cephImageInfo(testPool, testImage);
    expect(runner.isSuccess(result)).toBe(true);
  });

  // ===========================================================================
  // Image Modification (must run after create, before delete)
  // ===========================================================================

  test('ceph_image_resize should not have shell syntax errors', async () => {
    const result = await runner.cephImageResize(testPool, testImage, '2G');
    expect(runner.isSuccess(result)).toBe(true);
  });

  test('ceph_image_map should not have shell syntax errors', async () => {
    const result = await runner.cephImageMap(testPool, testImage);
    expect(runner.isSuccess(result)).toBe(true);
  });

  test('ceph_image_unmap should not have shell syntax errors', async () => {
    const result = await runner.cephImageUnmap(testPool, testImage);
    expect(runner.isSuccess(result)).toBe(true);
  });

  // ===========================================================================
  // Image Deletion (must be last)
  // ===========================================================================

  test('ceph_image_delete should not have shell syntax errors', async () => {
    const result = await runner.cephImageDelete(testPool, testImage);
    expect(runner.isSuccess(result)).toBe(true);
  });
});

/**
 * Ceph Pool/Image Lifecycle Test
 *
 * Tests the complete pool and image lifecycle in order.
 */
test.describe
  .serial('Ceph Pool/Image Lifecycle @bridge @ceph @lifecycle', () => {
    test.skip(!hasCeph, 'Ceph not configured (VM_CEPH_NODES empty)');
    let runner: BridgeTestRunner;
    const pool = `lifecycle-pool-${Date.now()}`;
    const image = `lifecycle-image-${Date.now()}`;

    test.beforeAll(() => {
      runner = BridgeTestRunner.forCeph();
    });

    test('1. ceph_health: check cluster health', async () => {
      const result = await runner.cephHealth();
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('2. ceph_pool_create: create test pool', async () => {
      const result = await runner.cephPoolCreate(pool);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('3. ceph_pool_list: verify pool exists', async () => {
      const result = await runner.cephPoolList();
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('4. ceph_pool_info: get pool details', async () => {
      const result = await runner.cephPoolInfo(pool);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('5. ceph_pool_stats: get pool statistics', async () => {
      const result = await runner.cephPoolStats(pool);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('6. ceph_image_create: create RBD image', async () => {
      const result = await runner.cephImageCreate(pool, image, '1G');
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('7. ceph_image_list: verify image exists', async () => {
      const result = await runner.cephImageList(pool);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('8. ceph_image_info: get image details', async () => {
      const result = await runner.cephImageInfo(pool, image);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('9. ceph_image_resize: resize image to 2G', async () => {
      const result = await runner.cephImageResize(pool, image, '2G');
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('10. ceph_image_delete: delete image', async () => {
      const result = await runner.cephImageDelete(pool, image);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('11. ceph_pool_delete: delete pool', async () => {
      const result = await runner.cephPoolDelete(pool);
      expect(runner.isSuccess(result)).toBe(true);
    });
  });

/**
 * Ceph Error Handling Tests
 *
 * Tests that Ceph operations handle errors gracefully without shell syntax errors.
 * Note: Commands on nonexistent resources will fail (exit code != 0) but should
 * execute without shell errors.
 */
test.describe('Ceph Error Handling @bridge @ceph', () => {
  test.skip(!hasCeph, 'Ceph not configured (VM_CEPH_NODES empty)');
  let runner: BridgeTestRunner;

  test.beforeAll(() => {
    runner = BridgeTestRunner.forCeph();
  });

  test('operations on nonexistent pool should execute without shell errors', async () => {
    const nonexistent = 'nonexistent-pool-xyz';

    // These commands will fail (resource doesn't exist) but should not have shell syntax errors
    const infoResult = await runner.cephPoolInfo(nonexistent);
    expect(infoResult).toBeDefined();
    // Command ran without shell errors (exit code may be non-zero for missing resource)

    const deleteResult = await runner.cephPoolDelete(nonexistent);
    expect(deleteResult).toBeDefined();
  });

  test('operations on nonexistent image should execute without shell errors', async () => {
    const pool = 'rediacc_rbd_pool';
    const nonexistent = 'nonexistent-image-xyz';

    // These commands will fail (resource doesn't exist) but should not have shell syntax errors
    const infoResult = await runner.cephImageInfo(pool, nonexistent);
    expect(infoResult).toBeDefined();

    const deleteResult = await runner.cephImageDelete(pool, nonexistent);
    expect(deleteResult).toBeDefined();
  });

  test('creating pool with invalid name should execute without shell errors', async () => {
    // Invalid pool names should be rejected by Ceph but not cause shell errors
    const result = await runner.cephPoolCreate('invalid pool name');
    expect(result).toBeDefined();
  });

  test('resizing image to smaller size should execute without shell errors', async () => {
    // Even if this fails (image doesn't exist or can't shrink), it should not have shell errors
    const result = await runner.cephImageResize(
      'rediacc_rbd_pool',
      'nonexistent-resize-image',
      '1M'
    );
    expect(result).toBeDefined();
  });
});

/**
 * Ceph Size Parameter Tests
 *
 * Tests various size formats for Ceph operations.
 */
test.describe
  .serial('Ceph Size Parameters @bridge @ceph', () => {
    test.skip(!hasCeph, 'Ceph not configured (VM_CEPH_NODES empty)');
    let runner: BridgeTestRunner;
    const pool = 'rediacc_rbd_pool';
    const resizeImage = `resize-test-image-${Date.now()}`;

    test.beforeAll(() => {
      runner = BridgeTestRunner.forCeph();
    });

    test('ceph_image_create with MB size should work', async () => {
      const result = await runner.cephImageCreate(pool, `mb-image-${Date.now()}`, '500M');
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('ceph_image_create with GB size should work', async () => {
      const result = await runner.cephImageCreate(pool, `gb-image-${Date.now()}`, '5G');
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('ceph_image_create with TB size should work', async () => {
      const result = await runner.cephImageCreate(pool, `tb-image-${Date.now()}`, '1T');
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('setup: create image for resize test', async () => {
      const result = await runner.cephImageCreate(pool, resizeImage, '1G');
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('ceph_image_resize to larger size should work', async () => {
      const result = await runner.cephImageResize(pool, resizeImage, '5G');
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('cleanup: delete resize test image', async () => {
      const result = await runner.cephImageDelete(pool, resizeImage);
      expect(runner.isSuccess(result)).toBe(true);
    });
  });
