import type { OpsCommandRunner } from './OpsCommandRunner';
import type { OpsVMExecutor } from './OpsVMExecutor';

/**
 * OpsVMLifecycle - Manages VM lifecycle operations
 *
 * Extracted from OpsManager to reduce file size.
 * Handles starting, stopping, resetting, and waiting for VMs.
 */
export class OpsVMLifecycle {
  /**
   * Error patterns that indicate missing infrastructure (KVM/libvirt not installed).
   * When these errors occur, we fail fast instead of waiting for VMs that can't be created.
   */
  private static readonly INFRASTRUCTURE_ERROR_PATTERNS = [
    'failed to list networks',
    'failed to check network',
    'virsh: command not found',
    'qemu-img: command not found',
    'libvirt',
    'cannot connect to',
    'failed to connect socket',
  ];

  constructor(
    private readonly commandRunner: OpsCommandRunner,
    private readonly vmExecutor: OpsVMExecutor,
    private readonly getAllVMIps: () => string[],
    private readonly getWorkerVMIps: () => string[],
    private readonly getCephVMIps: () => string[]
  ) {}

  /**
   * Check if an error output indicates missing infrastructure (KVM/libvirt not installed).
   * These errors should fail fast rather than waiting for VMs that can never be created.
   */
  private isInfrastructureError(output: string): boolean {
    const lowerOutput = output.toLowerCase();
    return OpsVMLifecycle.INFRASTRUCTURE_ERROR_PATTERNS.some((pattern) =>
      lowerOutput.includes(pattern.toLowerCase())
    );
  }

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
    const workerIps = this.getWorkerVMIps();
    if (workerIps.length === 0) {
      console.warn('[OpsVMLifecycle] No worker VMs configured, skipping wait');
      return true; // No workers to wait for = success
    }
    console.warn('[OpsVMLifecycle] Waiting for worker VMs to be ready...');

    const promises = workerIps.map((ip) => this.vmExecutor.waitForVM(ip, timeoutMs));
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
    // Note: Ceph provisioning is automatically enabled when VM_CEPH_NODES is configured
    const result = await this.commandRunner.run(['up'], ['--force', '--parallel'], 1800000);

    // Check for infrastructure errors that should fail fast
    if (result.code !== 0) {
      const combinedOutput = `${result.stdout} ${result.stderr}`;

      if (this.isInfrastructureError(combinedOutput)) {
        console.error('[OpsVMLifecycle] Infrastructure error - KVM/libvirt not available');
        console.error('[OpsVMLifecycle] Run: sudo renet ops host setup');
        console.error('[OpsVMLifecycle] Error output:', combinedOutput.slice(0, 500));
        return { success: false, duration: Date.now() - startTime };
      }

      // Note: The command may return non-zero if middleware auth fails (rdc not found),
      // but VMs may still be successfully created. We verify actual VM readiness below.
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
