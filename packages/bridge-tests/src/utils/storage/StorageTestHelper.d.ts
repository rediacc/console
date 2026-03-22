/**
 * S3-compatible storage configuration.
 */
export interface S3Config {
    endpoint: string;
    accessKey: string;
    secretKey: string;
    bucket: string;
    region?: string;
}
/**
 * Default RustFS configuration for E2E testing.
 * Matches ops/scripts/init.sh constants.
 */
export declare const DEFAULT_RUSTFS_CONFIG: S3Config;
/**
 * Result of storage operations.
 */
export interface StorageResult {
    success: boolean;
    stdout: string;
    stderr: string;
    code: number;
}
/**
 * Helper for interacting with S3-compatible storage in E2E tests.
 *
 * Uses rclone for all operations, which is available on bridge/worker VMs.
 * Operations are executed via SSH to the bridge VM.
 *
 * DELEGATES TO SSHExecutor:
 * All SSH operations are delegated to the centralized SSHExecutor to ensure
 * consistent behavior and avoid code duplication.
 */
export declare class StorageTestHelper {
    private readonly bridgeHost;
    private readonly s3Config;
    private readonly sshExecutor;
    constructor(bridgeHost: string, s3Config?: S3Config);
    /**
     * Execute a command on the bridge VM via SSH.
     * Uses SSHExecutor for consistent SSH options.
     */
    private executeOnBridge;
    /**
     * Build rclone flags for S3 connection.
     */
    private getRcloneFlags;
    /**
     * Check if the storage service is accessible.
     * RustFS returns 403 for unauthenticated requests, which means server is running.
     */
    isAvailable(): Promise<boolean>;
    /**
     * List all buckets.
     */
    listBuckets(): Promise<string[]>;
    /**
     * Create a new bucket.
     */
    createBucket(name: string): Promise<StorageResult>;
    /**
     * Delete a bucket and all its contents.
     */
    deleteBucket(name: string): Promise<StorageResult>;
    /**
     * List objects in a bucket.
     */
    listObjects(bucket?: string): Promise<string[]>;
    /**
     * Check if an object exists in a bucket.
     */
    objectExists(bucket: string, key: string): Promise<boolean>;
    /**
     * Upload content to a bucket.
     */
    uploadContent(bucket: string, key: string, content: string): Promise<StorageResult>;
    /**
     * Download content from a bucket.
     */
    downloadContent(bucket: string, key: string): Promise<string | null>;
    /**
     * Delete an object from a bucket.
     */
    deleteObject(bucket: string, key: string): Promise<StorageResult>;
    /**
     * Get storage statistics for a bucket.
     */
    getBucketStats(bucket?: string): Promise<{
        count: number;
        size: number;
    }>;
    /**
     * Upload a file from the bridge VM to storage.
     */
    uploadFile(bucket: string, localPath: string, remotePath?: string): Promise<StorageResult>;
    /**
     * Download a file from storage to the bridge VM.
     */
    downloadFile(bucket: string, remotePath: string, localPath: string): Promise<StorageResult>;
    /**
     * Sync a local directory to a bucket.
     */
    syncToStorage(localDir: string, bucket: string, remotePrefix?: string): Promise<StorageResult>;
    /**
     * Sync a bucket to a local directory.
     */
    syncFromStorage(bucket: string, localDir: string, remotePrefix?: string): Promise<StorageResult>;
    /**
     * Execute an rclone command.
     */
    private executeRclone;
    /**
     * Create a unique test bucket for isolation.
     */
    createTestBucket(prefix?: string): Promise<string>;
    /**
     * Clean up a test bucket.
     */
    cleanupTestBucket(bucketName: string): Promise<void>;
    /**
     * Get the S3 config for use in VaultBuilder.
     */
    getVaultStorageConfig(): {
        name: string;
        type: 's3';
        endpoint: string;
        bucket: string;
        accessKey: string;
        secretKey: string;
        region?: string;
    };
}
//# sourceMappingURL=StorageTestHelper.d.ts.map
