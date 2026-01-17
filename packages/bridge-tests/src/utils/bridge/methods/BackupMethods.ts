import type { VaultBuilder } from '../../vault/VaultBuilder';
import type { ExecResult, TestFunctionOptions } from '../types';

/**
 * Backup, checkpoint, and push/pull methods for BridgeTestRunner.
 */
export class BackupMethods {
  constructor(
    private readonly testFunction: (opts: TestFunctionOptions) => Promise<ExecResult>,
    private readonly testFunctionWithVault: (
      functionName: string,
      vault: VaultBuilder,
      timeout?: number
    ) => Promise<ExecResult>
  ) {}

  /**
   * Push repository to a destination machine.
   * Uses backup_push with destinationType=machine.
   */
  async push(repository: string, destMachine: string, datastorePath?: string): Promise<ExecResult> {
    return this.testFunction({
      function: 'backup_push',
      repository,
      destMachine,
      datastorePath,
      destinationType: 'machine',
    });
  }

  /**
   * Pull repository from a source machine.
   * Uses backup_pull with sourceType=machine.
   */
  async pull(
    repository: string,
    sourceMachine: string,
    datastorePath?: string
  ): Promise<ExecResult> {
    return this.testFunction({
      function: 'backup_pull',
      repository,
      sourceMachine,
      datastorePath,
      sourceType: 'machine',
    });
  }

  /**
   * Push repository with all available options.
   * Supports both machine and storage destinations.
   */
  async pushWithOptions(
    repository: string,
    options: {
      destinationType?: 'machine' | 'storage';
      to?: string;
      machines?: string[];
      storages?: string[];
      dest?: string;
      tag?: string;
      state?: 'online' | 'offline';
      checkpoint?: boolean;
      override?: boolean;
      grand?: string;
      datastorePath?: string;
      destMachine?: string;
    }
  ): Promise<ExecResult> {
    return this.testFunction({
      function: 'backup_push',
      repository,
      ...options,
    });
  }

  /**
   * Pull repository with all available options.
   * Supports both machine and storage sources.
   */
  async pullWithOptions(
    repository: string,
    options: {
      sourceType?: 'machine' | 'storage';
      from?: string;
      grand?: string;
      datastorePath?: string;
      sourceMachine?: string;
    }
  ): Promise<ExecResult> {
    return this.testFunction({
      function: 'backup_pull',
      repository,
      ...options,
    });
  }

  /**
   * Backup repository to storage.
   * Uses backup_push with destinationType=storage.
   * @deprecated Legacy wrapper - use pushWithOptions() directly
   */
  async backup(
    repository: string,
    datastorePath?: string,
    storageName?: string
  ): Promise<ExecResult> {
    return this.testFunction({
      function: 'backup_push',
      repository,
      datastorePath,
      destinationType: 'storage',
      to: storageName,
    });
  }

  /**
   * Deploy repository to a machine.
   * Uses backup_push with destinationType=machine.
   * @deprecated Legacy wrapper - use pushWithOptions() directly
   */
  async deploy(
    repository: string,
    destMachine: string,
    datastorePath?: string
  ): Promise<ExecResult> {
    return this.testFunction({
      function: 'backup_push',
      repository,
      destMachine,
      datastorePath,
      destinationType: 'machine',
    });
  }

  async checkpointCreate(
    repository: string,
    checkpointName: string,
    datastorePath?: string,
    networkId?: string | number
  ): Promise<ExecResult> {
    return this.testFunction({
      function: 'checkpoint_create',
      repository,
      checkpointName,
      datastorePath,
      networkId: networkId === undefined ? undefined : String(networkId),
    });
  }

  async checkpointRestore(
    repository: string,
    checkpointName: string,
    datastorePath?: string,
    networkId?: string | number
  ): Promise<ExecResult> {
    return this.testFunction({
      function: 'checkpoint_restore',
      repository,
      checkpointName,
      datastorePath,
      networkId: networkId === undefined ? undefined : String(networkId),
    });
  }

  /**
   * Push repository with full vault configuration.
   * Enables testing ALL backup_push parameters including:
   * - destinationType (machine/storage)
   * - machines array (parallel deployment)
   * - storages array (parallel backup)
   * - tag, state, checkpoint, override, grand
   */
  async pushWithVault(vault: VaultBuilder, timeout?: number): Promise<ExecResult> {
    return this.testFunctionWithVault('backup_push', vault, timeout);
  }

  /**
   * Pull repository with full vault configuration.
   * Enables testing ALL backup_pull parameters including:
   * - sourceType (machine/storage)
   * - from (source selection)
   * - grand (CoW pre-seeding)
   */
  async pullWithVault(vault: VaultBuilder, timeout?: number): Promise<ExecResult> {
    return this.testFunctionWithVault('backup_pull', vault, timeout);
  }
}
