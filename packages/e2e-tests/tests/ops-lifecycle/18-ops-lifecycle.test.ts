import { expect, test } from '@playwright/test';
import { getOpsManager } from '../../src/utils/bridge/OpsManager';
import { InfrastructureManager } from '../../src/utils/infrastructure/InfrastructureManager';

/**
 * OPS VM-lifecycle tests (DESTRUCTIVE).
 *
 * These stop/start/reset the VMs, so they cannot run inside the shared bridge
 * E2E topology — they would tear down the very VMs the rest of the suite is
 * using. They live in this dedicated subdir precisely so the base
 * playwright.config.ts never COLLECTS them (its testIgnore lists the
 * ops-lifecycle subdir): a collected-but-skipped test is dishonest
 * coverage, and the zero-skip gate (run-e2e.sh --fail-on-skip) forbids it.
 *
 * The ops lifecycle itself IS exercised in CI by the dedicated OPS Tests job
 * (.github/workflows/ci-ops-test.yml drives ops setup, check, up --basic,
 * status, up --skip-orchestration and down on throwaway VMs), so excluding
 * these playwright wrappers loses no CI coverage of THOSE verbs.
 *
 * CORRECTED 2026-08-15: this used to claim CI drives "up/status/down/reset".
 * There is no `reset` CLI verb at all -- command-tree.json gives ops exactly
 * up, down, status, ssh, setup and check -- and the string never appears in
 * that workflow. The reset tests below are still real: they call
 * OpsManager.resetVMs(), which runs `renet ops up --force --parallel`
 * (packages/provisioning/src/ops/OpsVMLifecycle.ts:127). What was false was
 * the claim that CI covers them; no config selects this file, so it does not. They remain runnable locally by pointing Playwright at this file
 * directly (there is no CI guard here anymore — exclusion is by config, not a
 * runtime skip).
 */
test.describe('VM Lifecycle @bridge @ops @slow', () => {
  const ops = getOpsManager();

  // Increase timeout for infrastructure operations
  test.setTimeout(600000); // 10 minutes

  test('should report initial status', async () => {
    const result = await ops.getStatus();

    // Status command should succeed regardless of VM state
    expect(result.code).toBe(0);
    expect(result.stdout).toBeTruthy();
  });

  test('should check VM reachability', async () => {
    const vmIds = ops.getVMIds();
    const bridgeIp = ops.getBridgeVMIp();
    const workerIps = ops.getWorkerVMIps();

    console.warn(`Bridge VM: ${vmIds.bridge} -> ${bridgeIp}`);
    console.warn(`Worker VMs: ${vmIds.workers.join(', ')} -> ${workerIps.join(', ')}`);

    // Just log the current state - don't fail if VMs are down
    const bridgeReachable = await ops.isVMReachable(bridgeIp);
    console.warn(`Bridge VM reachable: ${bridgeReachable}`);

    for (const ip of workerIps) {
      const reachable = await ops.isVMReachable(ip);
      console.warn(`Worker ${ip} reachable: ${reachable}`);
    }
  });

  test('should stop VMs if running', async () => {
    // Check current state
    const { ready } = await ops.areAllVMsReady();

    if (ready) {
      console.warn('VMs are running, stopping them...');
      await ops.stopVMs();

      // Allow some time for VMs to fully stop
      await new Promise((resolve) => setTimeout(resolve, 5000));

      // Verify VMs are stopped (not reachable)
      const bridgeIp = ops.getBridgeVMIp();
      const stillReachable = await ops.isVMReachable(bridgeIp);
      expect(stillReachable).toBe(false);

      console.warn('VMs stopped successfully');
    } else {
      console.warn('VMs are already stopped, skipping');
    }
  });

  test('should start VMs with basic mode', async () => {
    console.warn('Starting VMs with --basic mode...');

    const result = await ops.startVMs({ basic: true, parallel: true });

    // Note: The command may return non-zero if some orchestration steps fail
    // (e.g., middleware auth), but VMs may still be created successfully.
    // We verify actual VM readiness below.

    console.warn(`Start command returned code: ${result.success ? 0 : 1}`);

    // Wait for bridge VM to be ready
    const bridgeIp = ops.getBridgeVMIp();
    const bridgeReady = await ops.waitForVM(bridgeIp, 180000);
    expect(bridgeReady).toBe(true);

    console.warn('Bridge VM is ready');

    // Re-deploy renet to VMs after fresh start
    // This is needed because startVMs creates fresh VMs without renet
    console.warn('Re-deploying renet to fresh VMs...');
    const infra = new InfrastructureManager();
    await infra.ensureRenetOnVMs();
    console.warn('Renet deployed to VMs');
  });

  test('should verify SSH connectivity to all VMs', async () => {
    // In basic mode (from previous test), only bridge + first worker are created
    const bridgeIp = ops.getBridgeVMIp();
    const workerIps = ops.getWorkerVMIps();
    const basicVMs = [bridgeIp, workerIps[0]];

    for (const ip of basicVMs) {
      const ready = await ops.waitForVM(ip, 180000);
      expect(ready).toBe(true);
      const sshReady = await ops.isSSHReady(ip);
      expect(sshReady).toBe(true);
      console.warn(`SSH ready on ${ip}`);
    }
  });

  test('should execute commands on VMs', async () => {
    // In basic mode, only bridge + first worker are created
    const bridgeIp = ops.getBridgeVMIp();
    const workerIps = ops.getWorkerVMIps();
    const basicVMs = [bridgeIp, workerIps[0]];

    for (const ip of basicVMs) {
      const result = await ops.executeOnVM(ip, 'hostname && uptime');

      expect(result.code).toBe(0);
      expect(result.stdout).toBeTruthy();
      console.warn(`${ip}: ${result.stdout.trim().split('\n')[0]}`);
    }
  });

  test('should verify renet is installed on VMs', async () => {
    // In basic mode, only bridge + first worker are created
    const bridgeIp = ops.getBridgeVMIp();
    const workerIps = ops.getWorkerVMIps();
    const basicVMs = [bridgeIp, workerIps[0]];

    for (const ip of basicVMs) {
      const installed = await ops.isRenetInstalledOnVM(ip);
      const version = await ops.getRenetVersionOnVM(ip);

      expect(installed).toBe(true);
      expect(version).toBeTruthy();
      console.warn(`${ip}: renet ${version}`);
    }
  });

  test('should report status after VMs are up', async () => {
    const result = await ops.getStatus();

    expect(result.code).toBe(0);
    expect(result.stdout).toBeTruthy();

    // Should show running VMs
    const output = result.stdout.toLowerCase();
    expect(output).toMatch(/running|up|ready/i);
  });
});

/**
 * VM Reset Tests
 *
 * Tests the soft reset functionality that recreates VMs while preserving configuration.
 */
test.describe('VM Reset @bridge @ops @slow', () => {
  const ops = getOpsManager();

  test.setTimeout(600000); // 10 minutes

  test('should perform soft reset', async () => {
    const result = await ops.resetVMs();

    expect(result.success).toBe(true);
    console.warn(`Reset completed in ${(result.duration / 1000).toFixed(1)}s`);

    // In basic mode, only bridge + first worker are created
    const bridgeIp = ops.getBridgeVMIp();
    const workerIps = ops.getWorkerVMIps();
    const basicVMs = [bridgeIp, workerIps[0]];

    // Verify basic mode VMs are ready after reset
    for (const ip of basicVMs) {
      const ready = await ops.waitForVM(ip, 180000);
      expect(ready).toBe(true);
    }

    // Re-deploy renet to VMs after reset
    // This is needed because resetVMs recreates fresh VMs without renet
    console.warn('Re-deploying renet to fresh VMs after reset...');
    const infra = new InfrastructureManager();
    await infra.ensureRenetOnVMs();
    console.warn('Renet deployed to VMs');
  });

  test('should have clean state after reset', async () => {
    // In basic mode, only bridge + first worker are created
    const bridgeIp = ops.getBridgeVMIp();
    const workerIps = ops.getWorkerVMIps();
    const basicVMs = [bridgeIp, workerIps[0]];

    for (const ip of basicVMs) {
      // Verify uptime is low (recently rebooted)
      const result = await ops.executeOnVM(ip, 'cat /proc/uptime | cut -d" " -f1');

      expect(result.code).toBe(0);

      const uptimeSeconds = Number.parseFloat(result.stdout.trim());
      // VM should have been up for less than 10 minutes after reset
      expect(uptimeSeconds).toBeLessThan(600);
      console.warn(`${ip}: uptime ${uptimeSeconds.toFixed(0)}s`);
    }
  });
});
