import {
  parseGetOrganizationTeams,
  parseGetOrganizationVault,
  parseGetRegionBridges,
  parseGetTeamMachines,
  parseGetTeamRepositories,
  parseGetTeamStorages,
} from '@rediacc/shared/api';
import {
  type FunctionRequirements,
  parseVaultContent,
  type QueueRequestContext,
  QueueVaultBuilder,
  type QueueVaultBuilderConfig,
} from '@rediacc/shared/queue-vault';
import type {
  GetOrganizationTeams_ResultSet1,
  GetRegionBridges_ResultSet1,
  GetTeamMachines_ResultSet1,
  GetTeamRepositories_ResultSet1,
  GetTeamStorages_ResultSet1,
} from '@rediacc/shared/types';
import { apiClient, typedApi } from './api.js';

/** Generic vault data type for parsed vault content */
type ParsedVaultData = Record<string, unknown>;

interface FetchedVaults {
  organizationVault?: ParsedVaultData;
  teamVault?: ParsedVaultData;
  machineVault?: ParsedVaultData;
  vaultContent?: ParsedVaultData;
  storageVault?: ParsedVaultData;
  bridgeVault?: ParsedVaultData;
}

async function fetchOrganizationVault(): Promise<ParsedVaultData | undefined> {
  try {
    const response = await typedApi.GetOrganizationVault({});
    const vault = parseGetOrganizationVault(response as never);
    return parseVaultContent<ParsedVaultData>(vault?.vaultContent) ?? undefined;
  } catch {
    return undefined;
  }
}

async function fetchTeamVault(teamName: string): Promise<ParsedVaultData | undefined> {
  try {
    const response = await typedApi.GetOrganizationTeams({});
    const teams = parseGetOrganizationTeams(response as never);
    const team = teams.find((t: GetOrganizationTeams_ResultSet1) => t.teamName === teamName);
    return parseVaultContent<ParsedVaultData>(team?.vaultContent) ?? undefined;
  } catch {
    return undefined;
  }
}

async function fetchMachineVault(
  teamName: string,
  machineName: string
): Promise<ParsedVaultData | undefined> {
  try {
    const response = await typedApi.GetTeamMachines({ teamName });
    const machines = parseGetTeamMachines(response as never);
    const machine = machines.find((m: GetTeamMachines_ResultSet1) => m.machineName === machineName);
    return parseVaultContent<ParsedVaultData>(machine?.vaultContent) ?? undefined;
  } catch {
    return undefined;
  }
}

async function fetchRepositoryVault(
  teamName: string,
  repositoryGuid: string
): Promise<ParsedVaultData | undefined> {
  try {
    const response = await typedApi.GetTeamRepositories({ teamName });
    const repositories = parseGetTeamRepositories(response as never);
    const repository = repositories.find(
      (r: GetTeamRepositories_ResultSet1) => r.repositoryGuid === repositoryGuid
    );
    const vaultContent = parseVaultContent<ParsedVaultData>(repository?.vaultContent);
    if (!vaultContent) return undefined;

    if (repository?.repositoryNetworkId !== undefined) {
      (vaultContent as Record<string, unknown>).repositoryNetworkId =
        repository.repositoryNetworkId;
    }
    if (repository?.repositoryNetworkMode) {
      (vaultContent as Record<string, unknown>).networkMode = repository.repositoryNetworkMode;
    }
    return vaultContent;
  } catch {
    return undefined;
  }
}

async function fetchStorageVault(
  teamName: string,
  storageName: string
): Promise<ParsedVaultData | undefined> {
  try {
    const response = await typedApi.GetTeamStorages({ teamName });
    const storageList = parseGetTeamStorages(response as never);
    const storage = storageList.find(
      (s: GetTeamStorages_ResultSet1) => s.storageName === storageName
    );
    return parseVaultContent<ParsedVaultData>(storage?.vaultContent) ?? undefined;
  } catch {
    return undefined;
  }
}

async function fetchBridgeVault(
  regionName: string,
  bridgeName: string
): Promise<ParsedVaultData | undefined> {
  try {
    const response = await typedApi.GetRegionBridges({ regionName });
    const bridges = parseGetRegionBridges(response as never);
    const bridge = bridges.find((b: GetRegionBridges_ResultSet1) => b.bridgeName === bridgeName);
    return parseVaultContent<ParsedVaultData>(bridge?.vaultContent) ?? undefined;
  } catch {
    return undefined;
  }
}

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
  ): Promise<FetchedVaults> {
    const vaults: FetchedVaults = {};

    // Organization vault is always fetched (optional)
    vaults.organizationVault = await fetchOrganizationVault();

    if (requirements.team) {
      vaults.teamVault = await fetchTeamVault(context.teamName);
    }

    if (requirements.machine && context.machineName) {
      vaults.machineVault = await fetchMachineVault(context.teamName, context.machineName);
    }

    if (requirements.repository && context.params.repository) {
      const repositoryGuid = context.params.repository as string;
      vaults.vaultContent = await fetchRepositoryVault(context.teamName, repositoryGuid);
    }

    if (requirements.storage) {
      const storageName = this.resolveStorageName(context.params);
      if (storageName) {
        vaults.storageVault = await fetchStorageVault(context.teamName, storageName);
      }
    }

    if (requirements.bridge && context.bridgeName && context.regionName) {
      vaults.bridgeVault = await fetchBridgeVault(context.regionName, context.bridgeName);
    }

    return vaults;
  }

  private resolveStorageName(params: Record<string, unknown>): string | undefined {
    const storages = params.storages;
    const firstStorage = Array.isArray(storages) ? storages[0] : undefined;
    return (params.to ?? params.from ?? firstStorage) as string | undefined;
  }
}

export const queueService = new CliQueueService();
