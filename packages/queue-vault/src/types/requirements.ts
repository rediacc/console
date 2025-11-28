import type { VaultData } from './vault'

export interface QueueRequestContext {
  teamName: string
  machineName?: string | null
  bridgeName?: string
  repositoryGuid?: string
  repositoryLoopbackIp?: string
  repositoryNetworkMode?: string
  repositoryTag?: string
  storageName?: string
  functionName: string
  params: Record<string, unknown>
  priority: number
  addedVia: string
  teamVault?: VaultData | string | null
  machineVault?: VaultData | string | null
  repositoryVault?: VaultData | string | null
  bridgeVault?: VaultData | string | null
  companyVault?: VaultData | string | null
  companyCredential?: string
  storageVault?: VaultData | string | null
  destinationMachineVault?: VaultData | string | null
  destinationStorageVault?: VaultData | string | null
  destinationRepositoryVault?: VaultData | string | null
  sourceMachineVault?: VaultData | string | null
  sourceStorageVault?: VaultData | string | null
  sourceRepositoryVault?: VaultData | string | null
  allRepositoryCredentials?: Record<string, string>
  additionalStorageData?: Record<string, VaultData>
  additionalMachineData?: Record<string, VaultData>
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
