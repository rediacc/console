// Re-export services from shared

// Re-export types from shared for convenience
export type {
  AssignmentConflict,
  AssignmentResult,
  BulkOperationRequest,
  BulkValidationResult,
  CapacityValidation,
  CephResource,
  CephResourceType,
  ConflictResolution,
  ConflictResolutionAction,
  ConflictResolutionResult,
  ConflictType,
  ExclusivityValidation,
  InvalidMachine,
  MachineAssignment,
  MachineAssignmentSummary,
  ValidationConfig,
  ValidationContext,
  ValidationError,
  ValidationResult,
  ValidationRule,
  ValidationSummary,
  ValidationWarning,
} from '@rediacc/shared/services/machine';
export {
  MachineAssignmentService,
  MachineValidationService,
} from '@rediacc/shared/services/machine';
// BatchApiService - uses web-specific API, keep local implementation
export { BatchApiService } from './batch-api.service';
