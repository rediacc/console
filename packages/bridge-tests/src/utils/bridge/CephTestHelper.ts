import { BridgeTestRunner, ExecResult } from "./BridgeTestRunner";

/**
 * Ceph-specific test utilities for managing pools, images, snapshots, and clones.
 *
 * Provides:
 * - Unique resource naming to avoid conflicts
 * - Full lifecycle helpers for setting up and tearing down Ceph resources
 * - Critical teardown ordering for COW clones
 */
export class CephTestHelper {
  private runner: BridgeTestRunner;
  private testId: string;

  // Track created resources for cleanup
  private createdPools: string[] = [];
  private createdImages: Map<string, string[]> = new Map(); // pool -> images
  private createdSnapshots: Map<string, { image: string; snapshots: string[] }[]> = new Map(); // pool -> [{image, snapshots}]
  private createdClones: Map<string, string[]> = new Map(); // pool -> clones
  private mountedClones: string[] = [];

  constructor(runner: BridgeTestRunner) {
    this.runner = runner;
    this.testId = Date.now().toString(36);
  }

  // ===========================================================================
  // Resource Name Generation
  // ===========================================================================

  /**
   * Generate unique pool name for testing.
   */
  generatePoolName(suffix?: string): string {
    const name = `test-pool-${this.testId}${suffix ? `-${suffix}` : ""}`;
    return name;
  }

  /**
   * Generate unique image name for testing.
   */
  generateImageName(suffix?: string): string {
    const name = `test-image-${this.testId}${suffix ? `-${suffix}` : ""}`;
    return name;
  }

  /**
   * Generate unique snapshot name for testing.
   */
  generateSnapshotName(suffix?: string): string {
    const name = `test-snap-${this.testId}${suffix ? `-${suffix}` : ""}`;
    return name;
  }

  /**
   * Generate unique clone name for testing.
   */
  generateCloneName(suffix?: string): string {
    const name = `test-clone-${this.testId}${suffix ? `-${suffix}` : ""}`;
    return name;
  }

  // ===========================================================================
  // Resource Creation with Tracking
  // ===========================================================================

  /**
   * Create a pool and track it for cleanup.
   */
  async createPool(poolName: string): Promise<ExecResult> {
    const result = await this.runner.cephPoolCreate(poolName);
    if (result.code === 0) {
      this.createdPools.push(poolName);
    }
    return result;
  }

  /**
   * Create an image and track it for cleanup.
   */
  async createImage(pool: string, image: string, size: string): Promise<ExecResult> {
    const result = await this.runner.cephImageCreate(pool, image, size);
    if (result.code === 0) {
      if (!this.createdImages.has(pool)) {
        this.createdImages.set(pool, []);
      }
      this.createdImages.get(pool)!.push(image);
    }
    return result;
  }

  /**
   * Create a snapshot and track it for cleanup.
   */
  async createSnapshot(pool: string, image: string, snapshot: string): Promise<ExecResult> {
    const result = await this.runner.cephSnapshotCreate(pool, image, snapshot);
    if (result.code === 0) {
      if (!this.createdSnapshots.has(pool)) {
        this.createdSnapshots.set(pool, []);
      }
      const poolSnapshots = this.createdSnapshots.get(pool)!;
      const imageEntry = poolSnapshots.find((e) => e.image === image);
      if (imageEntry) {
        imageEntry.snapshots.push(snapshot);
      } else {
        poolSnapshots.push({ image, snapshots: [snapshot] });
      }
    }
    return result;
  }

  /**
   * Create a clone and track it for cleanup.
   */
  async createClone(
    pool: string,
    image: string,
    snapshot: string,
    clone: string,
  ): Promise<ExecResult> {
    const result = await this.runner.cephCloneCreate(pool, image, snapshot, clone);
    if (result.code === 0) {
      if (!this.createdClones.has(pool)) {
        this.createdClones.set(pool, []);
      }
      this.createdClones.get(pool)!.push(clone);
    }
    return result;
  }

  /**
   * Mount a clone with COW and track it for cleanup.
   */
  async mountClone(clone: string, mountPoint: string, cowSize?: string): Promise<ExecResult> {
    const result = await this.runner.cephCloneMount(clone, mountPoint, cowSize);
    if (result.code === 0) {
      this.mountedClones.push(clone);
    }
    return result;
  }

  // ===========================================================================
  // Full Stack Lifecycle
  // ===========================================================================

  /**
   * Create a complete Ceph stack: pool -> image -> snapshot -> clone.
   * Returns all created resource names.
   */
  async createFullStack(imageSize = "1G"): Promise<{
    pool: string;
    image: string;
    snapshot: string;
    clone: string;
  }> {
    const pool = this.generatePoolName();
    const image = this.generateImageName();
    const snapshot = this.generateSnapshotName();
    const clone = this.generateCloneName();

    // Create in order
    const poolResult = await this.createPool(pool);
    if (poolResult.code !== 0) {
      throw new Error(`Failed to create pool: ${poolResult.stderr}`);
    }

    const imageResult = await this.createImage(pool, image, imageSize);
    if (imageResult.code !== 0) {
      throw new Error(`Failed to create image: ${imageResult.stderr}`);
    }

    const snapshotResult = await this.createSnapshot(pool, image, snapshot);
    if (snapshotResult.code !== 0) {
      throw new Error(`Failed to create snapshot: ${snapshotResult.stderr}`);
    }

    const cloneResult = await this.createClone(pool, image, snapshot, clone);
    if (cloneResult.code !== 0) {
      throw new Error(`Failed to create clone: ${cloneResult.stderr}`);
    }

    return { pool, image, snapshot, clone };
  }

  /**
   * Teardown a complete Ceph stack in correct order.
   * CRITICAL: Must follow exact order to avoid device busy errors.
   */
  async teardownFullStack(
    pool: string,
    image: string,
    snapshot: string,
    clone: string,
  ): Promise<void> {
    const errors: string[] = [];

    // 1. Delete clone first
    const cloneResult = await this.runner.cephCloneDelete(pool, clone);
    if (cloneResult.code !== 0) {
      errors.push(`Clone delete failed: ${cloneResult.stderr}`);
    }

    // 2. Unprotect snapshot (required before deletion)
    const unprotectResult = await this.runner.cephSnapshotUnprotect(pool, image, snapshot);
    if (unprotectResult.code !== 0 && !unprotectResult.stderr.includes("not protected")) {
      errors.push(`Snapshot unprotect failed: ${unprotectResult.stderr}`);
    }

    // 3. Delete snapshot
    const snapResult = await this.runner.cephSnapshotDelete(pool, image, snapshot);
    if (snapResult.code !== 0) {
      errors.push(`Snapshot delete failed: ${snapResult.stderr}`);
    }

    // 4. Delete image
    const imageResult = await this.runner.cephImageDelete(pool, image);
    if (imageResult.code !== 0) {
      errors.push(`Image delete failed: ${imageResult.stderr}`);
    }

    // 5. Delete pool
    const poolResult = await this.runner.cephPoolDelete(pool);
    if (poolResult.code !== 0) {
      errors.push(`Pool delete failed: ${poolResult.stderr}`);
    }

    if (errors.length > 0) {
      throw new Error(`Teardown errors:\n${errors.join("\n")}`);
    }
  }

  // ===========================================================================
  // Cleanup All Created Resources
  // ===========================================================================

  /**
   * Clean up all resources created during testing.
   * CRITICAL: Must follow exact teardown order for COW clones.
   */
  async cleanup(): Promise<{ success: boolean; errors: string[] }> {
    const errors: string[] = [];

    // 1. Unmount all mounted clones first (CRITICAL ORDER)
    for (const clone of this.mountedClones) {
      try {
        const result = await this.runner.cephCloneUnmount(clone);
        if (result.code !== 0) {
          errors.push(`Failed to unmount clone ${clone}: ${result.stderr}`);
        }
      } catch (e) {
        errors.push(`Exception unmounting clone ${clone}: ${e}`);
      }
    }
    this.mountedClones = [];

    // 2. Delete clones
    for (const [pool, clones] of this.createdClones) {
      for (const clone of clones) {
        try {
          const result = await this.runner.cephCloneDelete(pool, clone);
          if (result.code !== 0) {
            errors.push(`Failed to delete clone ${clone}: ${result.stderr}`);
          }
        } catch (e) {
          errors.push(`Exception deleting clone ${clone}: ${e}`);
        }
      }
    }
    this.createdClones.clear();

    // 3. Unprotect and delete snapshots
    for (const [pool, imageSnapshots] of this.createdSnapshots) {
      for (const { image, snapshots } of imageSnapshots) {
        for (const snapshot of snapshots) {
          try {
            // Unprotect first
            await this.runner.cephSnapshotUnprotect(pool, image, snapshot);
            // Then delete
            const result = await this.runner.cephSnapshotDelete(pool, image, snapshot);
            if (result.code !== 0) {
              errors.push(`Failed to delete snapshot ${snapshot}: ${result.stderr}`);
            }
          } catch (e) {
            errors.push(`Exception deleting snapshot ${snapshot}: ${e}`);
          }
        }
      }
    }
    this.createdSnapshots.clear();

    // 4. Delete images
    for (const [pool, images] of this.createdImages) {
      for (const image of images) {
        try {
          const result = await this.runner.cephImageDelete(pool, image);
          if (result.code !== 0) {
            errors.push(`Failed to delete image ${image}: ${result.stderr}`);
          }
        } catch (e) {
          errors.push(`Exception deleting image ${image}: ${e}`);
        }
      }
    }
    this.createdImages.clear();

    // 5. Delete pools last
    for (const pool of this.createdPools) {
      try {
        const result = await this.runner.cephPoolDelete(pool);
        if (result.code !== 0) {
          errors.push(`Failed to delete pool ${pool}: ${result.stderr}`);
        }
      } catch (e) {
        errors.push(`Exception deleting pool ${pool}: ${e}`);
      }
    }
    this.createdPools = [];

    return {
      success: errors.length === 0,
      errors,
    };
  }

  // ===========================================================================
  // Verification Helpers
  // ===========================================================================

  /**
   * Check if Ceph cluster is healthy and available.
   */
  async isClusterHealthy(): Promise<boolean> {
    const result = await this.runner.cephHealth();
    return result.code === 0;
  }

  /**
   * Verify pool exists.
   */
  async poolExists(pool: string): Promise<boolean> {
    const result = await this.runner.cephPoolList();
    return result.code === 0 && result.stdout.includes(pool);
  }

  /**
   * Verify image exists in pool.
   */
  async imageExists(pool: string, image: string): Promise<boolean> {
    const result = await this.runner.cephImageList(pool);
    return result.code === 0 && result.stdout.includes(image);
  }

  /**
   * Verify snapshot exists.
   */
  async snapshotExists(pool: string, image: string, snapshot: string): Promise<boolean> {
    const result = await this.runner.cephSnapshotList(pool, image);
    return result.code === 0 && result.stdout.includes(snapshot);
  }
}
