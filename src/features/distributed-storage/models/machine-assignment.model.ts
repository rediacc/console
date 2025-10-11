import type { Machine } from '@/types'
import type { MachineAssignmentType } from '@/types'

export interface MachineAssignment {
  machineId: string
  machineName: string
  assignmentType: MachineAssignmentType
  resourceId?: string
  resourceName?: string
  assignedAt?: Date
}

export interface BulkOperationRequest {
  machines: string[]
  operation: 'assign' | 'remove'
  targetType: 'cluster' | 'image' | 'clone'
  targetResource: string
  teamName: string
}

export interface AssignmentConflict {
  machine: Machine
  machineName: string
  currentAssignment: MachineAssignment
  requestedAssignment: string
  conflictType: 'exclusivity' | 'availability' | 'permission'
  targetType?: 'cluster' | 'image' | 'clone'
  targetResource?: string
  message?: string
}

export type ConflictResolutionAction = 'skip' | 'force' | 'cancel'

export interface ConflictResolution {
  conflict: AssignmentConflict
  action: ConflictResolutionAction
  resolved: boolean
  error?: string
}

export interface ConflictResolutionResult {
  resolution: ConflictResolutionAction
  reason?: string
}

export interface DistributedStorageResource {
  id: string
  name: string
  type: 'cluster' | 'pool' | 'image' | 'snapshot' | 'clone'
  assignedMachines?: string[]
  teamName?: string
}

export interface AssignmentResult {
  success: boolean
  assignedMachines: string[]
  failedMachines: string[]
  conflicts: AssignmentConflict[]
}

export interface MachineAssignmentSummary {
  totalMachines: number
  availableMachines: number
  clusterAssignedMachines: number
  imageAssignedMachines: number
  cloneAssignedMachines: number
  assignmentBreakdown: Map<MachineAssignmentType, number>
}