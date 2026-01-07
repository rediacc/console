import {
  parseGetOrganizationVault,
  parseGetOrganizationTeams,
  parseGetTeamMachines,
  parseGetTeamRepositories,
  parseGetTeamStorages,
  parseGetRegionBridges,
} from '@rediacc/shared/api';
import {
  type FunctionRequirements,
  type QueueRequestContext,
  QueueVaultBuilder,
  type QueueVaultBuilderConfig,
  parseVaultContent,
} from '@rediacc/shared/queue-vault';
import type {
  GetOrganizationTeams_ResultSet1,
  GetRegionBridges_ResultSet1,
  GetTeamMachines_ResultSet1,
  GetTeamRepositories_ResultSet1,
  GetTeamStorages_ResultSet1,
} from '@rediacc/shared/types';
import { typedApi, apiClient } from './api.js';

/** Generic vault data type for parsed vault content */
type ParsedVaultData = Record<string, unknown>;

interface MachineContext {
  ip: string;
  user: string;
  port?: number;
  datastore?: string;
  ssh_password?: string;
}

interface QueueContext {
  teamName: string;
  machineName?: string;
  bridgeName?: string;
  regionName?: string;
  functionName: string;
  params: Record<string, unknown>;
  priority: number;
  /** Direct machine context for test-connection (bypasses vault lookup) */
  machineContext?: MachineContext;
  /** User's preferred language for task output (en, de, es, fr, ja, ar, ru, tr, zh) */
  language?: string;
}

class CliQueueService {
  private createBuilder(apiUrl: string): QueueVaultBuilder {
    const builderConfig: QueueVaultBuilderConfig = {
      getApiUrl: () => apiUrl,
      encodeBase64: (value: string) => Buffer.from(value, 'utf-8').toString('base64'),
      validateParams: true,
      validateConnections: true,
    };
    return new QueueVaultBuilder(builderConfig);
  }

  getFunctionRequirements(functionName: string): FunctionRequirements {
    // Create a temporary builder just for getting requirements (doesn't need API URL)
    const builder = this.createBuilder('');
    return builder.getFunctionRequirements(functionName);
  }

  async buildQueueVault(context: QueueContext): Promise<string> {
    // Resolve API URL before building vault
    const apiUrl = await apiClient.getApiUrl();
    const builder = this.createBuilder(apiUrl);

    const requirements = this.getFunctionRequirements(context.functionName);
    const vaults = await this.fetchRequiredVaults(context, requirements);

    // If machineContext is provided directly, use it instead of fetched vault
    // This is used for ssh_test to test connections to new machines
    let machineVault = vaults.machineVault;
    if (context.machineContext) {
      const directMachineVault: ParsedVaultData = {
        ip: context.machineContext.ip,
        user: context.machineContext.user,
        port: context.machineContext.port,
        datastore: context.machineContext.datastore,
        ssh_password: context.machineContext.ssh_password,
      };
      machineVault = directMachineVault;
    }

    const requestContext: QueueRequestContext = {
      teamName: context.teamName,
      machineName: context.machineName,
      bridgeName: context.bridgeName,
      functionName: context.functionName,
      params: context.params,
      priority: context.priority,
      addedVia: 'cli',
      teamVault: vaults.teamVault,
      machineVault,
      repositoryVault: vaults.vaultContent,
      organizationVault: vaults.organizationVault,
      storageVault: vaults.storageVault,
      bridgeVault: vaults.bridgeVault,
      repositoryGuid: context.params.repository as string | undefined,
      repositoryNetworkId: (vaults.vaultContent as { repositoryNetworkId?: number } | undefined)
        ?.repositoryNetworkId,
      repositoryNetworkMode: (vaults.vaultContent as { networkMode?: string } | undefined)
        ?.networkMode,
      storageName: (context.params.to ?? context.params.from) as string | undefined,
      language: context.language,
    };

    return builder.buildQueueVault(requestContext);
  }

  private async fetchRequiredVaults(
    context: QueueContext,
    requirements: FunctionRequirements
  ): Promise<{
    organizationVault?: ParsedVaultData;
    teamVault?: ParsedVaultData;
    machineVault?: ParsedVaultData;
    vaultContent?: ParsedVaultData;
    storageVault?: ParsedVaultData;
    bridgeVault?: ParsedVaultData;
  }> {
    const vaults: {
      organizationVault?: ParsedVaultData;
      teamVault?: ParsedVaultData;
      machineVault?: ParsedVaultData;
      vaultContent?: ParsedVaultData;
      storageVault?: ParsedVaultData;
      bridgeVault?: ParsedVaultData;
    } = {};

    try {
      const response = await typedApi.GetOrganizationVault({});
      const organizationVault = parseGetOrganizationVault(response as never);
      const parsed = parseVaultContent<ParsedVaultData>(organizationVault?.vaultContent);
      if (parsed) {
        vaults.organizationVault = parsed;
      }
    } catch {
      // Ignore organization vault failures - optional context
    }

    if (requirements.team) {
      try {
        const response = await typedApi.GetOrganizationTeams({});
        const teams = parseGetOrganizationTeams(response as never);
        const team = teams.find(
          (t: GetOrganizationTeams_ResultSet1) => t.teamName === context.teamName
        );
        const parsed = parseVaultContent<ParsedVaultData>(team?.vaultContent);
        if (parsed) {
          vaults.teamVault = parsed;
        }
      } catch {
        // Team vault fetch failed
      }
    }

    if (requirements.machine && context.machineName) {
      try {
        const response = await typedApi.GetTeamMachines({ teamName: context.teamName });
        const machines = parseGetTeamMachines(response as never);
        const machine = machines.find(
          (m: GetTeamMachines_ResultSet1) => m.machineName === context.machineName
        );
        const parsed = parseVaultContent<ParsedVaultData>(machine?.vaultContent);
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
        const response = await typedApi.GetTeamRepositories({ teamName: context.teamName });
        const repositories = parseGetTeamRepositories(response as never);
        const repository = repositories.find(
          (r: GetTeamRepositories_ResultSet1) => r.repositoryGuid === repositoryGuid
        );
        const vaultContent = parseVaultContent<ParsedVaultData>(repository?.vaultContent);
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
      const storageName = (context.params.to ?? context.params.from ?? firstStorage) as
        | string
        | undefined;
      if (storageName) {
        try {
          const response = await typedApi.GetTeamStorages({ teamName: context.teamName });
          const storageList = parseGetTeamStorages(response as never);
          const storage = storageList.find(
            (s: GetTeamStorages_ResultSet1) => s.storageName === storageName
          );
          const parsed = parseVaultContent<ParsedVaultData>(storage?.vaultContent);
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
        const response = await typedApi.GetRegionBridges({ regionName: context.regionName });
        const bridges = parseGetRegionBridges(response as never);
        const bridge = bridges.find(
          (b: GetRegionBridges_ResultSet1) => b.bridgeName === context.bridgeName
        );
        const parsed = parseVaultContent<ParsedVaultData>(bridge?.vaultContent);
        if (parsed) {
          vaults.bridgeVault = parsed;
        }
      } catch {
        // Bridge vault fetch failed
      }
    }

    return vaults;
  }
}

export const queueService = new CliQueueService();
