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
    const queueVault: any = {
      function: context.functionName,
      params: context.params,
      priority: context.priority,
      description: context.description,
      addedVia: context.addedVia,
      contextData: {}
    }

    // Add data based on requirements
    if (requirements.company) {
      queueVault.contextData.company = this.extractCompanyData(context.companyVault)
    }

    if (requirements.team) {
      queueVault.contextData.team = this.extractTeamData(context.teamVault, context.teamName)
    }

    if (requirements.machine) {
      queueVault.contextData.machine = this.extractMachineData(
        context.machineVault, 
        context.machineName,
        context.companyVault
      )
    }

    if (requirements.repository && context.repositoryName) {
      queueVault.contextData.repository = this.extractRepositoryData(
        context.repositoryVault,
        context.repositoryName,
        context.companyVault
      )
    }

    if (requirements.storage && context.storageName) {
      queueVault.contextData.storage = this.extractStorageData(
        context.storageVault,
        context.storageName
      )
    }

    if (requirements.bridge && context.bridgeName) {
      queueVault.contextData.bridge = this.extractBridgeData(
        context.bridgeVault,
        context.bridgeName,
        context.companyVault
      )
    }

    if (requirements.plugin) {
      queueVault.contextData.plugins = this.extractPluginData(context.companyVault)
    }

    return minifyJSON(JSON.stringify(queueVault))
  }

  /**
   * Extract company-level data
   */
  private extractCompanyData(companyVault: any): any {
    if (!companyVault) return {}

    const data: any = {}

    // Company vault fields from COMPANY entity
    data.UNIVERSAL_USER_ID = companyVault.UNIVERSAL_USER_ID
    data.UNIVERSAL_USER_NAME = companyVault.UNIVERSAL_USER_NAME
    data.DOCKER_JSON_CONF = companyVault.DOCKER_JSON_CONF
    data.LOG_FILE = companyVault.LOG_FILE
    
    // Ensure SSH keys are in base64 format
    if (companyVault.SSH_PRIVATE_KEY) {
      data.SSH_PRIVATE_KEY = this.ensureBase64(companyVault.SSH_PRIVATE_KEY)
    }
    if (companyVault.SSH_PUBLIC_KEY) {
      data.SSH_PUBLIC_KEY = this.ensureBase64(companyVault.SSH_PUBLIC_KEY)
    }

    return data
  }

  /**
   * Extract team-specific data
   */
  private extractTeamData(teamVault: any, teamName: string): any {
    const data: any = {
      name: teamName
    }

    if (teamVault) {
      // Team vault fields from TEAM entity - ensure base64 format
      if (teamVault.SSH_PRIVATE_KEY) {
        data.SSH_PRIVATE_KEY = this.ensureBase64(teamVault.SSH_PRIVATE_KEY)
      }
      if (teamVault.SSH_PUBLIC_KEY) {
        data.SSH_PUBLIC_KEY = this.ensureBase64(teamVault.SSH_PUBLIC_KEY)
      }
    }

    return data
  }

  /**
   * Extract machine-specific data
   */
  private extractMachineData(machineVault: any, machineName: string, companyVault: any): any {
    const data: any = {
      name: machineName
    }

    // Machine vault fields from MACHINE entity
    if (machineVault && Object.keys(machineVault).length > 0) {
      data.IP = machineVault.ip || machineVault.IP
      data.USER = machineVault.user || machineVault.USER
      data.DATASTORE = machineVault.datastore || machineVault.DATASTORE
      data.HOST_ENTRY = machineVault.host_entry || machineVault.HOST_ENTRY
      data.ssh_key_configured = machineVault.ssh_key_configured
      data.SSH_PASSWORD = machineVault.ssh_password
      if (machineVault.port) {
        data.port = machineVault.port
      }
    }

    return data
  }

  /**
   * Extract repository-specific data
   */
  private extractRepositoryData(repositoryVault: any, repositoryName: string, companyVault: any): any {
    const data: any = {
      name: repositoryName
    }

    // Repository vault fields from REPOSITORY entity
    if (repositoryVault) {
      data.size = repositoryVault.size
      data.credential = repositoryVault.credential
    }

    return data
  }

  /**
   * Extract storage-specific data
   */
  private extractStorageData(storageVault: any, storageName: string): any {
    const data: any = {
      name: storageName
    }

    // Storage vault fields - include all fields as storage has dynamic fields
    if (storageVault) {
      Object.keys(storageVault).forEach(key => {
        data[key] = storageVault[key]
      })
    }

    return data
  }

  /**
   * Extract bridge-specific data
   */
  private extractBridgeData(bridgeVault: any, bridgeName: string, companyVault: any): any {
    const data: any = {
      name: bridgeName
    }

    // Bridge vault fields - BRIDGE entity has no required fields per vaults.json
    if (bridgeVault) {
      Object.keys(bridgeVault).forEach(key => {
        data[key] = bridgeVault[key]
      })
    }

    return data
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
  async fetchVaultData(entityType: string, entityName: string): Promise<any> {
    // This would be implemented with actual API calls
    // For now, return empty object
    return {}
  }

  /**
   * Ensure a string is in base64 format
   * If it's already base64, return as-is
   * If it's not, encode it to base64
   */
  private ensureBase64(value: string): string {
    if (!value) return value
    
    // Check if it's already base64
    // Base64 regex pattern - allows for padding and newlines
    const base64Regex = /^[A-Za-z0-9+/]*={0,2}$/
    const cleanValue = value.replace(/\s/g, '') // Remove whitespace for checking
    
    if (base64Regex.test(cleanValue) && cleanValue.length % 4 === 0) {
      // Already looks like base64
      return value
    }
    
    // Not base64, encode it
    try {
      // Convert string to base64
      return btoa(value)
    } catch (e) {
      // If btoa fails (e.g., for non-Latin1 characters), use a more robust approach
      // Convert to UTF-8 bytes first, then to base64
      const utf8Bytes = new TextEncoder().encode(value)
      let binary = ''
      utf8Bytes.forEach(byte => {
        binary += String.fromCharCode(byte)
      })
      return btoa(binary)
    }
  }
}

// Export singleton instance
export const queueDataService = new QueueDataService()

// Export function requirements type from functions.json
export type FunctionName = keyof typeof functionsData.functions