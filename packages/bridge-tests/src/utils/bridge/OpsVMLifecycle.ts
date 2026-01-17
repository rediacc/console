import type { OpsCommandRunner } from './OpsCommandRunner';
import type { OpsVMExecutor } from './OpsVMExecutor';

/**
 * OpsVMLifecycle - Manages VM lifecycle operations
 *
 * Extracted from OpsManager to reduce file size.
 * Handles starting, stopping, resetting, and waiting for VMs.
 */
export class OpsVMLifecycle {
  constructor(
    private readonly commandRunner: OpsCommandRunner,
    private readonly vmExecutor: OpsVMExecutor,
    private readonly getAllVMIps: () => string[],
    private readonly getWorkerVMIps: () => string[],
    private readonly getCephVMIps: () => string[]
  ) {}

  /**
   * Get ops status
   */
  async getStatus(): Promise<{ stdout: string; stderr: string; code: number }> {
    return this.commandRunner.run(['status'], [], 30000);
  }

  /**
   * Start VMs using ops scripts
   */
  async startVMs(
    options: { force?: boolean; basic?: boolean; parallel?: boolean } = {}
  ): Promise<{ success: boolean; stdout: string; stderr: string }> {
    const args: string[] = [];

    if (options.force) args.push('--force');
    if (options.basic) args.push('--basic');
    if (options.parallel) args.push('--parallel');

    console.warn('[OpsVMLifecycle] Starting VMs...');
    const result = await this.commandRunner.run(['up'], args, 600000); // 10 minute timeout

    return {
      success: result.code === 0,
      stdout: result.stdout,
      stderr: result.stderr,
    };
  }

  /**
   * Stop all VMs
   */
  async stopVMs(): Promise<{ success: boolean; stdout: string; stderr: string }> {
    console.warn('[OpsVMLifecycle] Stopping VMs...');
    const result = await this.commandRunner.run(['down'], [], 120000); // 2 minute timeout

    return {
      success: result.code === 0,
      stdout: result.stdout,
      stderr: result.stderr,
    };
  }

  /**
   * Wait for all VMs to be ready
   */
  async waitForAllVMs(timeoutMs = 180000): Promise<boolean> {
    console.warn('[OpsVMLifecycle] Waiting for all VMs to be ready...');

    const promises = this.getAllVMIps().map((ip) => this.vmExecutor.waitForVM(ip, timeoutMs));
    const results = await Promise.all(promises);

    return results.every((ready) => ready);
  }

  /**
   * Wait for worker VMs to be ready
   */
  async waitForWorkerVMs(timeoutMs = 180000): Promise<boolean> {
    console.warn('[OpsVMLifecycle] Waiting for worker VMs to be ready...');

    const promises = this.getWorkerVMIps().map((ip) => this.vmExecutor.waitForVM(ip, timeoutMs));
    const results = await Promise.all(promises);

    return results.every((ready) => ready);
  }

  /**
   * Soft reset VMs by force restarting them.
   */
  async resetVMs(): Promise<{ success: boolean; duration: number }> {
    const startTime = Date.now();

    console.warn('[OpsVMLifecycle] Performing soft reset (renet ops up --force --parallel)...');
    // 30 min timeout to allow Ceph provisioning to complete fully
    const extraEnv: Record<string, string> = {};
    if (this.getCephVMIps().length > 0) {
      extraEnv.PROVISION_CEPH_CLUSTER = 'true';
    }
    const result =
      Object.keys(extraEnv).length > 0
        ? await this.commandRunner.runWithEnv(['up'], ['--force', '--parallel'], extraEnv, 1800000)
        : await this.commandRunner.run(['up'], ['--force', '--parallel'], 1800000);

    // Note: The command may return non-zero if middleware auth fails (rdc not found),
    // but VMs may still be successfully created. We verify actual VM readiness below.
    if (result.code !== 0) {
      console.warn(
        '[OpsVMLifecycle] renet ops command returned non-zero, verifying VM readiness anyway...'
      );
    }

    // Wait for all VMs to be ready after reset - this is the real success criteria
    console.warn('[OpsVMLifecycle] Waiting for VMs to be ready after reset...');
    const allReady = await this.waitForAllVMs(180000);

    if (!allReady) {
      console.error('[OpsVMLifecycle] VMs did not become ready after reset');
      return { success: false, duration: Date.now() - startTime };
    }

    console.warn(
      `[OpsVMLifecycle] VM reset completed in ${((Date.now() - startTime) / 1000).toFixed(1)}s`
    );
    return { success: true, duration: Date.now() - startTime };
  }

  /**
   * Ensure VMs are running - start them if not
   */
  async ensureVMsRunning(
    options: { basic?: boolean },
    areAllVMsReady: () => Promise<{
      ready: boolean;
      status: Map<string, { reachable: boolean; sshReady: boolean }>;
    }>
  ): Promise<{ success: boolean; wasStarted: boolean; message: string }> {
    const { ready, status } = await areAllVMsReady();

    if (ready) {
      return { success: true, wasStarted: false, message: 'All VMs are already running and ready' };
    }

    console.warn('[OpsVMLifecycle] Some VMs are not ready:');
    for (const [ip, vmStatus] of status) {
      if (!vmStatus.reachable || !vmStatus.sshReady) {
        console.warn(`  - ${ip}: reachable=${vmStatus.reachable}, sshReady=${vmStatus.sshReady}`);
      }
    }

    console.warn('[OpsVMLifecycle] Starting VMs...');
    const startResult = await this.startVMs({ basic: options.basic });

    if (!startResult.success) {
      return {
        success: false,
        wasStarted: false,
        message: `Failed to start VMs: ${startResult.stderr}`,
      };
    }

    const allReady = await this.waitForAllVMs();

    if (!allReady) {
      return {
        success: false,
        wasStarted: true,
        message: 'VMs started but not all became ready in time',
      };
    }

    return { success: true, wasStarted: true, message: 'VMs started successfully and are ready' };
  }
}
