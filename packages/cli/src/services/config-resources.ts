/**
 * Resource CRUD methods for self-hosted (local/S3) configs.
 * Extends ConfigServiceBase with machine, storage, repository, and network ID management.
 * All resource access goes through ResourceState, eliminating mode-specific branches.
 */

import { promises as fs } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { DEFAULTS } from '@rediacc/shared/config';
import { MIN_NETWORK_ID, NETWORK_ID_INCREMENT } from '@rediacc/shared/queue-vault';
import {
  addMachineSSHConfigEntry,
  removeMachineSSHConfigEntry,
} from '@rediacc/shared-desktop/vscode';
import { configFileStorage } from '../adapters/config-file-storage.js';
import { t } from '../i18n/index.js';
import type {
  ArchivedRepository,
  BackupStrategyConfig,
  BackupStrategyDestination,
  CloudProviderConfig,
  InfraConfig,
  MachineConfig,
  RdcConfig,
  RepositoryConfig,
  StorageConfig,
} from '../types/index.js';
import { hasCloudCredentials } from '../types/index.js';
import { ConfigServiceBase } from './config-base.js';
import { findFreeNetworkIdSlot, pickInitialNetworkId } from './config-network-id.js';
import {
  assertRestoredForkKeyIsExplicit,
  buildCredentialsMap,
  buildGuidMap,
  resolveDestructiveTargetFromRepos,
  resolveExactOrLatest,
} from './config-resources-resolve.js';
import { outputService } from './output.js';

export { AmbiguousRepoTargetError } from './config-resources-resolve.js';

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
    ssh: { privateKeyPath: string; publicKeyPath?: string };
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
    let sshPrivateKey = sshContent?.privateKey;
    let sshPublicKey = sshContent?.publicKey;
    // Fall back to the standard local SSH key when none is configured (e.g. a
    // config auto-created without `rdc config init --ssh-key`). Keeps the
    // common case zero-config: if ~/.ssh/id_rsa (or id_ed25519) exists, use it.
    if (!sshPrivateKey) {
      const sshDir = path.join(os.homedir(), '.ssh');
      for (const name of ['id_rsa', 'id_ed25519']) {
        const keyPath = path.join(sshDir, name);
        try {
          sshPrivateKey = await fs.readFile(keyPath, 'utf-8');
          sshPublicKey = await fs.readFile(`${keyPath}.pub`, 'utf-8').catch(() => undefined);
          break;
        } catch {
          // try the next default key
        }
      }
    }
    if (!sshPrivateKey) {
      throw new Error(
        `Config "${configName}" has no SSH key configured and no default key found at ~/.ssh/id_rsa or ~/.ssh/id_ed25519`
      );
    }

    return {
      machines,
      ssh: { privateKeyPath: '' },
      sshPrivateKey,
      sshPublicKey,
      renetPath: config.renetPath ?? DEFAULTS.CONTEXT.RENET_BINARY,
      cfDnsApiToken: config.credentials?.cfDnsApiToken,
      cfDnsZoneId: config.infra?.cfDnsZoneId,
      certEmail: config.infra?.certEmail,
      datastoreSize: config.defaults?.datastoreSize,
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
    try {
      addMachineSSHConfigEntry({
        machineName,
        host: config.ip,
        port: config.port ?? DEFAULTS.SSH.PORT,
        sshUser: config.user,
        datastore: config.datastore,
      });
      outputService.info(t('commands.config.machine.add.sshConfigWritten', { name: machineName }));
    } catch (err) {
      outputService.warn(t('commands.config.machine.add.sshConfigFailed', { error: String(err) }));
    }
  }

  async removeMachine(machineName: string): Promise<void> {
    await this.requireSelfHosted();
    const state = await this.getResourceState();
    const machines = state.getMachines();
    if (!(machineName in machines)) throw new Error(`Machine "${machineName}" not found`);
    delete machines[machineName];
    await state.setMachines(machines);
    try {
      removeMachineSSHConfigEntry(machineName);
    } catch {
      /* non-fatal */
    }
    outputService.info(t('commands.config.machine.remove.sshConfigCleared', { name: machineName }));
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

  async setRenetPath(renetPath: string): Promise<void> {
    const name = this.getEffectiveConfigName();
    await this.requireSelfHosted(name);
    await configFileStorage.update(name, (cfg) => ({ ...cfg, renetPath }));
  }

  async updateConfigFields(updates: {
    cfDnsApiToken?: string;
    cfDnsZoneId?: string;
    certEmail?: string;
    acmeCertCache?: RdcConfig['infra'] extends infer I
      ? I extends { acmeCertCache?: infer A }
        ? A
        : never
      : never;
  }): Promise<void> {
    const name = this.getEffectiveConfigName();
    await this.requireSelfHosted(name);
    await configFileStorage.update(name, (cfg) => ({
      ...cfg,
      credentials:
        'cfDnsApiToken' in updates
          ? { ...(cfg.credentials ?? {}), cfDnsApiToken: updates.cfDnsApiToken }
          : cfg.credentials,
      infra: {
        ...(cfg.infra ?? {}),
        ...('cfDnsZoneId' in updates ? { cfDnsZoneId: updates.cfDnsZoneId } : {}),
        ...('certEmail' in updates ? { certEmail: updates.certEmail } : {}),
        ...('acmeCertCache' in updates ? { acmeCertCache: updates.acmeCertCache } : {}),
      },
    }));
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
    if (!(storageName in storages))
      throw new Error(
        `Storage "${storageName}" not found. Available: ${Object.keys(storages).join(', ') || 'none'}`
      );
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
    return buildGuidMap(state.getRepositories());
  }

  async getRepositoryCredentials(): Promise<Record<string, string>> {
    const config = await this.getCurrent();
    if (!config || hasCloudCredentials(config)) return {};
    const state = await this.getResourceState();
    return buildCredentialsMap(state.getRepositories());
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
    const key = resolveExactOrLatest(repos, repoRef, !repoRef.includes(':'));
    return key ? repos[key] : undefined;
  }

  /**
   * Resolve a repository reference to its actual config dictionary key.
   * Needed for mutation operations (remove, update networkId, etc.).
   */
  async getRepositoryKey(repoRef: string): Promise<string | undefined> {
    const config = await this.getCurrent();
    if (!config || hasCloudCredentials(config)) return undefined;
    const state = await this.getResourceState();
    return resolveExactOrLatest(state.getRepositories(), repoRef, !repoRef.includes(':'));
  }

  /**
   * Strict resolver for destructive commands (repo delete, repo takeover,
   * config repository remove, datastore unfork). Fails closed on ambiguity
   * so a bare `--name` cannot silently hit the wrong repo. See issue #495.
   *
   * - Exact-key match wins (same as `getRepositoryKey`).
   * - For a bare ref, refuses when more than one config key shares the base
   *   name, even if the `:latest` fallback would otherwise resolve.
   * - For a bare ref that resolves to a fork (grandGuid set and !== guid),
   *   refuses — the operator must say `<name>:<tag>` explicitly so we do not
   *   destroy a fork registered in the grand slot by mistake.
   */
  async resolveDestructiveTarget(
    repoRef: string
  ): Promise<{ key: string; config: RepositoryConfig }> {
    const config = await this.getCurrent();
    if (!config || hasCloudCredentials(config))
      throw new Error(`Repository "${repoRef}" not found in context`);
    return resolveDestructiveTargetFromRepos(
      (await this.getResourceState()).getRepositories(),
      repoRef
    );
  }

  /**
   * List all tags for a given base repository name.
   */
  async listRepositoriesByName(
    baseName: string
  ): Promise<{ key: string; tag: string; config: RepositoryConfig }[]> {
    const { parseRepoRef } = await import('../utils/config-schema.js');
    const repos = await this.listRepositories();
    return repos.flatMap((r) => {
      const ref = parseRepoRef(r.name);
      return ref.name === baseName ? [{ key: r.name, tag: ref.tag, config: r.config }] : [];
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

    // Scrub `secrets` from the archived entry. Archives exist to preserve
    // identity (repositoryGuid + LUKS credential for backup decryption);
    // deploy-time secrets are out of scope and would otherwise survive a
    // delete-then-restore cycle. ArchivedRepositorySchema.omit({secrets})
    // mirrors this at the schema layer.
    const scrubbed = { ...repos[repoName] };
    delete scrubbed.secrets;
    const archived: ArchivedRepository = {
      ...scrubbed,
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
    assertRestoredForkKeyIsExplicit(archived, restoredName);

    const repos = state.getRepositories();
    if (restoredName in repos)
      throw new Error(
        `Repository "${restoredName}" already exists. Use --name to specify a different name.`
      );
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
    const isExpired = (r: ArchivedRepository) => new Date(r.deletedAt).getTime() < cutoff;
    const expired = all.filter(isExpired);
    if (expired.length > 0) await state.setDeletedRepositories(all.filter((r) => !isExpired(r)));
    return expired;
  }

  // ============================================================================
  // Backup Strategy
  // ============================================================================

  async getBackupStrategy(strategyName: string): Promise<BackupStrategyConfig | undefined> {
    const config = await this.requireSelfHosted();
    return config.resources?.backupStrategies?.[strategyName];
  }

  async listBackupStrategies(): Promise<Record<string, BackupStrategyConfig>> {
    const config = await this.requireSelfHosted();
    return config.resources?.backupStrategies ?? {};
  }

  async setBackupStrategy(
    strategyName: string,
    update: Partial<BackupStrategyConfig>
  ): Promise<void> {
    const configName = this.getEffectiveConfigName();
    const current = await this.requireSelfHosted(configName);
    const strategies: Record<string, BackupStrategyConfig> = {
      ...(current.resources?.backupStrategies ?? {}),
    };
    const existing = strategies[strategyName] ?? { destinations: [], schedule: '' };
    strategies[strategyName] = { ...existing, ...update };
    await configFileStorage.update(configName, (cfg) => ({
      ...cfg,
      resources: { ...(cfg.resources ?? {}), backupStrategies: strategies },
    }));
  }

  async removeBackupStrategy(strategyName: string): Promise<void> {
    const configName = this.getEffectiveConfigName();
    const current = await this.requireSelfHosted(configName);
    const strategies: Record<string, BackupStrategyConfig> = {
      ...(current.resources?.backupStrategies ?? {}),
    };
    delete strategies[strategyName];
    await configFileStorage.update(configName, (cfg) => ({
      ...cfg,
      resources: { ...(cfg.resources ?? {}), backupStrategies: strategies },
    }));
  }

  async addBackupDestination(strategyName: string, dest: BackupStrategyDestination): Promise<void> {
    const configName = this.getEffectiveConfigName();
    const current = await this.requireSelfHosted(configName);
    const strategies: Record<string, BackupStrategyConfig> = {
      ...(current.resources?.backupStrategies ?? {}),
    };
    if (!Object.hasOwn(strategies, strategyName)) {
      throw new Error(
        `Backup strategy "${strategyName}" not found. Create it first with: rdc config backup-strategy set --name ${strategyName} --cron "..."`
      );
    }
    const strategy = strategies[strategyName];
    const destinations = [...strategy.destinations];
    const idx = destinations.findIndex((d) => d.name === dest.name);
    if (idx >= 0) destinations[idx] = { ...destinations[idx], ...dest };
    else destinations.push(dest);
    destinations.sort((a, b) => a.name.localeCompare(b.name));
    strategies[strategyName] = { ...strategy, destinations };
    await configFileStorage.update(configName, (cfg) => ({
      ...cfg,
      resources: { ...(cfg.resources ?? {}), backupStrategies: strategies },
    }));
  }

  async removeBackupDestination(strategyName: string, destName: string): Promise<void> {
    const configName = this.getEffectiveConfigName();
    const current = await this.requireSelfHosted(configName);
    const strategies: Record<string, BackupStrategyConfig> = {
      ...(current.resources?.backupStrategies ?? {}),
    };
    if (!Object.hasOwn(strategies, strategyName)) return;
    const strategy = strategies[strategyName];
    strategies[strategyName] = {
      ...strategy,
      destinations: strategy.destinations.filter((d) => d.name !== destName),
    };
    await configFileStorage.update(configName, (cfg) => ({
      ...cfg,
      resources: { ...(cfg.resources ?? {}), backupStrategies: strategies },
    }));
  }

  // ============================================================================
  // Cloud Provider CRUD
  // ============================================================================

  async addCloudProvider(name: string, config: CloudProviderConfig): Promise<void> {
    const configName = this.getEffectiveConfigName();
    await this.requireSelfHosted(configName);
    await configFileStorage.update(configName, (cfg) => ({
      ...cfg,
      resources: {
        ...(cfg.resources ?? {}),
        cloudProviders: { ...(cfg.resources?.cloudProviders ?? {}), [name]: config },
      },
    }));
  }

  async removeCloudProvider(name: string): Promise<void> {
    const configName = this.getEffectiveConfigName();
    await this.requireSelfHosted(configName);
    await configFileStorage.update(configName, (cfg) => {
      const providers = { ...(cfg.resources?.cloudProviders ?? {}) };
      if (!(name in providers)) throw new Error(`Cloud provider "${name}" not found`);
      delete providers[name];
      return { ...cfg, resources: { ...(cfg.resources ?? {}), cloudProviders: providers } };
    });
  }

  async listCloudProviders(): Promise<{ name: string; config: CloudProviderConfig }[]> {
    const config = await this.getCurrent();
    if (!config?.resources?.cloudProviders) return [];
    return Object.entries(config.resources.cloudProviders)
      .map(([name, providerConfig]) => ({ name, config: providerConfig }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }

  // ============================================================================
  // Network ID Allocation (per config file)
  // ============================================================================

  private scanUsedNetworkIds(config: RdcConfig): Set<number> {
    const usedIds = new Set<number>();
    const repos = config.resources?.repositories;
    if (repos) {
      for (const repo of Object.values(repos)) {
        if (repo.networkId !== undefined && repo.networkId > 0) {
          usedIds.add(repo.networkId);
        }
      }
    }
    return usedIds;
  }

  async allocateNetworkId(): Promise<number> {
    // Network ID space: 2816 to ~16,777,152, step 64 → ~261,944 possible IDs.
    const MAX_NETWORK_ID = 16_711_680;

    const name = this.getEffectiveConfigName();
    let allocated = 0;
    await configFileStorage.update(name, (config) => {
      const usedIds = this.scanUsedNetworkIds(config);
      let nextId = config.defaults?.nextNetworkId;

      if (nextId === undefined || nextId < MIN_NETWORK_ID) {
        nextId = pickInitialNetworkId(usedIds);
      }

      // If the forward counter is approaching the limit, scan for freed gaps.
      // This handles long-running systems where many repos have been created and deleted.
      if (nextId > MAX_NETWORK_ID) {
        nextId = findFreeNetworkIdSlot(usedIds, MAX_NETWORK_ID);
      }

      allocated = nextId;
      return {
        ...config,
        defaults: { ...(config.defaults ?? {}), nextNetworkId: nextId + NETWORK_ID_INCREMENT },
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
