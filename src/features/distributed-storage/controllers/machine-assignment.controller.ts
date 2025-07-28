import type { Machine } from '@/types'
import { 
  MachineAssignmentService, 
  MachineValidationService 
} from '../services'
import type {
  useMachineAssignment,
  useMachineExclusivity,
  CloneIdentifier,
  PoolIdentifier,
  AssignmentResult
} from '../hooks'
import type {
  AssignmentConflict,
  ConflictResolution,
  ValidationResult
} from '../models'
import {
  WorkflowStep,
  WorkflowResult,
  AssignmentWorkflowOptions,
  AssignmentWorkflowResult,
  ConflictResolutionStrategy,
  MigrationPlan,
  MigrationResult,
  OperationProgress,
  ProgressCallback,
  ControllerValidationContext,
  Command,
  WorkflowError,
  ValidationError,
  ConflictError,
  WorkflowEvent,
  WorkflowEventData,
  WorkflowEventHandler
} from './types'

export class MachineAssignmentController {
  private assignmentHook: ReturnType<typeof useMachineAssignment>
  private exclusivityHook: ReturnType<typeof useMachineExclusivity>
  private eventHandlers: Set<WorkflowEventHandler> = new Set()
  private commandHistory: Command[] = []
  
  constructor(
    assignmentHook: ReturnType<typeof useMachineAssignment>,
    exclusivityHook: ReturnType<typeof useMachineExclusivity>
  ) {
    this.assignmentHook = assignmentHook
    this.exclusivityHook = exclusivityHook
  }
  
  /**
   * Subscribe to workflow events
   */
  subscribe(handler: WorkflowEventHandler): () => void {
    this.eventHandlers.add(handler)
    return () => this.eventHandlers.delete(handler)
  }
  
  /**
   * Emit workflow event
   */
  private emit(event: WorkflowEvent, workflowId: string, data?: any) {
    const eventData: WorkflowEventData = {
      event,
      workflowId,
      timestamp: new Date(),
      data
    }
    this.eventHandlers.forEach(handler => handler(eventData))
  }
  
  /**
   * Assign a machine to a cluster with full workflow
   */
  async assignMachineToCluster(
    machineNames: string[],
    clusterName: string,
    teamName: string,
    options: AssignmentWorkflowOptions = {}
  ): Promise<AssignmentWorkflowResult> {
    const workflowId = `assign-cluster-${Date.now()}`
    this.emit(WorkflowEvent.STARTED, workflowId, { machineNames, clusterName })
    
    const steps: WorkflowStep[] = []
    const result: AssignmentWorkflowResult = {
      success: false,
      completedSteps: [],
      assignedMachines: [],
      skippedMachines: [],
      conflicts: [],
      validationResults: []
    }
    
    try {
      // Step 1: Validation
      if (options.validateFirst !== false) {
        steps.push({
          name: 'validate',
          description: 'Validating machine availability',
          execute: async () => {
            const availability = await this.exclusivityHook.checkAvailability(machineNames)
            
            if (availability.unavailable.length > 0) {
              result.conflicts = Object.entries(availability.conflicts).map(([machine, conflict]) => ({
                machineName: machine,
                currentAssignment: conflict,
                targetType: 'cluster',
                targetResource: clusterName
              }))
              
              if (options.conflictResolutionStrategy === ConflictResolutionStrategy.FAIL_FAST) {
                throw new ConflictError('Machines are already assigned', result.conflicts)
              }
              
              result.skippedMachines = availability.unavailable
            }
            
            result.validationResults?.push({
              isValid: availability.unavailable.length === 0,
              errors: availability.unavailable.map(m => ({
                code: 'MACHINE_UNAVAILABLE',
                message: `Machine ${m} is not available`,
                severity: 'error' as const
              })),
              warnings: []
            })
            
            this.emit(WorkflowEvent.VALIDATION_COMPLETED, workflowId, { 
              available: availability.available,
              unavailable: availability.unavailable 
            })
          }
        })
      }
      
      // Step 2: Conflict Resolution
      if (result.conflicts.length > 0 && options.autoResolveConflicts) {
        steps.push({
          name: 'resolveConflicts',
          description: 'Resolving assignment conflicts',
          execute: async () => {
            const resolved = await this.resolveAssignmentConflicts(
              result.conflicts,
              options.conflictResolutionStrategy || ConflictResolutionStrategy.SKIP_CONFLICTS
            )
            
            // Update machine lists based on resolution
            const resolvedMachines = resolved
              .filter(r => r.resolved)
              .map(r => r.conflict.machineName)
            
            const finalMachines = machineNames.filter(m => 
              !result.skippedMachines.includes(m) || resolvedMachines.includes(m)
            )
            
            // Update the machines to assign
            machineNames.length = 0
            machineNames.push(...finalMachines)
          }
        })
      }
      
      // Step 3: Assignment
      steps.push({
        name: 'assign',
        description: 'Assigning machines to cluster',
        execute: async () => {
          const assignResult = await this.assignmentHook.assignToCluster(
            machineNames.filter(m => !result.skippedMachines.includes(m)),
            clusterName
          )
          
          if (assignResult.success) {
            result.assignedMachines = machineNames.filter(m => !result.skippedMachines.includes(m))
          } else {
            result.assignedMachines = machineNames.filter(m => 
              !result.skippedMachines.includes(m) && 
              !assignResult.failedMachines?.includes(m)
            )
            throw new WorkflowError(
              assignResult.message || 'Assignment failed',
              'assign',
              false,
              assignResult
            )
          }
        },
        rollback: async () => {
          // Rollback by removing from cluster
          if (result.assignedMachines.length > 0) {
            await this.assignmentHook.removeFromCluster(result.assignedMachines)
          }
        }
      })
      
      // Execute workflow
      for (const step of steps) {
        try {
          this.emit(WorkflowEvent.PROGRESS_UPDATE, workflowId, {
            step: step.name,
            description: step.description
          })
          
          await step.execute()
          result.completedSteps.push(step.name)
          
          this.emit(WorkflowEvent.STEP_COMPLETED, workflowId, { step: step.name })
        } catch (error) {
          result.failedStep = step.name
          result.error = error as Error
          
          this.emit(WorkflowEvent.STEP_FAILED, workflowId, { 
            step: step.name, 
            error: error instanceof Error ? error.message : 'Unknown error' 
          })
          
          // Attempt rollback
          if (step.rollback) {
            this.emit(WorkflowEvent.ROLLBACK_STARTED, workflowId)
            await step.rollback()
            this.emit(WorkflowEvent.ROLLBACK_COMPLETED, workflowId)
          }
          
          throw error
        }
      }
      
      result.success = true
      this.emit(WorkflowEvent.COMPLETED, workflowId, result)
      
      // Record command for undo
      this.recordCommand({
        execute: async () => {
          await this.assignmentHook.assignToCluster(result.assignedMachines, clusterName)
        },
        undo: async () => {
          await this.assignmentHook.removeFromCluster(result.assignedMachines)
        },
        canUndo: () => true,
        description: `Assign ${result.assignedMachines.length} machines to cluster ${clusterName}`
      })
      
      return result
    } catch (error) {
      result.success = false
      result.error = error as Error
      this.emit(WorkflowEvent.FAILED, workflowId, { error })
      throw error
    }
  }
  
  /**
   * Reassign an image to a different machine
   */
  async reassignImageMachine(
    imageName: string,
    currentMachineName: string,
    newMachineName: string,
    poolInfo: PoolIdentifier,
    options: AssignmentWorkflowOptions = {}
  ): Promise<AssignmentWorkflowResult> {
    const workflowId = `reassign-image-${Date.now()}`
    this.emit(WorkflowEvent.STARTED, workflowId, { imageName, currentMachineName, newMachineName })
    
    const result: AssignmentWorkflowResult = {
      success: false,
      completedSteps: [],
      assignedMachines: [],
      skippedMachines: [],
      conflicts: []
    }
    
    try {
      // Validate new machine availability
      if (options.validateFirst !== false) {
        const availability = await this.exclusivityHook.checkAvailability([newMachineName])
        
        if (availability.unavailable.length > 0) {
          throw new ValidationError(
            `Machine ${newMachineName} is not available for assignment`,
            undefined,
            [newMachineName]
          )
        }
      }
      
      // Perform reassignment
      const assignResult = await this.assignmentHook.reassignImage(
        imageName,
        newMachineName,
        poolInfo
      )
      
      if (assignResult.success) {
        result.assignedMachines = [newMachineName]
        result.success = true
        
        // Record command for undo
        this.recordCommand({
          execute: async () => {
            await this.assignmentHook.reassignImage(imageName, newMachineName, poolInfo)
          },
          undo: async () => {
            await this.assignmentHook.reassignImage(imageName, currentMachineName, poolInfo)
          },
          canUndo: () => true,
          description: `Reassign image ${imageName} from ${currentMachineName} to ${newMachineName}`
        })
      } else {
        throw new WorkflowError(assignResult.message || 'Reassignment failed', 'reassign')
      }
      
      this.emit(WorkflowEvent.COMPLETED, workflowId, result)
      return result
    } catch (error) {
      result.success = false
      result.error = error as Error
      this.emit(WorkflowEvent.FAILED, workflowId, { error })
      throw error
    }
  }
  
  /**
   * Migrate machines between clusters
   */
  async migrateClusterMachines(
    plan: MigrationPlan,
    progressCallback?: ProgressCallback
  ): Promise<MigrationResult> {
    const workflowId = `migrate-${Date.now()}`
    const result: MigrationResult = {
      success: false,
      migratedMachines: [],
      failedMachines: [],
      errors: {}
    }
    
    const progress: OperationProgress = {
      operationId: workflowId,
      type: 'migration',
      status: 'preparing',
      totalSteps: plan.machines.length * 2, // Remove + assign for each
      currentStep: 0,
      currentStepName: 'Preparing migration',
      startTime: new Date()
    }
    
    try {
      // Validate source and target
      progress.status = 'validating'
      progress.currentStepName = 'Validating migration plan'
      progressCallback?.(progress)
      
      if (plan.sourcType !== 'cluster' || plan.targetType !== 'cluster') {
        throw new ValidationError('Migration currently only supports cluster-to-cluster')
      }
      
      // Execute migration for each machine
      progress.status = 'executing'
      
      for (let i = 0; i < plan.machines.length; i++) {
        const machine = plan.machines[i]
        
        try {
          // Remove from source
          progress.currentStep = i * 2 + 1
          progress.currentStepName = `Removing ${machine} from ${plan.sourceResource}`
          progressCallback?.(progress)
          
          const removeResult = await this.assignmentHook.removeFromCluster([machine])
          
          if (!removeResult.success) {
            throw new Error(removeResult.message || 'Failed to remove from source cluster')
          }
          
          // Assign to target
          progress.currentStep = i * 2 + 2
          progress.currentStepName = `Assigning ${machine} to ${plan.targetResource}`
          progressCallback?.(progress)
          
          const assignResult = await this.assignmentHook.assignToCluster([machine], plan.targetResource)
          
          if (assignResult.success) {
            result.migratedMachines.push(machine)
          } else {
            // Rollback - reassign to source
            await this.assignmentHook.assignToCluster([machine], plan.sourceResource)
            throw new Error(assignResult.message || 'Failed to assign to target cluster')
          }
        } catch (error) {
          result.failedMachines.push(machine)
          result.errors[machine] = error instanceof Error ? error.message : 'Unknown error'
        }
      }
      
      result.success = result.failedMachines.length === 0
      
      progress.status = result.success ? 'completed' : 'failed'
      progress.currentStepName = result.success ? 'Migration completed' : 'Migration failed'
      progressCallback?.(progress)
      
      return result
    } catch (error) {
      progress.status = 'failed'
      progress.currentStepName = 'Migration failed'
      progressCallback?.(progress)
      throw error
    }
  }
  
  /**
   * Resolve assignment conflicts
   */
  async resolveAssignmentConflicts(
    conflicts: AssignmentConflict[],
    strategy: ConflictResolutionStrategy
  ): Promise<ConflictResolution[]> {
    const resolutions: ConflictResolution[] = []
    
    for (const conflict of conflicts) {
      let resolution: ConflictResolution
      
      switch (strategy) {
        case ConflictResolutionStrategy.SKIP_CONFLICTS:
          resolution = {
            conflict,
            action: 'skip',
            resolved: false
          }
          break
          
        case ConflictResolutionStrategy.FORCE_REASSIGN:
          // First remove from current assignment
          if (conflict.currentAssignment.assignmentType === 'CLUSTER') {
            await this.assignmentHook.removeFromCluster([conflict.machineName])
          } else if (conflict.currentAssignment.assignmentType === 'CLONE') {
            // Need clone info to remove - skip for now
            resolution = {
              conflict,
              action: 'skip',
              resolved: false,
              error: 'Cannot auto-remove from clone assignment'
            }
            break
          }
          
          resolution = {
            conflict,
            action: 'force',
            resolved: true
          }
          break
          
        case ConflictResolutionStrategy.FAIL_FAST:
          throw new ConflictError('Conflict detected', [conflict], strategy)
          
        default:
          resolution = {
            conflict,
            action: 'skip',
            resolved: false
          }
      }
      
      resolutions.push(resolution)
    }
    
    return resolutions
  }
  
  /**
   * Validate and assign with detailed feedback
   */
  async validateAndAssign(
    context: ControllerValidationContext
  ): Promise<AssignmentWorkflowResult> {
    const validationResults = MachineValidationService.validateBulkAssignment(
      context.machines,
      context.targetType
    )
    
    if (!validationResults.allValid) {
      throw new ValidationError(
        'Validation failed',
        [validationResults as any],
        validationResults.invalidMachines.map(m => m.machineName)
      )
    }
    
    // Proceed with assignment based on type
    switch (context.targetType) {
      case 'CLUSTER':
        return this.assignMachineToCluster(
          context.machines.map(m => m.machineName),
          context.targetResource,
          context.teamName,
          context.options
        )
        
      default:
        throw new Error(`Assignment to ${context.targetType} not implemented`)
    }
  }
  
  /**
   * Record command for undo/redo
   */
  private recordCommand(command: Command) {
    this.commandHistory.push(command)
    
    // Limit history size
    if (this.commandHistory.length > 50) {
      this.commandHistory.shift()
    }
  }
  
  /**
   * Undo last operation
   */
  async undoLastOperation(): Promise<boolean> {
    const lastCommand = this.commandHistory.pop()
    
    if (lastCommand && lastCommand.canUndo()) {
      await lastCommand.undo()
      return true
    }
    
    return false
  }
  
  /**
   * Get operation history
   */
  getOperationHistory(): Command[] {
    return [...this.commandHistory]
  }
}