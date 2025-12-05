export { MachineAssignmentController } from './machine-assignment.controller';
export { BulkOperationsController } from './bulk-operations.controller';

// Re-export types
export * from './types';

// Factory functions for creating controllers with hooks
import type {
  useMachineAssignment,
  useBulkMachineOperations,
  useMachineExclusivity,
} from '../hooks';
import { MachineAssignmentController } from './machine-assignment.controller';
import { BulkOperationsController } from './bulk-operations.controller';

/**
 * Create a machine assignment controller instance
 */
export function createMachineAssignmentController(
  assignmentHook: ReturnType<typeof useMachineAssignment>,
  exclusivityHook: ReturnType<typeof useMachineExclusivity>
): MachineAssignmentController {
  return new MachineAssignmentController(assignmentHook, exclusivityHook);
}

/**
 * Create a bulk operations controller instance
 */
export function createBulkOperationsController(
  bulkHook: ReturnType<typeof useBulkMachineOperations>,
  assignmentHook: ReturnType<typeof useMachineAssignment>,
  exclusivityHook: ReturnType<typeof useMachineExclusivity>
): BulkOperationsController {
  return new BulkOperationsController(bulkHook, assignmentHook, exclusivityHook);
}
