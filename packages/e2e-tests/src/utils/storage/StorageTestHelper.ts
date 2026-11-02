import {
  DEFAULT_RUSTFS_ACCESS_KEY,
  DEFAULT_RUSTFS_BUCKET,
  DEFAULT_RUSTFS_ENDPOINT,
  DEFAULT_RUSTFS_SECRET_KEY,
} from '../../constants';
import { getSSHExecutor, SSHExecutor } from '../ssh';
import {
  buildS3CurlCommand,
  parseS3CurlOutput,
  type S3CurlRequest,
  type S3CurlResponse,
  xmlValues,
} from './s3-curl';

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
 * Every operation is one SigV4-signed `curl --aws-sigv4` request, so the VMs need nothing beyond curl 7.75+.
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
   * Run a shell command on the bridge VM (for fixtures that edit a downloaded object).
   */
  runOnBridge(command: string): Promise<StorageResult> {
    return this.executeOnBridge(command);
  }

  /**
   * Run one signed S3 request on the bridge VM.
   */
  private async s3(request: S3CurlRequest): Promise<S3CurlResponse & StorageResult> {
    const result = await this.executeOnBridge(buildS3CurlCommand(this.s3Config, request));
    const response = parseS3CurlOutput(result, request);
    return {
      ...response,
      success: response.ok,
      stdout: response.body,
      stderr: result.stderr,
      code: result.code,
    };
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
    const result = await this.s3({ method: 'GET' });
    return result.ok ? xmlValues(result.body, 'Name') : [];
  }

  /**
   * Create a new bucket.
   */
  createBucket(name: string): Promise<StorageResult> {
    return this.s3({ method: 'PUT', path: name });
  }

  /**
   * Delete a bucket and all its contents.
   */
  async deleteBucket(name: string): Promise<StorageResult> {
    for (const key of await this.listObjects(name)) {
      await this.deleteObject(name, key);
    }
    return this.s3({ method: 'DELETE', path: name });
  }

  /**
   * List object keys in a bucket (ListObjectsV2, first page).
   */
  async listObjects(bucket = this.s3Config.bucket): Promise<string[]> {
    const result = await this.s3({ method: 'GET', path: `${bucket}?list-type=2` });
    return result.ok ? xmlValues(result.body, 'Key') : [];
  }

  /**
   * Check if an object exists in a bucket.
   */
  async objectExists(bucket: string, key: string): Promise<boolean> {
    const result = await this.s3({ method: 'HEAD', path: `${bucket}/${key}` });
    return result.ok;
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
      return await this.uploadFile(bucket, tmpFile, key);
    } finally {
      await this.executeOnBridge(`rm -f ${tmpFile}`);
    }
  }

  /**
   * Download content from a bucket.
   */
  async downloadContent(bucket: string, key: string): Promise<string | null> {
    const result = await this.s3({ method: 'GET', path: `${bucket}/${key}` });
    return result.ok ? result.body : null;
  }

  /**
   * Delete an object from a bucket.
   */
  deleteObject(bucket: string, key: string): Promise<StorageResult> {
    return this.s3({ method: 'DELETE', path: `${bucket}/${key}` });
  }

  /**
   * Upload a file from the bridge VM to storage.
   */
  uploadFile(bucket: string, localPath: string, remotePath?: string): Promise<StorageResult> {
    const destination = remotePath ?? localPath.split('/').pop();
    return this.s3({ method: 'PUT', path: `${bucket}/${destination}`, bodyFile: localPath });
  }

  /**
   * Download a file from storage to the bridge VM.
   */
  downloadFile(bucket: string, remotePath: string, localPath: string): Promise<StorageResult> {
    return this.s3({ method: 'GET', path: `${bucket}/${remotePath}`, outputFile: localPath });
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
}
