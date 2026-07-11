import type { ExecResult, TestFunctionOptions } from '../types';

/**
 * Repository management methods for BridgeTestRunner.
 */
export class RepositoryMethods {
  constructor(private readonly testFunction: (opts: TestFunctionOptions) => Promise<ExecResult>) {}

  async repositoryNew(
    name: string,
    size: string,
    password?: string,
    datastorePath?: string
  ): Promise<ExecResult> {
    return this.testFunction({
      function: 'repository_create',
      repository: name,
      size,
      password,
      datastorePath,
    });
  }

  async repositoryRm(name: string, datastorePath?: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'repository_delete',
      repository: name,
      datastorePath,
    });
  }

  async repositoryMount(
    name: string,
    password?: string,
    datastorePath?: string
  ): Promise<ExecResult> {
    return this.testFunction({
      function: 'repository_mount',
      repository: name,
      password,
      datastorePath,
    });
  }

  async repositoryUnmount(name: string, datastorePath?: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'repository_unmount',
      repository: name,
      datastorePath,
    });
  }

  async repositoryUp(
    name: string,
    datastorePath?: string,
    networkId?: string
  ): Promise<ExecResult> {
    return this.testFunction({
      function: 'repository_up',
      repository: name,
      datastorePath,
      networkId,
    });
  }

  async repositoryDown(
    name: string,
    datastorePath?: string,
    networkId?: string
  ): Promise<ExecResult> {
    return this.testFunction({
      function: 'repository_down',
      repository: name,
      datastorePath,
      networkId,
    });
  }

  async repositoryList(datastorePath?: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'repository_list',
      datastorePath,
    });
  }

  async repositoryResize(
    name: string,
    newSize: string,
    password?: string,
    datastorePath?: string
  ): Promise<ExecResult> {
    return this.testFunction({
      function: 'repository_resize',
      repository: name,
      newSize,
      password,
      datastorePath,
    });
  }

  async repositoryInfo(name: string, datastorePath?: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'repository_info',
      repository: name,
      datastorePath,
    });
  }

  async repositoryStatus(name: string, datastorePath?: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'repository_status',
      repository: name,
      datastorePath,
    });
  }

  async repositoryValidate(name: string, datastorePath?: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'repository_validate',
      repository: name,
      datastorePath,
    });
  }

  async repositoryGrow(
    name: string,
    newSize: string,
    password?: string,
    datastorePath?: string
  ): Promise<ExecResult> {
    return this.testFunction({
      function: 'repository_expand',
      repository: name,
      newSize,
      password,
      datastorePath,
    });
  }

  // Runtime-generic verbs (spec 01 §4.3 / 03 §5.4): the same function dispatches
  // to the docker per-repo dockerd or the kube namespace based on the repo's
  // datastore placement. Exercised on docker repos here; the kube arm rides the
  // cluster suite live-run.

  async repositoryHealth(name: string, datastorePath?: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'repository_health',
      repository: name,
      datastorePath,
    });
  }

  async repositoryLogs(
    name: string,
    opts: { container?: string; lines?: string; datastorePath?: string } = {}
  ): Promise<ExecResult> {
    return this.testFunction({
      function: 'repository_logs',
      repository: name,
      container: opts.container,
      lines: opts.lines,
      datastorePath: opts.datastorePath,
    });
  }

  async repositoryExec(
    name: string,
    command: string,
    opts: { container?: string; datastorePath?: string } = {}
  ): Promise<ExecResult> {
    return this.testFunction({
      function: 'repository_exec',
      repository: name,
      command,
      container: opts.container,
      datastorePath: opts.datastorePath,
    });
  }

  // repository_promote (formerly repository_takeover): swap a fork's LUKS image
  // over its grand so the fork's data becomes the grand's (spec 06 §2).
  async repositoryPromote(
    parent: string,
    fork: string,
    datastorePath?: string
  ): Promise<ExecResult> {
    return this.testFunction({
      function: 'repository_promote',
      parent,
      fork,
      datastorePath,
    });
  }
}
