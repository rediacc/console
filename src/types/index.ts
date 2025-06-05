export interface Machine {
  machineName: string
  teamName: string
  bridgeName: string
  regionName?: string
  queueCount: number
  vaultVersion: number
  vaultContent?: string
}