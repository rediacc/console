export interface Machine {
  machineName: string
  teamName: string
  bridgeName: string
  regionName?: string
  queueCount: number
  vaultVersion: number
  vaultContent?: string
  vaultStatus?: string
  vaultStatusTime?: string
}

export interface Repository {
  repositoryName: string
  repositoryGuid: string
  teamName: string
  vaultVersion: number
  vaultContent?: string
  grandGuid?: string
}