/**
 * ResourceState interface and LocalResourceState implementation.
 *
 * ResourceState abstracts access to machines, storages, repositories, and SSH keys.
 * Storage shape (v2): resources are nested under `config.resources.*` and SSH is
 * at `config.credentials.ssh`. Encryption-at-rest is per-field (see Step 13) —
 * when `config.encryption.mode === 'master-password'` is set, sensitive values
 * are replaced by encrypted blob pointers in `config.encryption.encryptedFields`.
 */

import { DEFAULTS } from '@rediacc/shared/config';
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
 * Blob used when encryption-at-rest is active. The `encrypted` field holds the
 * AES-GCM ciphertext of the JSON-serialized combined resources (machines,
 * storages, repositories, sshContent). On v2, this lives under
 * `config.encryption.encryptedFields['/resources']` as a single compound blob
 * for simplicity; per-individual-field encryption is a future evolution.
 */
const RESOURCES_BLOB_POINTER = '/resources';

export class LocalResourceState implements ResourceState {
  private readonly configName: string;
  private readonly masterPassword: string | null;
  private readonly state: LocalState;

  private constructor(configName: string, masterPassword: string | null, state: LocalState) {
    this.configName = configName;
    this.masterPassword = masterPassword;
    this.state = state;
  }

  static async load(
    config: RdcConfig,
    configName: string,
    masterPassword: string | null
  ): Promise<LocalResourceState> {
    let state: LocalState;

    const encryptionMode = config.encryption?.mode ?? DEFAULTS.CONTEXT.CONFIG_KIND;
    const encryptedBlob =
      encryptionMode === 'master-password'
        ? config.encryption?.encryptedFields?.[RESOURCES_BLOB_POINTER]
        : undefined;

    if (encryptedBlob && masterPassword) {
      // Encrypted mode: decrypt the combined resources blob
      // (ciphertext+nonce+tag concatenation format matches aes.ts helpers)
      const serialized = `${encryptedBlob.nonce}:${encryptedBlob.tag}:${encryptedBlob.ciphertext}`;
      const decrypted = await decryptSection<{
        machines: Record<string, MachineConfig>;
        storages: Record<string, StorageConfig>;
        repositories: Record<string, RepositoryConfig>;
        deletedRepositories?: ArchivedRepository[];
        sshContent?: SSHContent | null;
      }>(serialized, masterPassword);

      state = {
        machines: decrypted.machines,
        storages: decrypted.storages,
        repositories: decrypted.repositories,
        deletedRepositories: decrypted.deletedRepositories ?? [],
        sshContent: decrypted.sshContent ?? null,
      };
    } else {
      // Plaintext mode: read from config.resources and config.credentials
      const sshCred = config.credentials?.ssh;
      state = {
        machines: config.resources?.machines ?? {},
        storages: config.resources?.storages ?? {},
        repositories: config.resources?.repositories ?? {},
        deletedRepositories: config.resources?.deletedRepositories ?? [],
        sshContent: sshCred
          ? {
              privateKey: sshCred.privateKey,
              publicKey: sshCred.publicKey,
              knownHosts: sshCred.knownHosts,
            }
          : null,
      };
    }

    return new LocalResourceState(configName, masterPassword, state);
  }

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

  private async persist(): Promise<void> {
    const configName = this.configName;
    const sshContent = this.state.sshContent;

    if (this.masterPassword) {
      const serialized = await encryptSection(
        {
          machines: this.state.machines,
          storages: this.state.storages,
          repositories: this.state.repositories,
          deletedRepositories: this.state.deletedRepositories,
          sshContent: this.state.sshContent,
        },
        this.masterPassword
      );
      // nodeCryptoProvider.encrypt returns nonce:tag:ciphertext format.
      const [nonce, tag, ciphertext] = serialized.split(':');

      await configFileStorage.update(configName, (cfg) => ({
        ...cfg,
        encryption: {
          mode: 'master-password',
          encryptedFields: {
            ...(cfg.encryption?.encryptedFields ?? {}),
            [RESOURCES_BLOB_POINTER]: { nonce, tag, ciphertext },
          },
        },
        resources: undefined,
        credentials: cfg.credentials ? { ...cfg.credentials, ssh: undefined } : cfg.credentials,
      }));
    } else {
      await configFileStorage.update(configName, (cfg) => ({
        ...cfg,
        resources: {
          ...(cfg.resources ?? {}),
          machines: Object.keys(this.state.machines).length > 0 ? this.state.machines : undefined,
          storages: Object.keys(this.state.storages).length > 0 ? this.state.storages : undefined,
          repositories:
            Object.keys(this.state.repositories).length > 0 ? this.state.repositories : undefined,
          deletedRepositories:
            this.state.deletedRepositories.length > 0 ? this.state.deletedRepositories : undefined,
        },
        credentials: {
          ...(cfg.credentials ?? {}),
          ssh: sshContent
            ? {
                privateKey: sshContent.privateKey,
                publicKey: sshContent.publicKey,
                knownHosts: sshContent.knownHosts,
              }
            : undefined,
        },
        encryption:
          cfg.encryption?.mode === 'master-password' ? { mode: 'plaintext' } : cfg.encryption,
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

  static load(
    config: RdcConfig,
    configName: string,
    adapter: RemoteConfigAdapter,
    version: number,
    sdkEpoch: number
  ): RemoteResourceState {
    const sshCred = config.credentials?.ssh;
    const state: LocalState = {
      machines: config.resources?.machines ?? {},
      storages: config.resources?.storages ?? {},
      repositories: config.resources?.repositories ?? {},
      deletedRepositories: config.resources?.deletedRepositories ?? [],
      sshContent: sshCred
        ? {
            privateKey: sshCred.privateKey,
            publicKey: sshCred.publicKey,
            knownHosts: sshCred.knownHosts,
          }
        : null,
    };
    return new RemoteResourceState(adapter, configName, version, sdkEpoch, state, config.id);
  }

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

  private async persist(): Promise<void> {
    const sshContent = this.state.sshContent;
    const fullConfig: RdcConfig = {
      schemaVersion: 2,
      id: this.configId,
      version: this.version,
      resources: {
        machines: this.state.machines,
        storages: this.state.storages,
        repositories: this.state.repositories,
        deletedRepositories:
          this.state.deletedRepositories.length > 0 ? this.state.deletedRepositories : undefined,
      },
      credentials: sshContent
        ? {
            ssh: {
              privateKey: sshContent.privateKey,
              publicKey: sshContent.publicKey,
              knownHosts: sshContent.knownHosts,
            },
          }
        : undefined,
      encryption: { mode: 'plaintext' },
    };

    const result = await this.adapter.push(fullConfig, this.version);
    this.version = result.version;
  }
}
