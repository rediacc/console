import {
  type FunctionRequirements,
  type QueueRequestContext,
  QueueVaultBuilder,
  type QueueVaultBuilderConfig,
  type VaultData,
} from '@rediacc/shared/queue-vault';
import type {
  GetCompanyTeams_ResultSet1,
  GetRegionBridges_ResultSet1,
  GetTeamMachines_ResultSet1,
  GetTeamRepositories_ResultSet1,
  GetTeamStorages_ResultSet1,
} from '@rediacc/shared/types';
import { api, apiClient } from './api.js';

interface QueueContext {
  teamName: string;
  machineName?: string;
  bridgeName?: string;
  regionName?: string;
  functionName: string;
  params: Record<string, unknown>;
  priority: number;
}

export class CliQueueService {
  private builder: QueueVaultBuilder;

  constructor() {
    const builderConfig: QueueVaultBuilderConfig = {
      getApiUrl: () => apiClient.getApiUrl(),
      encodeBase64: (value: string) => Buffer.from(value, 'utf-8').toString('base64'),
    };
    this.builder = new QueueVaultBuilder(builderConfig);
  }

  getFunctionRequirements(functionName: string): FunctionRequirements {
    return this.builder.getFunctionRequirements(functionName);
  }

  async buildQueueVault(context: QueueContext): Promise<string> {
    const requirements = this.getFunctionRequirements(context.functionName);
    const vaults = await this.fetchRequiredVaults(context, requirements);

    const requestContext: QueueRequestContext = {
      teamName: context.teamName,
      machineName: context.machineName,
      bridgeName: context.bridgeName,
      functionName: context.functionName,
      params: context.params,
      priority: context.priority,
      addedVia: 'cli',
      teamVault: vaults.teamVault,
      machineVault: vaults.machineVault,
      repositoryVault: vaults.vaultContent,
      companyVault: vaults.companyVault,
      storageVault: vaults.storageVault,
      bridgeVault: vaults.bridgeVault,
      repositoryGuid: context.params.repository as string | undefined,
      repositoryNetworkId: (vaults.vaultContent as { repositoryNetworkId?: number })
        ?.repositoryNetworkId,
      repositoryNetworkMode: (vaults.vaultContent as { networkMode?: string })?.networkMode,
      storageName: (context.params.to || context.params.from) as string | undefined,
    };

    return this.builder.buildQueueVault(requestContext);
  }

  private async fetchRequiredVaults(
    context: QueueContext,
    requirements: FunctionRequirements
  ): Promise<{
    companyVault?: VaultData;
    teamVault?: VaultData;
    machineVault?: VaultData;
    vaultContent?: VaultData;
    storageVault?: VaultData;
    bridgeVault?: VaultData;
  }> {
    const vaults: {
      companyVault?: VaultData;
      teamVault?: VaultData;
      machineVault?: VaultData;
      vaultContent?: VaultData;
      storageVault?: VaultData;
      bridgeVault?: VaultData;
    } = {};

    try {
      const companyVault = await api.company.getVault();
      const parsed = this.parseVaultContent(companyVault.vault);
      if (parsed) {
        vaults.companyVault = parsed;
      }
    } catch {
      // Ignore company vault failures - optional context
    }

    if (requirements.team) {
      try {
        const teams = await api.teams.list();
        const team = teams.find((t: GetCompanyTeams_ResultSet1) => t.teamName === context.teamName);
        const parsed = this.parseVaultContent(team?.vaultContent);
        if (parsed) {
          vaults.teamVault = parsed;
        }
      } catch {
        // Team vault fetch failed
      }
    }

    if (requirements.machine && context.machineName) {
      try {
        const machines = await api.machines.list(context.teamName);
        const machine = machines.find(
          (m: GetTeamMachines_ResultSet1) => m.machineName === context.machineName
        );
        const parsed = this.parseVaultContent(machine?.vaultContent);
        if (parsed) {
          vaults.machineVault = parsed;
        }
      } catch {
        // Machine vault fetch failed
      }
    }

    if (requirements.repository && context.params.repository) {
      try {
        const repositoryGuid = context.params.repository as string;
        const repositories = await api.repositories.list({ teamName: context.teamName });
        const repository = repositories.find(
          (r: GetTeamRepositories_ResultSet1) => r.repositoryGuid === repositoryGuid
        );
        const vaultContent = this.parseVaultContent(repository?.vaultContent);
        if (vaultContent) {
          if (repository?.repositoryNetworkId !== undefined) {
            (vaultContent as Record<string, unknown>).repositoryNetworkId =
              repository.repositoryNetworkId;
          }
          if (repository?.repositoryNetworkMode) {
            (vaultContent as Record<string, unknown>).networkMode =
              repository.repositoryNetworkMode;
          }
          vaults.vaultContent = vaultContent;
        }
      } catch {
        // Repository vault fetch failed
      }
    }

    if (requirements.storage) {
      const storages = context.params.storages;
      const firstStorage = Array.isArray(storages) ? storages[0] : undefined;
      const storageName = (context.params.to || context.params.from || firstStorage) as
        | string
        | undefined;
      if (storageName) {
        try {
          const storageList = await api.storage.list({ teamName: context.teamName });
          const storage = storageList.find(
            (s: GetTeamStorages_ResultSet1) => s.storageName === storageName
          );
          const parsed = this.parseVaultContent(storage?.vaultContent);
          if (parsed) {
            vaults.storageVault = parsed;
          }
        } catch {
          // Storage vault fetch failed
        }
      }
    }

    if (requirements.bridge && context.bridgeName && context.regionName) {
      try {
        const bridges = await api.regions.getBridges({ regionName: context.regionName });
        const bridge = bridges.find(
          (b: GetRegionBridges_ResultSet1) => b.bridgeName === context.bridgeName
        );
        const parsed = this.parseVaultContent(bridge?.vaultContent);
        if (parsed) {
          vaults.bridgeVault = parsed;
        }
      } catch {
        // Bridge vault fetch failed
      }
    }

    return vaults;
  }

  private parseVaultContent(
    value?: string | Record<string, unknown> | null
  ): VaultData | undefined {
    if (!value) {
      return undefined;
    }

    if (typeof value === 'string') {
      try {
        return JSON.parse(value) as VaultData;
      } catch {
        return undefined;
      }
    }

    return value as VaultData;
  }
}

export const queueService = new CliQueueService();
