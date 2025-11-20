// Runtime configuration from nginx
export interface RediaccConfig {
  // Instance Information
  instanceName: string
  
  // API Configuration
  apiUrl: string
  domain: string
  httpPort: string
  
  // Feature Flags
  enableDebug: string
  enableAnalytics: string
  enableMaintenance: string
  
  // Version Information
  version: string
  buildTime: string
  environment: string
  
  // Custom Configuration
  customConfig: string
  
  // Additional Settings
  maxUploadSize: string
  sessionTimeout: string
  defaultLanguage: string
  
  // Feature URLs
  docsUrl: string
  supportUrl: string
  templatesUrl: string

  // Security Settings
  csrfEnabled: string
  httpsOnly: string
}

// Extend Window interface to include our config
declare global {
  interface Window {
    REDIACC_CONFIG?: RediaccConfig
  }
}

export type MachineAssignmentType = 'AVAILABLE' | 'CLUSTER' | 'IMAGE' | 'CLONE'

export interface MachineAssignmentStatus {
  assignmentType: MachineAssignmentType
  assignmentDetails: string
  status?: string
}

export interface Machine {
  machineName: string
  machineGuid?: string
  teamName: string
  bridgeName: string
  regionName?: string
  queueCount: number
  vaultVersion: number
  vaultContent?: string
  vaultStatus?: string
  vaultStatusTime?: string
  distributedStorageClusterName?: string
  assignmentStatus?: MachineAssignmentStatus
}

export interface Repository {
  repositoryName: string
  repositoryGuid: string
  teamName: string
  vaultVersion: number
  vaultContent?: string
  grandGuid?: string
  repoTag?: string
}

export interface PluginContainer {
  name: string
  image: string
  status: string
  [key: string]: unknown
}
