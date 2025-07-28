export { useMachineAssignment } from './useMachineAssignment'
export { useBulkMachineOperations } from './useBulkMachineOperations'
export { useMachineExclusivity } from './useMachineExclusivity'
export { useDebouncedMachineValidation, useRealtimeValidation } from './useDebouncedMachineValidation'

// Re-export types for convenience
export type { CloneIdentifier, PoolIdentifier, AssignmentResult } from './useMachineAssignment'
export type { BulkOperationProgress, BulkOperationResult } from './useBulkMachineOperations'
export type { MachineAvailability, ValidationCache } from './useMachineExclusivity'