import type { ExecResult, TestFunctionOptions } from '../types';

/**
 * Machine setup and initialization methods for BridgeTestRunner.
 */
export class SetupMethods {
  constructor(private readonly testFunction: (opts: TestFunctionOptions) => Promise<ExecResult>) {}

  async setup(datastorePath?: string, uid?: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'setup',
      datastorePath,
      uid,
    });
  }

  async osSetup(datastorePath?: string, uid?: string): Promise<ExecResult> {
    // os_setup is now an alias for setup
    return this.testFunction({
      function: 'setup',
      datastorePath,
      uid,
    });
  }

  /**
   * Setup with all installation parameters.
   * Tests the 6 new installation params added for vault parameter fixes.
   */
  async setupWithOptions(options: {
    datastorePath?: string;
    uid?: string;
    from?: 'apt-repo' | 'tar-static' | 'deb-local';
    dockerSource?: 'docker-repo' | 'package-manager' | 'snap' | 'manual';
    installAmdDriver?: 'auto' | 'true' | 'false';
    installNvidiaDriver?: 'auto' | 'true' | 'false';
    installCriu?: 'auto' | 'true' | 'false' | 'manual';
  }): Promise<ExecResult> {
    return this.testFunction({
      function: 'setup',
      datastorePath: options.datastorePath,
      uid: options.uid,
      installSource: options.from,
      dockerSource: options.dockerSource,
      installAmdDriver: options.installAmdDriver,
      installNvidiaDriver: options.installNvidiaDriver,
      installCriu: options.installCriu,
    });
  }

  async fixUserGroups(uid?: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'machine_fix_groups',
      uid,
    });
  }
}
