// Re-export services from shared
export { MachineAssignmentService } from '@rediacc/shared/services/machine';
export { MachineValidationService } from '@rediacc/shared/services/machine';

// BatchApiService - uses web-specific API, keep local implementation
export { BatchApiService } from './batch-api.service';

// Re-export types from shared for convenience
export type {
  MachineAssignment,
  BulkOperationRequest,
  AssignmentConflict,
  ConflictResolution,
  ConflictResolutionResult,
  CephResource,
  AssignmentResult,
  MachineAssignmentSummary,
  ValidationResult,
  ValidationError,
  ValidationWarning,
  InvalidMachine,
  BulkValidationResult,
  ValidationSummary,
  ValidationRule,
  ValidationContext,
  ExclusivityValidation,
  CapacityValidation,
  ValidationConfig,
  CephResourceType,
  ConflictType,
  ConflictResolutionAction,
} from '@rediacc/shared/services/machine';
