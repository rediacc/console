import { minifyJSON } from '@/utils/json'
import functionsData from '@/data/functions.json'

// Type definitions

export interface QueueRequestContext {
  teamName: string
  machineName?: string | null  // Made optional for bridge-only queue items
  bridgeName?: string
  repositoryGuid?: string
  storageName?: string
  functionName: string
  params: Record<string, any>
  priority: number
  description: string
  addedVia: string
  // Vault data from different entities
  teamVault?: any
  machineVault?: any
  repositoryVault?: any
  bridgeVault?: any
  companyVault?: any
  storageVault?: any
  destinationMachineVault?: any  // For push operations to another machine
  destinationStorageVault?: any  // For push operations to storage systems
  // For functions that need all repository credentials
  allRepositoryCredentials?: Record<string, string>
}

export interface FunctionRequirements {
  machine?: boolean
  team?: boolean
  company?: boolean
  repository?: boolean
  storage?: boolean
  plugin?: boolean
  bridge?: boolean
}

/**
 * Service to build queue request data based on function requirements
 * This centralizes the logic for including context-specific data
 */
class QueueDataService {
  getFunctionRequirements(functionName: string): FunctionRequirements {
    return functionsData.functions[functionName as keyof typeof functionsData.functions]?.requirements || {}
  }

  async buildQueueVault(context: QueueRequestContext): Promise<string> {
    try {
      const requirements = this.getFunctionRequirements(context.functionName)
      
      const queueVaultData: any = {
        function: context.functionName,
        machine: context.machineName || '', // Use empty string if no machine name
        team: context.teamName,
        params: context.params,
        contextData: {
          GENERAL_SETTINGS: this.buildGeneralSettings(context)
        }
      }

    if (requirements.machine && context.machineVault && context.machineName) {
      queueVaultData.contextData.MACHINES = {
        [context.machineName]: this.extractMachineForGeneralSettings(context.machineVault)
      }
      
      // For push function, also add destination machine if pushing to another machine
      if (context.functionName === 'push' && 
          context.params.destinationType === 'machine' && 
          context.params.to && 
          context.params.to !== context.machineName) {
        // We need to get the destination machine's vault data
        // This should be passed in the context as destinationMachineVault
        if (context.destinationMachineVault) {
          queueVaultData.contextData.MACHINES[context.params.to] = 
            this.extractMachineForGeneralSettings(context.destinationMachineVault)
        }
      }
    }
    
    // For push function to storage systems
    if (context.functionName === 'push' && 
        context.params.destinationType === 'storage' && 
        context.params.to) {
      // Initialize STORAGE_SYSTEMS if it doesn't exist
      if (!queueVaultData.contextData.STORAGE_SYSTEMS) {
        queueVaultData.contextData.STORAGE_SYSTEMS = {}
      }
      
      // Add the storage configuration
      if (context.destinationStorageVault) {
        // Parse the vault if it's a string
        const parsedVault = typeof context.destinationStorageVault === 'string' 
          ? JSON.parse(context.destinationStorageVault) 
          : context.destinationStorageVault
        
        // Get the provider type
        const provider = parsedVault.provider
        if (!provider) {
          throw new Error('Storage provider type is required')
        }
        
        // Transform storage config to environment variables expected by the script
        const storageConfig: any = {
          RCLONE_REDIACC_BACKEND: provider  // The provider type (e.g., 'onedrive', 's3', 'drive')
        }
        
        // Only add folder if it exists in the vault
        if (parsedVault.folder !== undefined && parsedVault.folder !== null) {
          storageConfig.RCLONE_REDIACC_FOLDER = parsedVault.folder
        }
        
        // Only add parameters if they exist in the vault
        if (parsedVault.parameters) {
          storageConfig.RCLONE_PARAMETERS = parsedVault.parameters
        }
        
        // Use provider-specific prefix (e.g., RCLONE_ONEDRIVE_, RCLONE_S3_)
        const providerPrefix = `RCLONE_${provider.toUpperCase()}`
        
        // Dynamically add all other fields from the vault as rclone config
        Object.entries(parsedVault).forEach(([key, value]) => {
          // Skip special fields that we've already handled
          if (key === 'provider' || key === 'folder' || key === 'parameters') {
            return
          }
          
          // Convert the key to uppercase for rclone environment variable format
          const envKey = `${providerPrefix}_${key.toUpperCase()}`
          
          // Handle different value types
          if (value === null || value === undefined) {
            return // Skip null/undefined values
          } else if (typeof value === 'object') {
            // For objects (like tokens), keep as object (not stringified)
            storageConfig[envKey] = value
          } else {
            // For primitives, use as-is
            storageConfig[envKey] = String(value)
          }
        })
        
        queueVaultData.contextData.STORAGE_SYSTEMS[context.params.to] = storageConfig
      }
    } else if (context.functionName === 'ssh_test' && context.machineVault && !context.machineName) {
      // For ssh_test with bridge-only tasks (no machine name), include SSH details directly in vault data
      const machineData = this.extractMachineForGeneralSettings(context.machineVault)
      // Add ssh_password if present in the machine vault
      const parsedVault = typeof context.machineVault === 'string' ? JSON.parse(context.machineVault) : context.machineVault
      if (parsedVault.ssh_password) {
        machineData.ssh_password = parsedVault.ssh_password
      }
      // Include the SSH connection info directly in the root vault data for bridge-only tasks
      Object.assign(queueVaultData, machineData)
    }

    // Add REPO_CREDENTIALS after MACHINES if repository is required
    if (requirements.repository && context.repositoryGuid && context.repositoryVault) {
      try {
        const repoVault = typeof context.repositoryVault === 'string' 
          ? JSON.parse(context.repositoryVault) 
          : context.repositoryVault
        
        
        if (repoVault.credential) {
          queueVaultData.contextData.REPO_CREDENTIALS = {
            [context.repositoryGuid]: repoVault.credential
          }
        }
      } catch (e) {
      }
    }

    // For functions like 'list' that need all REPO_CREDENTIALS
    // Repository credentials are passed separately, not from company vault
    if (context.functionName === 'list' && context.allRepositoryCredentials) {
      queueVaultData.contextData.REPO_CREDENTIALS = context.allRepositoryCredentials
    }

    // For 'mount' and 'unmount' functions that need PLUGINS
    if ((context.functionName === 'mount' || context.functionName === 'unmount') && context.companyVault?.PLUGINS) {
      queueVaultData.contextData.PLUGINS = context.companyVault.PLUGINS
    }


    const dataExtractors = [
      [requirements.company, 'company', () => this.extractCompanyData(context.companyVault)],
      [requirements.repository && context.repositoryGuid, 'repository', () => 
        this.extractRepositoryData(context.repositoryVault, context.repositoryGuid!, context.companyVault)],
      [requirements.storage && context.storageName, 'storage', () => 
        this.extractStorageData(context.storageVault, context.storageName!)],
      [requirements.bridge && context.bridgeName, 'bridge', () => 
        this.extractBridgeData(context.bridgeVault, context.bridgeName!, context.companyVault)],
      [requirements.plugin, 'plugins', () => this.extractPluginData(context.companyVault)]
    ] as const

    dataExtractors.forEach(([condition, key, extractor]) => {
      if (condition) queueVaultData.contextData[key] = extractor()
    })


      return minifyJSON(JSON.stringify(queueVaultData))
    } catch (error) {
      console.error('Error building queue vault:', error)
      console.error('Context:', context)
      throw new Error(`Failed to build queue vault: ${error instanceof Error ? error.message : 'Unknown error'}`)
    }
  }

  private extractCompanyData(companyVault: any): any {
    if (!companyVault) return {}
    const { UNIVERSAL_USER_ID, UNIVERSAL_USER_NAME, DOCKER_JSON_CONF, LOG_FILE, REPO_CREDENTIALS, PLUGINS } = companyVault
    return { UNIVERSAL_USER_ID, UNIVERSAL_USER_NAME, DOCKER_JSON_CONF, LOG_FILE, REPO_CREDENTIALS, PLUGINS }
  }


  private extractMachineForGeneralSettings(machineVault: any): any {
    if (!machineVault || !Object.keys(machineVault).length) return {}
    
    const fieldMappings = [
      { targetKey: 'IP', sources: ['ip', 'IP'] },
      { targetKey: 'USER', sources: ['user', 'USER'] },
      { targetKey: 'DATASTORE', sources: ['datastore', 'DATASTORE'] },
      { targetKey: 'HOST_ENTRY', sources: ['host_entry', 'HOST_ENTRY'] }
    ]

    return fieldMappings.reduce((target, { targetKey, sources }) => {
      const sourceKey = sources.find(s => machineVault[s] !== undefined)
      if (sourceKey !== undefined) target[targetKey] = machineVault[sourceKey]
      return target
    }, {} as any)
  }

  private extractRepositoryData(repositoryVault: any, repositoryGuid: string, _companyVault: any): any {
    return {
      guid: repositoryGuid,
      ...(repositoryVault && { size: repositoryVault.size, credential: repositoryVault.credential })
    }
  }

  private extractStorageData(storageVault: any, storageName: string): any {
    return this.extractEntityData(storageName, storageVault)
  }

  private extractBridgeData(bridgeVault: any, bridgeName: string, _companyVault: any): any {
    return this.extractEntityData(bridgeName, bridgeVault)
  }

  private extractEntityData(name: string, vault: any): any {
    return { name, ...(vault && vault) }
  }

  private extractPluginData(companyVault: any): any {
    return companyVault?.PLUGINS || {}
  }

  async fetchVaultData(_entityType: string, _entityName: string): Promise<any> {
    return {}
  }

  /**
   * Build GENERAL_SETTINGS object from context
   */
  private buildGeneralSettings(context: QueueRequestContext): any {
    const generalSettings: any = {}
    
    if (context.companyVault && typeof context.companyVault === 'object') {
      this.addCompanyVaultToGeneralSettings(generalSettings, context.companyVault)
    }

    if (context.teamVault && typeof context.teamVault === 'object') {
      this.addTeamVaultToGeneralSettings(generalSettings, context.teamVault)
    }

    return generalSettings
  }

  /**
   * Add company vault data to general settings
   */
  private addCompanyVaultToGeneralSettings(generalSettings: any, companyVault: any): void {
    this.copySimpleFields(generalSettings, companyVault, ['UNIVERSAL_USER_ID', 'UNIVERSAL_USER_NAME', 'DOCKER_JSON_CONF'])
    this.copySSHKeys(generalSettings, companyVault)
  }

  /**
   * Add team vault data to general settings (overrides company data)
   */
  private addTeamVaultToGeneralSettings(generalSettings: any, teamVault: any): void {
    this.copySSHKeys(generalSettings, teamVault)
  }

  private copySimpleFields(target: any, source: any, fields: string[]): void {
    fields.forEach(field => {
      if (source[field]) {
        target[field] = source[field]
      }
    })
  }

  private copySSHKeys(target: any, source: any): void {
    const sshKeyFields = ['SSH_PRIVATE_KEY', 'SSH_PUBLIC_KEY']
    sshKeyFields.forEach(field => {
      if (source[field]) {
        target[field] = this.ensureBase64(source[field])
      }
    })
  }

  /**
   * Ensure a string is in base64 format
   * If it's already base64, return as-is
   * If it's not, encode it to base64
   */
  private ensureBase64(value: string): string {
    if (!value) return value
    
    return this.isBase64(value) ? value : this.encodeToBase64(value)
  }

  /**
   * Check if a string is already base64 encoded
   */
  private isBase64(value: string): boolean {
    const base64Pattern = /^[A-Za-z0-9+/]*={0,2}$/
    const valueWithoutWhitespace = value.replace(/\s/g, '')
    
    return this.isValidBase64Format(valueWithoutWhitespace, base64Pattern)
  }

  private isValidBase64Format(value: string, pattern: RegExp): boolean {
    return pattern.test(value) && value.length % 4 === 0
  }

  /**
   * Encode a string to base64, handling UTF-8 characters
   */
  private encodeToBase64(value: string): string {
    try {
      return btoa(value)
    } catch {
      // Handle non-Latin1 characters by encoding to UTF-8 first
      const utf8Bytes = new TextEncoder().encode(value)
      const binaryString = Array.from(utf8Bytes)
        .map(byte => String.fromCharCode(byte))
        .join('')
      return btoa(binaryString)
    }
  }
}

// Export singleton instance
export const queueDataService = new QueueDataService()

// Export function requirements type from functions.json
export type FunctionName = keyof typeof functionsData.functions