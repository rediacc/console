import { expect, test } from '@playwright/test';
import { getOpsManager } from '../src/utils/renet-functions/OpsManager';
import { log } from '../src/utils/log';

/**
 * RustFS Operations Tests
 *
 * Tests for RustFS S3-compatible storage operations:
 * - Start/stop RustFS container
 * - Bucket creation and listing
 * - Signed S3 access from the bridge and from workers
 *
 * RustFS runs on the bridge VM and provides S3-compatible storage
 * that workers can access with signed `curl --aws-sigv4` requests.
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
        log('RustFS is running, stopping it...');
        const result = await ops.stopRustFS();
        expect(result.success).toBe(true);

        // Verify it's stopped
        const stillRunning = await ops.isRustFSRunning();
        expect(stillRunning).toBe(false);
        log('RustFS stopped');
      } else {
        log('RustFS is not running, skipping stop');
      }
    });

    test('should start RustFS', async () => {
      const result = await ops.startRustFS();

      expect(result.success).toBe(true);
      expect(result.message).toContain('success');

      // Verify it's running
      const isRunning = await ops.isRustFSRunning();
      expect(isRunning).toBe(true);

      log('RustFS started successfully');
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

      log(`RustFS S3 endpoint HTTP status: ${httpCode}`);
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

      log(`RustFS console HTTP status: ${httpCode}`);
    });
  });
});

/**
 * Bucket Operations Tests
 */
test.describe('RustFS Bucket Operations @bridge @rustfs', () => {
  const ops = getOpsManager();

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
      log(result.message);
    });

    test('should create custom bucket', async () => {
      const result = await ops.createRustFSBucket(testBucket);

      expect(result.success).toBe(true);
      expect(result.message).toContain(testBucket);
      log(result.message);
    });

    test('should list default bucket', async () => {
      const result = await ops.listRustFSBucket();

      expect(result.success).toBe(true);
      // Empty bucket is fine
      log(`Default bucket contents: ${result.contents || '(empty)'}`);
    });

    test('should list custom bucket', async () => {
      const result = await ops.listRustFSBucket(testBucket);

      expect(result.success).toBe(true);
      // Empty bucket is fine
      log(`${testBucket} contents: ${result.contents || '(empty)'}`);
    });

    test('should upload test file to bucket', async () => {
      const bridgeIp = ops.getBridgeVMIp();

      // Create a test file and upload it with a signed PUT
      const written = await ops.executeOnVM(
        bridgeIp,
        'echo "e2e-test-content-$(date +%s)" > /tmp/test-file.txt'
      );
      expect(written.code).toBe(0);

      const result = await ops.rustfsS3Request(
        { method: 'PUT', path: `${testBucket}/test-file.txt`, bodyFile: '/tmp/test-file.txt' },
        { vmIp: bridgeIp, fromWorker: false }
      );

      expect(result.ok).toBe(true);
      log('Test file uploaded');
    });

    test('should list bucket with uploaded file', async () => {
      const result = await ops.listRustFSBucket(testBucket);

      expect(result.success).toBe(true);
      expect(result.contents).toContain('test-file.txt');
      log(`Bucket contents: ${result.contents}`);
    });
  });
});

/**
 * Worker Access Tests
 */
test.describe('RustFS Worker Access @bridge @rustfs', () => {
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

  test('should verify RustFS access from the first worker', async () => {
    const vmIds = ops.getVMIds();
    const firstWorkerId = vmIds.workers[0];

    const result = await ops.verifyRustFSAccessFromWorker(firstWorkerId);

    expect(result.success).toBe(true);
    log(result.message);
  });

  test('should verify RustFS access from all workers', async () => {
    const vmIds = ops.getVMIds();

    for (const workerId of vmIds.workers) {
      const result = await ops.verifyRustFSAccessFromWorker(workerId);

      expect(result.success).toBe(true);
      log(`Worker ${workerId}: ${result.message}`);
    }
  });
});

/**
 * RustFS Integration Tests
 *
 * Tests end-to-end workflow: start RustFS, upload/download files from workers
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

    test('should upload file from worker to RustFS', async () => {
      const vmIds = ops.getVMIds();
      const workerId = vmIds.workers[0];
      const workerIp = ops.calculateVMIp(workerId);

      // Create a file on the worker and upload it with a signed PUT
      const written = await ops.executeOnVM(
        workerIp,
        'echo "uploaded-from-worker-$(hostname)-$(date +%s)" > /tmp/worker-test.txt'
      );
      expect(written.code).toBe(0);
      const result = await ops.rustfsS3Request(
        {
          method: 'PUT',
          path: `${integrationBucket}/worker-test.txt`,
          bodyFile: '/tmp/worker-test.txt',
        },
        { vmIp: workerIp, fromWorker: true }
      );

      // Always log output for debugging
      console.warn(
        `[RustFS Upload] Worker ${workerId} (${workerIp}) HTTP status: ${result.status}`
      );
      if (result.stderr) console.warn(`[RustFS Upload] stderr: ${result.stderr}`);

      expect(result.ok).toBe(true);
    });

    test('should download file from RustFS to another worker', async () => {
      const vmIds = ops.getVMIds();

      // Use second worker if available, otherwise first
      const downloadWorkerId = vmIds.workers.length > 1 ? vmIds.workers[1] : vmIds.workers[0];
      const downloadWorkerIp = ops.calculateVMIp(downloadWorkerId);

      // Download the file to another worker with a signed GET
      const result = await ops.rustfsS3Request(
        { method: 'GET', path: `${integrationBucket}/worker-test.txt` },
        { vmIp: downloadWorkerIp, fromWorker: true }
      );

      // Always log output for debugging
      console.warn(
        `[RustFS Download] Worker ${downloadWorkerId} (${downloadWorkerIp}) HTTP status: ${result.status}`
      );
      console.warn(`[RustFS Download] body: ${result.body}`);
      if (result.stderr) console.warn(`[RustFS Download] stderr: ${result.stderr}`);

      expect(result.ok).toBe(true);
      expect(result.body).toContain('uploaded-from-worker');
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

      log('RustFS stopped cleanly');
    } else {
      log('RustFS already stopped');
    }
  });
});
