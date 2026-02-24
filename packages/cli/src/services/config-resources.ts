/**
 * Resource CRUD methods for self-hosted (local/S3) configs.
 * Extends ConfigServiceBase with machine, storage, repository, and network ID management.
 * All resource access goes through ResourceState, eliminating mode-specific branches.
 */

import { DEFAULTS } from '@rediacc/shared/config';
import { MIN_NETWORK_ID, NETWORK_ID_INCREMENT } from '@rediacc/shared/queue-vault';
import { ConfigServiceBase } from './config-base.js';
import { configFileStorage } from '../adapters/config-file-storage.js';
import { hasCloudCredentials } from '../types/index.js';
import type {
  BackupConfig,
  InfraConfig,
  MachineConfig,
  RdcConfig,
  RepositoryConfig,
  SSHConfig,
  StorageConfig,
} from '../types/index.js';

class ConfigService extends ConfigServiceBase {
  /**
   * Require the current config to be in a self-hosted mode (local or S3).
   */
  protected async requireSelfHosted(configName?: string): Promise<RdcConfig> {
    const config = configName ? await configFileStorage.load(configName) : await this.getCurrent();
    if (!config) throw new Error('No active config');
    if (hasCloudCredentials(config)) {
      throw new Error(`Config "${configName ?? this.getEffectiveConfigName()}" is a cloud config`);
    }
    return config;
  }

  /**
   * Get local configuration for the current config.
   * Uses ResourceState for mode-agnostic access to machines and SSH keys.
   */
  async getLocalConfig(): Promise<{
    machines: Record<string, MachineConfig | undefined>;
    ssh: SSHConfig;
    sshPrivateKey?: string;
    sshPublicKey?: string;
    renetPath: string;
  }> {
    const config = await this.requireSelfHosted();
    const state = await this.getResourceState();
    const machines = state.getMachines();
    const configName = this.getEffectiveConfigName();

    if (Object.keys(machines).length === 0) {
      throw new Error(`Config "${configName}" has no machines configured`);
    }

    const sshContent = state.getSSH();
    if (!sshContent?.privateKey && !config.ssh?.privateKeyPath) {
      throw new Error(`Config "${configName}" has no SSH key configured`);
    }

    return {
      machines,
      ssh: config.ssh ?? { privateKeyPath: '' },
      sshPrivateKey: sshContent?.privateKey,
      sshPublicKey: sshContent?.publicKey,
      renetPath: config.renetPath ?? DEFAULTS.CONTEXT.RENET_BINARY,
    };
  }

  async getLocalMachine(machineName: string): Promise<MachineConfig> {
    const localConfig = await this.getLocalConfig();
    const machine = localConfig.machines[machineName];
    if (!machine) {
      const available = Object.keys(localConfig.machines).join(', ');
      throw new Error(`Machine "${machineName}" not found. Available: ${available}`);
    }
    return machine;
  }

  // ============================================================================
  // Machine CRUD
  // ============================================================================

  async addMachine(machineName: string, config: MachineConfig): Promise<void> {
    await this.requireSelfHosted();
    const state = await this.getResourceState();
    const machines = state.getMachines();
    machines[machineName] = config;
    await state.setMachines(machines);
  }

  async removeMachine(machineName: string): Promise<void> {
    await this.requireSelfHosted();
    const state = await this.getResourceState();
    const machines = state.getMachines();
    if (!(machineName in machines)) throw new Error(`Machine "${machineName}" not found`);
    delete machines[machineName];
    await state.setMachines(machines);
  }

  async listMachines(): Promise<{ name: string; config: MachineConfig }[]> {
    await this.requireSelfHosted();
    const state = await this.getResourceState();
    return Object.entries(state.getMachines()).map(([name, config]) => ({
      name,
      config,
    }));
  }

  async updateMachine(machineName: string, updates: Partial<MachineConfig>): Promise<void> {
    await this.requireSelfHosted();
    const state = await this.getResourceState();
    const machines = state.getMachines();
    if (!(machineName in machines)) throw new Error(`Machine "${machineName}" not found`);
    machines[machineName] = { ...machines[machineName], ...updates };
    await state.setMachines(machines);
  }

  async setMachineInfra(machineName: string, infra: Partial<InfraConfig>): Promise<void> {
    await this.requireSelfHosted();
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
    const name = this.getEffectiveConfigName();
    await this.requireSelfHosted(name);
    await this.update(name, { ssh });
  }

  async setRenetPath(renetPath: string): Promise<void> {
    const name = this.getEffectiveConfigName();
    await this.requireSelfHosted(name);
    await this.update(name, { renetPath });
  }

  // ============================================================================
  // Storage CRUD
  // ============================================================================

  async addStorage(storageName: string, config: StorageConfig): Promise<void> {
    await this.requireSelfHosted();
    const state = await this.getResourceState();
    const storages = state.getStorages();
    storages[storageName] = config;
    await state.setStorages(storages);
  }

  async removeStorage(storageName: string): Promise<void> {
    await this.requireSelfHosted();
    const state = await this.getResourceState();
    const storages = state.getStorages();
    if (!(storageName in storages)) throw new Error(`Storage "${storageName}" not found`);
    delete storages[storageName];
    await state.setStorages(storages);
  }

  async listStorages(): Promise<{ name: string; config: StorageConfig }[]> {
    await this.requireSelfHosted();
    const state = await this.getResourceState();
    return Object.entries(state.getStorages()).map(([name, config]) => ({
      name,
      config,
    }));
  }

  async getStorage(storageName: string): Promise<StorageConfig> {
    await this.requireSelfHosted();
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

  async addRepository(repoName: string, config: RepositoryConfig): Promise<void> {
    await this.requireSelfHosted();
    const state = await this.getResourceState();
    const repos = state.getRepositories();
    repos[repoName] = config;
    await state.setRepositories(repos);
  }

  async removeRepository(repoName: string): Promise<void> {
    await this.requireSelfHosted();
    const state = await this.getResourceState();
    const repos = state.getRepositories();
    if (!(repoName in repos)) throw new Error(`Repository "${repoName}" not found`);
    delete repos[repoName];
    await state.setRepositories(repos);
  }

  async listRepositories(): Promise<{ name: string; config: RepositoryConfig }[]> {
    await this.requireSelfHosted();
    const state = await this.getResourceState();
    return Object.entries(state.getRepositories()).map(([name, config]) => ({
      name,
      config,
    }));
  }

  async getRepositoryGuidMap(): Promise<Record<string, string>> {
    const config = await this.getCurrent();
    if (!config || hasCloudCredentials(config)) return {};

    const state = await this.getResourceState();
    const repos = state.getRepositories();
    const map: Record<string, string> = {};
    for (const [repoName, repoConfig] of Object.entries(repos)) {
      const tag = repoConfig.tag ?? DEFAULTS.REPOSITORY.TAG;
      map[repoConfig.repositoryGuid] = `${repoName}:${tag}`;
    }
    return map;
  }

  async getRepositoryCredentials(): Promise<Record<string, string>> {
    const config = await this.getCurrent();
    if (!config || hasCloudCredentials(config)) return {};

    const state = await this.getResourceState();
    const repos = state.getRepositories();
    const map: Record<string, string> = {};
    for (const [, repoConfig] of Object.entries(repos)) {
      if (repoConfig.credential) {
        map[repoConfig.repositoryGuid] = repoConfig.credential;
      }
    }
    return map;
  }

  async getRepository(repoName: string): Promise<RepositoryConfig | undefined> {
    const config = await this.getCurrent();
    if (!config || hasCloudCredentials(config)) return undefined;

    const state = await this.getResourceState();
    return state.getRepositories()[repoName];
  }

  // ============================================================================
  // Backup Configuration
  // ============================================================================

  async setBackupConfig(config: Partial<BackupConfig>): Promise<void> {
    const name = this.getEffectiveConfigName();
    const current = await this.requireSelfHosted(name);
    const backup: BackupConfig = {
      defaultDestination: '',
      ...current.backup,
      ...config,
    };
    await this.update(name, { backup });
  }

  async getBackupConfig(): Promise<BackupConfig | undefined> {
    const config = await this.requireSelfHosted();
    return config.backup;
  }

  // ============================================================================
  // Network ID Allocation (per config file)
  // ============================================================================

  /**
   * Scan all repositories in a config and return an array of used network IDs.
   */
  private scanUsedNetworkIds(config: RdcConfig): number[] {
    const usedIds: number[] = [];
    if (config.repositories) {
      for (const repo of Object.values(config.repositories)) {
        if (repo.networkId !== undefined && repo.networkId > 0) {
          usedIds.push(repo.networkId);
        }
      }
    }
    return usedIds;
  }

  async allocateNetworkId(): Promise<number> {
    const name = this.getEffectiveConfigName();
    let allocated = 0;
    await configFileStorage.update(name, (config) => {
      let nextId = config.nextNetworkId;

      if (nextId === undefined || nextId < MIN_NETWORK_ID) {
        const usedIds = this.scanUsedNetworkIds(config);
        nextId =
          usedIds.length === 0 ? MIN_NETWORK_ID : Math.max(...usedIds) + NETWORK_ID_INCREMENT;
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
    await this.requireSelfHosted();
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

export const configService = new ConfigService();
