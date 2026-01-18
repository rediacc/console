import {
  DEFAULT_RUSTFS_ACCESS_KEY,
  DEFAULT_RUSTFS_BUCKET,
  DEFAULT_RUSTFS_ENDPOINT,
  DEFAULT_RUSTFS_SECRET_KEY,
} from '../../constants';
import { getSSHExecutor, SSHExecutor } from '../ssh';

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
export const DEFAULT_RUSTFS_CONFIG: S3Config = {
  endpoint: DEFAULT_RUSTFS_ENDPOINT,
  accessKey: DEFAULT_RUSTFS_ACCESS_KEY,
  secretKey: DEFAULT_RUSTFS_SECRET_KEY,
  bucket: DEFAULT_RUSTFS_BUCKET,
};

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
export class StorageTestHelper {
  private readonly bridgeHost: string;
  private readonly s3Config: S3Config;
  private readonly sshExecutor: SSHExecutor;

  constructor(bridgeHost: string, s3Config: S3Config = DEFAULT_RUSTFS_CONFIG) {
    this.bridgeHost = bridgeHost;
    this.s3Config = s3Config;
    this.sshExecutor = getSSHExecutor();
  }

  /**
   * Execute a command on the bridge VM via SSH.
   * Uses SSHExecutor for consistent SSH options.
   */
  private async executeOnBridge(command: string, timeout = 30000): Promise<StorageResult> {
    console.warn(`[Storage SSH ${this.bridgeHost}] ${command}`);

    const result = await this.sshExecutor.execute(this.bridgeHost, command, {
      connectTimeout: 10,
      batchMode: true,
      execTimeout: timeout,
    });

    return {
      success: result.success,
      stdout: result.stdout,
      stderr: result.stderr,
      code: result.code,
    };
  }

  /**
   * Build rclone flags for S3 connection.
   */
  private getRcloneFlags(): string {
    return [
      '--s3-provider Other',
      `--s3-endpoint ${this.s3Config.endpoint}`,
      `--s3-access-key-id ${this.s3Config.accessKey}`,
      `--s3-secret-access-key ${this.s3Config.secretKey}`,
      '--s3-force-path-style',
    ].join(' ');
  }

  /**
   * Check if the storage service is accessible.
   * RustFS returns 403 for unauthenticated requests, which means server is running.
   */
  async isAvailable(): Promise<boolean> {
    const result = await this.executeOnBridge(
      `curl -s -o /dev/null -w '%{http_code}' ${this.s3Config.endpoint}/`
    );
    const httpCode = result.stdout.trim();
    // 403 = Access Denied (server running, auth required)
    // 200 = OK
    return result.success && (httpCode === '403' || httpCode === '200');
  }

  /**
   * List all buckets.
   */
  async listBuckets(): Promise<string[]> {
    const result = await this.executeRclone('lsd :s3:');
    if (!result.success) return [];

    return result.stdout
      .split('\n')
      .filter((line) => line.trim())
      .map((line) => {
        // Parse rclone lsd output: "-1 2024-01-01 00:00:00 -1 bucketname"
        const parts = line.trim().split(/\s+/);
        return parts[parts.length - 1];
      })
      .filter(Boolean);
  }

  /**
   * Create a new bucket.
   */
  async createBucket(name: string): Promise<StorageResult> {
    return this.executeRclone(`mkdir :s3:${name}`);
  }

  /**
   * Delete a bucket and all its contents.
   */
  async deleteBucket(name: string): Promise<StorageResult> {
    return this.executeRclone(`purge :s3:${name}`);
  }

  /**
   * List objects in a bucket.
   */
  async listObjects(bucket = this.s3Config.bucket): Promise<string[]> {
    const result = await this.executeRclone(`ls :s3:${bucket}`);
    if (!result.success) return [];

    return result.stdout
      .split('\n')
      .filter((line) => line.trim())
      .map((line) => {
        // Parse rclone ls output: "size filename"
        const parts = line.trim().split(/\s+/);
        return parts.slice(1).join(' ');
      })
      .filter(Boolean);
  }

  /**
   * Check if an object exists in a bucket.
   */
  async objectExists(bucket: string, key: string): Promise<boolean> {
    // Use lsf with --files-only to check if file exists
    // Returns the filename if it exists, empty if not
    const result = await this.executeRclone(`lsf :s3:${bucket}/${key}`);
    return result.success && result.stdout.trim().length > 0;
  }

  /**
   * Upload content to a bucket.
   */
  async uploadContent(bucket: string, key: string, content: string): Promise<StorageResult> {
    const tmpFile = `/tmp/storage-test-${Date.now()}.txt`;

    // Write content to temp file on bridge
    const writeResult = await this.executeOnBridge(
      `echo '${content.replaceAll("'", "'\\''")}' > ${tmpFile}`
    );
    if (!writeResult.success) return writeResult;

    try {
      // Upload file to S3 using copyto (not copy) to set exact key name
      return await this.executeRclone(`copyto ${tmpFile} :s3:${bucket}/${key}`);
    } finally {
      // Cleanup temp file
      await this.executeOnBridge(`rm -f ${tmpFile}`);
    }
  }

  /**
   * Download content from a bucket.
   */
  async downloadContent(bucket: string, key: string): Promise<string | null> {
    const tmpFile = `/tmp/storage-download-${Date.now()}.txt`;

    try {
      // Use copyto (not copy) to download to exact file path
      const downloadResult = await this.executeRclone(`copyto :s3:${bucket}/${key} ${tmpFile}`);
      if (!downloadResult.success) return null;

      const readResult = await this.executeOnBridge(`cat ${tmpFile}`);
      return readResult.success ? readResult.stdout : null;
    } finally {
      await this.executeOnBridge(`rm -f ${tmpFile}`);
    }
  }

  /**
   * Delete an object from a bucket.
   */
  async deleteObject(bucket: string, key: string): Promise<StorageResult> {
    return this.executeRclone(`delete :s3:${bucket}/${key}`);
  }

  /**
   * Get storage statistics for a bucket.
   */
  async getBucketStats(bucket = this.s3Config.bucket): Promise<{ count: number; size: number }> {
    const result = await this.executeRclone(`size :s3:${bucket} --json`);
    if (!result.success) return { count: 0, size: 0 };

    try {
      const stats = JSON.parse(result.stdout);
      return {
        count: stats.count ?? 0,
        size: stats.bytes ?? 0,
      };
    } catch {
      return { count: 0, size: 0 };
    }
  }

  /**
   * Upload a file from the bridge VM to storage.
   */
  async uploadFile(bucket: string, localPath: string, remotePath?: string): Promise<StorageResult> {
    const destination = remotePath ?? localPath.split('/').pop();
    return this.executeRclone(`copy ${localPath} :s3:${bucket}/${destination}`);
  }

  /**
   * Download a file from storage to the bridge VM.
   */
  async downloadFile(
    bucket: string,
    remotePath: string,
    localPath: string
  ): Promise<StorageResult> {
    return this.executeRclone(`copy :s3:${bucket}/${remotePath} ${localPath}`);
  }

  /**
   * Sync a local directory to a bucket.
   */
  async syncToStorage(
    localDir: string,
    bucket: string,
    remotePrefix?: string
  ): Promise<StorageResult> {
    const destination = remotePrefix ? `:s3:${bucket}/${remotePrefix}` : `:s3:${bucket}`;
    return this.executeRclone(`sync ${localDir} ${destination}`);
  }

  /**
   * Sync a bucket to a local directory.
   */
  async syncFromStorage(
    bucket: string,
    localDir: string,
    remotePrefix?: string
  ): Promise<StorageResult> {
    const source = remotePrefix ? `:s3:${bucket}/${remotePrefix}` : `:s3:${bucket}`;
    return this.executeRclone(`sync ${source} ${localDir}`);
  }

  /**
   * Execute an rclone command.
   */
  private async executeRclone(command: string): Promise<StorageResult> {
    const fullCommand = `rclone ${command} ${this.getRcloneFlags()}`;
    return this.executeOnBridge(fullCommand);
  }

  /**
   * Create a unique test bucket for isolation.
   */
  async createTestBucket(prefix = 'e2e-test'): Promise<string> {
    const bucketName = `${prefix}-${Date.now()}`;
    await this.createBucket(bucketName);
    return bucketName;
  }

  /**
   * Clean up a test bucket.
   */
  async cleanupTestBucket(bucketName: string): Promise<void> {
    await this.deleteBucket(bucketName);
  }

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
  } {
    return {
      name: 'rustfs',
      type: 's3',
      endpoint: this.s3Config.endpoint,
      bucket: this.s3Config.bucket,
      accessKey: this.s3Config.accessKey,
      secretKey: this.s3Config.secretKey,
      region: this.s3Config.region,
    };
  }
}
