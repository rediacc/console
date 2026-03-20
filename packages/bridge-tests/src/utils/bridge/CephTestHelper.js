/**
 * Ceph-specific test utilities for managing pools, images, snapshots, and clones.
 *
 * Provides:
 * - Unique resource naming to avoid conflicts
 * - Full lifecycle helpers for setting up and tearing down Ceph resources
 * - Critical teardown ordering for COW clones
 */
export class CephTestHelper {
    constructor(runner) {
        // Track created resources for cleanup
        this.createdPools = [];
        this.createdImages = new Map(); // pool -> images
        this.createdSnapshots = new Map(); // pool -> [{image, snapshots}]
        this.createdClones = new Map(); // pool -> clones
        this.mountedClones = [];
        this.runner = runner;
        this.testId = Date.now().toString(36);
    }
    // ===========================================================================
    // Resource Name Generation
    // ===========================================================================
    /**
     * Generate unique pool name for testing.
     */
    generatePoolName(suffix) {
        const name = `test-pool-${this.testId}${suffix ? `-${suffix}` : ''}`;
        return name;
    }
    /**
     * Generate unique image name for testing.
     */
    generateImageName(suffix) {
        const name = `test-image-${this.testId}${suffix ? `-${suffix}` : ''}`;
        return name;
    }
    /**
     * Generate unique snapshot name for testing.
     */
    generateSnapshotName(suffix) {
        const name = `test-snap-${this.testId}${suffix ? `-${suffix}` : ''}`;
        return name;
    }
    /**
     * Generate unique clone name for testing.
     */
    generateCloneName(suffix) {
        const name = `test-clone-${this.testId}${suffix ? `-${suffix}` : ''}`;
        return name;
    }
    // ===========================================================================
    // Resource Creation with Tracking
    // ===========================================================================
    /**
     * Create a pool and track it for cleanup.
     */
    async createPool(poolName) {
        const result = await this.runner.cephPoolCreate(poolName);
        if (result.code === 0) {
            this.createdPools.push(poolName);
        }
        return result;
    }
    /**
     * Create an image and track it for cleanup.
     */
    async createImage(pool, image, size) {
        const result = await this.runner.cephImageCreate(pool, image, size);
        if (result.code === 0) {
            if (!this.createdImages.has(pool)) {
                this.createdImages.set(pool, []);
            }
            this.createdImages.get(pool).push(image);
        }
        return result;
    }
    /**
     * Create a snapshot and track it for cleanup.
     */
    async createSnapshot(pool, image, snapshot) {
        const result = await this.runner.cephSnapshotCreate(pool, image, snapshot);
        if (result.code === 0) {
            if (!this.createdSnapshots.has(pool)) {
                this.createdSnapshots.set(pool, []);
            }
            const poolSnapshots = this.createdSnapshots.get(pool);
            const imageEntry = poolSnapshots.find((e) => e.image === image);
            if (imageEntry) {
                imageEntry.snapshots.push(snapshot);
            }
            else {
                poolSnapshots.push({ image, snapshots: [snapshot] });
            }
        }
        return result;
    }
    /**
     * Create a clone and track it for cleanup.
     */
    async createClone(pool, image, snapshot, clone) {
        const result = await this.runner.cephCloneCreate(pool, image, snapshot, clone);
        if (result.code === 0) {
            if (!this.createdClones.has(pool)) {
                this.createdClones.set(pool, []);
            }
            this.createdClones.get(pool).push(clone);
        }
        return result;
    }
    /**
     * Mount a clone with COW and track it for cleanup.
     */
    async mountClone(clone, mountPoint, cowSize) {
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
    async createFullStack(imageSize = '1G') {
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
    async teardownFullStack(pool, image, snapshot, clone) {
        const errors = [];
        // 1. Delete clone first
        const cloneResult = await this.runner.cephCloneDelete(pool, clone);
        if (cloneResult.code !== 0) {
            errors.push(`Clone delete failed: ${cloneResult.stderr}`);
        }
        // 2. Unprotect snapshot (required before deletion)
        const unprotectResult = await this.runner.cephSnapshotUnprotect(pool, image, snapshot);
        if (unprotectResult.code !== 0 && !unprotectResult.stderr.includes('not protected')) {
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
            throw new Error(`Teardown errors:\n${errors.join('\n')}`);
        }
    }
    // ===========================================================================
    // Cleanup All Created Resources
    // ===========================================================================
    /**
     * Clean up all resources created during testing.
     * CRITICAL: Must follow exact teardown order for COW clones.
     */
    async cleanup() {
        const errors = [];
        // 1. Unmount all mounted clones first (CRITICAL ORDER)
        await this.cleanupMountedClones(errors);
        // 2. Delete clones
        await this.cleanupClones(errors);
        // 3. Unprotect and delete snapshots
        await this.cleanupSnapshots(errors);
        // 4. Delete images
        await this.cleanupImages(errors);
        // 5. Delete pools last
        await this.cleanupPools(errors);
        return {
            success: errors.length === 0,
            errors,
        };
    }
    /**
     * Unmount all mounted clones.
     */
    async cleanupMountedClones(errors) {
        for (const clone of this.mountedClones) {
            try {
                const result = await this.runner.cephCloneUnmount(clone);
                if (result.code !== 0) {
                    errors.push(`Failed to unmount clone ${clone}: ${result.stderr}`);
                }
            }
            catch (e) {
                errors.push(`Exception unmounting clone ${clone}: ${e}`);
            }
        }
        this.mountedClones = [];
    }
    /**
     * Delete all created clones.
     */
    async cleanupClones(errors) {
        for (const [pool, clones] of this.createdClones) {
            for (const clone of clones) {
                try {
                    const result = await this.runner.cephCloneDelete(pool, clone);
                    if (result.code !== 0) {
                        errors.push(`Failed to delete clone ${clone}: ${result.stderr}`);
                    }
                }
                catch (e) {
                    errors.push(`Exception deleting clone ${clone}: ${e}`);
                }
            }
        }
        this.createdClones.clear();
    }
    /**
     * Unprotect and delete all created snapshots.
     */
    async cleanupSnapshots(errors) {
        for (const [pool, imageSnapshots] of this.createdSnapshots) {
            await this.cleanupImageSnapshots(pool, imageSnapshots, errors);
        }
        this.createdSnapshots.clear();
    }
    /**
     * Unprotect and delete snapshots for a specific pool and image set.
     */
    async cleanupImageSnapshots(pool, imageSnapshots, errors) {
        for (const { image, snapshots } of imageSnapshots) {
            await this.cleanupSnapshotsForImage(pool, image, snapshots, errors);
        }
    }
    /**
     * Unprotect and delete snapshots for a specific image.
     */
    async cleanupSnapshotsForImage(pool, image, snapshots, errors) {
        for (const snapshot of snapshots) {
            try {
                // Unprotect first
                await this.runner.cephSnapshotUnprotect(pool, image, snapshot);
                // Then delete
                const result = await this.runner.cephSnapshotDelete(pool, image, snapshot);
                if (result.code !== 0) {
                    errors.push(`Failed to delete snapshot ${snapshot}: ${result.stderr}`);
                }
            }
            catch (e) {
                errors.push(`Exception deleting snapshot ${snapshot}: ${e}`);
            }
        }
    }
    /**
     * Delete all created images.
     */
    async cleanupImages(errors) {
        for (const [pool, images] of this.createdImages) {
            for (const image of images) {
                try {
                    const result = await this.runner.cephImageDelete(pool, image);
                    if (result.code !== 0) {
                        errors.push(`Failed to delete image ${image}: ${result.stderr}`);
                    }
                }
                catch (e) {
                    errors.push(`Exception deleting image ${image}: ${e}`);
                }
            }
        }
        this.createdImages.clear();
    }
    /**
     * Delete all created pools.
     */
    async cleanupPools(errors) {
        for (const pool of this.createdPools) {
            try {
                const result = await this.runner.cephPoolDelete(pool);
                if (result.code !== 0) {
                    errors.push(`Failed to delete pool ${pool}: ${result.stderr}`);
                }
            }
            catch (e) {
                errors.push(`Exception deleting pool ${pool}: ${e}`);
            }
        }
        this.createdPools = [];
    }
    // ===========================================================================
    // Verification Helpers
    // ===========================================================================
    /**
     * Check if Ceph cluster is healthy and available.
     */
    async isClusterHealthy() {
        const result = await this.runner.cephHealth();
        return result.code === 0;
    }
    /**
     * Verify pool exists.
     */
    async poolExists(pool) {
        const result = await this.runner.cephPoolList();
        return result.code === 0 && result.stdout.includes(pool);
    }
    /**
     * Verify image exists in pool.
     */
    async imageExists(pool, image) {
        const result = await this.runner.cephImageList(pool);
        return result.code === 0 && result.stdout.includes(image);
    }
    /**
     * Verify snapshot exists.
     */
    async snapshotExists(pool, image, snapshot) {
        const result = await this.runner.cephSnapshotList(pool, image);
        return result.code === 0 && result.stdout.includes(snapshot);
    }
}
//# sourceMappingURL=CephTestHelper.js.map