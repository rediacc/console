/**
 * Resource CRUD methods for self-hosted (local/S3) configs.
 * Extends ConfigServiceBase with machine, storage, repository, and network ID management.
 * All resource access goes through ResourceState, eliminating mode-specific branches.
 */

import { DEFAULTS } from '@rediacc/shared/config';
import { MIN_NETWORK_ID, NETWORK_ID_INCREMENT } from '@rediacc/shared/queue-vault';
import { configFileStorage } from '../adapters/config-file-storage.js';
import type {
  ArchivedRepository,
  BackupStrategyConfig,
  BackupStrategyDestination,
  CloudProviderConfig,
  InfraConfig,
  MachineConfig,
  RdcConfig,
  RepositoryConfig,
  SSHConfig,
  StorageConfig,
} from '../types/index.js';
import { hasCloudCredentials } from '../types/index.js';
import { ConfigServiceBase } from './config-base.js';

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
    cfDnsApiToken?: string;
    cfDnsZoneId?: string;
    certEmail?: string;
    datastoreSize?: string;
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
      cfDnsApiToken: config.cfDnsApiToken,
      cfDnsZoneId: config.cfDnsZoneId,
      certEmail: config.certEmail,
      datastoreSize: config.datastoreSize,
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
    return Object.entries(state.getMachines())
      .map(([name, config]) => ({ name, config }))
      .sort((a, b) => a.name.localeCompare(b.name));
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

  async updateConfigFields(
    updates: Partial<
      Pick<RdcConfig, 'cfDnsApiToken' | 'cfDnsZoneId' | 'certEmail' | 'acmeCertCache'>
    >
  ): Promise<void> {
    const name = this.getEffectiveConfigName();
    await this.requireSelfHosted(name);
    await this.update(name, updates);
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
    return Object.entries(state.getStorages())
      .map(([name, config]) => ({ name, config }))
      .sort((a, b) => a.name.localeCompare(b.name));
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

  async removeRepository(repoRef: string): Promise<void> {
    await this.requireSelfHosted();
    const key = await this.getRepositoryKey(repoRef);
    if (!key) throw new Error(`Repository "${repoRef}" not found`);
    const state = await this.getResourceState();
    const repos = state.getRepositories();
    delete repos[key];
    await state.setRepositories(repos);
  }

  async listRepositories(): Promise<{ name: string; config: RepositoryConfig }[]> {
    await this.requireSelfHosted();
    const state = await this.getResourceState();
    return Object.entries(state.getRepositories())
      .map(([name, config]) => ({ name, config }))
      .sort((a, b) => a.name.localeCompare(b.name));
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

  /**
   * Resolve a repository reference to its config.
   * Supports: direct key match, legacy names, and bare names (defaults to :latest).
   */
  async getRepository(repoRef: string): Promise<RepositoryConfig | undefined> {
    const config = await this.getCurrent();
    if (!config || hasCloudCredentials(config)) return undefined;

    const state = await this.getResourceState();
    const repos = state.getRepositories();

    // 1. Direct match (composite key or legacy key)
    if (repoRef in repos) return repos[repoRef];

    // 2. If no colon, try name:latest
    if (!repoRef.includes(':')) {
      const latestKey = `${repoRef}:latest`;
      if (latestKey in repos) return repos[latestKey];
    }

    return undefined;
  }

  /**
   * Resolve a repository reference to its actual config dictionary key.
   * Needed for mutation operations (remove, update networkId, etc.).
   */
  async getRepositoryKey(repoRef: string): Promise<string | undefined> {
    const config = await this.getCurrent();
    if (!config || hasCloudCredentials(config)) return undefined;

    const state = await this.getResourceState();
    const repos = state.getRepositories();

    if (repoRef in repos) return repoRef;
    if (!repoRef.includes(':')) {
      const latestKey = `${repoRef}:latest`;
      if (latestKey in repos) return latestKey;
    }
    return undefined;
  }

  /**
   * List all tags for a given base repository name.
   */
  async listRepositoriesByName(
    baseName: string
  ): Promise<{ key: string; tag: string; config: RepositoryConfig }[]> {
    const { parseRepoRef } = await import('../utils/config-schema.js');
    const repos = await this.listRepositories();
    return repos
      .filter((r) => {
        const { name } = parseRepoRef(r.name);
        return name === baseName;
      })
      .map((r) => {
        const { tag } = parseRepoRef(r.name);
        return { key: r.name, tag, config: r.config };
      });
  }

  // ============================================================================
  // Repository Archive (credential preservation on delete)
  // ============================================================================

  async archiveRepository(repoName: string): Promise<void> {
    await this.requireSelfHosted();
    const state = await this.getResourceState();
    const repos = state.getRepositories();
    if (!(repoName in repos)) throw new Error(`Repository "${repoName}" not found`);

    const archived: ArchivedRepository = {
      ...repos[repoName],
      name: repoName,
      deletedAt: new Date().toISOString(),
    };

    const deletedRepos = state.getDeletedRepositories();
    deletedRepos.push(archived);
    await state.setDeletedRepositories(deletedRepos);

    delete repos[repoName];
    await state.setRepositories(repos);
  }

  async restoreArchivedRepository(guid: string, name?: string): Promise<string> {
    await this.requireSelfHosted();
    const state = await this.getResourceState();
    const deletedRepos = state.getDeletedRepositories();
    const index = deletedRepos.findIndex((r) => r.repositoryGuid === guid);
    if (index === -1) throw new Error(`Archived repository with GUID "${guid}" not found`);

    const archived = deletedRepos[index];
    const restoredName = name ?? archived.name;

    const repos = state.getRepositories();
    if (restoredName in repos) {
      throw new Error(
        `Repository "${restoredName}" already exists. Use --name to specify a different name.`
      );
    }

    const { name: originalName, deletedAt, ...repoConfig } = archived;
    void originalName;
    void deletedAt;
    repos[restoredName] = repoConfig;
    await state.setRepositories(repos);

    deletedRepos.splice(index, 1);
    await state.setDeletedRepositories(deletedRepos);
    return restoredName;
  }

  async listArchivedRepositories(): Promise<ArchivedRepository[]> {
    await this.requireSelfHosted();
    const state = await this.getResourceState();
    return state.getDeletedRepositories();
  }

  async purgeArchivedRepositories(): Promise<number> {
    await this.requireSelfHosted();
    const state = await this.getResourceState();
    const count = state.getDeletedRepositories().length;
    await state.setDeletedRepositories([]);
    return count;
  }

  async purgeExpiredArchives(graceDays: number): Promise<ArchivedRepository[]> {
    await this.requireSelfHosted();
    const state = await this.getResourceState();
    const cutoff = Date.now() - graceDays * 86400000;
    const all = state.getDeletedRepositories();
    const expired = all.filter((r) => new Date(r.deletedAt).getTime() < cutoff);
    if (expired.length > 0) {
      const remaining = all.filter((r) => new Date(r.deletedAt).getTime() >= cutoff);
      await state.setDeletedRepositories(remaining);
    }
    return expired;
  }

  // ============================================================================
  // Backup Strategy
  // ============================================================================

  async setBackupStrategy(config: Partial<BackupStrategyConfig>): Promise<void> {
    const name = this.getEffectiveConfigName();
    const current = await this.requireSelfHosted(name);
    const backupStrategy: BackupStrategyConfig = {
      destinations: [],
      ...current.backupStrategy,
      ...config,
    };
    await this.update(name, { backupStrategy });
  }

  async getBackupStrategy(): Promise<BackupStrategyConfig | undefined> {
    const config = await this.requireSelfHosted();
    return config.backupStrategy;
  }

  async addBackupDestination(dest: BackupStrategyDestination): Promise<void> {
    const name = this.getEffectiveConfigName();
    const current = await this.requireSelfHosted(name);
    const backupStrategy: BackupStrategyConfig = {
      destinations: [],
      ...current.backupStrategy,
    };
    const idx = backupStrategy.destinations.findIndex((d) => d.storage === dest.storage);
    if (idx >= 0) {
      backupStrategy.destinations[idx] = { ...backupStrategy.destinations[idx], ...dest };
    } else {
      backupStrategy.destinations.push(dest);
    }
    backupStrategy.destinations.sort((a, b) => a.storage.localeCompare(b.storage));
    await this.update(name, { backupStrategy });
  }

  async removeBackupDestination(storageName: string): Promise<void> {
    const name = this.getEffectiveConfigName();
    const current = await this.requireSelfHosted(name);
    const backupStrategy: BackupStrategyConfig = {
      destinations: [],
      ...current.backupStrategy,
    };
    backupStrategy.destinations = backupStrategy.destinations.filter(
      (d) => d.storage !== storageName
    );
    await this.update(name, { backupStrategy });
  }

  // ============================================================================
  // Cloud Provider CRUD
  // ============================================================================

  async addCloudProvider(name: string, config: CloudProviderConfig): Promise<void> {
    const configName = this.getEffectiveConfigName();
    await this.requireSelfHosted(configName);
    const current = await this.getCurrent();
    const providers = { ...current?.cloudProviders };
    providers[name] = config;
    await this.update(configName, { cloudProviders: providers });
  }

  async removeCloudProvider(name: string): Promise<void> {
    const configName = this.getEffectiveConfigName();
    await this.requireSelfHosted(configName);
    const current = await this.getCurrent();
    const providers = { ...current?.cloudProviders };
    if (!(name in providers)) throw new Error(`Cloud provider "${name}" not found`);
    delete providers[name];
    await this.update(configName, { cloudProviders: providers });
  }

  async listCloudProviders(): Promise<{ name: string; config: CloudProviderConfig }[]> {
    const config = await this.getCurrent();
    if (!config?.cloudProviders) return [];
    return Object.entries(config.cloudProviders)
      .map(([name, providerConfig]) => ({ name, config: providerConfig }))
      .sort((a, b) => a.name.localeCompare(b.name));
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

  async ensureRepositoryNetworkId(repoRef: string): Promise<number> {
    await this.requireSelfHosted();
    const key = await this.getRepositoryKey(repoRef);
    if (!key) throw new Error(`Repository "${repoRef}" not found`);

    const state = await this.getResourceState();
    const repos = state.getRepositories();
    const repo = repos[key];

    if (repo.networkId !== undefined && repo.networkId > 0) return repo.networkId;

    const networkId = await this.allocateNetworkId();
    repos[key] = { ...repo, networkId };
    await state.setRepositories(repos);
    return networkId;
  }
}

export const configService = new ConfigService();
