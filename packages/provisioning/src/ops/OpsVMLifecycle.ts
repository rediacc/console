import type { OpsCommandRunner } from './OpsCommandRunner';
import type { OpsVMExecutor } from './OpsVMExecutor';

/**
 * Wall-clock budget for one `renet ops up --force --parallel`, covering VM
 * creation, bridge/worker setup and (when VM_CEPH_NODES is set) the whole Ceph
 * bootstrap. 30 minutes is generous against the ~13 minutes a healthy 6-VM
 * ceph run takes, and it is deliberately a HARD budget rather than a hint:
 * overrunning it means the fleet is half-built, and OPS_RESET_TIMEOUT_MS exists
 * so a knowingly-slow host can raise it rather than have the suite lie about
 * what it provisioned.
 */
function resetTimeoutMs(): number {
  return Number(process.env.OPS_RESET_TIMEOUT_MS) || 1800000;
}

/**
 * OpsVMLifecycle - Manages VM lifecycle operations
 *
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
    private readonly getCephVMIps: () => string[],
    /**
     * Per-group env threaded into every ops subprocess spawned here. Empty for
     * single-group callers (ambient env wins, unchanged behavior); populated for
     * a second concurrent KVM group so its up/down/reset carry its own VM_NET.
     */
    private readonly groupEnv: Record<string, string> = {}
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
    return this.commandRunner.runWithEnv(['status'], [], this.groupEnv, 30000);
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
    // Same budget as resetVMs, and for the same reason: a ceph-pool topology
    // bootstraps cephadm (mon+mgr+OSDs) inside `ops up`, which exceeds 10
    // minutes on loaded hosts — and startVMs({force}) recreates the VMs on
    // every attempt, so a shorter cap makes ceph clusters unprovisionable
    // rather than slow.
    const result = await this.commandRunner.runWithEnv(
      ['up'],
      args,
      this.groupEnv,
      resetTimeoutMs()
    );

    if (result.timedOut) {
      console.error(
        `[OpsVMLifecycle] ops up EXCEEDED its ${(resetTimeoutMs() / 1000).toFixed(0)}s budget and was killed`
      );
    }

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
    const result = await this.commandRunner.runWithEnv(['down'], [], this.groupEnv, 120000); // 2 minute timeout

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
    // Note: Ceph provisioning is automatically enabled when VM_CEPH_NODES is configured
    const result = await this.commandRunner.runWithEnv(
      ['up'],
      ['--force', '--parallel'],
      this.groupEnv,
      resetTimeoutMs()
    );

    // Check for infrastructure errors that should fail fast
    if (result.code !== 0) {
      const combinedOutput = `${result.stdout} ${result.stderr}`;

      // A reset we KILLED is not a reset that failed on its own, and it must
      // never fall through to the readiness probe below. `renet ops up` treats
      // Ceph provisioning as non-fatal, so a SIGTERM landing in the middle of
      // it leaves SSH-reachable VMs, prints "Cluster started successfully",
      // and passes the probe -- the reset then reports SUCCESS at 1800.8s and
      // the suite dies a second later on a Ceph error that names Ceph rather
      // than the budget. That is console run 33937342780.
      if (result.timedOut) {
        console.error(
          `[OpsVMLifecycle] ops up EXCEEDED its ${(resetTimeoutMs() / 1000).toFixed(0)}s budget and was killed - failing the reset`
        );
        console.error(
          '[OpsVMLifecycle] The fleet is half-provisioned; any error after this point describes the wreckage, not the cause.'
        );
        console.error('[OpsVMLifecycle] Last output:', combinedOutput.slice(-1000));
        return { success: false, duration: Date.now() - startTime };
      }

      if (this.isInfrastructureError(combinedOutput)) {
        console.error('[OpsVMLifecycle] Infrastructure error - KVM/libvirt not available');
        console.error('[OpsVMLifecycle] Run: sudo renet ops host setup');
        console.error('[OpsVMLifecycle] Error output:', combinedOutput.slice(0, 500));
        return { success: false, duration: Date.now() - startTime };
      }

      // An orchestration failure (registry/docker/ceph provisioning) leaves
      // SSH-reachable but unusable VMs: the readiness probe below would pass
      // and the suite would then spin its whole ceph-health budget on a
      // cluster that was never provisioned. Fail fast with renet's error.
      if (combinedOutput.includes('orchestration failed')) {
        console.error('[OpsVMLifecycle] ops up orchestration failed - failing the reset');
        console.error('[OpsVMLifecycle] Error output:', combinedOutput.slice(-1000));
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
