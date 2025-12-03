import type { Machine, MachineAssignmentType } from '@/types'

export interface ValidationResult {
  isValid: boolean
  errors: ValidationError[]
  warnings: ValidationWarning[]
  context?: Record<string, unknown>
}

export interface ValidationError {
  code: string
  message: string
  field?: string
  severity?: 'error' | 'warning'
  context?: Record<string, unknown>
  metadata?: Record<string, unknown>
}

export interface ValidationWarning {
  code: string
  message: string
  field?: string
  severity: 'low' | 'medium' | 'high'
}

export interface InvalidMachine {
  machine: Machine
  machineName: string
  errors: ValidationError[]
  canOverride: boolean
}

export interface BulkValidationResult {
  validMachines: Machine[]
  invalidMachines: InvalidMachine[]
  summary: ValidationSummary
  canProceed: boolean
  allValid: boolean
  errors: Record<string, ValidationError[]>
  warnings: Record<string, ValidationWarning[]>
}

export interface ValidationSummary {
  totalMachines: number
  validCount: number
  invalidCount: number
  errorTypes: Map<string, number>
  warningCount: number
  criticalErrors: boolean
}

export type ValidationRule = 'exclusivity' | 'availability' | 'permission' | 'capacity' | 'compatibility'

export interface ValidationContext {
  targetType: 'cluster' | 'image' | 'clone'
  targetResource?: string
  teamName: string
  userId?: string
  skipWarnings?: boolean
}

export interface ExclusivityValidation {
  isExclusive: boolean
  conflictType?: 'cluster' | 'image' | 'clone'
  conflictResource?: string
  canOverride: boolean
  assignmentType?: MachineAssignmentType
  resourceName?: string
  machineName?: string
}

export interface CapacityValidation {
  hasCapacity: boolean
  currentCount: number
  maxCount: number
  remainingCapacity: number
}

export interface ValidationConfig {
  checkExclusivity: boolean
  checkAvailability: boolean
  checkPermissions: boolean
  checkCapacity: boolean
  allowOverride: boolean
}
