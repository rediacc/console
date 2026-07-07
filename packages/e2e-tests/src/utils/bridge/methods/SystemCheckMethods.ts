import type { ExecResult, TestFunctionOptions } from '../types';

/**
 * System check and verification methods for BridgeTestRunner.
 * Contains methods for testing machine health, compatibility, and setup status.
 */
export class SystemCheckMethods {
  constructor(private readonly testFunction: (opts: TestFunctionOptions) => Promise<ExecResult>) {}

  async ping(): Promise<ExecResult> {
    return this.testFunction({ function: 'machine_ping' });
  }

  async nop(): Promise<ExecResult> {
    return this.testFunction({ function: 'daemon_nop' });
  }

  async hello(): Promise<ExecResult> {
    return this.testFunction({ function: 'machine_version' });
  }

  async sshTest(): Promise<ExecResult> {
    return this.testFunction({ function: 'machine_ssh_test' });
  }

  async checkKernelCompatibility(): Promise<ExecResult> {
    return this.testFunction({ function: 'machine_check_kernel' });
  }

  async checkSetup(): Promise<ExecResult> {
    return this.testFunction({ function: 'machine_check_setup' });
  }

  async checkMemory(): Promise<ExecResult> {
    return this.testFunction({ function: 'machine_check_memory' });
  }

  async checkSudo(): Promise<ExecResult> {
    return this.testFunction({ function: 'machine_check_sudo' });
  }

  async checkTools(): Promise<ExecResult> {
    return this.testFunction({ function: 'machine_check_tools' });
  }

  async checkRenet(): Promise<ExecResult> {
    return this.testFunction({ function: 'machine_check_renet' });
  }

  async checkCriu(): Promise<ExecResult> {
    return this.testFunction({ function: 'machine_check_criu' });
  }

  async checkBtrfs(): Promise<ExecResult> {
    return this.testFunction({ function: 'machine_check_btrfs' });
  }

  async checkDrivers(): Promise<ExecResult> {
    return this.testFunction({ function: 'machine_check_drivers' });
  }

  async checkSystem(): Promise<ExecResult> {
    return this.testFunction({ function: 'machine_check_system' });
  }

  async checkUsers(): Promise<ExecResult> {
    return this.testFunction({ function: 'machine_check_users' });
  }

  async checkRediaccCli(): Promise<ExecResult> {
    return this.testFunction({ function: 'machine_check_cli' });
  }

  async checkDatastore(datastorePath?: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'datastore_status',
      datastorePath,
    });
  }
}
