import type { VaultBuilder } from '../../vault/VaultBuilder';
import type { ExecResult, TestFunctionOptions } from '../types';
/**
 * Backup, checkpoint, and push/pull methods for BridgeTestRunner.
 */
export declare class BackupMethods {
    private readonly testFunction;
    private readonly testFunctionWithVault;
    constructor(testFunction: (opts: TestFunctionOptions) => Promise<ExecResult>, testFunctionWithVault: (functionName: string, vault: VaultBuilder, timeout?: number) => Promise<ExecResult>);
    /**
     * Push repository to a destination machine.
     * Uses backup_push with destinationType=machine.
     */
    push(repository: string, destMachine: string, datastorePath?: string): Promise<ExecResult>;
    /**
     * Pull repository from a source machine.
     * Uses backup_pull with sourceType=machine.
     */
    pull(repository: string, sourceMachine: string, datastorePath?: string): Promise<ExecResult>;
    /**
     * Push repository with all available options.
     * Supports both machine and storage destinations.
     */
    pushWithOptions(repository: string, options: {
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
    }): Promise<ExecResult>;
    /**
     * Pull repository with all available options.
     * Supports both machine and storage sources.
     */
    pullWithOptions(repository: string, options: {
        sourceType?: 'machine' | 'storage';
        from?: string;
        grand?: string;
        datastorePath?: string;
        sourceMachine?: string;
    }): Promise<ExecResult>;
    /**
     * Backup repository to storage.
     * Uses backup_push with destinationType=storage.
     * @deprecated Legacy wrapper - use pushWithOptions() directly
     */
    backup(repository: string, datastorePath?: string, storageName?: string): Promise<ExecResult>;
    /**
     * Deploy repository to a machine.
     * Uses backup_push with destinationType=machine.
     * @deprecated Legacy wrapper - use pushWithOptions() directly
     */
    deploy(repository: string, destMachine: string, datastorePath?: string): Promise<ExecResult>;
    checkpointCreate(repository: string, checkpointName: string, datastorePath?: string, networkId?: string | number): Promise<ExecResult>;
    checkpointRestore(repository: string, checkpointName: string, datastorePath?: string, networkId?: string | number): Promise<ExecResult>;
    /**
     * Push repository with full vault configuration.
     * Enables testing ALL backup_push parameters including:
     * - destinationType (machine/storage)
     * - machines array (parallel deployment)
     * - storages array (parallel backup)
     * - tag, state, checkpoint, override, grand
     */
    pushWithVault(vault: VaultBuilder, timeout?: number): Promise<ExecResult>;
    /**
     * Pull repository with full vault configuration.
     * Enables testing ALL backup_pull parameters including:
     * - sourceType (machine/storage)
     * - from (source selection)
     * - grand (CoW pre-seeding)
     */
    pullWithVault(vault: VaultBuilder, timeout?: number): Promise<ExecResult>;
}
//# sourceMappingURL=BackupMethods.d.ts.map
