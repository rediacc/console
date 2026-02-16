/**
 * ResourceState interface and LocalResourceState implementation.
 *
 * ResourceState abstracts access to machines, storages, repositories, and SSH keys.
 * S3StateService and LocalResourceState both implement it, eliminating mode branching
 * in context-resources.ts.
 *
 * LocalResourceState wraps config.json reads/writes with optional AES-256-GCM encryption.
 * When encrypted, all resource data is stored as a single blob in NamedContext.encryptedResources.
 */

import { nodeCryptoProvider } from '../adapters/crypto.js';
import { configStorage } from '../adapters/storage.js';
import type {
  MachineConfig,
  NamedContext,
  RepositoryConfig,
  SSHContent,
  StorageConfig,
} from '../types/index.js';

// =============================================================================
// Shared Encryption Helpers (used by both S3StateService and LocalResourceState)
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
  sshContent: SSHContent | null;
}

/**
 * ResourceState implementation backed by config.json.
 * Supports optional AES-256-GCM encryption via masterPassword.
 */
export class LocalResourceState implements ResourceState {
  private readonly contextName: string;
  private readonly masterPassword: string | null;
  private readonly state: LocalState;

  private constructor(contextName: string, masterPassword: string | null, state: LocalState) {
    this.contextName = contextName;
    this.masterPassword = masterPassword;
    this.state = state;
  }

  /**
   * Load resource state from a NamedContext.
   * If encrypted, decrypts the encryptedResources blob.
   * If unencrypted, reads from inline context fields.
   */
  static async load(
    context: NamedContext,
    masterPassword: string | null
  ): Promise<LocalResourceState> {
    let state: LocalState;

    if (context.encrypted && context.encryptedResources && masterPassword) {
      // Encrypted local mode: decrypt the single blob
      const decrypted = await decryptSection<{
        machines: Record<string, MachineConfig>;
        storages: Record<string, StorageConfig>;
        repositories: Record<string, RepositoryConfig>;
        sshContent?: SSHContent | null;
      }>(context.encryptedResources, masterPassword);

      state = {
        machines: decrypted.machines,
        storages: decrypted.storages,
        repositories: decrypted.repositories,
        sshContent: decrypted.sshContent ?? null,
      };
    } else {
      // Unencrypted local mode: read directly from context fields
      state = {
        machines: context.machines ?? {},
        storages: context.storages ?? {},
        repositories: context.repositories ?? {},
        sshContent: context.sshContent ?? null,
      };
    }

    return new LocalResourceState(context.name, masterPassword, state);
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

  async setSSH(ssh: SSHContent): Promise<void> {
    this.state.sshContent = ssh;
    await this.persist();
  }

  // ===========================================================================
  // Persistence
  // ===========================================================================

  private async persist(): Promise<void> {
    const contextName = this.contextName;

    if (this.masterPassword) {
      // Encrypted: store all sections as a single encrypted blob
      const blob = await encryptSection(
        {
          machines: this.state.machines,
          storages: this.state.storages,
          repositories: this.state.repositories,
          sshContent: this.state.sshContent,
        },
        this.masterPassword
      );

      await configStorage.update((config) => {
        const ctx = config.contexts[contextName];
        if (!ctx) throw new Error(`Context "${contextName}" not found`);
        return {
          ...config,
          contexts: {
            ...config.contexts,
            [contextName]: {
              ...ctx,
              encrypted: true,
              encryptedResources: blob,
              machines: undefined,
              storages: undefined,
              repositories: undefined,
              sshContent: undefined,
            },
          },
        };
      });
    } else {
      // Unencrypted: store sections directly on the context
      await configStorage.update((config) => {
        const ctx = config.contexts[contextName];
        if (!ctx) throw new Error(`Context "${contextName}" not found`);
        return {
          ...config,
          contexts: {
            ...config.contexts,
            [contextName]: {
              ...ctx,
              machines: this.state.machines,
              storages: this.state.storages,
              repositories: this.state.repositories,
              sshContent: this.state.sshContent ?? undefined,
              encrypted: undefined,
              encryptedResources: undefined,
            },
          },
        };
      });
    }
  }
}
