import type { VaultContextData, VaultData } from './vault'

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
  description: string
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

export type QueueItemStatus = 'pending' | 'submitting' | 'submitted' | 'failed' | 'cancelled' | 'completed'

export interface QueueItemData {
  teamName: string
  machineName?: string
  bridgeName?: string
  queueVault: string
  priority?: number
}

export interface QueueItem {
  id: string
  data: QueueItemData
  retryCount: number
  status: QueueItemStatus
  timestamp: number
  submitFunction: (data: QueueItemData) => Promise<unknown>
  taskId?: string
}

export interface ActiveTask {
  bridgeName: string
  machineName: string
  taskId: string
  priority: number
  status: 'pending' | 'assigned' | 'processing'
  timestamp: number
}

export interface QueueVaultPayload {
  function: string
  machine: string
  team: string
  params: Record<string, unknown>
  contextData: VaultContextData
}
