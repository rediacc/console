import { expect, test } from '@playwright/test';
import { getOpsManager } from '../src/utils/bridge/OpsManager';

/**
 * OPS Workflow Tests (non-destructive, bridge topology).
 *
 * The destructive VM-lifecycle/reset tests moved to tests/ops-lifecycle/ so
 * the bridge run never collects-then-skips them (see that file's header and
 * the base playwright.config.ts testIgnore). What remains here is the
 * parallel-execution check, which runs safely against the live bridge
 * topology without stopping/starting VMs.
 */
test.describe('Parallel Execution @bridge @ops', () => {
  const ops = getOpsManager();

  test('should execute commands on all workers in parallel', async () => {
    // In basic mode, only first worker is available
    const command = 'hostname -I';
    const workerIps = ops.getWorkerVMIps();
    const basicWorkerIps = [workerIps[0]]; // Only first worker in basic mode

    const results = await ops.executeOnAllWorkers(command);

    // Filter to only check workers that exist in basic mode
    for (const [ip, result] of results) {
      if (!basicWorkerIps.includes(ip)) continue;
      expect(result.code).toBe(0);
      // hostname -I may return multiple IPs (including Docker bridge 172.17.0.1)
      // Check that our expected IP is the first one in the output
      const firstIp = result.stdout.trim().split(/\s+/)[0];
      expect(firstIp).toBe(ip);
      console.warn(`Worker ${ip}: OK`);
    }
  });
});
