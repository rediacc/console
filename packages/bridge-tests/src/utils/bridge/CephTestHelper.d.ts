import { BridgeTestRunner, ExecResult } from './BridgeTestRunner';
/**
 * Ceph-specific test utilities for managing pools, images, snapshots, and clones.
 *
 * Provides:
 * - Unique resource naming to avoid conflicts
 * - Full lifecycle helpers for setting up and tearing down Ceph resources
 * - Critical teardown ordering for COW clones
 */
export declare class CephTestHelper {
    private readonly runner;
    private readonly testId;
    private createdPools;
    private readonly createdImages;
    private readonly createdSnapshots;
    private readonly createdClones;
    private mountedClones;
    constructor(runner: BridgeTestRunner);
    /**
     * Generate unique pool name for testing.
     */
    generatePoolName(suffix?: string): string;
    /**
     * Generate unique image name for testing.
     */
    generateImageName(suffix?: string): string;
    /**
     * Generate unique snapshot name for testing.
     */
    generateSnapshotName(suffix?: string): string;
    /**
     * Generate unique clone name for testing.
     */
    generateCloneName(suffix?: string): string;
    /**
     * Create a pool and track it for cleanup.
     */
    createPool(poolName: string): Promise<ExecResult>;
    /**
     * Create an image and track it for cleanup.
     */
    createImage(pool: string, image: string, size: string): Promise<ExecResult>;
    /**
     * Create a snapshot and track it for cleanup.
     */
    createSnapshot(pool: string, image: string, snapshot: string): Promise<ExecResult>;
    /**
     * Create a clone and track it for cleanup.
     */
    createClone(pool: string, image: string, snapshot: string, clone: string): Promise<ExecResult>;
    /**
     * Mount a clone with COW and track it for cleanup.
     */
    mountClone(clone: string, mountPoint: string, cowSize?: string): Promise<ExecResult>;
    /**
     * Create a complete Ceph stack: pool -> image -> snapshot -> clone.
     * Returns all created resource names.
     */
    createFullStack(imageSize?: string): Promise<{
        pool: string;
        image: string;
        snapshot: string;
        clone: string;
    }>;
    /**
     * Teardown a complete Ceph stack in correct order.
     * CRITICAL: Must follow exact order to avoid device busy errors.
     */
    teardownFullStack(pool: string, image: string, snapshot: string, clone: string): Promise<void>;
    /**
     * Clean up all resources created during testing.
     * CRITICAL: Must follow exact teardown order for COW clones.
     */
    cleanup(): Promise<{
        success: boolean;
        errors: string[];
    }>;
    /**
     * Unmount all mounted clones.
     */
    private cleanupMountedClones;
    /**
     * Delete all created clones.
     */
    private cleanupClones;
    /**
     * Unprotect and delete all created snapshots.
     */
    private cleanupSnapshots;
    /**
     * Unprotect and delete snapshots for a specific pool and image set.
     */
    private cleanupImageSnapshots;
    /**
     * Unprotect and delete snapshots for a specific image.
     */
    private cleanupSnapshotsForImage;
    /**
     * Delete all created images.
     */
    private cleanupImages;
    /**
     * Delete all created pools.
     */
    private cleanupPools;
    /**
     * Check if Ceph cluster is healthy and available.
     */
    isClusterHealthy(): Promise<boolean>;
    /**
     * Verify pool exists.
     */
    poolExists(pool: string): Promise<boolean>;
    /**
     * Verify image exists in pool.
     */
    imageExists(pool: string, image: string): Promise<boolean>;
    /**
     * Verify snapshot exists.
     */
    snapshotExists(pool: string, image: string, snapshot: string): Promise<boolean>;
}
//# sourceMappingURL=CephTestHelper.d.ts.map
