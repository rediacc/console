import type { ExecResult, TestFunctionOptions } from '../types';
/**
 * Ceph storage methods for BridgeTestRunner.
 * Includes pool, image, snapshot, and clone operations.
 */
export declare class CephMethods {
    private readonly testFunction;
    constructor(testFunction: (opts: TestFunctionOptions) => Promise<ExecResult>);
    cephHealth(): Promise<ExecResult>;
    cephPoolCreate(pool: string, pgNum?: string): Promise<ExecResult>;
    cephPoolDelete(pool: string): Promise<ExecResult>;
    cephPoolList(): Promise<ExecResult>;
    cephPoolInfo(pool: string): Promise<ExecResult>;
    cephPoolStats(pool: string): Promise<ExecResult>;
    cephImageCreate(pool: string, image: string, size: string): Promise<ExecResult>;
    cephImageDelete(pool: string, image: string): Promise<ExecResult>;
    cephImageList(pool: string): Promise<ExecResult>;
    cephImageInfo(pool: string, image: string): Promise<ExecResult>;
    cephImageResize(pool: string, image: string, newSize: string): Promise<ExecResult>;
    cephImageMap(pool: string, image: string): Promise<ExecResult>;
    cephImageUnmap(pool: string, image: string): Promise<ExecResult>;
    /**
     * Format an RBD image with a filesystem.
     * Maps the image, formats with specified filesystem, and unmaps.
     * Used to prepare images for COW mount by adding a filesystem.
     */
    cephImageFormat(pool: string, image: string, filesystem?: string, label?: string): Promise<ExecResult>;
    cephSnapshotCreate(pool: string, image: string, snapshot: string): Promise<ExecResult>;
    cephSnapshotDelete(pool: string, image: string, snapshot: string): Promise<ExecResult>;
    cephSnapshotList(pool: string, image: string): Promise<ExecResult>;
    cephSnapshotProtect(pool: string, image: string, snapshot: string): Promise<ExecResult>;
    cephSnapshotUnprotect(pool: string, image: string, snapshot: string): Promise<ExecResult>;
    cephSnapshotRollback(pool: string, image: string, snapshot: string): Promise<ExecResult>;
    cephCloneCreate(pool: string, image: string, snapshot: string, clone: string): Promise<ExecResult>;
    cephCloneDelete(pool: string, clone: string): Promise<ExecResult>;
    cephCloneList(pool: string, image: string, snapshot: string): Promise<ExecResult>;
    cephCloneFlatten(pool: string, clone: string): Promise<ExecResult>;
    /**
     * Mount a Ceph clone with Copy-on-Write overlay.
     * This is the CORE Ceph use case for read-write access to immutable clones.
     */
    cephCloneMount(clone: string, mountPoint: string, cowSize?: string, pool?: string): Promise<ExecResult>;
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
    cephCloneUnmount(clone: string, keepCow?: boolean, pool?: string, force?: boolean): Promise<ExecResult>;
}
//# sourceMappingURL=CephMethods.d.ts.map