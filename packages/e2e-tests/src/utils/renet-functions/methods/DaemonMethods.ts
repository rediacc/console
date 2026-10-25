import type { ExecResult, TestFunctionOptions } from '../types';

/**
 * Daemon management methods for RenetFunctionsTestRunner.
 */
export class DaemonMethods {
  constructor(private readonly testFunction: (opts: TestFunctionOptions) => Promise<ExecResult>) {}

  daemonSetup(networkId?: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'daemon_setup',
      networkId,
    });
  }

  daemonTeardown(networkId?: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'daemon_teardown',
      networkId,
    });
  }

  daemonStart(
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

  daemonStop(repository?: string, datastorePath?: string, networkId?: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'daemon_stop',
      repository,
      datastorePath,
      networkId,
    });
  }

  daemonStatus(
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

  daemonRestart(
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

  daemonLogs(repository?: string, datastorePath?: string, networkId?: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'daemon_logs',
      repository,
      datastorePath,
      networkId,
    });
  }

  renetStart(networkId?: string): Promise<ExecResult> {
    return this.testFunction({ function: 'daemon_start', networkId });
  }

  renetStop(networkId?: string): Promise<ExecResult> {
    return this.testFunction({ function: 'daemon_stop', networkId });
  }

  renetStatus(networkId?: string): Promise<ExecResult> {
    return this.testFunction({ function: 'daemon_status', networkId });
  }
}
