/**
 * Resource CRUD methods for self-hosted (local/S3) contexts.
 * Extends ContextServiceBase with machine, storage, repository, and network ID management.
 * All resource access goes through ResourceState, eliminating mode-specific branches.
 */

import { DEFAULTS } from '@rediacc/shared/config';
import { MIN_NETWORK_ID, NETWORK_ID_INCREMENT } from '@rediacc/shared/queue-vault';
import { ContextServiceBase } from './context-base.js';
import { configStorage } from '../adapters/storage.js';
import type {
  BackupConfig,
  CliConfig,
  InfraConfig,
  MachineConfig,
  NamedContext,
  RepositoryConfig,
  SSHConfig,
  StorageConfig,
} from '../types/index.js';

class ContextService extends ContextServiceBase {
  /**
   * Require the current context to be in a self-hosted mode (local or S3).
   */
  protected async requireSelfHostedMode(contextName?: string): Promise<NamedContext> {
    const context = contextName ? await this.get(contextName) : await this.getCurrent();
    if (!context) {
      throw new Error('No active context');
    }
    if ((context.mode ?? 'cloud') === 'cloud') {
      throw new Error(`Context "${context.name}" is not in local or S3 mode`);
    }
    return context;
  }

  /**
   * Get local configuration for the current context.
   * Uses ResourceState for mode-agnostic access to machines and SSH keys.
   */
  async getLocalConfig(): Promise<{
    machines: Record<string, MachineConfig | undefined>;
    ssh: SSHConfig;
    sshPrivateKey?: string;
    sshPublicKey?: string;
    renetPath: string;
  }> {
    const context = await this.requireSelfHostedMode();
    const state = await this.getResourceState();
    const machines = state.getMachines();

    if (Object.keys(machines).length === 0) {
      throw new Error(`Context "${context.name}" has no machines configured`);
    }

    const sshContent = state.getSSH();
    if (!sshContent?.privateKey && !context.ssh?.privateKeyPath) {
      throw new Error(`Context "${context.name}" has no SSH key configured`);
    }

    return {
      machines,
      ssh: context.ssh ?? { privateKeyPath: '' },
      sshPrivateKey: sshContent?.privateKey,
      sshPublicKey: sshContent?.publicKey,
      renetPath: context.renetPath ?? DEFAULTS.CONTEXT.RENET_BINARY,
    };
  }

  async getLocalMachine(machineName: string): Promise<MachineConfig> {
    const config = await this.getLocalConfig();
    const machine = config.machines[machineName];
    if (!machine) {
      const available = Object.keys(config.machines).join(', ');
      throw new Error(`Machine "${machineName}" not found. Available: ${available}`);
    }
    return machine;
  }

  async createLocal(
    name: string,
    sshKeyPath: string,
    options?: { renetPath?: string; masterPassword?: string }
  ): Promise<void> {
    const context: NamedContext = {
      name,
      mode: 'local',
      apiUrl: 'local://',
      ssh: {
        privateKeyPath: sshKeyPath,
        publicKeyPath: `${sshKeyPath}.pub`,
      },
      machines: options?.masterPassword ? undefined : {},
      encrypted: !!options?.masterPassword,
      renetPath: options?.renetPath,
      masterPassword: options?.masterPassword,
    };
    await this.create(context);
  }

  // ============================================================================
  // Machine CRUD
  // ============================================================================

  async addLocalMachine(machineName: string, config: MachineConfig): Promise<void> {
    await this.requireSelfHostedMode();
    const state = await this.getResourceState();
    const machines = state.getMachines();
    machines[machineName] = config;
    await state.setMachines(machines);
  }

  async removeLocalMachine(machineName: string): Promise<void> {
    await this.requireSelfHostedMode();
    const state = await this.getResourceState();
    const machines = state.getMachines();
    if (!(machineName in machines)) throw new Error(`Machine "${machineName}" not found`);
    delete machines[machineName];
    await state.setMachines(machines);
  }

  async listLocalMachines(): Promise<{ name: string; config: MachineConfig }[]> {
    await this.requireSelfHostedMode();
    const state = await this.getResourceState();
    return Object.entries(state.getMachines()).map(([name, config]) => ({
      name,
      config,
    }));
  }

  async updateLocalMachine(machineName: string, updates: Partial<MachineConfig>): Promise<void> {
    await this.requireSelfHostedMode();
    const state = await this.getResourceState();
    const machines = state.getMachines();
    if (!(machineName in machines)) throw new Error(`Machine "${machineName}" not found`);
    machines[machineName] = { ...machines[machineName], ...updates };
    await state.setMachines(machines);
  }

  async setMachineInfra(machineName: string, infra: Partial<InfraConfig>): Promise<void> {
    await this.requireSelfHostedMode();
    const state = await this.getResourceState();
    const machines = state.getMachines();
    if (!(machineName in machines)) throw new Error(`Machine "${machineName}" not found`);
    machines[machineName] = {
      ...machines[machineName],
      infra: { ...machines[machineName].infra, ...infra },
    };
    await state.setMachines(machines);
  }

  async setLocalSSH(ssh: SSHConfig): Promise<void> {
    const name = this.getEffectiveContextName();
    await this.requireSelfHostedMode(name);
    await this.update(name, { ssh });
  }

  async setRenetPath(renetPath: string): Promise<void> {
    const name = this.getEffectiveContextName();
    await this.requireSelfHostedMode(name);
    await this.update(name, { renetPath });
  }

  // ============================================================================
  // Storage CRUD
  // ============================================================================

  async addLocalStorage(storageName: string, config: StorageConfig): Promise<void> {
    await this.requireSelfHostedMode();
    const state = await this.getResourceState();
    const storages = state.getStorages();
    storages[storageName] = config;
    await state.setStorages(storages);
  }

  async removeLocalStorage(storageName: string): Promise<void> {
    await this.requireSelfHostedMode();
    const state = await this.getResourceState();
    const storages = state.getStorages();
    if (!(storageName in storages)) throw new Error(`Storage "${storageName}" not found`);
    delete storages[storageName];
    await state.setStorages(storages);
  }

  async listLocalStorages(): Promise<{ name: string; config: StorageConfig }[]> {
    await this.requireSelfHostedMode();
    const state = await this.getResourceState();
    return Object.entries(state.getStorages()).map(([name, config]) => ({
      name,
      config,
    }));
  }

  async getLocalStorage(storageName: string): Promise<StorageConfig> {
    await this.requireSelfHostedMode();
    const state = await this.getResourceState();
    const storages = state.getStorages();
    if (!(storageName in storages)) {
      const available = Object.keys(storages).join(', ');
      throw new Error(`Storage "${storageName}" not found. Available: ${available || 'none'}`);
    }
    return storages[storageName];
  }

  // ============================================================================
  // Repository CRUD
  // ============================================================================

  async addLocalRepository(repoName: string, config: RepositoryConfig): Promise<void> {
    await this.requireSelfHostedMode();
    const state = await this.getResourceState();
    const repos = state.getRepositories();
    repos[repoName] = config;
    await state.setRepositories(repos);
  }

  async removeLocalRepository(repoName: string): Promise<void> {
    await this.requireSelfHostedMode();
    const state = await this.getResourceState();
    const repos = state.getRepositories();
    if (!(repoName in repos)) throw new Error(`Repository "${repoName}" not found`);
    delete repos[repoName];
    await state.setRepositories(repos);
  }

  async listLocalRepositories(): Promise<{ name: string; config: RepositoryConfig }[]> {
    await this.requireSelfHostedMode();
    const state = await this.getResourceState();
    return Object.entries(state.getRepositories()).map(([name, config]) => ({
      name,
      config,
    }));
  }

  async getRepositoryGuidMap(): Promise<Record<string, string>> {
    const context = await this.getCurrent();
    if (!context || (context.mode ?? 'cloud') === 'cloud') return {};

    const state = await this.getResourceState();
    const repos = state.getRepositories();
    const map: Record<string, string> = {};
    for (const [repoName, config] of Object.entries(repos)) {
      const tag = config.tag ?? DEFAULTS.REPOSITORY.TAG;
      map[config.repositoryGuid] = `${repoName}:${tag}`;
    }
    return map;
  }

  async getRepositoryCredentials(): Promise<Record<string, string>> {
    const context = await this.getCurrent();
    if (!context || (context.mode ?? 'cloud') === 'cloud') return {};

    const state = await this.getResourceState();
    const repos = state.getRepositories();
    const map: Record<string, string> = {};
    for (const [, config] of Object.entries(repos)) {
      if (config.credential) {
        map[config.repositoryGuid] = config.credential;
      }
    }
    return map;
  }

  async getLocalRepository(repoName: string): Promise<RepositoryConfig | undefined> {
    const context = await this.getCurrent();
    if (!context || (context.mode ?? 'cloud') === 'cloud') return undefined;

    const state = await this.getResourceState();
    return state.getRepositories()[repoName];
  }

  // ============================================================================
  // Backup Configuration
  // ============================================================================

  async setBackupConfig(config: Partial<BackupConfig>): Promise<void> {
    const name = this.getEffectiveContextName();
    const context = await this.requireSelfHostedMode(name);
    const backup: BackupConfig = {
      defaultDestination: '',
      ...context.backup,
      ...config,
    };
    await this.update(name, { backup });
  }

  async getBackupConfig(): Promise<BackupConfig | undefined> {
    const context = await this.requireSelfHostedMode();
    return context.backup;
  }

  // ============================================================================
  // Network ID Allocation (global counter across all contexts)
  // ============================================================================

  /**
   * Scan all contexts in config.json to compute the next available network ID.
   * Used as migration fallback when the global counter doesn't exist yet.
   */
  private computeGlobalNextNetworkId(config: CliConfig): number {
    const usedIds: number[] = [];

    for (const context of Object.values(config.contexts)) {
      if (!context?.repositories) continue;
      for (const repo of Object.values(context.repositories)) {
        if (repo.networkId !== undefined && repo.networkId > 0) {
          usedIds.push(repo.networkId);
        }
      }
    }

    if (usedIds.length === 0) return MIN_NETWORK_ID;
    return Math.max(...usedIds) + NETWORK_ID_INCREMENT;
  }

  /**
   * Allocate a globally unique network ID. Uses an atomic read-modify-write
   * on the global counter in config.json. On first use (or if the counter is
   * missing), scans all contexts to compute the correct starting value.
   */
  async allocateNetworkId(): Promise<number> {
    let allocated = 0;
    await configStorage.update((config) => {
      let nextId = config.nextNetworkId;

      if (nextId === undefined || nextId < MIN_NETWORK_ID) {
        // Migration: scan ALL contexts to find max used network ID
        nextId = this.computeGlobalNextNetworkId(config);
      }

      allocated = nextId;
      return {
        ...config,
        nextNetworkId: nextId + NETWORK_ID_INCREMENT,
      };
    });
    return allocated;
  }

  async ensureRepositoryNetworkId(repoName: string): Promise<number> {
    await this.requireSelfHostedMode();
    const state = await this.getResourceState();
    const repos = state.getRepositories();

    if (!(repoName in repos)) throw new Error(`Repository "${repoName}" not found`);
    const repo = repos[repoName];

    if (repo.networkId !== undefined && repo.networkId > 0) return repo.networkId;

    const networkId = await this.allocateNetworkId();
    repos[repoName] = { ...repo, networkId };
    await state.setRepositories(repos);
    return networkId;
  }
}

export const contextService = new ContextService();
