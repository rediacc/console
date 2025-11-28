import { minifyJSON } from '../utils/json'
import { isBase64, getParamArray, getParamValue } from '../utils/validation'
import { FUNCTION_REQUIREMENTS } from '../data/functionRequirements'
import type {
  QueueRequestContext,
  FunctionRequirements,
  VaultData,
  VaultContextData,
  StorageSystemContextData,
} from '../types'

export interface QueueVaultBuilderConfig {
  getApiUrl: () => string
  encodeBase64: (value: string) => string
}

export class QueueVaultBuilder {
  constructor(private config: QueueVaultBuilderConfig) {}

  getFunctionRequirements(functionName: string): FunctionRequirements {
    const functionKey = functionName as keyof typeof FUNCTION_REQUIREMENTS
    return FUNCTION_REQUIREMENTS[functionKey]?.requirements || {}
  }

  async buildQueueVault(context: QueueRequestContext): Promise<string> {
    try {
      const requirements = this.getFunctionRequirements(context.functionName)
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
          GENERAL_SETTINGS: this.buildGeneralSettings(context),
        } as VaultContextData,
      }

      if (requirements.machine && context.machineVault && context.machineName) {
        queueVaultData.contextData.MACHINES = queueVaultData.contextData.MACHINES || {}
        queueVaultData.contextData.MACHINES[context.machineName] = this.extractMachineData(context.machineVault)
        const destinationName = (context.params as Record<string, string>).to
        if (
          context.functionName === 'deploy' &&
          destinationName &&
          destinationName !== context.machineName &&
          context.destinationMachineVault
        ) {
          queueVaultData.contextData.MACHINES[destinationName] = this.extractMachineData(
            context.destinationMachineVault,
          )
        }
      }

      // For ssh_test with bridge-only tasks (no machine name), include SSH details directly in vault data
      if (context.functionName === 'ssh_test' && context.machineVault && !context.machineName) {
        const machineData = this.extractMachineData(context.machineVault)
        const parsedVault =
          typeof context.machineVault === 'string' ? JSON.parse(context.machineVault) : context.machineVault
        if ((parsedVault as Record<string, unknown>).ssh_password) {
          ;(machineData as Record<string, unknown>).ssh_password = (parsedVault as Record<string, unknown>).ssh_password
        }
        // Include the SSH connection info directly in the root vault data for bridge-only tasks
        Object.assign(queueVaultData, machineData)
      }

      if (context.functionName === 'backup') {
        const targets = getParamArray(context.params as Record<string, unknown>, 'storages')
        if (!targets.length) {
          const fallbackTarget = getParamValue(context.params as Record<string, unknown>, 'to')
          if (fallbackTarget) {
            targets.push(fallbackTarget)
          }
        }
        if (targets.length > 0) {
          queueVaultData.contextData.STORAGE_SYSTEMS = queueVaultData.contextData.STORAGE_SYSTEMS || {}
          targets.forEach((storageName, index) => {
            const storageVault =
              context.additionalStorageData?.[storageName] ||
              (index === 0 ? context.destinationStorageVault : undefined)
            if (storageVault) {
              queueVaultData.contextData.STORAGE_SYSTEMS![storageName] = this.buildStorageConfig(storageVault)
            }
          })
        }
      }

      if (context.functionName === 'list') {
        const sourceName = getParamValue(context.params as Record<string, unknown>, 'from')
        if (sourceName && context.additionalStorageData?.[sourceName]) {
          queueVaultData.contextData.STORAGE_SYSTEMS = queueVaultData.contextData.STORAGE_SYSTEMS || {}
          queueVaultData.contextData.STORAGE_SYSTEMS[sourceName] = this.buildStorageConfig(
            context.additionalStorageData[sourceName],
          )
        }

        if (sourceName && context.additionalMachineData?.[sourceName]) {
          queueVaultData.contextData.MACHINES = queueVaultData.contextData.MACHINES || {}
          queueVaultData.contextData.MACHINES[sourceName] = this.extractMachineData(
            context.additionalMachineData[sourceName],
          )
        }
      }

      // Handle pull function with other machines (via additionalMachineData)
      if (
        context.functionName === 'pull' &&
        (context.params as Record<string, string>).sourceType === 'machine' &&
        (context.params as Record<string, string>).from
      ) {
        const fromName = (context.params as Record<string, string>).from
        if (context.additionalMachineData?.[fromName]) {
          queueVaultData.contextData.MACHINES = queueVaultData.contextData.MACHINES || {}
          queueVaultData.contextData.MACHINES[fromName] = this.extractMachineData(
            context.additionalMachineData[fromName],
          )
        }
      }

      // Handle pull function with storage systems (via additionalStorageData)
      if (
        context.functionName === 'pull' &&
        (context.params as Record<string, string>).sourceType === 'storage' &&
        (context.params as Record<string, string>).from
      ) {
        const fromName = (context.params as Record<string, string>).from
        if (context.additionalStorageData?.[fromName]) {
          queueVaultData.contextData.STORAGE_SYSTEMS = queueVaultData.contextData.STORAGE_SYSTEMS || {}
          queueVaultData.contextData.STORAGE_SYSTEMS[fromName] = this.buildStorageConfig(
            context.additionalStorageData[fromName],
          )
        }
      }

      // Add REPO_CREDENTIALS after MACHINES if repository is required
      if (requirements.repository && context.repositoryGuid && context.repositoryVault) {
        try {
          const repoVault =
            typeof context.repositoryVault === 'string'
              ? JSON.parse(context.repositoryVault)
              : context.repositoryVault

          if (repoVault.credential) {
            queueVaultData.contextData.REPO_CREDENTIALS = {
              [context.repositoryGuid]: repoVault.credential,
            }
          }
        } catch {
          // Ignore vault parsing errors - repository vault is optional
        }
      }

      // Add REPO_LOOPBACK_IP if repository loopback IP is provided
      if (requirements.repository && context.repositoryLoopbackIp) {
        queueVaultData.contextData.REPO_LOOPBACK_IP = context.repositoryLoopbackIp
      }

      // Add REPO_NETWORK_MODE if repository network mode is provided
      if (requirements.repository && context.repositoryNetworkMode) {
        queueVaultData.contextData.REPO_NETWORK_MODE = context.repositoryNetworkMode
      }

      // Add REPO_TAG if repository tag is provided
      if (requirements.repository && context.repositoryTag !== undefined) {
        queueVaultData.contextData.REPO_TAG = context.repositoryTag
      }

      // For functions like 'list' that need all REPO_CREDENTIALS
      // Repository credentials are passed separately, not from company vault
      if (context.functionName === 'list' && context.allRepositoryCredentials) {
        queueVaultData.contextData.REPO_CREDENTIALS = context.allRepositoryCredentials
      }

      // For 'mount', 'unmount', 'new', and 'up' functions that need PLUGINS
      if (
        ['mount', 'unmount', 'new', 'up'].includes(context.functionName) &&
        context.companyVault &&
        (context.companyVault as VaultData).PLUGINS
      ) {
        queueVaultData.contextData.PLUGINS = (context.companyVault as VaultData).PLUGINS as VaultData
      }

      const dataExtractors: Array<[boolean | undefined, keyof VaultContextData, () => VaultData]> = [
        [requirements.company, 'company', () => this.extractCompanyData(context.companyVault)],
        [
          Boolean(requirements.repository && context.repositoryGuid),
          'repository',
          () => this.extractRepositoryData(context.repositoryVault, context.repositoryGuid ?? '', context.companyVault),
        ],
        [
          requirements.storage && Boolean(context.storageName),
          'storage',
          () => this.extractStorageData(context.storageVault, context.storageName!),
        ],
        [
          requirements.bridge && Boolean(context.bridgeName),
          'bridge',
          () => this.extractBridgeData(context.bridgeVault, context.bridgeName!),
        ],
        [requirements.plugin, 'plugins', () => this.extractPluginData(context.companyVault)],
      ]

      dataExtractors.forEach(([condition, key, extractor]) => {
        if (condition) {
          queueVaultData.contextData[key] = extractor()
        }
      })

      return minifyJSON(JSON.stringify(queueVaultData))
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error'
      throw new Error(`Failed to build queue vault: ${message}`)
    }
  }

  private extractCompanyData(companyVault: VaultData | string | null | undefined): VaultData {
    if (!companyVault) return {}
    if (typeof companyVault === 'string') {
      try {
        return JSON.parse(companyVault) as VaultData
      } catch {
        return {}
      }
    }
    const { UNIVERSAL_USER_ID, UNIVERSAL_USER_NAME, DOCKER_JSON_CONF, LOG_FILE, REPO_CREDENTIALS, PLUGINS } =
      companyVault as Record<string, unknown>
    return { UNIVERSAL_USER_ID, UNIVERSAL_USER_NAME, DOCKER_JSON_CONF, LOG_FILE, REPO_CREDENTIALS, PLUGINS }
  }

  private extractMachineData(machineVault: VaultData | string | null | undefined): VaultData {
    if (!machineVault) return {}
    const vault = typeof machineVault === 'string' ? JSON.parse(machineVault) : machineVault
    const fieldMappings = [
      { targetKey: 'IP', sources: ['ip', 'IP'] },
      { targetKey: 'USER', sources: ['user', 'USER'] },
      { targetKey: 'DATASTORE', sources: ['datastore', 'DATASTORE'] },
      { targetKey: 'HOST_ENTRY', sources: ['host_entry', 'HOST_ENTRY'] },
    ]
    return fieldMappings.reduce<Record<string, unknown>>((target, { targetKey, sources }) => {
      const sourceKey = sources.find((source) => (vault as Record<string, unknown>)[source] !== undefined)
      if (sourceKey) {
        target[targetKey] = (vault as Record<string, unknown>)[sourceKey]
      }
      return target
    }, {})
  }

  private extractRepositoryData(
    repositoryVault: VaultData | string | null | undefined,
    repositoryGuid: string,
    _companyVault: VaultData | string | null | undefined,
  ): VaultData {
    const repository = typeof repositoryVault === 'string' ? JSON.parse(repositoryVault) : repositoryVault
    return {
      guid: repositoryGuid,
      ...(repository && {
        size: (repository as Record<string, unknown>).size,
        credential: (repository as Record<string, unknown>).credential,
      }),
    }
  }

  private extractStorageData(storageVault: VaultData | string | null | undefined, storageName: string): VaultData {
    if (!storageVault) return { name: storageName }
    if (typeof storageVault === 'string') {
      return { name: storageName, ...JSON.parse(storageVault) }
    }
    return { name: storageName, ...storageVault }
  }

  private extractBridgeData(bridgeVault: VaultData | string | null | undefined, bridgeName: string): VaultData {
    if (!bridgeVault) return { name: bridgeName }
    if (typeof bridgeVault === 'string') {
      return { name: bridgeName, ...JSON.parse(bridgeVault) }
    }
    return { name: bridgeName, ...bridgeVault }
  }

  private extractPluginData(companyVault: VaultData | string | null | undefined): VaultData {
    const company = typeof companyVault === 'string' ? JSON.parse(companyVault) : companyVault
    return (company as Record<string, unknown>)?.PLUGINS ? ((company as Record<string, unknown>).PLUGINS as VaultData) : {}
  }

  private buildStorageConfig(vault: VaultData | string): StorageSystemContextData {
    const parsedVault = typeof vault === 'string' ? JSON.parse(vault) : vault
    const provider = (parsedVault as Record<string, string>).provider
    if (!provider) {
      throw new Error('Storage provider type is required')
    }

    const storageConfig: StorageSystemContextData = {
      RCLONE_REDIACC_BACKEND: provider,
    }

    const folder = (parsedVault as Record<string, unknown>).folder
    if (folder !== undefined && folder !== null) {
      storageConfig.RCLONE_REDIACC_FOLDER = folder
    }

    const parameters = (parsedVault as Record<string, unknown>).parameters
    if (parameters) {
      storageConfig.RCLONE_PARAMETERS = parameters
    }

    const providerPrefix = `RCLONE_${provider.toUpperCase()}`
    Object.entries(parsedVault).forEach(([key, value]) => {
      if (['provider', 'folder', 'parameters'].includes(key)) {
        return
      }
      const envKey = `${providerPrefix}_${key.toUpperCase()}`
      storageConfig[envKey] = value
    })

    return storageConfig
  }

  private buildGeneralSettings(context: QueueRequestContext): VaultData {
    const generalSettings: VaultData = {}
    if (context.companyCredential) {
      generalSettings.COMPANY_ID = context.companyCredential
    }

    generalSettings.SYSTEM_API_URL = this.config.getApiUrl()
    generalSettings.TEAM_NAME = context.teamName
    if (context.machineName) {
      generalSettings.MACHINE_NAME = context.machineName
    }

    if (context.companyVault && typeof context.companyVault === 'object') {
      this.addCompanyVaultToGeneralSettings(generalSettings, context.companyVault)
    }

    if (context.teamVault && typeof context.teamVault === 'object') {
      this.addTeamVaultToGeneralSettings(generalSettings, context.teamVault)
    }

    return generalSettings
  }

  private addCompanyVaultToGeneralSettings(generalSettings: VaultData, companyVault: VaultData) {
    const { UNIVERSAL_USER_ID, UNIVERSAL_USER_NAME, DOCKER_JSON_CONF, PLUGINS } = companyVault as Record<string, unknown>
    if (UNIVERSAL_USER_ID) generalSettings.UNIVERSAL_USER_ID = UNIVERSAL_USER_ID
    if (UNIVERSAL_USER_NAME) generalSettings.UNIVERSAL_USER_NAME = UNIVERSAL_USER_NAME
    if (DOCKER_JSON_CONF) generalSettings.DOCKER_JSON_CONF = DOCKER_JSON_CONF
    if (PLUGINS) generalSettings.PLUGINS = PLUGINS
  }

  private addTeamVaultToGeneralSettings(generalSettings: VaultData, teamVault: VaultData) {
    const sshKeyFields = ['SSH_PRIVATE_KEY', 'SSH_PUBLIC_KEY']
    sshKeyFields.forEach((field) => {
      const value = (teamVault as Record<string, unknown>)[field]
      if (value && typeof value === 'string') {
        generalSettings[field] = this.ensureBase64(value)
      }
    })
  }

  private ensureBase64(value: string): string {
    if (!value) return value
    return isBase64(value) ? value : this.config.encodeBase64(value)
  }
}
