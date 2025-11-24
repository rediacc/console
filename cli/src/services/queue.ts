import { apiClient } from './api.js'

// Function requirements data (subset of what's needed)
interface FunctionRequirements {
  machine?: boolean
  team?: boolean
  company?: boolean
  repository?: boolean
  storage?: boolean
  plugin?: boolean
  bridge?: boolean
}

interface FunctionData {
  requirements: FunctionRequirements
}

// Simplified functions data - in production, this would be imported from core/data/functions.json
const FUNCTION_REQUIREMENTS: Record<string, FunctionRequirements> = {
  setup: { machine: true, team: true, company: true },
  hello: { machine: true, team: true },
  ping: { machine: true, team: true },
  ssh_test: { machine: true, team: true },
  uninstall: { machine: true, team: true },
  new: { machine: true, team: true, repository: true },
  mount: { machine: true, team: true, repository: true },
  unmount: { machine: true, team: true, repository: true },
  up: { machine: true, team: true, repository: true, bridge: true },
  down: { machine: true, team: true, repository: true },
  validate: { machine: true, team: true, repository: true, bridge: true },
  resize: { machine: true, team: true, repository: true },
  expand: { machine: true, team: true, repository: true },
  rm: { machine: true, team: true, repository: true },
  apply_template: { machine: true, team: true, repository: true },
  ownership: { machine: true, team: true, repository: true },
  list: { machine: true, team: true, company: true },
  deploy: { machine: true, team: true, repository: true },
  backup: { machine: true, team: true, repository: true, storage: true },
  push: { machine: true, team: true, repository: true, storage: true },
  pull: { machine: true, team: true, repository: true, storage: true },
  nop: { machine: true, team: true },
}

type VaultData = Record<string, unknown>

interface QueueContext {
  teamName: string
  machineName?: string
  bridgeName?: string
  functionName: string
  params: Record<string, unknown>
  priority: number
}

interface VaultContextData {
  GENERAL_SETTINGS: VaultData
  MACHINES?: Record<string, VaultData>
  STORAGE_SYSTEMS?: Record<string, VaultData>
  REPO_CREDENTIALS?: Record<string, string>
  REPO_LOOPBACK_IP?: string
  REPO_NETWORK_MODE?: string
  REPO_TAG?: string
  PLUGINS?: VaultData
  company?: VaultData
  repository?: VaultData
  storage?: VaultData
  bridge?: VaultData
  plugins?: VaultData
}

export class CliQueueService {
  getFunctionRequirements(functionName: string): FunctionRequirements {
    return FUNCTION_REQUIREMENTS[functionName] || {}
  }

  async buildQueueVault(context: QueueContext): Promise<string> {
    const requirements = this.getFunctionRequirements(context.functionName)

    // Fetch required vaults
    const vaults = await this.fetchRequiredVaults(context, requirements)

    // Build the queue vault data structure
    const queueVaultData: {
      function: string
      machine: string
      team: string
      params: Record<string, unknown>
      contextData: VaultContextData
    } = {
      function: context.functionName,
      machine: context.machineName || '',
      team: context.teamName,
      params: context.params,
      contextData: {
        GENERAL_SETTINGS: this.buildGeneralSettings(context, vaults),
      },
    }

    // Add MACHINES data if machine is required
    if (requirements.machine && vaults.machineVault && context.machineName) {
      queueVaultData.contextData.MACHINES = {
        [context.machineName]: this.extractMachineData(vaults.machineVault),
      }
    }

    // Add company data if required
    if (requirements.company && vaults.companyVault) {
      queueVaultData.contextData.company = this.extractCompanyData(vaults.companyVault)
    }

    // Add repository data if required
    if (requirements.repository && context.params.repo) {
      const repoGuid = context.params.repo as string
      if (vaults.repositoryVault) {
        queueVaultData.contextData.repository = this.extractRepositoryData(
          vaults.repositoryVault,
          repoGuid
        )

        // Add REPO_CREDENTIALS
        const repoVault = typeof vaults.repositoryVault === 'string'
          ? JSON.parse(vaults.repositoryVault)
          : vaults.repositoryVault
        if (repoVault.credential) {
          queueVaultData.contextData.REPO_CREDENTIALS = {
            [repoGuid]: repoVault.credential,
          }
        }

        // Add loopback IP and network mode if available
        if (repoVault.repoLoopbackIp) {
          queueVaultData.contextData.REPO_LOOPBACK_IP = repoVault.repoLoopbackIp
        }
        if (repoVault.networkMode) {
          queueVaultData.contextData.REPO_NETWORK_MODE = repoVault.networkMode
        }
      }
    }

    // Add storage data if required
    if (requirements.storage && vaults.storageVault) {
      const storageName = (context.params.to || context.params.from) as string
      if (storageName) {
        queueVaultData.contextData.storage = this.extractStorageData(
          vaults.storageVault,
          storageName
        )

        // Also add to STORAGE_SYSTEMS
        queueVaultData.contextData.STORAGE_SYSTEMS = {
          [storageName]: this.buildStorageConfig(vaults.storageVault),
        }
      }
    }

    // Add bridge data if required
    if (requirements.bridge && vaults.bridgeVault && context.bridgeName) {
      queueVaultData.contextData.bridge = this.extractBridgeData(
        vaults.bridgeVault,
        context.bridgeName
      )
    }

    // Add plugins if available
    if (vaults.companyVault) {
      const companyData = typeof vaults.companyVault === 'string'
        ? JSON.parse(vaults.companyVault)
        : vaults.companyVault
      if (companyData.PLUGINS) {
        queueVaultData.contextData.PLUGINS = companyData.PLUGINS
        queueVaultData.contextData.plugins = companyData.PLUGINS
      }
    }

    return this.minifyJSON(JSON.stringify(queueVaultData))
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

  private buildGeneralSettings(
    context: QueueContext,
    vaults: { companyVault?: VaultData; teamVault?: VaultData }
  ): VaultData {
    const generalSettings: VaultData = {
      SYSTEM_API_URL: `${apiClient.getApiUrl()}`,
      TEAM_NAME: context.teamName,
    }

    if (context.machineName) {
      generalSettings.MACHINE_NAME = context.machineName
    }

    // Add company vault fields
    if (vaults.companyVault) {
      const { UNIVERSAL_USER_ID, UNIVERSAL_USER_NAME, DOCKER_JSON_CONF, PLUGINS } = vaults.companyVault
      if (UNIVERSAL_USER_ID) generalSettings.UNIVERSAL_USER_ID = UNIVERSAL_USER_ID
      if (UNIVERSAL_USER_NAME) generalSettings.UNIVERSAL_USER_NAME = UNIVERSAL_USER_NAME
      if (DOCKER_JSON_CONF) generalSettings.DOCKER_JSON_CONF = DOCKER_JSON_CONF
      if (PLUGINS) generalSettings.PLUGINS = PLUGINS
    }

    // Add SSH keys from team vault
    if (vaults.teamVault) {
      const sshKeyFields = ['SSH_PRIVATE_KEY', 'SSH_PUBLIC_KEY']
      for (const field of sshKeyFields) {
        const value = vaults.teamVault[field]
        if (value && typeof value === 'string') {
          generalSettings[field] = this.ensureBase64(value)
        }
      }
    }

    return generalSettings
  }

  private extractCompanyData(companyVault: VaultData): VaultData {
    const { UNIVERSAL_USER_ID, UNIVERSAL_USER_NAME, DOCKER_JSON_CONF, LOG_FILE, REPO_CREDENTIALS, PLUGINS } = companyVault
    return { UNIVERSAL_USER_ID, UNIVERSAL_USER_NAME, DOCKER_JSON_CONF, LOG_FILE, REPO_CREDENTIALS, PLUGINS }
  }

  private extractMachineData(machineVault: VaultData): VaultData {
    const fieldMappings = [
      { targetKey: 'IP', sources: ['ip', 'IP'] },
      { targetKey: 'USER', sources: ['user', 'USER'] },
      { targetKey: 'DATASTORE', sources: ['datastore', 'DATASTORE'] },
      { targetKey: 'HOST_ENTRY', sources: ['host_entry', 'HOST_ENTRY'] },
    ]

    const result: VaultData = {}
    for (const { targetKey, sources } of fieldMappings) {
      const sourceKey = sources.find((source) => machineVault[source] !== undefined)
      if (sourceKey) {
        result[targetKey] = machineVault[sourceKey]
      }
    }
    return result
  }

  private extractRepositoryData(repositoryVault: VaultData, repositoryGuid: string): VaultData {
    return {
      guid: repositoryGuid,
      size: repositoryVault.size,
      credential: repositoryVault.credential,
    }
  }

  private extractStorageData(storageVault: VaultData, storageName: string): VaultData {
    return { name: storageName, ...storageVault }
  }

  private extractBridgeData(bridgeVault: VaultData, bridgeName: string): VaultData {
    return { name: bridgeName, ...bridgeVault }
  }

  private buildStorageConfig(vault: VaultData): VaultData {
    const provider = vault.provider as string
    if (!provider) {
      throw new Error('Storage provider type is required')
    }

    const storageConfig: VaultData = {
      RCLONE_REDIACC_BACKEND: provider,
    }

    if (vault.folder !== undefined && vault.folder !== null) {
      storageConfig.RCLONE_REDIACC_FOLDER = vault.folder
    }

    if (vault.parameters) {
      storageConfig.RCLONE_PARAMETERS = vault.parameters
    }

    const providerPrefix = `RCLONE_${provider.toUpperCase()}`
    for (const [key, value] of Object.entries(vault)) {
      if (['provider', 'folder', 'parameters'].includes(key)) continue
      const envKey = `${providerPrefix}_${key.toUpperCase()}`
      storageConfig[envKey] = value
    }

    return storageConfig
  }

  private ensureBase64(value: string): string {
    if (!value) return value
    return this.isBase64(value) ? value : Buffer.from(value).toString('base64')
  }

  private isBase64(value: string): boolean {
    const base64Pattern = /^[A-Za-z0-9+/]*={0,2}$/
    const valueWithoutWhitespace = value.replace(/\s/g, '')
    return base64Pattern.test(valueWithoutWhitespace) && valueWithoutWhitespace.length % 4 === 0
  }

  private minifyJSON(json: string): string {
    try {
      return JSON.stringify(JSON.parse(json))
    } catch {
      return json
    }
  }
}

export const queueService = new CliQueueService()
export default queueService
