import {
  QueueVaultBuilder,
  type QueueVaultBuilderConfig,
  type QueueRequestContext,
  type FunctionRequirements,
  type VaultData,
} from '@rediacc/queue-vault'
import { apiClient } from './api.js'

interface QueueContext {
  teamName: string
  machineName?: string
  bridgeName?: string
  functionName: string
  params: Record<string, unknown>
  priority: number
}

export class CliQueueService {
  private builder: QueueVaultBuilder

  constructor() {
    const builderConfig: QueueVaultBuilderConfig = {
      getApiUrl: () => apiClient.getApiUrl(),
      encodeBase64: (value: string) => Buffer.from(value, 'utf-8').toString('base64'),
    }
    this.builder = new QueueVaultBuilder(builderConfig)
  }

  getFunctionRequirements(functionName: string): FunctionRequirements {
    return this.builder.getFunctionRequirements(functionName)
  }

  async buildQueueVault(context: QueueContext): Promise<string> {
    // Fetch required vaults (CLI-specific)
    const requirements = this.getFunctionRequirements(context.functionName)
    const vaults = await this.fetchRequiredVaults(context, requirements)

    // Build QueueRequestContext from CLI context + fetched vaults
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
      repositoryVault: vaults.repositoryVault,
      companyVault: vaults.companyVault,
      storageVault: vaults.storageVault,
      bridgeVault: vaults.bridgeVault,
      repositoryGuid: context.params.repo as string | undefined,
      repositoryLoopbackIp: (vaults.repositoryVault as { repoLoopbackIp?: string })?.repoLoopbackIp,
      repositoryNetworkMode: (vaults.repositoryVault as { networkMode?: string })?.networkMode,
      storageName: (context.params.to || context.params.from) as string | undefined,
    }

    // Use shared builder
    return this.builder.buildQueueVault(requestContext)
  }

  private async fetchRequiredVaults(
    context: QueueContext,
    requirements: FunctionRequirements
  ): Promise<{
    companyVault?: VaultData
    teamVault?: VaultData
    machineVault?: VaultData
    repositoryVault?: VaultData
    storageVault?: VaultData
    bridgeVault?: VaultData
  }> {
    const vaults: {
      companyVault?: VaultData
      teamVault?: VaultData
      machineVault?: VaultData
      repositoryVault?: VaultData
      storageVault?: VaultData
      bridgeVault?: VaultData
    } = {}

    // Fetch company vault (contains universal user ID, etc.)
    try {
      const companyResponse = await apiClient.get('/GetCompanyVault', {})
      const companyData = companyResponse.resultSets?.[0]?.data?.[0] as { vaultContent?: string } | undefined
      if (companyData?.vaultContent) {
        vaults.companyVault = typeof companyData.vaultContent === 'string'
          ? JSON.parse(companyData.vaultContent)
          : companyData.vaultContent
      }
    } catch {
      // Company vault fetch failed - continue with empty
    }

    // Fetch team vault (contains SSH keys) from GetCompanyTeams
    if (requirements.team) {
      try {
        const teamsResponse = await apiClient.get('/GetCompanyTeams', {})
        const teams = teamsResponse.resultSets?.[0]?.data as Array<{ teamName: string; vaultContent?: string }> | undefined
        const team = teams?.find(t => t.teamName === context.teamName)
        if (team?.vaultContent) {
          vaults.teamVault = typeof team.vaultContent === 'string'
            ? JSON.parse(team.vaultContent)
            : team.vaultContent
        }
      } catch {
        // Team vault fetch failed
      }
    }

    // Fetch machine vault from GetTeamMachines
    if (requirements.machine && context.machineName) {
      try {
        const machinesResponse = await apiClient.get('/GetTeamMachines', {
          teamName: context.teamName,
        })
        const machines = machinesResponse.resultSets?.[0]?.data as Array<{ machineName: string; vaultContent?: string }> | undefined
        const machine = machines?.find(m => m.machineName === context.machineName)
        if (machine?.vaultContent) {
          vaults.machineVault = typeof machine.vaultContent === 'string'
            ? JSON.parse(machine.vaultContent)
            : machine.vaultContent
        }
      } catch {
        // Machine vault fetch failed
      }
    }

    // Fetch repository vault from GetTeamRepositories
    if (requirements.repository && context.params.repo) {
      try {
        const repoGuid = context.params.repo as string
        const reposResponse = await apiClient.get('/GetTeamRepositories', {
          teamName: context.teamName,
        })
        const repos = reposResponse.resultSets?.[0]?.data as Array<{ repoGuid: string; vaultContent?: string; repoLoopbackIP?: string; repoNetworkMode?: string }> | undefined
        const repo = repos?.find(r => r.repoGuid === repoGuid)
        if (repo?.vaultContent) {
          const repoVault = typeof repo.vaultContent === 'string'
            ? JSON.parse(repo.vaultContent)
            : repo.vaultContent
          // Add loopback IP and network mode to vault data
          if (repo.repoLoopbackIP) {
            repoVault.repoLoopbackIp = repo.repoLoopbackIP
          }
          if (repo.repoNetworkMode) {
            repoVault.networkMode = repo.repoNetworkMode
          }
          vaults.repositoryVault = repoVault
        }
      } catch {
        // Repository vault fetch failed
      }
    }

    // Fetch storage vault from GetTeamStorages
    if (requirements.storage) {
      const storages = context.params.storages
      const firstStorage = Array.isArray(storages) ? storages[0] : undefined
      const storageName = (context.params.to || context.params.from || firstStorage) as string
      if (storageName) {
        try {
          const storagesResponse = await apiClient.get('/GetTeamStorages', {
            teamName: context.teamName,
          })
          const storageList = storagesResponse.resultSets?.[0]?.data as Array<{ storageName: string; vaultContent?: string }> | undefined
          const storage = storageList?.find(s => s.storageName === storageName)
          if (storage?.vaultContent) {
            vaults.storageVault = typeof storage.vaultContent === 'string'
              ? JSON.parse(storage.vaultContent)
              : storage.vaultContent
          }
        } catch {
          // Storage vault fetch failed
        }
      }
    }

    // Fetch bridge vault from GetRegionBridges
    if (requirements.bridge && context.bridgeName) {
      try {
        const bridgesResponse = await apiClient.get('/GetRegionBridges', {})
        const bridges = bridgesResponse.resultSets?.[0]?.data as Array<{ bridgeName: string; vaultContent?: string }> | undefined
        const bridge = bridges?.find(b => b.bridgeName === context.bridgeName)
        if (bridge?.vaultContent) {
          vaults.bridgeVault = typeof bridge.vaultContent === 'string'
            ? JSON.parse(bridge.vaultContent)
            : bridge.vaultContent
        }
      } catch {
        // Bridge vault fetch failed
      }
    }

    return vaults
  }

}

export const queueService = new CliQueueService()
export default queueService
