import { expect, test } from '@playwright/test';
import { BridgeTestRunner } from '../src/utils/bridge/BridgeTestRunner';

// Check if Ceph is configured - skip Ceph tests if not
const cephNodes = (process.env.VM_CEPH_NODES ?? '').trim().toLowerCase();
const hasCeph = cephNodes.length > 0 && cephNodes !== 'none';

/**
 * Ceph Full Stack Workflow
 *
 * Tests the complete Ceph workflow including COW clone mounting.
 */
test.describe
  .serial('Ceph Full Stack Workflow @bridge @ceph @integration', () => {
    test.skip(!hasCeph, 'Ceph not configured (VM_CEPH_NODES empty)');
    let runner: BridgeTestRunner;
    const pool = `integration-pool-${Date.now()}`;
    const image = `integration-image-${Date.now()}`;
    const snapshot = `integration-snap-${Date.now()}`;
    const clone = `integration-clone-${Date.now()}`;
    const mountPoint = `/mnt/integration-${Date.now()}`;

    test.beforeAll(() => {
      runner = BridgeTestRunner.forCeph();
    });

    // Health check
    test('1. check Ceph cluster health', async () => {
      const result = await runner.cephHealth();
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Create stack
    test('2. create pool', async () => {
      const result = await runner.cephPoolCreate(pool);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('3. create image in pool', async () => {
      const result = await runner.cephImageCreate(pool, image, '1G');
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('3a. format image with btrfs', async () => {
      const result = await runner.cephImageFormat(
        pool,
        image,
        'btrfs',
        `integration-${Date.now()}`
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('4. create snapshot of image', async () => {
      const result = await runner.cephSnapshotCreate(pool, image, snapshot);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('5. protect snapshot', async () => {
      const result = await runner.cephSnapshotProtect(pool, image, snapshot);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('6. create clone from snapshot', async () => {
      const result = await runner.cephCloneCreate(pool, image, snapshot, clone);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // COW Mount (the CORE use case)
    test('7. mount clone with COW overlay', async () => {
      const result = await runner.cephCloneMount(clone, mountPoint, '10G', pool);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Teardown in EXACT order
    test('8. unmount clone (exact teardown order)', async () => {
      const result = await runner.cephCloneUnmount(clone, false, pool);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('9. delete clone', async () => {
      const result = await runner.cephCloneDelete(pool, clone);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('10. unprotect snapshot', async () => {
      const result = await runner.cephSnapshotUnprotect(pool, image, snapshot);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('11. delete snapshot', async () => {
      const result = await runner.cephSnapshotDelete(pool, image, snapshot);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('12. delete image', async () => {
      const result = await runner.cephImageDelete(pool, image);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('13. delete pool', async () => {
      const result = await runner.cephPoolDelete(pool);
      expect(runner.isSuccess(result)).toBe(true);
    });
  });
