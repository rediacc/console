/**
 * ResourceState interface and LocalResourceState implementation.
 *
 * ResourceState abstracts access to machines, storages, repositories, and SSH keys.
 * LocalResourceState wraps config file reads/writes with optional AES-256-GCM encryption.
 * When encrypted, all resource data is stored as a single blob in RdcConfig.encryptedResources.
 */

import { configFileStorage } from '../adapters/config-file-storage.js';
import { nodeCryptoProvider } from '../adapters/crypto.js';
import type { RemoteConfigAdapter } from '../adapters/remote-config-adapter.js';
import type {
  ArchivedRepository,
  MachineConfig,
  RdcConfig,
  RepositoryConfig,
  SSHContent,
  StorageConfig,
} from '../types/index.js';

// =============================================================================
// Encryption Helpers
// =============================================================================

export async function encryptSection(data: unknown, password: string): Promise<string> {
  const json = JSON.stringify(data);
  return nodeCryptoProvider.encrypt(json, password);
}

export async function decryptSection<T>(encrypted: string, password: string): Promise<T> {
  const json = await nodeCryptoProvider.decrypt(encrypted, password);
  return JSON.parse(json) as T;
}

// =============================================================================
// ResourceState Interface
// =============================================================================

export interface ResourceState {
  getMachines(): Record<string, MachineConfig>;
  setMachines(machines: Record<string, MachineConfig>): Promise<void>;
  getStorages(): Record<string, StorageConfig>;
  setStorages(storages: Record<string, StorageConfig>): Promise<void>;
  getRepositories(): Record<string, RepositoryConfig>;
  setRepositories(repos: Record<string, RepositoryConfig>): Promise<void>;
  getDeletedRepositories(): ArchivedRepository[];
  setDeletedRepositories(repos: ArchivedRepository[]): Promise<void>;
  getSSH(): SSHContent | null;
  setSSH(ssh: SSHContent): Promise<void>;
}

// =============================================================================
// LocalResourceState
// =============================================================================

interface LocalState {
  machines: Record<string, MachineConfig>;
  storages: Record<string, StorageConfig>;
  repositories: Record<string, RepositoryConfig>;
  deletedRepositories: ArchivedRepository[];
  sshContent: SSHContent | null;
}

/**
 * ResourceState implementation backed by config.json.
 * Supports optional AES-256-GCM encryption via masterPassword.
 */
export class LocalResourceState implements ResourceState {
  private readonly configName: string;
  private readonly masterPassword: string | null;
  private readonly state: LocalState;

  private constructor(configName: string, masterPassword: string | null, state: LocalState) {
    this.configName = configName;
    this.masterPassword = masterPassword;
    this.state = state;
  }

  /**
   * Load resource state from an RdcConfig.
   * If encrypted, decrypts the encryptedResources blob.
   * If unencrypted, reads from inline config fields.
   */
  static async load(
    config: RdcConfig,
    configName: string,
    masterPassword: string | null
  ): Promise<LocalResourceState> {
    let state: LocalState;

    if (config.encrypted && config.encryptedResources && masterPassword) {
      // Encrypted mode: decrypt the single blob
      const decrypted = await decryptSection<{
        machines: Record<string, MachineConfig>;
        storages: Record<string, StorageConfig>;
        repositories: Record<string, RepositoryConfig>;
        deletedRepositories?: ArchivedRepository[];
        sshContent?: SSHContent | null;
      }>(config.encryptedResources, masterPassword);

      state = {
        machines: decrypted.machines,
        storages: decrypted.storages,
        repositories: decrypted.repositories,
        deletedRepositories: decrypted.deletedRepositories ?? [],
        sshContent: decrypted.sshContent ?? null,
      };
    } else {
      // Unencrypted mode: read directly from config fields
      state = {
        machines: config.machines ?? {},
        storages: config.storages ?? {},
        repositories: config.repositories ?? {},
        deletedRepositories: config.deletedRepositories ?? [],
        sshContent: config.sshContent ?? null,
      };
    }

    return new LocalResourceState(configName, masterPassword, state);
  }

  // ===========================================================================
  // Getters (return cached in-memory data)
  // ===========================================================================

  getMachines(): Record<string, MachineConfig> {
    return this.state.machines;
  }

  getStorages(): Record<string, StorageConfig> {
    return this.state.storages;
  }

  getRepositories(): Record<string, RepositoryConfig> {
    return this.state.repositories;
  }

  getDeletedRepositories(): ArchivedRepository[] {
    return this.state.deletedRepositories;
  }

  getSSH(): SSHContent | null {
    return this.state.sshContent;
  }

  // ===========================================================================
  // Setters (update in-memory cache + persist to config.json)
  // ===========================================================================

  async setMachines(machines: Record<string, MachineConfig>): Promise<void> {
    this.state.machines = machines;
    await this.persist();
  }

  async setStorages(storages: Record<string, StorageConfig>): Promise<void> {
    this.state.storages = storages;
    await this.persist();
  }

  async setRepositories(repos: Record<string, RepositoryConfig>): Promise<void> {
    this.state.repositories = repos;
    await this.persist();
  }

  async setDeletedRepositories(repos: ArchivedRepository[]): Promise<void> {
    this.state.deletedRepositories = repos;
    await this.persist();
  }

  async setSSH(ssh: SSHContent): Promise<void> {
    this.state.sshContent = ssh;
    await this.persist();
  }

  // ===========================================================================
  // Persistence
  // ===========================================================================

  private async persist(): Promise<void> {
    const configName = this.configName;

    if (this.masterPassword) {
      // Encrypted: store all sections as a single encrypted blob
      const blob = await encryptSection(
        {
          machines: this.state.machines,
          storages: this.state.storages,
          repositories: this.state.repositories,
          deletedRepositories: this.state.deletedRepositories,
          sshContent: this.state.sshContent,
        },
        this.masterPassword
      );

      await configFileStorage.update(configName, (cfg) => ({
        ...cfg,
        encrypted: true,
        encryptedResources: blob,
        machines: undefined,
        storages: undefined,
        repositories: undefined,
        sshContent: undefined,
      }));
    } else {
      // Unencrypted: store sections directly on the config
      await configFileStorage.update(configName, (cfg) => ({
        ...cfg,
        machines: this.state.machines,
        storages: this.state.storages,
        repositories: this.state.repositories,
        deletedRepositories:
          this.state.deletedRepositories.length > 0 ? this.state.deletedRepositories : undefined,
        sshContent: this.state.sshContent ?? undefined,
        encrypted: undefined,
        encryptedResources: undefined,
      }));
    }
  }
}

// =============================================================================
// RemoteResourceState
// =============================================================================

/**
 * ResourceState implementation backed by remote encrypted config storage.
 * Mutations trigger an encrypted push to the account server via RemoteConfigAdapter.
 */
export class RemoteResourceState implements ResourceState {
  private readonly adapter: RemoteConfigAdapter;
  private readonly configName: string;
  private version: number;
  private readonly sdkEpoch: number;
  private readonly state: LocalState;
  private readonly configId: string;

  private constructor(
    adapter: RemoteConfigAdapter,
    configName: string,
    version: number,
    sdkEpoch: number,
    state: LocalState,
    configId: string
  ) {
    this.adapter = adapter;
    this.configName = configName;
    this.version = version;
    this.sdkEpoch = sdkEpoch;
    this.state = state;
    this.configId = configId;
  }

  /**
   * Load resource state from a remote-pulled RdcConfig.
   * The config is already decrypted by the adapter.
   */
  static load(
    config: RdcConfig,
    configName: string,
    adapter: RemoteConfigAdapter,
    version: number,
    sdkEpoch: number
  ): RemoteResourceState {
    const state: LocalState = {
      machines: config.machines ?? {},
      storages: config.storages ?? {},
      repositories: config.repositories ?? {},
      deletedRepositories: config.deletedRepositories ?? [],
      sshContent: config.sshContent ?? null,
    };
    return new RemoteResourceState(adapter, configName, version, sdkEpoch, state, config.id);
  }

  // ===========================================================================
  // Getters (return cached in-memory data)
  // ===========================================================================

  getMachines(): Record<string, MachineConfig> {
    return this.state.machines;
  }

  getStorages(): Record<string, StorageConfig> {
    return this.state.storages;
  }

  getRepositories(): Record<string, RepositoryConfig> {
    return this.state.repositories;
  }

  getDeletedRepositories(): ArchivedRepository[] {
    return this.state.deletedRepositories;
  }

  getSSH(): SSHContent | null {
    return this.state.sshContent;
  }

  // ===========================================================================
  // Setters (update in-memory cache + push to remote)
  // ===========================================================================

  async setMachines(machines: Record<string, MachineConfig>): Promise<void> {
    this.state.machines = machines;
    await this.persist();
  }

  async setStorages(storages: Record<string, StorageConfig>): Promise<void> {
    this.state.storages = storages;
    await this.persist();
  }

  async setRepositories(repos: Record<string, RepositoryConfig>): Promise<void> {
    this.state.repositories = repos;
    await this.persist();
  }

  async setDeletedRepositories(repos: ArchivedRepository[]): Promise<void> {
    this.state.deletedRepositories = repos;
    await this.persist();
  }

  async setSSH(ssh: SSHContent): Promise<void> {
    this.state.sshContent = ssh;
    await this.persist();
  }

  // ===========================================================================
  // Persistence (push encrypted config to remote server)
  // ===========================================================================

  private async persist(): Promise<void> {
    const fullConfig: RdcConfig = {
      id: this.configId,
      version: this.version,
      machines: this.state.machines,
      storages: this.state.storages,
      repositories: this.state.repositories,
      deletedRepositories:
        this.state.deletedRepositories.length > 0 ? this.state.deletedRepositories : undefined,
      sshContent: this.state.sshContent ?? undefined,
    };

    const result = await this.adapter.push(fullConfig, this.version);
    this.version = result.version;
  }
}
