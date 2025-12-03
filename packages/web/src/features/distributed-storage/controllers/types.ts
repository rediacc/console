import type { Machine, MachineAssignmentType } from '@/types'
import type {
  BulkOperationResult
} from '../hooks'
import type {
  AssignmentConflict
} from '../models'
import type { ValidationResult as BaseValidationResult, BulkValidationResult } from '../models/machine-validation.model'

// Re-export ValidationResult from model
export type ValidationResult = BaseValidationResult

// Workflow types
export interface WorkflowStep {
  name: string
  description: string
  execute: () => Promise<void>
  rollback?: () => Promise<void>
  canSkip?: boolean
}

export interface WorkflowResult {
  success: boolean
  completedSteps: string[]
  failedStep?: string
  error?: Error
  data?: unknown
}

// Assignment workflow types
export interface AssignmentWorkflowOptions {
  validateFirst?: boolean
  autoResolveConflicts?: boolean
  conflictResolutionStrategy?: ConflictResolutionStrategy
  notifyOnCompletion?: boolean
  trackProgress?: boolean
}

export enum ConflictResolutionStrategy {
  FAIL_FAST = 'FAIL_FAST',
  SKIP_CONFLICTS = 'SKIP_CONFLICTS',
  FORCE_REASSIGN = 'FORCE_REASSIGN',
  INTERACTIVE = 'INTERACTIVE'
}

export interface AssignmentWorkflowResult extends WorkflowResult {
  assignedMachines: string[]
  skippedMachines: string[]
  conflicts: AssignmentConflict[]
  validationResults?: ValidationResult[]
}

// Bulk operation workflow types
export interface BulkOperationWorkflowOptions {
  batchSize?: number
  maxRetries?: number
  retryDelay?: number
  stopOnFirstError?: boolean
  validateBeforeEachBatch?: boolean
  generateReport?: boolean
  workflowId?: string
}

export interface BulkOperationBatch {
  batchNumber: number
  machines: string[]
  status: 'pending' | 'processing' | 'completed' | 'failed'
  result?: BulkOperationResult
  error?: Error
  retryCount?: number
}

export interface BulkOperationWorkflowResult extends WorkflowResult {
  totalMachines: number
  successfulMachines: string[]
  failedMachines: string[]
  batches: BulkOperationBatch[]
  report?: BulkOperationReport
}

// Migration types
export interface MigrationPlan {
  sourcType: 'cluster' | 'image' | 'clone'
  sourceResource: string
  targetType: 'cluster' | 'image' | 'clone'
  targetResource: string
  machines: string[]
  validationPassed?: boolean
  estimatedDuration?: number
}

export interface MigrationResult {
  success: boolean
  migratedMachines: string[]
  failedMachines: string[]
  rollbackPerformed?: boolean
  errors: Record<string, string>
}

// Progress tracking
export interface OperationProgress {
  operationId: string
  type: 'assignment' | 'bulk' | 'migration'
  status: 'preparing' | 'validating' | 'executing' | 'completing' | 'completed' | 'failed'
  totalSteps: number
  currentStep: number
  currentStepName: string
  startTime: Date
  estimatedCompletion?: Date
  details?: Record<string, unknown>
}

export interface ProgressCallback {
  (progress: OperationProgress): void
}

// Report types
export interface BulkOperationReport {
  operationId: string
  operationType: string
  startTime: Date
  endTime: Date
  duration: number
  summary: {
    total: number
    successful: number
    failed: number
    skipped: number
  }
  batches: Array<{
    batchNumber: number
    size: number
    duration: number
    status: string
    errors?: string[]
  }>
  machineDetails: Array<{
    machineName: string
    status: 'success' | 'failed' | 'skipped'
    error?: string
    duration?: number
  }>
}

// Validation context for controllers
export interface ControllerValidationContext {
  machines: Machine[]
  targetType: MachineAssignmentType
  targetResource: string
  teamName: string
  options?: AssignmentWorkflowOptions
}

// Command pattern for undo/redo
export interface Command {
  execute(): Promise<void>
  undo(): Promise<void>
  canUndo(): boolean
  description: string
}

export interface CommandHistory {
  executed: Command[]
  undone: Command[]
  maxHistorySize: number
}

// Event types for observer pattern
export enum WorkflowEvent {
  STARTED = 'WORKFLOW_STARTED',
  STEP_COMPLETED = 'WORKFLOW_STEP_COMPLETED',
  STEP_FAILED = 'WORKFLOW_STEP_FAILED',
  VALIDATION_COMPLETED = 'VALIDATION_COMPLETED',
  CONFLICT_DETECTED = 'CONFLICT_DETECTED',
  PROGRESS_UPDATE = 'PROGRESS_UPDATE',
  COMPLETED = 'WORKFLOW_COMPLETED',
  FAILED = 'WORKFLOW_FAILED',
  ROLLBACK_STARTED = 'ROLLBACK_STARTED',
  ROLLBACK_COMPLETED = 'ROLLBACK_COMPLETED'
}

export type WorkflowEventPayloadMap = {
  [WorkflowEvent.STARTED]:
    | { totalMachines: number; targetType: 'cluster' | 'image' | 'clone'; targetResource: string }
    | { machineNames: string[]; clusterName: string }
    | { imageName: string; currentMachineName: string; newMachineName: string }
  [WorkflowEvent.STEP_COMPLETED]: { step: string }
  [WorkflowEvent.STEP_FAILED]: { step: string; error: string }
  [WorkflowEvent.VALIDATION_COMPLETED]:
    | { valid: number; invalid: number }
    | { available: string[]; unavailable: string[] }
  [WorkflowEvent.CONFLICT_DETECTED]: AssignmentConflict[]
  [WorkflowEvent.PROGRESS_UPDATE]:
    | { step: string; description: string }
    | { message: string; percentage: number; completed: number; total: number }
  [WorkflowEvent.COMPLETED]: AssignmentWorkflowResult | BulkOperationWorkflowResult
  [WorkflowEvent.FAILED]: { error: unknown }
  [WorkflowEvent.ROLLBACK_STARTED]: undefined
  [WorkflowEvent.ROLLBACK_COMPLETED]: undefined
}

export type WorkflowEventEnvelope<TEvent extends WorkflowEvent> =
  TEvent extends WorkflowEvent
    ? WorkflowEventPayloadMap[TEvent] extends undefined
      ? {
          event: TEvent
          workflowId: string
          timestamp: Date
        }
      : {
          event: TEvent
          workflowId: string
          timestamp: Date
          data: WorkflowEventPayloadMap[TEvent]
        }
    : never

export type WorkflowEventData = WorkflowEventEnvelope<WorkflowEvent>

export type WorkflowEventHandler = (event: WorkflowEventData) => void

// Error types
export class WorkflowError extends Error {
  constructor(
    message: string,
    public step?: string,
    public recoverable?: boolean,
    public data?: unknown
  ) {
    super(message)
    this.name = 'WorkflowError'
  }
}

export class ValidationError extends Error {
  constructor(
    message: string,
    public validationResults?: Array<ValidationResult | BulkValidationResult>,
    public machines?: string[]
  ) {
    super(message)
    this.name = 'ValidationError'
  }
}

export class ConflictError extends Error {
  constructor(
    message: string,
    public conflicts?: AssignmentConflict[],
    public resolutionStrategy?: ConflictResolutionStrategy
  ) {
    super(message)
    this.name = 'ConflictError'
  }
}
