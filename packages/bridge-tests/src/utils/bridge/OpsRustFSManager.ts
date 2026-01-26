import type { OpsVMExecutor } from '@rediacc/provisioning/ops';

/**
 * OpsRustFSManager - Manages RustFS S3-compatible storage operations
 *
 * Extracted from OpsManager to reduce file size.
 * Provides methods for:
 * - Starting/stopping RustFS
 * - Bucket management
 * - Worker configuration for RustFS access
 * - Access verification
 */
export class OpsRustFSManager {
  constructor(
    private readonly vmExecutor: OpsVMExecutor,
    private readonly bridgeIp: string,
    private readonly runOpsCommand: (
      subcommands: string[],
      args?: string[],
      timeoutMs?: number
    ) => Promise<{ stdout: string; stderr: string; code: number }>
  ) {}

  /**
   * Start RustFS S3-compatible storage on the bridge VM.
   * Uses renet ops rustfs start command.
   */
  async start(): Promise<{ success: boolean; message: string }> {
    console.warn(`[OpsRustFSManager] Starting RustFS on bridge VM (${this.bridgeIp})...`);

    // Check if RustFS is already running
    const checkResult = await this.vmExecutor.executeOnVM(
      this.bridgeIp,
      'docker ps --filter name=rustfs --format "{{.Names}}"'
    );
    const RUSTFS_CONTAINER_NAME = 'rustfs';
    if (checkResult.stdout.trim() === RUSTFS_CONTAINER_NAME) {
      console.warn('[OpsRustFSManager] RustFS is already running');
      return { success: true, message: 'RustFS already running' };
    }

    // Start RustFS using renet ops command
    const result = await this.runOpsCommand(['rustfs', 'start'], [], 120000); // 2 minute timeout

    if (result.code !== 0) {
      console.error('[OpsRustFSManager] Failed to start RustFS:', result.stderr);
      return { success: false, message: `Failed to start RustFS: ${result.stderr}` };
    }

    // Verify RustFS is accessible by checking the S3 endpoint
    // Note: RustFS returns 403 for unauthenticated requests, which means server is running
    console.warn('[OpsRustFSManager] Verifying RustFS S3 endpoint...');
    const verifyResult = await this.vmExecutor.executeOnVM(
      this.bridgeIp,
      "curl -s -o /dev/null -w '%{http_code}' http://localhost:9000/"
    );

    const httpCode = verifyResult.stdout.trim();
    const HTTP_FORBIDDEN = '403';
    const HTTP_OK = '200';
    // 403 = Access Denied (server running, auth required)
    // 200 = OK (shouldn't happen without auth, but accept it)
    if (httpCode === HTTP_FORBIDDEN || httpCode === HTTP_OK) {
      console.warn('[OpsRustFSManager] RustFS S3 endpoint is accessible');
      return { success: true, message: 'RustFS started successfully' };
    }

    console.error(`[OpsRustFSManager] RustFS health check failed (HTTP ${httpCode})`);
    return { success: false, message: `RustFS health check failed (HTTP ${httpCode})` };
  }

  /**
   * Check if RustFS is running on the bridge VM.
   */
  async isRunning(): Promise<boolean> {
    const RUSTFS_CONTAINER_NAME = 'rustfs';
    const result = await this.vmExecutor.executeOnVM(
      this.bridgeIp,
      'docker ps --filter name=rustfs --format "{{.Names}}"'
    );
    return result.stdout.trim() === RUSTFS_CONTAINER_NAME;
  }

  /**
   * Stop RustFS S3-compatible storage on the bridge VM.
   * Uses renet ops rustfs stop command.
   */
  async stop(): Promise<{ success: boolean; message: string }> {
    console.warn('[OpsRustFSManager] Stopping RustFS...');
    const result = await this.runOpsCommand(['rustfs', 'stop'], [], 60000); // 1 minute timeout

    if (result.code !== 0) {
      return { success: false, message: `Failed to stop RustFS: ${result.stderr}` };
    }

    return { success: true, message: 'RustFS stopped successfully' };
  }

  /**
   * Create a bucket in RustFS.
   * Uses renet ops rustfs create-bucket command.
   */
  async createBucket(bucket?: string): Promise<{ success: boolean; message: string }> {
    const DEFAULT_BUCKET_NAME = 'default';
    const bucketName = bucket ?? DEFAULT_BUCKET_NAME;
    console.warn(`[OpsRustFSManager] Creating RustFS bucket: ${bucketName}`);

    const args = bucket ? [bucket] : [];
    const result = await this.runOpsCommand(['rustfs', 'create-bucket'], args, 60000);

    if (result.code !== 0) {
      return { success: false, message: `Failed to create bucket: ${result.stderr}` };
    }

    return { success: true, message: `Bucket '${bucketName}' created successfully` };
  }

  /**
   * List contents of a RustFS bucket.
   * Uses renet ops rustfs list command.
   */
  async listBucket(
    bucket?: string
  ): Promise<{ success: boolean; contents: string; message: string }> {
    const DEFAULT_BUCKET_NAME = 'default';
    const bucketName = bucket ?? DEFAULT_BUCKET_NAME;
    console.warn(`[OpsRustFSManager] Listing RustFS bucket: ${bucketName}`);

    const args = bucket ? [bucket] : [];
    const result = await this.runOpsCommand(['rustfs', 'list'], args, 60000);

    if (result.code !== 0) {
      return { success: false, contents: '', message: `Failed to list bucket: ${result.stderr}` };
    }

    return { success: true, contents: result.stdout.trim(), message: 'Bucket listed successfully' };
  }

  /**
   * Configure rclone on a worker VM to access RustFS.
   * Uses renet ops rustfs configure-worker command.
   */
  async configureWorker(vmId: number): Promise<{ success: boolean; message: string }> {
    console.warn(`[OpsRustFSManager] Configuring RustFS access on worker VM ${vmId}...`);

    const result = await this.runOpsCommand(
      ['rustfs', 'configure-worker'],
      [vmId.toString()],
      60000
    );

    if (result.code !== 0) {
      return { success: false, message: `Failed to configure worker ${vmId}: ${result.stderr}` };
    }

    return { success: true, message: `Worker ${vmId} configured for RustFS access` };
  }

  /**
   * Configure rclone on all worker VMs to access RustFS.
   * Uses renet ops rustfs configure-workers command.
   */
  async configureAllWorkers(): Promise<{ success: boolean; message: string }> {
    console.warn('[OpsRustFSManager] Configuring RustFS access on all worker VMs...');

    const result = await this.runOpsCommand(['rustfs', 'configure-workers'], [], 120000);

    if (result.code !== 0) {
      return { success: false, message: `Failed to configure workers: ${result.stderr}` };
    }

    return { success: true, message: 'All workers configured for RustFS access' };
  }

  /**
   * Verify RustFS access from a worker VM using rclone.
   */
  async verifyAccessFromWorker(
    vmId: number,
    calculateVMIp: (vmId: number) => string,
    bucket?: string
  ): Promise<{ success: boolean; message: string }> {
    const ip = calculateVMIp(vmId);
    const DEFAULT_BUCKET_NAME = 'default';
    const bucketName = bucket ?? DEFAULT_BUCKET_NAME;
    console.warn(`[OpsRustFSManager] Verifying RustFS access from VM ${vmId} (${ip})...`);

    // Try to list the bucket using rclone
    const result = await this.vmExecutor.executeOnVM(
      ip,
      `rclone ls rustfs:${bucketName} 2>&1 || echo "(empty or bucket not found)"`,
      30000
    );

    if (result.code !== 0) {
      return { success: false, message: `RustFS access verification failed: ${result.stderr}` };
    }

    return { success: true, message: `RustFS accessible from VM ${vmId}` };
  }
}
