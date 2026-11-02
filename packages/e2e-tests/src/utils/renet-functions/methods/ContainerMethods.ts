import type { ExecResult, TestFunctionOptions } from '../types';

/**
 * Container management methods for RenetFunctionsTestRunner.
 */
export class ContainerMethods {
  constructor(private readonly testFunction: (opts: TestFunctionOptions) => Promise<ExecResult>) {}

  containerStart(
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

  containerStop(
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

  containerRestart(
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

  containerLogs(
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

  containerExec(
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

  containerInspect(
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

  containerStats(
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

  containerList(
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

  containerKill(
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

  containerPause(
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

  containerUnpause(
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
