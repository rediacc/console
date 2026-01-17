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

  /**
   * Repository up with prep-only option.
   * Prepares the repository without starting services.
   */
  async repositoryUpPrepOnly(
    name: string,
    datastorePath?: string,
    networkId?: string
  ): Promise<ExecResult> {
    return this.testFunction({
      function: 'repository_up',
      repository: name,
      datastorePath,
      networkId,
      prepOnly: true,
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
}
