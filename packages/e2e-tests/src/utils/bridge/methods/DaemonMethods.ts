import type { ExecResult, TestFunctionOptions } from '../types';

/**
 * Daemon management methods for BridgeTestRunner.
 */
export class DaemonMethods {
  constructor(private readonly testFunction: (opts: TestFunctionOptions) => Promise<ExecResult>) {}

  async daemonSetup(networkId?: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'daemon_setup',
      networkId,
    });
  }

  async daemonTeardown(networkId?: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'daemon_teardown',
      networkId,
    });
  }

  async daemonStart(
    repository?: string,
    datastorePath?: string,
    networkId?: string
  ): Promise<ExecResult> {
    return this.testFunction({
      function: 'daemon_start',
      repository,
      datastorePath,
      networkId,
    });
  }

  async daemonStop(
    repository?: string,
    datastorePath?: string,
    networkId?: string
  ): Promise<ExecResult> {
    return this.testFunction({
      function: 'daemon_stop',
      repository,
      datastorePath,
      networkId,
    });
  }

  async daemonStatus(
    repository?: string,
    datastorePath?: string,
    networkId?: string
  ): Promise<ExecResult> {
    return this.testFunction({
      function: 'daemon_status',
      repository,
      datastorePath,
      networkId,
    });
  }

  async daemonRestart(
    repository?: string,
    datastorePath?: string,
    networkId?: string
  ): Promise<ExecResult> {
    return this.testFunction({
      function: 'daemon_restart',
      repository,
      datastorePath,
      networkId,
    });
  }

  async daemonLogs(
    repository?: string,
    datastorePath?: string,
    networkId?: string
  ): Promise<ExecResult> {
    return this.testFunction({
      function: 'daemon_logs',
      repository,
      datastorePath,
      networkId,
    });
  }

  async renetStart(networkId?: string): Promise<ExecResult> {
    return this.testFunction({ function: 'daemon_start', networkId });
  }

  async renetStop(networkId?: string): Promise<ExecResult> {
    return this.testFunction({ function: 'daemon_stop', networkId });
  }

  async renetStatus(networkId?: string): Promise<ExecResult> {
    return this.testFunction({ function: 'daemon_status', networkId });
  }
}
