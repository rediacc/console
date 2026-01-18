import { expect, test } from '@playwright/test';
import { DEFAULT_RUSTFS_ACCESS_KEY, DEFAULT_RUSTFS_SECRET_KEY } from '../src/constants';
import { getOpsManager } from '../src/utils/bridge/OpsManager';

/**
 * RustFS Operations Tests
 *
 * Tests for RustFS S3-compatible storage operations:
 * - Start/stop RustFS container
 * - Bucket creation and listing
 * - Worker configuration for rclone access
 *
 * RustFS runs on the bridge VM and provides S3-compatible storage
 * that workers can access via rclone.
 *
 * Prerequisites:
 * - VMs must be running (use 18-ops-workflow.test.ts first)
 * - Bridge VM must have Docker installed
 */
test.describe('RustFS Lifecycle @bridge @rustfs', () => {
  const ops = getOpsManager();

  // Increase timeout for container operations
  test.setTimeout(300000); // 5 minutes

  test.beforeAll(async () => {
    // Verify bridge VM is reachable
    const bridgeIp = ops.getBridgeVMIp();
    const ready = await ops.waitForVM(bridgeIp, 60000);
    if (!ready) {
      throw new Error('Bridge VM not reachable - run ops workflow tests first');
    }
  });

  test.describe('Container Operations', () => {
    test('should stop RustFS if running', async () => {
      // Check if RustFS is running
      const isRunning = await ops.isRustFSRunning();

      if (isRunning) {
        // eslint-disable-next-line no-console
        console.log('RustFS is running, stopping it...');
        const result = await ops.stopRustFS();
        expect(result.success).toBe(true);

        // Verify it's stopped
        const stillRunning = await ops.isRustFSRunning();
        expect(stillRunning).toBe(false);
        // eslint-disable-next-line no-console
        console.log('RustFS stopped');
      } else {
        // eslint-disable-next-line no-console
        console.log('RustFS is not running, skipping stop');
      }
    });

    test('should start RustFS', async () => {
      const result = await ops.startRustFS();

      expect(result.success).toBe(true);
      expect(result.message).toContain('success');

      // Verify it's running
      const isRunning = await ops.isRustFSRunning();
      expect(isRunning).toBe(true);

      // eslint-disable-next-line no-console
      console.log('RustFS started successfully');
    });

    test('should verify RustFS S3 endpoint is accessible', async () => {
      const bridgeIp = ops.getBridgeVMIp();

      // Check S3 endpoint (returns 403 for unauthenticated requests)
      const result = await ops.executeOnVM(
        bridgeIp,
        "curl -s -o /dev/null -w '%{http_code}' http://localhost:9000/"
      );

      expect(result.code).toBe(0);
      const httpCode = result.stdout.trim();
      // 403 = server running, auth required (expected)
      // 200 = server running, no auth (also acceptable)
      expect(['200', '403']).toContain(httpCode);

      // eslint-disable-next-line no-console
      console.log(`RustFS S3 endpoint HTTP status: ${httpCode}`);
    });

    test('should verify RustFS console is accessible', async () => {
      const bridgeIp = ops.getBridgeVMIp();

      // Check console endpoint on port 9001
      const result = await ops.executeOnVM(
        bridgeIp,
        "curl -s -o /dev/null -w '%{http_code}' http://localhost:9001/"
      );

      expect(result.code).toBe(0);
      const httpCode = result.stdout.trim();
      // Console should return 200 or redirect (302)
      expect(['200', '302', '403']).toContain(httpCode);

      // eslint-disable-next-line no-console
      console.log(`RustFS console HTTP status: ${httpCode}`);
    });
  });
});

/**
 * Bucket Operations Tests
 */
test.describe('RustFS Bucket Operations @bridge @rustfs', () => {
  const ops = getOpsManager();
  const rustfsAccessKey = process.env.RUSTFS_ACCESS_KEY ?? DEFAULT_RUSTFS_ACCESS_KEY;
  const rustfsSecretKey = process.env.RUSTFS_SECRET_KEY ?? DEFAULT_RUSTFS_SECRET_KEY;

  test.setTimeout(120000); // 2 minutes

  test.beforeAll(async () => {
    // Ensure RustFS is running
    const isRunning = await ops.isRustFSRunning();
    if (!isRunning) {
      const result = await ops.startRustFS();
      if (!result.success) {
        throw new Error('Failed to start RustFS');
      }
    }
  });

  test.describe('Bucket CRUD', () => {
    const testBucket = 'e2e-test-bucket';

    test('should create default bucket', async () => {
      const result = await ops.createRustFSBucket();

      expect(result.success).toBe(true);
      // eslint-disable-next-line no-console
      console.log(result.message);
    });

    test('should create custom bucket', async () => {
      const result = await ops.createRustFSBucket(testBucket);

      expect(result.success).toBe(true);
      expect(result.message).toContain(testBucket);
      // eslint-disable-next-line no-console
      console.log(result.message);
    });

    test('should list default bucket', async () => {
      const result = await ops.listRustFSBucket();

      expect(result.success).toBe(true);
      // Empty bucket is fine
      // eslint-disable-next-line no-console
      console.log(`Default bucket contents: ${result.contents || '(empty)'}`);
    });

    test('should list custom bucket', async () => {
      const result = await ops.listRustFSBucket(testBucket);

      expect(result.success).toBe(true);
      // Empty bucket is fine
      // eslint-disable-next-line no-console
      console.log(`${testBucket} contents: ${result.contents || '(empty)'}`);
    });

    test('should upload test file to bucket', async () => {
      const bridgeIp = ops.getBridgeVMIp();

      // Create a test file and upload via rclone
      const result = await ops.executeOnVM(
        bridgeIp,
        `echo "e2e-test-content-$(date +%s)" > /tmp/test-file.txt && ` +
          `rclone copy /tmp/test-file.txt rustfs:${testBucket}/ ` +
          `--s3-provider Other ` +
          `--s3-endpoint http://localhost:9000 ` +
          `--s3-access-key-id ${rustfsAccessKey} ` +
          `--s3-secret-access-key ${rustfsSecretKey} ` +
          `--s3-force-path-style`
      );

      expect(result.code).toBe(0);
      // eslint-disable-next-line no-console
      console.log('Test file uploaded');
    });

    test('should list bucket with uploaded file', async () => {
      const result = await ops.listRustFSBucket(testBucket);

      expect(result.success).toBe(true);
      expect(result.contents).toContain('test-file.txt');
      // eslint-disable-next-line no-console
      console.log(`Bucket contents: ${result.contents}`);
    });
  });
});

/**
 * Worker Configuration Tests
 */
test.describe('RustFS Worker Configuration @bridge @rustfs', () => {
  const ops = getOpsManager();

  test.setTimeout(180000); // 3 minutes

  test.beforeAll(async () => {
    // Ensure RustFS is running
    const isRunning = await ops.isRustFSRunning();
    if (!isRunning) {
      const result = await ops.startRustFS();
      if (!result.success) {
        throw new Error('Failed to start RustFS');
      }
    }

    // Ensure default bucket exists
    await ops.createRustFSBucket();
  });

  test('should configure single worker for RustFS access', async () => {
    const vmIds = ops.getVMIds();
    const firstWorker = vmIds.workers[0];

    const result = await ops.configureRustFSWorker(firstWorker);

    expect(result.success).toBe(true);
    // eslint-disable-next-line no-console
    console.log(result.message);
  });

  test('should verify rclone config on configured worker', async () => {
    const vmIds = ops.getVMIds();
    const firstWorkerId = vmIds.workers[0];
    const firstWorkerIp = ops.calculateVMIp(firstWorkerId);

    // Check rclone config file exists
    const result = await ops.executeOnVM(firstWorkerIp, 'cat ~/.config/rclone/rclone.conf');

    expect(result.code).toBe(0);
    expect(result.stdout).toContain('[rustfs]');
    expect(result.stdout).toContain('type = s3');
    expect(result.stdout).toContain('endpoint');

    // eslint-disable-next-line no-console
    console.log('Rclone config verified on worker');
  });

  test('should verify RustFS access from configured worker', async () => {
    const vmIds = ops.getVMIds();
    const firstWorkerId = vmIds.workers[0];

    const result = await ops.verifyRustFSAccessFromWorker(firstWorkerId);

    expect(result.success).toBe(true);
    // eslint-disable-next-line no-console
    console.log(result.message);
  });

  test('should configure all workers for RustFS access', async () => {
    const result = await ops.configureRustFSWorkers();

    expect(result.success).toBe(true);
    // eslint-disable-next-line no-console
    console.log(result.message);
  });

  test('should verify RustFS access from all workers', async () => {
    const vmIds = ops.getVMIds();

    for (const workerId of vmIds.workers) {
      const result = await ops.verifyRustFSAccessFromWorker(workerId);

      expect(result.success).toBe(true);
      // eslint-disable-next-line no-console
      console.log(`Worker ${workerId}: ${result.message}`);
    }
  });
});

/**
 * RustFS Integration Tests
 *
 * Tests end-to-end workflow: start RustFS, configure workers, upload/download files
 */
test.describe('RustFS Integration @bridge @rustfs @slow', () => {
  const ops = getOpsManager();
  const integrationBucket = 'e2e-integration-bucket';

  test.setTimeout(300000); // 5 minutes

  test.describe('End-to-End Workflow', () => {
    test('should start RustFS', async () => {
      const result = await ops.startRustFS();
      expect(result.success).toBe(true);
    });

    test('should create integration bucket', async () => {
      const result = await ops.createRustFSBucket(integrationBucket);
      expect(result.success).toBe(true);
    });

    test('should configure all workers', async () => {
      const result = await ops.configureRustFSWorkers();
      expect(result.success).toBe(true);
    });

    test('should upload file from worker to RustFS', async () => {
      const vmIds = ops.getVMIds();
      const workerId = vmIds.workers[0];
      const workerIp = ops.calculateVMIp(workerId);

      // Create and upload a file from worker (add -v for verbose output)
      const result = await ops.executeOnVM(
        workerIp,
        `echo "uploaded-from-worker-$(hostname)-$(date +%s)" > /tmp/worker-test.txt && ` +
          `rclone copy /tmp/worker-test.txt rustfs:${integrationBucket}/ -v 2>&1`
      );

      // Always log output for debugging
      console.warn(`[RustFS Upload] Worker ${workerId} (${workerIp}) exit code: ${result.code}`);
      console.warn(`[RustFS Upload] stdout: ${result.stdout}`);
      if (result.stderr) console.warn(`[RustFS Upload] stderr: ${result.stderr}`);

      expect(result.code).toBe(0);
    });

    test('should download file from RustFS to another worker', async () => {
      const vmIds = ops.getVMIds();

      // Use second worker if available, otherwise first
      const downloadWorkerId = vmIds.workers.length > 1 ? vmIds.workers[1] : vmIds.workers[0];
      const downloadWorkerIp = ops.calculateVMIp(downloadWorkerId);

      // Download the file to another worker (add -v for verbose output)
      const result = await ops.executeOnVM(
        downloadWorkerIp,
        `rclone copy rustfs:${integrationBucket}/worker-test.txt /tmp/downloaded/ -v 2>&1 && ` +
          `cat /tmp/downloaded/worker-test.txt`
      );

      // Always log output for debugging
      console.warn(
        `[RustFS Download] Worker ${downloadWorkerId} (${downloadWorkerIp}) exit code: ${result.code}`
      );
      console.warn(`[RustFS Download] stdout: ${result.stdout}`);
      if (result.stderr) console.warn(`[RustFS Download] stderr: ${result.stderr}`);

      expect(result.code).toBe(0);
      expect(result.stdout).toContain('uploaded-from-worker');
    });

    test('should list integration bucket with uploaded files', async () => {
      const result = await ops.listRustFSBucket(integrationBucket);

      // Always log output for debugging
      console.warn(`[RustFS List] Bucket ${integrationBucket} success: ${result.success}`);
      console.warn(`[RustFS List] contents: ${result.contents}`);
      console.warn(`[RustFS List] message: ${result.message}`);

      expect(result.success).toBe(true);
      expect(result.contents).toContain('worker-test.txt');
    });
  });
});

/**
 * RustFS Cleanup Tests
 */
test.describe('RustFS Cleanup @bridge @rustfs', () => {
  const ops = getOpsManager();

  test('should stop RustFS cleanly', async () => {
    const isRunning = await ops.isRustFSRunning();

    if (isRunning) {
      const result = await ops.stopRustFS();
      expect(result.success).toBe(true);

      // Verify stopped
      const stillRunning = await ops.isRustFSRunning();
      expect(stillRunning).toBe(false);

      // eslint-disable-next-line no-console
      console.log('RustFS stopped cleanly');
    } else {
      // eslint-disable-next-line no-console
      console.log('RustFS already stopped');
    }
  });
});
