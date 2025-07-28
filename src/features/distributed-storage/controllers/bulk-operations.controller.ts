import type { Machine } from '@/types'
import { 
  MachineAssignmentService, 
  MachineValidationService 
} from '../services'
import { BatchApiService } from '../services/batch-api.service'
import type {
  useBulkMachineOperations,
  useMachineAssignment,
  useMachineExclusivity,
  BulkOperationResult,
  CloneIdentifier
} from '../hooks'
import type { BulkValidationResult } from '../models'
import {
  WorkflowStep,
  BulkOperationWorkflowOptions,
  BulkOperationWorkflowResult,
  BulkOperationBatch,
  BulkOperationReport,
  OperationProgress,
  ProgressCallback,
  MigrationPlan,
  MigrationResult,
  WorkflowError,
  ValidationError,
  WorkflowEvent,
  WorkflowEventData,
  WorkflowEventHandler
} from './types'

export class BulkOperationsController {
  private bulkHook: ReturnType<typeof useBulkMachineOperations>
  private assignmentHook: ReturnType<typeof useMachineAssignment>
  private exclusivityHook: ReturnType<typeof useMachineExclusivity>
  private eventHandlers: Set<WorkflowEventHandler> = new Set()
  private operationQueue: Map<string, BulkOperationBatch[]> = new Map()
  
  constructor(
    bulkHook: ReturnType<typeof useBulkMachineOperations>,
    assignmentHook: ReturnType<typeof useMachineAssignment>,
    exclusivityHook: ReturnType<typeof useMachineExclusivity>
  ) {
    this.bulkHook = bulkHook
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
   * Execute bulk assignment workflow with validation and progress tracking
   */
  async executeBulkAssignmentWorkflow(
    machines: Machine[],
    targetType: 'cluster' | 'image' | 'clone',
    targetResource: string,
    additionalInfo?: CloneIdentifier,
    options: BulkOperationWorkflowOptions = {}
  ): Promise<BulkOperationWorkflowResult> {
    const workflowId = `bulk-assign-${Date.now()}`
    const startTime = new Date()
    
    this.emit(WorkflowEvent.STARTED, workflowId, { 
      totalMachines: machines.length,
      targetType,
      targetResource 
    })
    
    const result: BulkOperationWorkflowResult = {
      success: false,
      completedSteps: [],
      totalMachines: machines.length,
      successfulMachines: [],
      failedMachines: [],
      batches: []
    }
    
    try {
      // Step 1: Pre-validation
      const validationStep: WorkflowStep = {
        name: 'validation',
        description: 'Validating all machines',
        execute: async () => {
          const validationResult = await this.performBulkValidation(
            machines,
            targetType,
            options.validateBeforeEachBatch
          )
          
          if (!validationResult.allValid) {
            const invalidCount = validationResult.invalidMachines.length
            if (options.stopOnFirstError) {
              throw new ValidationError(
                `${invalidCount} machines failed validation`,
                [validationResult as any],
                validationResult.invalidMachines.map(m => m.machineName)
              )
            }
            
            // Remove invalid machines from the list
            machines = machines.filter(m => 
              !validationResult.invalidMachines.some(inv => inv.machineName === m.machineName)
            )
            result.failedMachines.push(...validationResult.invalidMachines.map(m => m.machineName))
          }
          
          this.emit(WorkflowEvent.VALIDATION_COMPLETED, workflowId, {
            valid: machines.length,
            invalid: validationResult.invalidMachines.length
          })
        }
      }
      
      await this.executeStep(validationStep, workflowId, result)
      
      // Step 2: Create batches
      const batchSize = options.batchSize || 10
      const batches = this.createBatches(machines.map(m => m.machineName), batchSize)
      this.operationQueue.set(workflowId, batches)
      
      // Step 3: Process batches
      const processingStep: WorkflowStep = {
        name: 'processing',
        description: 'Processing machine assignments in batches',
        execute: async () => {
          await this.processBatches(
            workflowId,
            batches,
            targetType,
            targetResource,
            additionalInfo,
            options,
            result
          )
        }
      }
      
      await this.executeStep(processingStep, workflowId, result)
      
      // Step 4: Generate report
      if (options.generateReport) {
        const reportStep: WorkflowStep = {
          name: 'reporting',
          description: 'Generating operation report',
          execute: async () => {
            result.report = this.generateBulkOperationReport(
              workflowId,
              'bulk-assignment',
              startTime,
              new Date(),
              result
            )
          }
        }
        
        await this.executeStep(reportStep, workflowId, result)
      }
      
      result.success = result.failedMachines.length === 0
      this.emit(WorkflowEvent.COMPLETED, workflowId, result)
      
      return result
    } catch (error) {
      result.success = false
      result.error = error as Error
      this.emit(WorkflowEvent.FAILED, workflowId, { error })
      throw error
    } finally {
      this.operationQueue.delete(workflowId)
    }
  }
  
  /**
   * Execute bulk migration between resources
   */
  async executeBulkMigration(
    plan: MigrationPlan,
    options: BulkOperationWorkflowOptions = {},
    progressCallback?: ProgressCallback
  ): Promise<MigrationResult> {
    const workflowId = `bulk-migrate-${Date.now()}`
    const batchSize = options.batchSize || 5
    
    const progress: OperationProgress = {
      operationId: workflowId,
      type: 'migration',
      status: 'preparing',
      totalSteps: Math.ceil(plan.machines.length / batchSize),
      currentStep: 0,
      currentStepName: 'Preparing migration',
      startTime: new Date()
    }
    
    progressCallback?.(progress)
    
    const result: MigrationResult = {
      success: false,
      migratedMachines: [],
      failedMachines: [],
      errors: {}
    }
    
    try {
      // Create batches for migration
      const batches = this.createBatches(plan.machines, batchSize)
      
      progress.status = 'executing'
      
      for (let i = 0; i < batches.length; i++) {
        const batch = batches[i]
        progress.currentStep = i + 1
        progress.currentStepName = `Processing batch ${i + 1} of ${batches.length}`
        progressCallback?.(progress)
        
        const batchResult = await this.processMigrationBatch(
          batch,
          plan,
          options.maxRetries || 3,
          options.retryDelay || 1000
        )
        
        result.migratedMachines.push(...batchResult.migratedMachines)
        result.failedMachines.push(...batchResult.failedMachines)
        Object.assign(result.errors, batchResult.errors)
        
        if (options.stopOnFirstError && batchResult.failedMachines.length > 0) {
          break
        }
      }
      
      result.success = result.failedMachines.length === 0
      
      progress.status = result.success ? 'completed' : 'failed'
      progress.currentStepName = `Migration ${result.success ? 'completed' : 'failed'}`
      progressCallback?.(progress)
      
      return result
    } catch (error) {
      progress.status = 'failed'
      progressCallback?.(progress)
      throw error
    }
  }
  
  /**
   * Process assignment with batch API service
   */
  private async processAssignmentWithBatching(
    machines: Machine[],
    targetType: 'cluster' | 'image' | 'clone',
    targetResource: string,
    teamName: string,
    options: BulkOperationWorkflowOptions,
    result: BulkOperationWorkflowResult
  ): Promise<void> {
    const machineNames = machines.map(m => m.machineName)
    
    const batchResult = await BatchApiService.batchMachineOperation(
      'assign',
      machineNames,
      {
        teamName,
        targetType,
        targetResource
      },
      (progress) => {
        this.emit(WorkflowEvent.PROGRESS_UPDATE, options.workflowId || '', {
          message: `Processing batch ${progress.currentBatch} of ${progress.totalBatches}`,
          percentage: progress.percentage,
          completed: progress.completed,
          total: progress.total
        })
      }
    )
    
    result.successfulMachines = batchResult.successful
    result.failedMachines = batchResult.failed.map(f => f.item)
    
    // Record batch information
    const batchInfo: BulkOperationBatch = {
      batchId: `batch-${Date.now()}`,
      machines: machineNames,
      status: batchResult.failed.length === 0 ? 'completed' : 'partial',
      successCount: batchResult.successful.length,
      failureCount: batchResult.failed.length,
      errors: batchResult.failed.reduce((acc, failure) => {
        acc[failure.item] = failure.error
        return acc
      }, {} as Record<string, string>)
    }
    
    result.batches.push(batchInfo)
  }

  /**
   * Perform bulk validation on machines
   */
  async performBulkValidation(
    machines: Machine[],
    targetType: 'cluster' | 'image' | 'clone',
    checkAvailability = true
  ): Promise<BulkValidationResult> {
    // Use batch validation for large machine lists
    if (machines.length > 100) {
      const batchResult = await BatchApiService.batchValidateMachines(
        machines,
        targetType
      )
      
      // Convert batch result to validation result format
      const validationResult: BulkValidationResult = {
        allValid: batchResult.failed.length === 0,
        validMachines: batchResult.successful,
        invalidMachines: batchResult.failed.map(f => f.item),
        errors: {},
        warnings: {}
      }
      
      batchResult.failed.forEach(failure => {
        validationResult.errors[failure.item.machineName] = [{
          code: 'VALIDATION_FAILED',
          message: failure.error,
          severity: 'error'
        }]
      })
      
      return validationResult
    }
    
    // Use validation service for smaller lists
    const validationResult = MachineValidationService.validateBulkAssignment(
      machines,
      targetType
    )
    
    // Additional availability check if requested
    if (checkAvailability && validationResult.validMachines.length > 0) {
      const availabilityCheck = await this.exclusivityHook.checkAvailability(
        validationResult.validMachines.map(m => m.machineName)
      )
      
      // Update validation result based on availability
      const unavailableMachines = validationResult.validMachines.filter(m =>
        availabilityCheck.unavailable.includes(m.machineName)
      )
      
      if (unavailableMachines.length > 0) {
        validationResult.invalidMachines.push(...unavailableMachines)
        validationResult.validMachines = validationResult.validMachines.filter(m =>
          !unavailableMachines.includes(m)
        )
        validationResult.allValid = false
        
        // Add availability errors
        unavailableMachines.forEach(machine => {
          if (!validationResult.errors[machine.machineName]) {
            validationResult.errors[machine.machineName] = []
          }
          validationResult.errors[machine.machineName].push({
            code: 'MACHINE_UNAVAILABLE',
            message: `Machine is already assigned to another resource`,
            severity: 'error'
          })
        })
      }
    }
    
    return validationResult
  }
  
  /**
   * Schedule bulk operation for later execution
   */
  async scheduleBulkOperation(
    operationId: string,
    machines: string[],
    operation: () => Promise<BulkOperationResult>,
    delay: number = 0
  ): Promise<string> {
    const batches = this.createBatches(machines, 10)
    this.operationQueue.set(operationId, batches)
    
    if (delay > 0) {
      setTimeout(() => {
        operation().finally(() => {
          this.operationQueue.delete(operationId)
        })
      }, delay)
    } else {
      operation().finally(() => {
        this.operationQueue.delete(operationId)
      })
    }
    
    return operationId
  }
  
  /**
   * Generate detailed bulk operation report
   */
  generateBulkOperationReport(
    operationId: string,
    operationType: string,
    startTime: Date,
    endTime: Date,
    result: BulkOperationWorkflowResult
  ): BulkOperationReport {
    const duration = endTime.getTime() - startTime.getTime()
    
    const report: BulkOperationReport = {
      operationId,
      operationType,
      startTime,
      endTime,
      duration,
      summary: {
        total: result.totalMachines,
        successful: result.successfulMachines.length,
        failed: result.failedMachines.length,
        skipped: result.totalMachines - result.successfulMachines.length - result.failedMachines.length
      },
      batches: result.batches.map((batch, index) => ({
        batchNumber: batch.batchNumber,
        size: batch.machines.length,
        duration: 0, // Would need to track per-batch timing
        status: batch.status,
        errors: batch.error ? [batch.error.message] : undefined
      })),
      machineDetails: []
    }
    
    // Add machine details
    result.successfulMachines.forEach(machine => {
      report.machineDetails.push({
        machineName: machine,
        status: 'success'
      })
    })
    
    result.failedMachines.forEach(machine => {
      report.machineDetails.push({
        machineName: machine,
        status: 'failed',
        error: result.error?.message || 'Unknown error'
      })
    })
    
    return report
  }
  
  /**
   * Get current operation status
   */
  getOperationStatus(operationId: string): BulkOperationBatch[] | undefined {
    return this.operationQueue.get(operationId)
  }
  
  /**
   * Cancel ongoing bulk operation
   */
  cancelOperation(operationId: string): boolean {
    return this.operationQueue.delete(operationId)
  }
  
  // Private helper methods
  
  private createBatches(items: string[], batchSize: number): BulkOperationBatch[] {
    const batches: BulkOperationBatch[] = []
    
    for (let i = 0; i < items.length; i += batchSize) {
      batches.push({
        batchNumber: Math.floor(i / batchSize) + 1,
        machines: items.slice(i, i + batchSize),
        status: 'pending'
      })
    }
    
    return batches
  }
  
  private async executeStep(
    step: WorkflowStep,
    workflowId: string,
    result: BulkOperationWorkflowResult
  ): Promise<void> {
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
      
      throw error
    }
  }
  
  private async processBatches(
    workflowId: string,
    batches: BulkOperationBatch[],
    targetType: 'cluster' | 'image' | 'clone',
    targetResource: string,
    additionalInfo: CloneIdentifier | undefined,
    options: BulkOperationWorkflowOptions,
    result: BulkOperationWorkflowResult
  ): Promise<void> {
    for (const batch of batches) {
      batch.status = 'processing'
      
      try {
        // Validate batch if requested
        if (options.validateBeforeEachBatch) {
          await this.bulkHook.validateSelection(
            batch.machines.map(name => ({ machineName: name } as Machine)),
            targetType
          )
        }
        
        // Process batch with retries
        let attempt = 0
        const maxRetries = options.maxRetries || 3
        
        while (attempt <= maxRetries) {
          try {
            const batchResult = await this.bulkHook.executeBulkAssignment(
              targetType,
              targetResource,
              targetType === 'clone' ? additionalInfo : undefined
            )
            
            batch.result = batchResult
            batch.status = 'completed'
            
            result.successfulMachines.push(...batchResult.successfulMachines)
            result.failedMachines.push(...batchResult.failedMachines)
            
            break
          } catch (error) {
            attempt++
            batch.retryCount = attempt
            
            if (attempt > maxRetries) {
              throw error
            }
            
            // Wait before retry
            await new Promise(resolve => setTimeout(resolve, options.retryDelay || 1000))
          }
        }
      } catch (error) {
        batch.status = 'failed'
        batch.error = error as Error
        
        if (options.stopOnFirstError) {
          throw error
        }
      }
      
      result.batches.push(batch)
    }
  }
  
  private async processMigrationBatch(
    batch: BulkOperationBatch,
    plan: MigrationPlan,
    maxRetries: number,
    retryDelay: number
  ): Promise<MigrationResult> {
    const result: MigrationResult = {
      success: false,
      migratedMachines: [],
      failedMachines: [],
      errors: {}
    }
    
    for (const machine of batch.machines) {
      let attempt = 0
      let migrated = false
      
      while (attempt <= maxRetries && !migrated) {
        try {
          // Remove from source
          if (plan.sourcType === 'cluster') {
            await this.assignmentHook.removeFromCluster([machine])
          }
          
          // Assign to target
          if (plan.targetType === 'cluster') {
            const assignResult = await this.assignmentHook.assignToCluster([machine], plan.targetResource)
            
            if (assignResult.success) {
              result.migratedMachines.push(machine)
              migrated = true
            } else {
              throw new Error(assignResult.message || 'Failed to assign to target')
            }
          }
        } catch (error) {
          attempt++
          
          if (attempt > maxRetries) {
            result.failedMachines.push(machine)
            result.errors[machine] = error instanceof Error ? error.message : 'Unknown error'
            
            // Try to rollback
            if (plan.sourcType === 'cluster' && !migrated) {
              try {
                await this.assignmentHook.assignToCluster([machine], plan.sourceResource)
              } catch (rollbackError) {
                result.errors[machine] += ' (rollback failed)'
              }
            }
          } else {
            await new Promise(resolve => setTimeout(resolve, retryDelay))
          }
        }
      }
    }
    
    result.success = result.failedMachines.length === 0
    return result
  }
}