/**
 * Resource CRUD methods for local/S3 mode contexts.
 * Extends ContextServiceBase with machine, storage, repository, and network ID management.
 * In S3 mode, delegates to S3StateService (state.json); in local mode, reads/writes config.json.
 */

import { DEFAULTS } from '@rediacc/shared/config';
import { MIN_NETWORK_ID, NETWORK_ID_INCREMENT } from '@rediacc/shared/queue-vault';
import { ContextServiceBase } from './context-base.js';
import type {
  BackupConfig,
  InfraConfig,
  MachineConfig,
  NamedContext,
  RepositoryConfig,
  SSHConfig,
  StorageConfig,
} from '../types/index.js';

class ContextService extends ContextServiceBase {
  /**
   * Require the current context to be in local or S3 mode.
   */
  protected async requireLocalOrS3Mode(contextName?: string): Promise<NamedContext> {
    const context = contextName ? await this.get(contextName) : await this.getCurrent();
    if (!context) {
      throw new Error('No active context');
    }
    if (context.mode !== 'local' && context.mode !== 's3') {
      throw new Error(`Context "${context.name}" is not in local or S3 mode`);
    }
    return context;
  }

  /**
   * Get local configuration for the current context.
   * In S3 mode, reads machines/SSH from state.json; in local mode, from config.json.
   */
  async getLocalConfig(): Promise<{
    machines: Record<string, MachineConfig | undefined>;
    ssh: SSHConfig;
    sshPrivateKey?: string;
    sshPublicKey?: string;
    renetPath: string;
  }> {
    const context = await this.requireLocalOrS3Mode();

    if (context.mode === 's3') {
      const s3 = await this.getS3State();
      const machines = s3.getMachines();
      if (Object.keys(machines).length === 0) {
        throw new Error(`Context "${context.name}" has no machines configured`);
      }
      const sshContent = s3.getSSH();
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

    if (!context.machines || Object.keys(context.machines).length === 0) {
      throw new Error(`Context "${context.name}" has no machines configured`);
    }
    if (!context.ssh?.privateKeyPath) {
      throw new Error(`Context "${context.name}" has no SSH key configured`);
    }
    return {
      machines: context.machines,
      ssh: context.ssh,
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
    options?: { renetPath?: string }
  ): Promise<void> {
    const context: NamedContext = {
      name,
      mode: 'local',
      apiUrl: 'local://',
      ssh: {
        privateKeyPath: sshKeyPath,
        publicKeyPath: `${sshKeyPath}.pub`,
      },
      machines: {},
      renetPath: options?.renetPath,
    };
    await this.create(context);
  }

  // ============================================================================
  // Machine CRUD
  // ============================================================================

  async addLocalMachine(machineName: string, config: MachineConfig): Promise<void> {
    const name = this.getEffectiveContextName();
    const context = await this.requireLocalOrS3Mode(name);

    if (context.mode === 's3') {
      const s3 = await this.getS3State();
      const machines = s3.getMachines();
      machines[machineName] = config;
      await s3.setMachines(machines);
      return;
    }

    const existingMachines = context.machines ?? {};
    await this.update(name, {
      machines: { ...existingMachines, [machineName]: config },
    });
  }

  async removeLocalMachine(machineName: string): Promise<void> {
    const name = this.getEffectiveContextName();
    const context = await this.requireLocalOrS3Mode(name);

    if (context.mode === 's3') {
      const s3 = await this.getS3State();
      const machines = s3.getMachines();
      if (!(machineName in machines)) throw new Error(`Machine "${machineName}" not found`);
      delete machines[machineName];
      await s3.setMachines(machines);
      return;
    }

    if (!context.machines?.[machineName]) {
      throw new Error(`Machine "${machineName}" not found`);
    }
    const remaining = { ...context.machines };
    delete remaining[machineName];
    await this.update(name, { machines: remaining });
  }

  async listLocalMachines(): Promise<{ name: string; config: MachineConfig }[]> {
    const context = await this.requireLocalOrS3Mode();

    if (context.mode === 's3') {
      const s3 = await this.getS3State();
      return Object.entries(s3.getMachines()).map(([name, config]) => ({
        name,
        config,
      }));
    }

    return Object.entries(context.machines ?? {}).map(([name, config]) => ({
      name,
      config,
    }));
  }

  async updateLocalMachine(machineName: string, updates: Partial<MachineConfig>): Promise<void> {
    const name = this.getEffectiveContextName();
    const context = await this.requireLocalOrS3Mode(name);

    if (context.mode === 's3') {
      const s3 = await this.getS3State();
      const machines = s3.getMachines();
      if (!(machineName in machines)) throw new Error(`Machine "${machineName}" not found`);
      machines[machineName] = { ...machines[machineName], ...updates };
      await s3.setMachines(machines);
      return;
    }

    const existing = context.machines?.[machineName];
    if (!existing) {
      throw new Error(`Machine "${machineName}" not found`);
    }
    await this.update(name, {
      machines: {
        ...context.machines,
        [machineName]: { ...existing, ...updates },
      },
    });
  }

  async setMachineInfra(machineName: string, infra: Partial<InfraConfig>): Promise<void> {
    const name = this.getEffectiveContextName();
    const context = await this.requireLocalOrS3Mode(name);

    if (context.mode === 's3') {
      const s3 = await this.getS3State();
      const machines = s3.getMachines();
      if (!(machineName in machines)) throw new Error(`Machine "${machineName}" not found`);
      machines[machineName] = {
        ...machines[machineName],
        infra: { ...machines[machineName].infra, ...infra },
      };
      await s3.setMachines(machines);
      return;
    }

    const existing = context.machines?.[machineName];
    if (!existing) {
      throw new Error(`Machine "${machineName}" not found`);
    }
    await this.update(name, {
      machines: {
        ...context.machines,
        [machineName]: {
          ...existing,
          infra: { ...existing.infra, ...infra },
        },
      },
    });
  }

  async setLocalSSH(ssh: SSHConfig): Promise<void> {
    const name = this.getEffectiveContextName();
    await this.requireLocalOrS3Mode(name);
    await this.update(name, { ssh });
  }

  async setRenetPath(renetPath: string): Promise<void> {
    const name = this.getEffectiveContextName();
    await this.requireLocalOrS3Mode(name);
    await this.update(name, { renetPath });
  }

  // ============================================================================
  // Storage CRUD
  // ============================================================================

  async addLocalStorage(storageName: string, config: StorageConfig): Promise<void> {
    const name = this.getEffectiveContextName();
    const context = await this.requireLocalOrS3Mode(name);

    if (context.mode === 's3') {
      const s3 = await this.getS3State();
      const storages = s3.getStorages();
      storages[storageName] = config;
      await s3.setStorages(storages);
      return;
    }

    const existingStorages = context.storages ?? {};
    await this.update(name, {
      storages: { ...existingStorages, [storageName]: config },
    });
  }

  async removeLocalStorage(storageName: string): Promise<void> {
    const name = this.getEffectiveContextName();
    const context = await this.requireLocalOrS3Mode(name);

    if (context.mode === 's3') {
      const s3 = await this.getS3State();
      const storages = s3.getStorages();
      if (!(storageName in storages)) throw new Error(`Storage "${storageName}" not found`);
      delete storages[storageName];
      await s3.setStorages(storages);
      return;
    }

    if (!context.storages?.[storageName]) {
      throw new Error(`Storage "${storageName}" not found`);
    }
    const remaining = { ...context.storages };
    delete remaining[storageName];
    await this.update(name, { storages: remaining });
  }

  async listLocalStorages(): Promise<{ name: string; config: StorageConfig }[]> {
    const context = await this.requireLocalOrS3Mode();

    if (context.mode === 's3') {
      const s3 = await this.getS3State();
      return Object.entries(s3.getStorages()).map(([name, config]) => ({
        name,
        config,
      }));
    }

    return Object.entries(context.storages ?? {}).map(([name, config]) => ({
      name,
      config,
    }));
  }

  async getLocalStorage(storageName: string): Promise<StorageConfig> {
    const context = await this.requireLocalOrS3Mode();

    if (context.mode === 's3') {
      const s3 = await this.getS3State();
      const storages = s3.getStorages();
      if (!(storageName in storages)) {
        const available = Object.keys(storages).join(', ');
        throw new Error(`Storage "${storageName}" not found. Available: ${available || 'none'}`);
      }
      return storages[storageName];
    }

    const storage = context.storages?.[storageName];
    if (!storage) {
      const available = Object.keys(context.storages ?? {}).join(', ');
      throw new Error(`Storage "${storageName}" not found. Available: ${available || 'none'}`);
    }
    return storage;
  }

  // ============================================================================
  // Repository CRUD
  // ============================================================================

  async addLocalRepository(repoName: string, config: RepositoryConfig): Promise<void> {
    const name = this.getEffectiveContextName();
    const context = await this.requireLocalOrS3Mode(name);

    if (context.mode === 's3') {
      const s3 = await this.getS3State();
      const repos = s3.getRepositories();
      repos[repoName] = config;
      await s3.setRepositories(repos);
      return;
    }

    const existing = context.repositories ?? {};
    await this.update(name, {
      repositories: { ...existing, [repoName]: config },
    });
  }

  async removeLocalRepository(repoName: string): Promise<void> {
    const name = this.getEffectiveContextName();
    const context = await this.requireLocalOrS3Mode(name);

    if (context.mode === 's3') {
      const s3 = await this.getS3State();
      const repos = s3.getRepositories();
      if (!(repoName in repos)) throw new Error(`Repository "${repoName}" not found`);
      delete repos[repoName];
      await s3.setRepositories(repos);
      return;
    }

    if (!context.repositories?.[repoName]) {
      throw new Error(`Repository "${repoName}" not found`);
    }
    const remaining = { ...context.repositories };
    delete remaining[repoName];
    await this.update(name, { repositories: remaining });
  }

  async listLocalRepositories(): Promise<{ name: string; config: RepositoryConfig }[]> {
    const context = await this.requireLocalOrS3Mode();

    if (context.mode === 's3') {
      const s3 = await this.getS3State();
      return Object.entries(s3.getRepositories()).map(([name, config]) => ({
        name,
        config,
      }));
    }

    return Object.entries(context.repositories ?? {}).map(([repoName, config]) => ({
      name: repoName,
      config,
    }));
  }

  async getRepositoryGuidMap(): Promise<Record<string, string>> {
    const context = await this.getCurrent();
    let repos: Record<string, RepositoryConfig> | undefined;

    if (context?.mode === 's3') {
      const s3 = await this.getS3State();
      repos = s3.getRepositories();
    } else {
      repos = context?.repositories;
    }

    if (!repos) return {};
    const map: Record<string, string> = {};
    for (const [repoName, config] of Object.entries(repos)) {
      const tag = config.tag ?? DEFAULTS.REPOSITORY.TAG;
      map[config.repositoryGuid] = `${repoName}:${tag}`;
    }
    return map;
  }

  async getRepositoryCredentials(): Promise<Record<string, string>> {
    const context = await this.getCurrent();
    let repos: Record<string, RepositoryConfig> | undefined;

    if (context?.mode === 's3') {
      const s3 = await this.getS3State();
      repos = s3.getRepositories();
    } else {
      repos = context?.repositories;
    }

    if (!repos) return {};
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

    if (context?.mode === 's3') {
      const s3 = await this.getS3State();
      return s3.getRepositories()[repoName];
    }

    return context?.repositories?.[repoName];
  }

  // ============================================================================
  // Backup Configuration
  // ============================================================================

  async setBackupConfig(config: Partial<BackupConfig>): Promise<void> {
    const name = this.getEffectiveContextName();
    const context = await this.requireLocalOrS3Mode(name);
    const backup: BackupConfig = {
      defaultDestination: '',
      ...context.backup,
      ...config,
    };
    await this.update(name, { backup });
  }

  async getBackupConfig(): Promise<BackupConfig | undefined> {
    const context = await this.requireLocalOrS3Mode();
    return context.backup;
  }

  // ============================================================================
  // Network ID Allocation
  // ============================================================================

  private computeNextNetworkId(repositories: Record<string, RepositoryConfig>): number {
    const usedIds = Object.values(repositories)
      .map((r) => r.networkId)
      .filter((id): id is number => id !== undefined && id > 0);

    if (usedIds.length === 0) return MIN_NETWORK_ID;
    return Math.max(...usedIds) + NETWORK_ID_INCREMENT;
  }

  async allocateNetworkId(): Promise<number> {
    const context = await this.requireLocalOrS3Mode();

    if (context.mode === 's3') {
      const s3 = await this.getS3State();
      return this.computeNextNetworkId(s3.getRepositories());
    }

    return this.computeNextNetworkId(context.repositories ?? {});
  }

  async ensureRepositoryNetworkId(repoName: string): Promise<number> {
    const name = this.getEffectiveContextName();
    const context = await this.requireLocalOrS3Mode(name);

    if (context.mode === 's3') {
      const s3 = await this.getS3State();
      const repos = s3.getRepositories();
      if (!(repoName in repos)) throw new Error(`Repository "${repoName}" not found`);
      const repo = repos[repoName];
      if (repo.networkId !== undefined && repo.networkId > 0) return repo.networkId;

      const networkId = this.computeNextNetworkId(repos);
      repos[repoName] = { ...repo, networkId };
      await s3.setRepositories(repos);
      return networkId;
    }

    const repo = context.repositories?.[repoName];
    if (!repo) {
      throw new Error(`Repository "${repoName}" not found`);
    }

    if (repo.networkId !== undefined && repo.networkId > 0) {
      return repo.networkId;
    }

    const networkId = this.computeNextNetworkId(context.repositories ?? {});
    await this.update(name, {
      repositories: {
        ...context.repositories,
        [repoName]: { ...repo, networkId },
      },
    });

    return networkId;
  }
}

export const contextService = new ContextService();
