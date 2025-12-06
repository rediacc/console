# Machine Assignment Redux Store

This Redux store manages the state for distributed storage machine assignments, including selection, validation, and bulk operations.

## Usage Example

```typescript
import { useMachineAssignmentStore } from '@/store/ceph/hooks'
import { useAppDispatch } from '@/store/store'
import { validateSelectedMachines } from '@/store/ceph/machineAssignmentMiddleware'

function MachineManagementComponent() {
  const dispatch = useAppDispatch()
  const {
    // Selection
    selectedMachines,
    selectedCount,
    hasSelection,
    selectMachines,
    deselectMachines,
    toggleSelection,
    clearSelection,
    
    // Operations
    isOperationInProgress,
    operationProgress,
    startOperation,
    completeOperation,
    
    // Filters
    activeFilters,
    updateFilter,
    
    // Validation
    areAllSelectedValid
  } = useMachineAssignmentStore()
  
  // Select machines
  const handleSelectMachines = (machines: string[]) => {
    selectMachines(machines)
    
    // Trigger validation
    dispatch(validateSelectedMachines({ 
      machines: machineList, 
      targetType: 'cluster' 
    }))
  }
  
  // Start bulk operation
  const handleBulkAssign = async () => {
    startOperation('assign', 'cluster', 'my-cluster', selectedCount)
    
    // ... perform operation ...
    
    completeOperation({
      success: true,
      successfulMachines: selectedMachines,
      failedMachines: [],
      errors: {}
    })
  }
  
  // Filter machines
  const handleFilter = (assignmentType: MachineAssignmentType) => {
    updateFilter('assignmentType', assignmentType)
  }
  
  return (
    // ... your component JSX
  )
}
```

## State Structure

### Selection State
- `selectedMachines`: Array of selected machine names
- `selectionMode`: 'single' | 'multiple' | null

### Validation State
- `assignmentValidation`: Cached validation results by machine name
- `validationTimestamps`: Timestamps for cache expiry

### Operation State
- `bulkOperationInProgress`: Boolean flag for ongoing operations
- `currentOperation`: Details of the current operation
- `lastOperationResult`: Result of the last completed operation
- `operationHistory`: Array of recent operations

### UI State
- `activeFilters`: Current filter criteria
- `expandedGroups`: Expanded UI groups

## Available Hooks

### `useMachineSelection()`
Manages machine selection state.

### `useBulkOperationState()`
Manages bulk operation progress and results.

### `useMachineFilters()`
Manages filtering of machine lists.

### `useMachineAssignmentUI()`
Manages UI-specific state like group expansions.

### `useMachineAssignmentStore()`
Combined hook that provides all functionality.

### `useIsMachineSelected(machineName)`
Check if a specific machine is selected.

### `useFilteredMachines(machines)`
Get filtered machine list based on active filters.

## Selectors

The store provides numerous selectors for efficient state access:

- `selectSelectedMachines`: Get selected machine names
- `selectSelectedMachineCount`: Get count of selected machines
- `selectIsAnyMachineSelected`: Check if any machine is selected
- `selectValidationForMachine`: Get validation result for a machine
- `selectIsOperationInProgress`: Check if operation is running
- `selectFilteredMachines`: Apply filters to machine list
- `selectSelectionSummary`: Get summary of current selection

## Middleware

### Validation Cache Cleanup
Automatically clears stale validation results after 5 minutes.

### Selection Persistence
Optionally persists selection to sessionStorage.

### Operation Logging
Logs all actions in development mode for debugging.

## Best Practices

1. **Always validate before operations**: Use the `validateSelectedMachines` thunk
2. **Clear selection after operations**: Call `clearSelection()` after successful operations
3. **Use selectors**: Always use selectors instead of accessing state directly
4. **Handle operation results**: Check `lastOperationResult` for success/failure
5. **Respect selection mode**: Check `selectionMode` before allowing multiple selections