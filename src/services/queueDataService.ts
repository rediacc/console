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
      machine: context.machineName,
      team: context.teamName,
      params: context.params,
      contextData: {}
    }

    // Initialize GENERAL_SETTINGS under contextData
    queueVault.contextData.GENERAL_SETTINGS = {}
    
    if (context.companyVault && typeof context.companyVault === 'object') {
      // Only add if values exist
      if (context.companyVault.UNIVERSAL_USER_ID) {
        queueVault.contextData.GENERAL_SETTINGS.UNIVERSAL_USER_ID = context.companyVault.UNIVERSAL_USER_ID
      }
      if (context.companyVault.UNIVERSAL_USER_NAME) {
        queueVault.contextData.GENERAL_SETTINGS.UNIVERSAL_USER_NAME = context.companyVault.UNIVERSAL_USER_NAME
      }
      // Add SSH keys to GENERAL_SETTINGS from company vault
      if (context.companyVault.SSH_PRIVATE_KEY) {
        queueVault.contextData.GENERAL_SETTINGS.SSH_PRIVATE_KEY = this.ensureBase64(context.companyVault.SSH_PRIVATE_KEY)
      }
      if (context.companyVault.SSH_PUBLIC_KEY) {
        queueVault.contextData.GENERAL_SETTINGS.SSH_PUBLIC_KEY = this.ensureBase64(context.companyVault.SSH_PUBLIC_KEY)
      }
    }

    // Also check team vault for SSH keys and add them to GENERAL_SETTINGS
    if (context.teamVault && typeof context.teamVault === 'object') {
      // Team SSH keys override company SSH keys if present
      if (context.teamVault.SSH_PRIVATE_KEY) {
        queueVault.contextData.GENERAL_SETTINGS.SSH_PRIVATE_KEY = this.ensureBase64(context.teamVault.SSH_PRIVATE_KEY)
      }
      if (context.teamVault.SSH_PUBLIC_KEY) {
        queueVault.contextData.GENERAL_SETTINGS.SSH_PUBLIC_KEY = this.ensureBase64(context.teamVault.SSH_PUBLIC_KEY)
      }
    }

    // Add MACHINES structure under contextData if machine is required
    if (requirements.machine && context.machineVault && context.machineName) {
      queueVault.contextData.MACHINES = {
        [context.machineName]: this.extractMachineForGeneralSettings(context.machineVault)
      }
    }

    // Add data based on requirements
    if (requirements.company) {
      queueVault.contextData.company = this.extractCompanyData(context.companyVault)
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

    return data
  }


  /**
   * Extract machine data for GENERAL_SETTINGS.MACHINES structure
   */
  private extractMachineForGeneralSettings(machineVault: any): any {
    const data: any = {}

    // Machine vault fields formatted for GENERAL_SETTINGS.MACHINES
    if (machineVault && Object.keys(machineVault).length > 0) {
      data.IP = machineVault.ip || machineVault.IP
      data.USER = machineVault.user || machineVault.USER
      data.DATASTORE = machineVault.datastore || machineVault.DATASTORE
      data.HOST_ENTRY = machineVault.host_entry || machineVault.HOST_ENTRY
    }

    return data
  }

  /**
   * Extract repository-specific data
   */
  private extractRepositoryData(repositoryVault: any, repositoryName: string, _companyVault: any): any {
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
  private extractBridgeData(bridgeVault: any, bridgeName: string, _companyVault: any): any {
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
  async fetchVaultData(_entityType: string, _entityName: string): Promise<any> {
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
    } catch {
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