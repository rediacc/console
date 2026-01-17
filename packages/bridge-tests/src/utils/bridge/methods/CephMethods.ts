import type { ExecResult, TestFunctionOptions } from '../types';

const DEFAULT_DATASTORE_SIZE = '10G';
const DEFAULT_CEPH_POOL_PG_NUM = '32';

/**
 * Ceph storage methods for BridgeTestRunner.
 * Includes pool, image, snapshot, and clone operations.
 */
export class CephMethods {
  constructor(private readonly testFunction: (opts: TestFunctionOptions) => Promise<ExecResult>) {}

  // ===========================================================================
  // Ceph Pool Functions
  // ===========================================================================

  async cephHealth(): Promise<ExecResult> {
    return this.testFunction({ function: 'ceph_health' });
  }

  async cephPoolCreate(pool: string, pgNum?: string): Promise<ExecResult> {
    const resolvedPgNum = pgNum ?? process.env.CEPH_POOL_PG_NUM ?? DEFAULT_CEPH_POOL_PG_NUM;
    return this.testFunction({
      function: 'ceph_pool_create',
      pool,
      pgNum: resolvedPgNum,
    });
  }

  async cephPoolDelete(pool: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'ceph_pool_delete',
      pool,
    });
  }

  async cephPoolList(): Promise<ExecResult> {
    return this.testFunction({ function: 'ceph_pool_list' });
  }

  async cephPoolInfo(pool: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'ceph_pool_info',
      pool,
    });
  }

  async cephPoolStats(pool: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'ceph_pool_stats',
      pool,
    });
  }

  // ===========================================================================
  // Ceph Image Functions
  // ===========================================================================

  async cephImageCreate(pool: string, image: string, size: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'ceph_image_create',
      pool,
      image,
      size,
    });
  }

  async cephImageDelete(pool: string, image: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'ceph_image_delete',
      pool,
      image,
    });
  }

  async cephImageList(pool: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'ceph_image_list',
      pool,
    });
  }

  async cephImageInfo(pool: string, image: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'ceph_image_info',
      pool,
      image,
    });
  }

  async cephImageResize(pool: string, image: string, newSize: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'ceph_image_resize',
      pool,
      image,
      newSize,
    });
  }

  async cephImageMap(pool: string, image: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'ceph_image_map',
      pool,
      image,
    });
  }

  async cephImageUnmap(pool: string, image: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'ceph_image_unmap',
      pool,
      image,
    });
  }

  /**
   * Format an RBD image with a filesystem.
   * Maps the image, formats with specified filesystem, and unmaps.
   * Used to prepare images for COW mount by adding a filesystem.
   */
  async cephImageFormat(
    pool: string,
    image: string,
    filesystem = 'btrfs',
    label?: string
  ): Promise<ExecResult> {
    return this.testFunction({
      function: 'ceph_image_format',
      pool,
      image,
      filesystem,
      label,
    });
  }

  // ===========================================================================
  // Ceph Snapshot Functions
  // ===========================================================================

  async cephSnapshotCreate(pool: string, image: string, snapshot: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'ceph_snapshot_create',
      pool,
      image,
      snapshot,
    });
  }

  async cephSnapshotDelete(pool: string, image: string, snapshot: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'ceph_snapshot_delete',
      pool,
      image,
      snapshot,
    });
  }

  async cephSnapshotList(pool: string, image: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'ceph_snapshot_list',
      pool,
      image,
    });
  }

  async cephSnapshotProtect(pool: string, image: string, snapshot: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'ceph_snapshot_protect',
      pool,
      image,
      snapshot,
    });
  }

  async cephSnapshotUnprotect(pool: string, image: string, snapshot: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'ceph_snapshot_unprotect',
      pool,
      image,
      snapshot,
    });
  }

  async cephSnapshotRollback(pool: string, image: string, snapshot: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'ceph_snapshot_rollback',
      pool,
      image,
      snapshot,
    });
  }

  // ===========================================================================
  // Ceph Clone Functions
  // ===========================================================================

  async cephCloneCreate(
    pool: string,
    image: string,
    snapshot: string,
    clone: string
  ): Promise<ExecResult> {
    return this.testFunction({
      function: 'ceph_clone_create',
      pool,
      image,
      snapshot,
      clone,
    });
  }

  async cephCloneDelete(pool: string, clone: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'ceph_clone_delete',
      pool,
      clone,
    });
  }

  async cephCloneList(pool: string, image: string, snapshot: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'ceph_clone_list',
      pool,
      image,
      snapshot,
    });
  }

  async cephCloneFlatten(pool: string, clone: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'ceph_clone_flatten',
      pool,
      clone,
    });
  }

  /**
   * Mount a Ceph clone with Copy-on-Write overlay.
   * This is the CORE Ceph use case for read-write access to immutable clones.
   */
  async cephCloneMount(
    clone: string,
    mountPoint: string,
    cowSize?: string,
    pool?: string
  ): Promise<ExecResult> {
    return this.testFunction({
      function: 'ceph_clone_mount',
      clone,
      mountPoint,
      cowSize: cowSize ?? DEFAULT_DATASTORE_SIZE,
      pool,
    });
  }

  /**
   * Unmount a Ceph clone. CRITICAL: Must follow exact teardown order.
   * 1. sync & umount filesystem
   * 2. dmsetup remove cow device
   * 3. losetup detach loop device
   * 4. rbd unmap device
   * 5. delete COW file (unless keepCow)
   *
   * @param clone - Clone name
   * @param keepCow - Keep COW file after unmount
   * @param pool - Ceph pool name
   * @param force - Force unmount even if busy
   */
  async cephCloneUnmount(
    clone: string,
    keepCow?: boolean,
    pool?: string,
    force?: boolean
  ): Promise<ExecResult> {
    return this.testFunction({
      function: 'ceph_clone_unmount',
      clone,
      keepCow,
      pool,
      force,
    });
  }
}
