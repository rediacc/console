import { minifyJSON } from '@/utils/json'
import functionsData from '@/data/functions.json'

// Type definitions

export interface QueueRequestContext {
  teamName: string
  machineName: string
  bridgeName?: string
  repositoryName?: string
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
  /**
   * Get requirements for a specific function
   */
  getFunctionRequirements(functionName: string): FunctionRequirements {
    const func = functionsData.functions[functionName as keyof typeof functionsData.functions]
    return func?.requirements || {}
  }

  /**
   * Build the complete queue vault data based on function requirements
   */
  async buildQueueVault(context: QueueRequestContext): Promise<string> {
    const requirements = this.getFunctionRequirements(context.functionName)
    
    // Start with base queue vault structure
    const queueVaultData: any = {
      function: context.functionName,
      machine: context.machineName,
      team: context.teamName,
      params: context.params,
      contextData: {}
    }

    // Initialize GENERAL_SETTINGS under contextData
    queueVaultData.contextData.GENERAL_SETTINGS = this.buildGeneralSettings(context)

    // Add MACHINES structure under contextData if machine is required
    if (requirements.machine && context.machineVault && context.machineName) {
      queueVaultData.contextData.MACHINES = {
        [context.machineName]: this.extractMachineForGeneralSettings(context.machineVault)
      }
    }

    // Add data based on requirements
    if (requirements.company) {
      queueVaultData.contextData.company = this.extractCompanyData(context.companyVault)
    }

    if (requirements.repository && context.repositoryName) {
      queueVaultData.contextData.repository = this.extractRepositoryData(
        context.repositoryVault,
        context.repositoryName,
        context.companyVault
      )
    }

    if (requirements.storage && context.storageName) {
      queueVaultData.contextData.storage = this.extractStorageData(
        context.storageVault,
        context.storageName
      )
    }

    if (requirements.bridge && context.bridgeName) {
      queueVaultData.contextData.bridge = this.extractBridgeData(
        context.bridgeVault,
        context.bridgeName,
        context.companyVault
      )
    }

    if (requirements.plugin) {
      queueVaultData.contextData.plugins = this.extractPluginData(context.companyVault)
    }

    return minifyJSON(JSON.stringify(queueVaultData))
  }

  /**
   * Extract company-level data
   */
  private extractCompanyData(companyVault: any): any {
    if (!companyVault) return {}

    const companyData: any = {}

    // Company vault fields from COMPANY entity
    companyData.UNIVERSAL_USER_ID = companyVault.UNIVERSAL_USER_ID
    companyData.UNIVERSAL_USER_NAME = companyVault.UNIVERSAL_USER_NAME
    companyData.DOCKER_JSON_CONF = companyVault.DOCKER_JSON_CONF
    companyData.LOG_FILE = companyVault.LOG_FILE

    return companyData
  }


  /**
   * Extract machine data for GENERAL_SETTINGS.MACHINES structure
   */
  private extractMachineForGeneralSettings(machineVault: any): any {
    const machineData: any = {}

    // Machine vault fields formatted for GENERAL_SETTINGS.MACHINES
    if (machineVault && Object.keys(machineVault).length > 0) {
      this.assignMachineFields(machineData, machineVault)
    }

    return machineData
  }

  private assignMachineFields(target: any, source: any): void {
    const fieldMappings = [
      { targetKey: 'IP', sources: ['ip', 'IP'] },
      { targetKey: 'USER', sources: ['user', 'USER'] },
      { targetKey: 'DATASTORE', sources: ['datastore', 'DATASTORE'] },
      { targetKey: 'HOST_ENTRY', sources: ['host_entry', 'HOST_ENTRY'] }
    ]

    fieldMappings.forEach(({ targetKey, sources }) => {
      const value = sources.map(s => source[s]).find(v => v !== undefined)
      if (value !== undefined) {
        target[targetKey] = value
      }
    })
  }

  /**
   * Extract repository-specific data
   */
  private extractRepositoryData(repositoryVault: any, repositoryName: string, _companyVault: any): any {
    const repositoryData: any = {
      name: repositoryName
    }

    // Repository vault fields from REPOSITORY entity
    if (repositoryVault) {
      repositoryData.size = repositoryVault.size
      repositoryData.credential = repositoryVault.credential
    }

    return repositoryData
  }

  /**
   * Extract storage-specific data
   */
  private extractStorageData(storageVault: any, storageName: string): any {
    return this.extractEntityData(storageName, storageVault)
  }

  /**
   * Extract bridge-specific data
   */
  private extractBridgeData(bridgeVault: any, bridgeName: string, _companyVault: any): any {
    return this.extractEntityData(bridgeName, bridgeVault)
  }

  /**
   * Generic entity data extraction
   */
  private extractEntityData(name: string, vault: any): any {
    const entityData: any = { name }

    if (vault) {
      Object.assign(entityData, vault)
    }

    return entityData
  }

  /**
   * Extract plugin data
   */
  private extractPluginData(companyVault: any): any {
    // Plugins are stored at company level
    if (!companyVault?.PLUGINS) return {}
    
    return companyVault.PLUGINS
  }

  /**
   * Helper to fetch vault data from API if needed
   * This is a placeholder - actual implementation would use React Query hooks
   */
  async fetchVaultData(_entityType: string, _entityName: string): Promise<any> {
    // This would be implemented with actual API calls
    // For now, return empty object
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
    this.copySimpleFields(generalSettings, companyVault, ['UNIVERSAL_USER_ID', 'UNIVERSAL_USER_NAME'])
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