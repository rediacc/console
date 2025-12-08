export type { BulkOperationProgress, BulkOperationResult } from './useBulkMachineOperations';
export { useBulkMachineOperations } from './useBulkMachineOperations';
export {
  useDebouncedMachineValidation,
  useRealtimeValidation,
} from './useDebouncedMachineValidation';
// Re-export types for convenience - renamed to avoid conflicts with models
export type {
  AssignmentResult as HookAssignmentResult,
  CloneIdentifier,
  PoolIdentifier,
} from './useMachineAssignment';
export { useMachineAssignment } from './useMachineAssignment';
export type { MachineAvailability, ValidationCache } from './useMachineExclusivity';
export { useMachineExclusivity } from './useMachineExclusivity';
