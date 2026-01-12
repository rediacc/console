import type { ExecResult, TestFunctionOptions } from '../types';

/**
 * Container management methods for BridgeTestRunner.
 */
export class ContainerMethods {
  constructor(private readonly testFunction: (opts: TestFunctionOptions) => Promise<ExecResult>) {}

  async containerStart(
    name: string,
    repository?: string,
    datastorePath?: string,
    networkId?: string
  ): Promise<ExecResult> {
    return this.testFunction({
      function: 'container_start',
      container: name,
      repository,
      datastorePath,
      networkId,
    });
  }

  async containerStop(
    name: string,
    repository?: string,
    datastorePath?: string,
    networkId?: string
  ): Promise<ExecResult> {
    return this.testFunction({
      function: 'container_stop',
      container: name,
      repository,
      datastorePath,
      networkId,
    });
  }

  async containerRestart(
    name: string,
    repository?: string,
    datastorePath?: string,
    networkId?: string
  ): Promise<ExecResult> {
    return this.testFunction({
      function: 'container_restart',
      container: name,
      repository,
      datastorePath,
      networkId,
    });
  }

  async containerLogs(
    name: string,
    repository?: string,
    datastorePath?: string,
    networkId?: string
  ): Promise<ExecResult> {
    return this.testFunction({
      function: 'container_logs',
      container: name,
      repository,
      datastorePath,
      networkId,
    });
  }

  async containerExec(
    name: string,
    command: string,
    repository?: string,
    datastorePath?: string,
    networkId?: string
  ): Promise<ExecResult> {
    return this.testFunction({
      function: 'container_exec',
      container: name,
      command,
      repository,
      datastorePath,
      networkId,
    });
  }

  async containerInspect(
    name: string,
    repository?: string,
    datastorePath?: string,
    networkId?: string
  ): Promise<ExecResult> {
    return this.testFunction({
      function: 'container_inspect',
      container: name,
      repository,
      datastorePath,
      networkId,
    });
  }

  async containerStats(
    name: string,
    repository?: string,
    datastorePath?: string,
    networkId?: string
  ): Promise<ExecResult> {
    return this.testFunction({
      function: 'container_stats',
      container: name,
      repository,
      datastorePath,
      networkId,
    });
  }

  async containerList(
    repository?: string,
    datastorePath?: string,
    networkId?: string
  ): Promise<ExecResult> {
    return this.testFunction({
      function: 'container_list',
      repository,
      datastorePath,
      networkId,
    });
  }

  async containerKill(
    name: string,
    repository?: string,
    datastorePath?: string,
    networkId?: string
  ): Promise<ExecResult> {
    return this.testFunction({
      function: 'container_kill',
      container: name,
      repository,
      datastorePath,
      networkId,
    });
  }

  async containerPause(
    name: string,
    repository?: string,
    datastorePath?: string,
    networkId?: string
  ): Promise<ExecResult> {
    return this.testFunction({
      function: 'container_pause',
      container: name,
      repository,
      datastorePath,
      networkId,
    });
  }

  async containerUnpause(
    name: string,
    repository?: string,
    datastorePath?: string,
    networkId?: string
  ): Promise<ExecResult> {
    return this.testFunction({
      function: 'container_unpause',
      container: name,
      repository,
      datastorePath,
      networkId,
    });
  }
}
