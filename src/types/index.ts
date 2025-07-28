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
}