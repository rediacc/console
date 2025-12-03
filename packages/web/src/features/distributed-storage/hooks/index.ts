export { useMachineAssignment } from './useMachineAssignment'
export { useBulkMachineOperations } from './useBulkMachineOperations'
export { useMachineExclusivity } from './useMachineExclusivity'
export { useDebouncedMachineValidation, useRealtimeValidation } from './useDebouncedMachineValidation'

// Re-export types for convenience - renamed to avoid conflicts with models
export type { CloneIdentifier, PoolIdentifier, AssignmentResult as HookAssignmentResult } from './useMachineAssignment'
export type { BulkOperationProgress, BulkOperationResult } from './useBulkMachineOperations'
export type { MachineAvailability, ValidationCache } from './useMachineExclusivity'