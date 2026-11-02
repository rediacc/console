import type { OpsVMExecutor } from '@rediacc/provisioning/ops';
import {
  DEFAULT_RUSTFS_ACCESS_KEY,
  DEFAULT_RUSTFS_BUCKET,
  DEFAULT_RUSTFS_ENDPOINT,
  DEFAULT_RUSTFS_SECRET_KEY,
} from '../../constants';
import {
  buildS3CurlCommand,
  parseS3CurlOutput,
  type S3CurlRequest,
  type S3CurlResponse,
} from '../storage/s3-curl';

/**
 * Budget for `renet ops rustfs start`: up to 5 RustFS image pulls 15 s apart, a 60 s readiness wait and the bucket creation.
 * The old 120 s budget failed global setup (console run 36514306445, E2E Workers ubuntu-24.04 5/8).
 */
const RUSTFS_START_TIMEOUT_MS = 480_000;

/**
 * OpsRustFSManager - Manages RustFS S3-compatible storage operations
 *
 * Extracted from OpsManager to reduce file size.
 * Provides methods for:
 * - Starting/stopping RustFS
 * - Bucket management
 * - Signed S3 requests (curl --aws-sigv4) from the bridge or from a worker
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
    const result = await this.runOpsCommand(['rustfs', 'start'], [], RUSTFS_START_TIMEOUT_MS);

    if (result.code !== 0) {
      console.error('[OpsRustFSManager] Failed to start RustFS:', result.stderr);
      return { success: false, message: `Failed to start RustFS: ${result.stderr}` };
    }

    // Verify RustFS is accessible by checking the S3 endpoint Note: RustFS returns 403 for unauthenticated requests, which means server is running
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
   * Run one signed S3 request against RustFS with `curl --aws-sigv4`, on the bridge (loopback) or on
   * a worker VM (the bridge's address). The VM needs only curl 7.75+.
   */
  async s3Request(
    request: S3CurlRequest,
    where: { vmIp: string; fromWorker: boolean }
  ): Promise<S3CurlResponse & { stderr: string; code: number }> {
    const port = new URL(DEFAULT_RUSTFS_ENDPOINT).port || '9000';
    const endpoint = `http://${where.fromWorker ? this.bridgeIp : 'localhost'}:${port}`;
    const command = buildS3CurlCommand(
      {
        endpoint,
        accessKey: process.env.RUSTFS_ACCESS_KEY ?? DEFAULT_RUSTFS_ACCESS_KEY,
        secretKey: process.env.RUSTFS_SECRET_KEY ?? DEFAULT_RUSTFS_SECRET_KEY,
        bucket: DEFAULT_RUSTFS_BUCKET,
      },
      request
    );
    const result = await this.vmExecutor.executeOnVM(where.vmIp, command, 60000);
    return { ...parseS3CurlOutput(result, request), stderr: result.stderr, code: result.code };
  }

  /**
   * Verify RustFS access from a worker VM: a signed bucket listing must answer 2xx.
   */
  async verifyAccessFromWorker(
    vmId: number,
    calculateVMIp: (vmId: number) => string,
    bucket?: string
  ): Promise<{ success: boolean; message: string }> {
    const ip = calculateVMIp(vmId);
    const bucketName = bucket ?? DEFAULT_RUSTFS_BUCKET;
    console.warn(`[OpsRustFSManager] Verifying RustFS access from VM ${vmId} (${ip})...`);

    const result = await this.s3Request(
      { method: 'GET', path: `${bucketName}?list-type=2` },
      { vmIp: ip, fromWorker: true }
    );

    if (!result.ok) {
      return {
        success: false,
        message: `RustFS access verification failed: HTTP ${result.status} ${result.stderr}`.trim(),
      };
    }

    return { success: true, message: `RustFS accessible from VM ${vmId}` };
  }
}
