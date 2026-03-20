import type { QueueVaultV2 } from '@rediacc/shared/queue-vault';
/**
 * Storage configuration for S3-compatible backends.
 * Used as input for withStorage() - converted to StorageSection internally.
 */
export interface StorageConfig {
    name: string;
    type: 's3' | 'b2' | 'azure' | 'gcs' | 'sftp';
    endpoint?: string;
    bucket: string;
    accessKey?: string;
    secretKey?: string;
    region?: string;
    folder?: string;
}
/**
 * Push function parameters.
 */
export interface PushParams {
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
}
/**
 * Pull function parameters.
 */
export interface PullParams {
    sourceType?: 'machine' | 'storage';
    from?: string;
    grand?: string;
}
/**
 * Builder for constructing vault JSON for E2E testing.
 * Simulates middleware vault construction without requiring middleware.
 *
 * @example
 * ```ts
 * const vault = new VaultBuilder()
 *   .withFunction('backup_push')
 *   .withTeam('Private Team')
 *   .withRepository('repo-guid', 'repo-name')
 *   .withMachine('192.168.111.11', 'muhammed', '/mnt/rediacc')
 *   .withPushParams({ destinationType: 'storage', dest: 'backup.tar' })
 *   .build();
 * ```
 */
export declare class VaultBuilder {
    private readonly vault;
    constructor();
    /**
     * Set the function name.
     */
    withFunction(name: string): this;
    /**
     * Set the team name.
     */
    withTeam(name: string): this;
    /**
     * Set the repository information.
     */
    withRepository(guid: string, name: string, networkId?: number): this;
    /**
     * Set the primary machine configuration.
     */
    withMachine(ip: string, user: string, datastore?: string, port?: number): this;
    /**
     * Set the destination machine for push operations.
     */
    withDestinationMachine(ip: string, user: string, datastore?: string): this;
    /**
     * Set the source machine for pull operations.
     */
    withSourceMachine(ip: string, user: string): this;
    /**
     * Set SSH credentials.
     */
    withSSHKey(privateKey: string, publicKey?: string): this;
    /**
     * Set SSH password.
     */
    withSSHPassword(password: string): this;
    /**
     * Add a storage system configuration.
     */
    withStorage(config: StorageConfig): this;
    /**
     * Add multiple storage system configurations.
     */
    withStorages(configs: StorageConfig[]): this;
    /**
     * Set backup_push specific parameters.
     */
    withPushParams(params: PushParams): this;
    private setPushStringParams;
    private setPushBooleanParams;
    private setPushArrayParams;
    /**
     * Set backup_pull specific parameters.
     */
    withPullParams(params: PullParams): this;
    /**
     * Set custom parameters.
     */
    withParams(params: Record<string, string | number | boolean>): this;
    /**
     * Set the datastore path.
     */
    withDatastore(path: string): this;
    /**
     * Build and return the vault object.
     */
    build(): QueueVaultV2;
    /**
     * Build and return the vault as JSON string.
     */
    toJSON(): string;
    /**
     * Build and write the vault to a file.
     * Returns the path to the created file.
     */
    toFile(filePath?: string): Promise<string>;
    /**
     * Create a VaultBuilder pre-configured for backup_push.
     */
    static forPush(): VaultBuilder;
    /**
     * Create a VaultBuilder pre-configured for backup_pull.
     */
    static forPull(): VaultBuilder;
    /**
     * Create a VaultBuilder pre-configured for checkpoint_create.
     */
    static forCheckpointCreate(): VaultBuilder;
    /**
     * Create a VaultBuilder pre-configured for checkpoint_restore.
     */
    static forCheckpointRestore(): VaultBuilder;
}
//# sourceMappingURL=VaultBuilder.d.ts.map