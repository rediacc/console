import type { Machine, MachineAssignmentType } from '@/types'
import type {
  MachineAssignment,
  BulkOperationRequest,
  AssignmentConflict,
  ConflictResolution,
  ConflictResolutionResult,
  DistributedStorageResource,
  AssignmentResult,
  MachineAssignmentSummary
} from '../models/machine-assignment.model'
import { MachineValidationService } from './machine-validation.service'
import type { ValidationContext } from '../models/machine-validation.model'

export class MachineAssignmentService {
  /**
   * Get the assignment type for a machine
   */
  static getMachineAssignmentType(machine: Machine): MachineAssignmentType {
    // Check cluster assignment first (stored directly on machine)
    if (machine.distributedStorageClusterName) {
      return 'CLUSTER'
    }

    // Check assignment status for other types
    if (machine.assignmentStatus) {
      return machine.assignmentStatus.assignmentType
    }

    // Default to available
    return 'AVAILABLE'
  }

  /**
   * Get detailed assignment information for a machine
   */
  static getMachineAssignmentDetails(machine: Machine): string | null {
    // Cluster assignment
    if (machine.distributedStorageClusterName) {
      return `Assigned to cluster: ${machine.distributedStorageClusterName}`
    }

    // Other assignments from status
    if (machine.assignmentStatus?.assignmentDetails) {
      return machine.assignmentStatus.assignmentDetails
    }

    return null
  }

  /**
   * Check if a machine can be assigned to a specific resource type
   */
  static canAssignMachine(
    machine: Machine,
    targetType: 'cluster' | 'image' | 'clone'
  ): boolean {
    const currentType = this.getMachineAssignmentType(machine)

    // Available machines can be assigned to anything
    if (currentType === 'AVAILABLE') {
      return true
    }

    // Clones can coexist with other assignments
    if (targetType === 'clone') {
      return true
    }

    // Cluster and image assignments are exclusive
    if ((targetType === 'cluster' || targetType === 'image') && 
        (currentType === 'CLUSTER' || currentType === 'IMAGE')) {
      return false
    }

    return true
  }

  /**
   * Format a user-friendly assignment message
   */
  static formatAssignmentMessage(
    type: MachineAssignmentType,
    resourceName?: string
  ): string {
    switch (type) {
      case 'CLUSTER':
        return resourceName ? `Assigned to cluster: ${resourceName}` : 'Assigned to cluster'
      case 'IMAGE':
        return resourceName ? `Assigned to image: ${resourceName}` : 'Assigned to image'
      case 'CLONE':
        return resourceName ? `Assigned to clone: ${resourceName}` : 'Assigned to clone'
      case 'AVAILABLE':
      default:
        return 'Available for assignment'
    }
  }

  /**
   * Filter machines that are available for a specific assignment type
   */
  static filterAvailableMachines(
    machines: Machine[],
    targetType: 'cluster' | 'image' | 'clone'
  ): Machine[] {
    return machines.filter(machine => this.canAssignMachine(machine, targetType))
  }

  /**
   * Group machines by their assignment type
   */
  static groupMachinesByAssignment(
    machines: Machine[]
  ): Map<MachineAssignmentType, Machine[]> {
    const groups = new Map<MachineAssignmentType, Machine[]>()

    // Initialize all types
    const types: MachineAssignmentType[] = ['AVAILABLE', 'CLUSTER', 'IMAGE', 'CLONE']
    types.forEach(type => groups.set(type, []))

    // Group machines
    machines.forEach(machine => {
      const type = this.getMachineAssignmentType(machine)
      const group = groups.get(type) || []
      group.push(machine)
      groups.set(type, group)
    })

    return groups
  }

  /**
   * Prepare a bulk assignment operation
   */
  static prepareBulkAssignment(
    machines: string[],
    operation: 'assign' | 'remove',
    targetType: 'cluster' | 'image' | 'clone',
    targetResource: string,
    teamName: string
  ): BulkOperationRequest {
    return {
      machines,
      operation,
      targetType,
      targetResource,
      teamName
    }
  }

  /**
   * Get assignment conflicts for a list of machines
   */
  static getAssignmentConflicts(
    machines: Machine[],
    targetType: string,
    targetResource: string
  ): AssignmentConflict[] {
    const conflicts: AssignmentConflict[] = []

    machines.forEach(machine => {
      const canAssign = this.canAssignMachine(machine, targetType as any)
      
      if (!canAssign) {
        const currentAssignment: MachineAssignment = {
          machineId: machine.machineGuid || '',
          machineName: machine.machineName,
          assignmentType: this.getMachineAssignmentType(machine),
          resourceName: machine.distributedStorageClusterName || 
                       machine.assignmentStatus?.assignmentDetails?.split(': ')[1]
        }

        conflicts.push({
          machine,
          currentAssignment,
          requestedAssignment: targetResource,
          conflictType: 'exclusivity',
          message: `Machine is already assigned to ${currentAssignment.assignmentType.toLowerCase()}: ${currentAssignment.resourceName}`
        })
      }
    })

    return conflicts
  }

  /**
   * Resolve an assignment conflict
   */
  static resolveAssignmentConflict(
    conflict: AssignmentConflict,
    resolution: ConflictResolution = 'skip'
  ): ConflictResolutionResult {
    switch (resolution) {
      case 'force':
        // Force assignment would require removing current assignment first
        return {
          resolution: 'force',
          reason: `Forcing reassignment from ${conflict.currentAssignment.assignmentType} to ${conflict.requestedAssignment}`
        }
      
      case 'cancel':
        return {
          resolution: 'cancel',
          reason: 'Operation cancelled by user'
        }
      
      case 'skip':
      default:
        return {
          resolution: 'skip',
          reason: `Skipping ${conflict.machine.machineName} due to existing assignment`
        }
    }
  }

  /**
   * Calculate assignment statistics for a set of machines
   */
  static calculateAssignmentSummary(machines: Machine[]): MachineAssignmentSummary {
    const groups = this.groupMachinesByAssignment(machines)
    const breakdown = new Map<MachineAssignmentType, number>()

    groups.forEach((machineList, type) => {
      breakdown.set(type, machineList.length)
    })

    return {
      totalMachines: machines.length,
      availableMachines: groups.get('AVAILABLE')?.length || 0,
      clusterAssignedMachines: groups.get('CLUSTER')?.length || 0,
      imageAssignedMachines: groups.get('IMAGE')?.length || 0,
      cloneAssignedMachines: groups.get('CLONE')?.length || 0,
      assignmentBreakdown: breakdown
    }
  }

  /**
   * Process assignment results and categorize successes/failures
   */
  static processAssignmentResults(
    requestedMachines: string[],
    actualResults: any[],
    conflicts: AssignmentConflict[]
  ): AssignmentResult {
    const assignedMachines: string[] = []
    const failedMachines: string[] = []

    // Track successful assignments
    actualResults.forEach(result => {
      if (result.success) {
        assignedMachines.push(result.machineName)
      } else {
        failedMachines.push(result.machineName)
      }
    })

    // Add conflicted machines to failed list
    conflicts.forEach(conflict => {
      if (!failedMachines.includes(conflict.machine.machineName)) {
        failedMachines.push(conflict.machine.machineName)
      }
    })

    return {
      success: assignedMachines.length > 0,
      assignedMachines,
      failedMachines,
      conflicts
    }
  }

  /**
   * Validate and prepare machines for assignment
   */
  static async validateAndPrepareAssignment(
    machines: Machine[],
    targetResource: DistributedStorageResource,
    context: ValidationContext
  ): Promise<{
    validMachines: Machine[]
    conflicts: AssignmentConflict[]
    canProceed: boolean
  }> {
    const validMachines: Machine[] = []
    const conflicts: AssignmentConflict[] = []

    // Validate each machine
    for (const machine of machines) {
      const validationResult = MachineValidationService.validateMachineAssignment(
        machine,
        targetResource,
        context
      )

      if (validationResult.isValid) {
        validMachines.push(machine)
      } else {
        // Convert validation errors to conflicts
        const conflict: AssignmentConflict = {
          machine,
          currentAssignment: {
            machineId: machine.machineGuid || '',
            machineName: machine.machineName,
            assignmentType: this.getMachineAssignmentType(machine),
            resourceName: this.getMachineAssignmentDetails(machine)?.split(': ')[1]
          },
          requestedAssignment: targetResource.name,
          conflictType: 'exclusivity',
          message: validationResult.errors[0]?.message || 'Validation failed'
        }
        conflicts.push(conflict)
      }
    }

    return {
      validMachines,
      conflicts,
      canProceed: validMachines.length > 0
    }
  }

  /**
   * Get assignment statistics by team
   */
  static getTeamAssignmentStats(
    machines: Machine[],
    teamName?: string
  ): Map<string, MachineAssignmentSummary> {
    const teamStats = new Map<string, MachineAssignmentSummary>()

    // Filter by team if specified
    const filteredMachines = teamName 
      ? machines.filter(m => m.teamName === teamName)
      : machines

    // Group by team
    const machinesByTeam = new Map<string, Machine[]>()
    filteredMachines.forEach(machine => {
      const team = machine.teamName
      if (!machinesByTeam.has(team)) {
        machinesByTeam.set(team, [])
      }
      machinesByTeam.get(team)!.push(machine)
    })

    // Calculate stats for each team
    machinesByTeam.forEach((teamMachines, team) => {
      teamStats.set(team, this.calculateAssignmentSummary(teamMachines))
    })

    return teamStats
  }
}