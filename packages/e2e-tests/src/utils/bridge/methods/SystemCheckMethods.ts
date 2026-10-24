import type { ExecResult, TestFunctionOptions } from '../types';

/**
 * System check and verification methods for BridgeTestRunner.
 * Contains methods for testing machine health, compatibility, and setup status.
 */
export class SystemCheckMethods {
  constructor(private readonly testFunction: (opts: TestFunctionOptions) => Promise<ExecResult>) {}

  ping(): Promise<ExecResult> {
    return this.testFunction({ function: 'machine_ping' });
  }

  nop(): Promise<ExecResult> {
    return this.testFunction({ function: 'daemon_nop' });
  }

  hello(): Promise<ExecResult> {
    return this.testFunction({ function: 'machine_version' });
  }

  networkUsed(): Promise<ExecResult> {
    return this.testFunction({ function: 'network_used' });
  }

  sshTest(): Promise<ExecResult> {
    return this.testFunction({ function: 'machine_ssh_test' });
  }

  checkKernelCompatibility(): Promise<ExecResult> {
    return this.testFunction({ function: 'machine_check_kernel' });
  }

  checkSetup(): Promise<ExecResult> {
    return this.testFunction({ function: 'machine_check_setup' });
  }

  checkMemory(): Promise<ExecResult> {
    return this.testFunction({ function: 'machine_check_memory' });
  }

  checkSudo(): Promise<ExecResult> {
    return this.testFunction({ function: 'machine_check_sudo' });
  }

  checkTools(): Promise<ExecResult> {
    return this.testFunction({ function: 'machine_check_tools' });
  }

  checkRenet(): Promise<ExecResult> {
    return this.testFunction({ function: 'machine_check_renet' });
  }

  checkCriu(): Promise<ExecResult> {
    return this.testFunction({ function: 'machine_check_criu' });
  }

  checkBtrfs(): Promise<ExecResult> {
    return this.testFunction({ function: 'machine_check_btrfs' });
  }

  checkDrivers(): Promise<ExecResult> {
    return this.testFunction({ function: 'machine_check_drivers' });
  }

  checkSystem(): Promise<ExecResult> {
    return this.testFunction({ function: 'machine_check_system' });
  }

  checkUsers(): Promise<ExecResult> {
    return this.testFunction({ function: 'machine_check_users' });
  }

  checkRediaccCli(): Promise<ExecResult> {
    return this.testFunction({ function: 'machine_check_cli' });
  }

  /** Dry-run converge: plans the daemon restarts without restarting any repository. */
  convergeRuntimeDryRun(): Promise<ExecResult> {
    return this.testFunction({ function: 'machine_converge_runtime', dryRun: true });
  }

  checkDatastore(datastorePath?: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'datastore_status',
      datastorePath,
    });
  }
}
