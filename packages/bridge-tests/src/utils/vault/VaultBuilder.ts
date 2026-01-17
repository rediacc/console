// Import queue-vault types from shared package
import * as fs from 'node:fs/promises';
import * as path from 'node:path';
import type { QueueVaultV2 } from '@rediacc/shared/queue-vault';
// Re-export for convenience

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
export class VaultBuilder {
  private readonly vault: QueueVaultV2;

  constructor() {
    this.vault = {
      $schema: 'queue-vault-v2',
      version: '2.0',
      task: {
        function: '',
        machine: '',
        team: '',
      },
      ssh: {
        private_key: '',
        public_key: '',
      },
      machine: {
        ip: '',
        user: '',
      },
    };
  }

  /**
   * Set the function name.
   */
  withFunction(name: string): this {
    this.vault.task.function = name;
    return this;
  }

  /**
   * Set the team name.
   */
  withTeam(name: string): this {
    this.vault.task.team = name;
    return this;
  }

  /**
   * Set the repository information.
   */
  withRepository(guid: string, name: string, networkId?: number): this {
    this.vault.task.repository = name;
    this.vault.repositories ??= {};
    this.vault.repositories[name] = {
      guid,
      name,
      network_id: networkId,
    };
    // Also add to params
    this.vault.params ??= {};
    this.vault.params.repository = guid;
    this.vault.params.repositoryName = name;
    return this;
  }

  /**
   * Set the primary machine configuration.
   */
  withMachine(ip: string, user: string, datastore?: string, port?: number): this {
    this.vault.task.machine = ip;
    this.vault.machine = {
      ip,
      user,
      port: port ?? 22,
      datastore,
    };
    return this;
  }

  /**
   * Set the destination machine for push operations.
   */
  withDestinationMachine(ip: string, user: string, datastore?: string): this {
    this.vault.extra_machines ??= {};
    this.vault.extra_machines.destination = {
      ip,
      user,
      port: 22,
      datastore,
    };
    // Also set dest_machine param for backup_push
    this.vault.params ??= {};
    this.vault.params.dest_machine = ip;
    return this;
  }

  /**
   * Set the source machine for pull operations.
   */
  withSourceMachine(ip: string, user: string): this {
    this.vault.extra_machines ??= {};
    this.vault.extra_machines.source = {
      ip,
      user,
      port: 22,
    };
    // Also set source_machine param for backup_pull
    this.vault.params ??= {};
    this.vault.params.source_machine = ip;
    return this;
  }

  /**
   * Set SSH credentials.
   */
  withSSHKey(privateKey: string, publicKey?: string): this {
    this.vault.ssh.private_key = Buffer.from(privateKey).toString('base64');
    this.vault.ssh.public_key = publicKey ? Buffer.from(publicKey).toString('base64') : '';
    return this;
  }

  /**
   * Set SSH password.
   */
  withSSHPassword(password: string): this {
    this.vault.ssh.password = password;
    return this;
  }

  /**
   * Add a storage system configuration.
   */
  withStorage(config: StorageConfig): this {
    this.vault.storage_systems ??= {};
    this.vault.storage_systems[config.name] = {
      backend: config.type,
      bucket: config.bucket,
      region: config.region,
      folder: config.folder,
      parameters: {
        endpoint: config.endpoint,
        access_key_id: config.accessKey,
        secret_access_key: config.secretKey,
      },
    };
    return this;
  }

  /**
   * Add multiple storage system configurations.
   */
  withStorages(configs: StorageConfig[]): this {
    for (const config of configs) {
      this.withStorage(config);
    }
    return this;
  }

  /**
   * Set backup_push specific parameters.
   */
  withPushParams(params: PushParams): this {
    this.vault.params ??= {};

    this.setPushStringParams(params);
    this.setPushBooleanParams(params);
    this.setPushArrayParams(params);

    return this;
  }

  private setPushStringParams(params: PushParams): void {
    if (params.destinationType) {
      this.vault.params!.destinationType = params.destinationType;
    }
    if (params.to) {
      this.vault.params!.to = params.to;
    }
    if (params.dest) {
      this.vault.params!.dest = params.dest;
    }
    if (params.tag) {
      this.vault.params!.tag = params.tag;
    }
    if (params.state) {
      this.vault.params!.state = params.state;
    }
    if (params.grand) {
      this.vault.params!.grand = params.grand;
    }
  }

  private setPushBooleanParams(params: PushParams): void {
    if (params.checkpoint !== undefined) {
      this.vault.params!.checkpoint = params.checkpoint;
    }
    if (params.override !== undefined) {
      this.vault.params!.override = params.override;
    }
  }

  private setPushArrayParams(params: PushParams): void {
    if (params.machines && params.machines.length > 0) {
      this.vault.params!.machines = params.machines.join(',');
    }
    if (params.storages && params.storages.length > 0) {
      this.vault.params!.storages = params.storages.join(',');
    }
  }

  /**
   * Set backup_pull specific parameters.
   */
  withPullParams(params: PullParams): this {
    this.vault.params ??= {};
    if (params.sourceType) {
      this.vault.params.sourceType = params.sourceType;
    }
    if (params.from) {
      this.vault.params.from = params.from;
    }
    if (params.grand) {
      this.vault.params.grand = params.grand;
    }
    return this;
  }

  /**
   * Set custom parameters.
   */
  withParams(params: Record<string, string | number | boolean>): this {
    this.vault.params ??= {};
    Object.assign(this.vault.params, params);
    return this;
  }

  /**
   * Set the datastore path.
   */
  withDatastore(path: string): this {
    this.vault.machine.datastore = path;
    this.vault.params ??= {};
    this.vault.params.datastore_path = path;
    return this;
  }

  /**
   * Build and return the vault object.
   */
  build(): QueueVaultV2 {
    return { ...this.vault };
  }

  /**
   * Build and return the vault as JSON string.
   */
  toJSON(): string {
    return JSON.stringify(this.vault, null, 2);
  }

  /**
   * Build and write the vault to a file.
   * Returns the path to the created file.
   */
  async toFile(filePath?: string): Promise<string> {
    const targetPath = filePath ?? `/tmp/vault-${Date.now()}.json`;
    await fs.mkdir(path.dirname(targetPath), { recursive: true });
    await fs.writeFile(targetPath, this.toJSON(), 'utf-8');
    return targetPath;
  }

  /**
   * Create a VaultBuilder pre-configured for backup_push.
   */
  static forPush(): VaultBuilder {
    return new VaultBuilder().withFunction('backup_push');
  }

  /**
   * Create a VaultBuilder pre-configured for backup_pull.
   */
  static forPull(): VaultBuilder {
    return new VaultBuilder().withFunction('backup_pull');
  }

  /**
   * Create a VaultBuilder pre-configured for checkpoint_create.
   */
  static forCheckpointCreate(): VaultBuilder {
    return new VaultBuilder().withFunction('checkpoint_create');
  }

  /**
   * Create a VaultBuilder pre-configured for checkpoint_restore.
   */
  static forCheckpointRestore(): VaultBuilder {
    return new VaultBuilder().withFunction('checkpoint_restore');
  }
}
