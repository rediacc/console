/**
 * Machine assignment and validation types
 * Platform-agnostic type definitions for machine operations
 */

import type {
  GetTeamMachines_ResultSet1,
  MachineAssignmentStatus,
  MachineAssignmentType,
} from '../../types';

// Re-export for convenience
export type { MachineAssignmentStatus };

// ============================================================================
// Machine Type Extensions
// ============================================================================

/**
 * Extended machine type with assignment status
 * Now inherits assignmentStatus from base type GetTeamMachines_ResultSet1
 */
export type MachineWithAssignmentStatus = GetTeamMachines_ResultSet1;

// ============================================================================
// Assignment Types
// ============================================================================

export interface MachineAssignment {
  machineId: string;
  machineName: string;
  assignmentType: MachineAssignmentType;
  resourceId?: string;
  resourceName?: string;
  assignedAt?: Date;
}

export interface BulkOperationRequest {
  machines: string[];
  operation: 'assign' | 'remove';
  targetType: CephResourceType;
  targetResource: string;
  teamName: string;
}

export type CephResourceType = 'cluster' | 'pool' | 'image' | 'snapshot' | 'clone';

export interface CephResource {
  id: string;
  name: string;
  type: CephResourceType;
  assignedMachines?: string[];
  teamName?: string;
}

export type ConflictType = 'exclusivity' | 'availability' | 'permission';

export interface AssignmentConflict {
  machine: MachineWithAssignmentStatus;
  machineName: string;
  currentAssignment: MachineAssignment;
  requestedAssignment: string;
  conflictType: ConflictType;
  targetType?: CephResourceType;
  targetResource?: string;
  message?: string;
}

export type ConflictResolutionAction = 'skip' | 'force' | 'cancel';

export interface ConflictResolution {
  conflict: AssignmentConflict;
  action: ConflictResolutionAction;
  resolved: boolean;
  error?: string;
}

export interface ConflictResolutionResult {
  resolution: ConflictResolutionAction;
  reason?: string;
}

export interface AssignmentResult {
  success: boolean;
  assignedMachines: string[];
  failedMachines: string[];
  conflicts: AssignmentConflict[];
}

export interface MachineAssignmentSummary {
  totalMachines: number;
  availableMachines: number;
  clusterAssignedMachines: number;
  imageAssignedMachines: number;
  cloneAssignedMachines: number;
  assignmentBreakdown: Map<MachineAssignmentType, number>;
}

// ============================================================================
// Validation Types
// ============================================================================

export interface ValidationResult {
  isValid: boolean;
  errors: ValidationError[];
  warnings: ValidationWarning[];
  context?: Record<string, unknown>;
}

export interface ValidationError {
  code: string;
  message: string;
  field?: string;
  severity?: 'error' | 'warning';
  context?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
}

export interface ValidationWarning {
  code: string;
  message: string;
  field?: string;
  severity: 'low' | 'medium' | 'high';
}

export interface InvalidMachine {
  machine: MachineWithAssignmentStatus;
  machineName: string;
  errors: ValidationError[];
  canOverride: boolean;
}

export interface BulkValidationResult {
  validMachines: MachineWithAssignmentStatus[];
  invalidMachines: InvalidMachine[];
  summary: ValidationSummary;
  canProceed: boolean;
  allValid: boolean;
  errors: Record<string, ValidationError[]>;
  warnings: Record<string, ValidationWarning[]>;
}

export interface ValidationSummary {
  totalMachines: number;
  validCount: number;
  invalidCount: number;
  errorTypes: Map<string, number>;
  warningCount: number;
  criticalErrors: boolean;
}

export type ValidationRule =
  | 'exclusivity'
  | 'availability'
  | 'permission'
  | 'capacity'
  | 'compatibility';

export interface ValidationContext {
  targetType: CephResourceType;
  targetResource?: string;
  teamName: string;
  userId?: string;
  skipWarnings?: boolean;
}

export interface ExclusivityValidation {
  isExclusive: boolean;
  conflictType?: 'cluster' | 'image' | 'clone';
  conflictResource?: string;
  canOverride: boolean;
  assignmentType?: MachineAssignmentType;
  resourceName?: string;
  machineName?: string;
}

export interface CapacityValidation {
  hasCapacity: boolean;
  currentCount: number;
  maxCount: number;
  remainingCapacity: number;
}

export interface ValidationConfig {
  checkExclusivity: boolean;
  checkAvailability: boolean;
  checkPermissions: boolean;
  checkCapacity: boolean;
  allowOverride: boolean;
}
