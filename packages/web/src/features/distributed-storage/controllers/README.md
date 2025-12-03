# Distributed Storage Controllers

Controllers orchestrate complex workflows and coordinate between hooks, services, and components.

## Usage Example

```typescript
import { 
  useMachineAssignment, 
  useBulkMachineOperations, 
  useMachineExclusivity,
  createMachineAssignmentController,
  createBulkOperationsController
} from '@/features/distributed-storage'

// In a React component
function MyComponent() {
  const teamName = 'Default'
  
  // Initialize hooks
  const assignmentHook = useMachineAssignment(teamName)
  const bulkHook = useBulkMachineOperations(teamName)
  const exclusivityHook = useMachineExclusivity(teamName)
  
  // Create controllers
  const assignmentController = useMemo(
    () => createMachineAssignmentController(assignmentHook, exclusivityHook),
    [assignmentHook, exclusivityHook]
  )
  
  const bulkController = useMemo(
    () => createBulkOperationsController(bulkHook, assignmentHook, exclusivityHook),
    [bulkHook, assignmentHook, exclusivityHook]
  )
  
  // Use controllers for complex operations
  const handleAssignToCluster = async (machines: string[], clusterName: string) => {
    try {
      // Subscribe to workflow events
      const unsubscribe = assignmentController.subscribe((event) => {
        console.log('Workflow event:', event)
        
        if (event.event === WorkflowEvent.PROGRESS_UPDATE) {
          // Update UI with progress
        }
      })
      
      // Execute assignment workflow
      const result = await assignmentController.assignMachineToCluster(
        machines,
        clusterName,
        teamName,
        {
          validateFirst: true,
          autoResolveConflicts: true,
          conflictResolutionStrategy: ConflictResolutionStrategy.SKIP_CONFLICTS
        }
      )
      
      if (result.success) {
        showMessage('success', `Assigned ${result.assignedMachines.length} machines`)
      } else {
        showMessage('error', result.error?.message || 'Assignment failed')
      }
      
      unsubscribe()
    } catch (error) {
      console.error('Assignment failed:', error)
    }
  }
  
  const handleBulkOperation = async (machines: Machine[]) => {
    try {
      // Execute bulk assignment with progress tracking
      const result = await bulkController.executeBulkAssignmentWorkflow(
        machines,
        'cluster',
        'my-cluster',
        undefined,
        {
          batchSize: 10,
          maxRetries: 3,
          validateBeforeEachBatch: true,
          generateReport: true
        }
      )
      
      if (result.report) {
        console.log('Operation report:', result.report)
        // Display report to user
      }
    } catch (error) {
      console.error('Bulk operation failed:', error)
    }
  }
  
  // ... rest of component
}
```

## Controller Features

### MachineAssignmentController

- **Workflow Management**: Orchestrates multi-step assignment workflows
- **Conflict Resolution**: Automatic handling of assignment conflicts
- **Rollback Support**: Undo operations on failure
- **Event System**: Subscribe to workflow events for real-time updates
- **Command History**: Track and undo operations

### BulkOperationsController

- **Batch Processing**: Process large operations in configurable batches
- **Retry Logic**: Automatic retry with exponential backoff
- **Progress Tracking**: Real-time progress updates
- **Report Generation**: Detailed operation reports
- **Queue Management**: Schedule and manage bulk operations

## Workflow Events

Controllers emit events throughout workflow execution:

- `WORKFLOW_STARTED`: Workflow begins
- `STEP_COMPLETED`: Individual step completes
- `VALIDATION_COMPLETED`: Validation phase completes
- `CONFLICT_DETECTED`: Assignment conflict found
- `PROGRESS_UPDATE`: Progress update available
- `WORKFLOW_COMPLETED`: Workflow completes successfully
- `WORKFLOW_FAILED`: Workflow fails
- `ROLLBACK_STARTED`: Rollback begins
- `ROLLBACK_COMPLETED`: Rollback completes

## Error Handling

Controllers throw specific error types:

- `WorkflowError`: General workflow failure
- `ValidationError`: Validation failure with details
- `ConflictError`: Assignment conflict with resolution options

## Best Practices

1. **Always use controllers for complex operations** involving multiple steps
2. **Subscribe to events** for UI updates and progress tracking
3. **Configure options** based on your use case (validation, conflict resolution)
4. **Handle errors gracefully** with appropriate user feedback
5. **Use reports** for audit trails and debugging