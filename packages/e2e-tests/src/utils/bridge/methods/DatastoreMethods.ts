import type { ExecResult, TestFunctionOptions } from '../types';

/**
 * Datastore management methods for BridgeTestRunner.
 */
export class DatastoreMethods {
  constructor(private readonly testFunction: (opts: TestFunctionOptions) => Promise<ExecResult>) {}

  async datastoreInit(size: string, datastorePath?: string, force?: boolean): Promise<ExecResult> {
    return this.testFunction({
      function: 'datastore_init',
      size,
      datastorePath,
      force,
    });
  }

  async datastoreMount(datastorePath?: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'datastore_mount',
      datastorePath,
    });
  }

  async datastoreUnmount(datastorePath?: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'datastore_unmount',
      datastorePath,
    });
  }

  async datastoreExpand(newSize: string, datastorePath?: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'datastore_expand',
      newSize,
      datastorePath,
    });
  }

  async datastoreResize(newSize: string, datastorePath?: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'datastore_resize',
      newSize,
      datastorePath,
    });
  }

  async datastoreValidate(datastorePath?: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'datastore_validate',
      datastorePath,
    });
  }
}
