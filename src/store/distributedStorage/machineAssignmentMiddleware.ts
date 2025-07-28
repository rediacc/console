import { Middleware } from '@reduxjs/toolkit'
import type { RootState } from '@/store/store'
import { clearStaleValidations } from './machineAssignmentSlice'

// Configuration
const VALIDATION_CACHE_DURATION = 5 * 60 * 1000 // 5 minutes
const VALIDATION_CLEANUP_INTERVAL = 60 * 1000 // Check every minute
const OPERATION_HISTORY_LIMIT = 20

// Middleware for managing side effects
export const machineAssignmentMiddleware: Middleware<{}, RootState> = 
  (store) => {
    // Set up periodic validation cache cleanup
    const validationCleanupInterval = setInterval(() => {
      store.dispatch(clearStaleValidations(VALIDATION_CACHE_DURATION))
    }, VALIDATION_CLEANUP_INTERVAL)
    
    // Clean up on unload
    if (typeof window !== 'undefined') {
      window.addEventListener('beforeunload', () => {
        clearInterval(validationCleanupInterval)
      })
    }
    
    return (next) => (action) => {
      const result = next(action)
      
      // Handle specific actions
      switch (action.type) {
        case 'machineAssignment/completeBulkOperation':
          // Clear validations for machines that were part of the operation
          const state = store.getState()
          const operationResult = state.machineAssignment.lastOperationResult
          
          if (operationResult) {
            const affectedMachines = [
              ...operationResult.successfulMachines,
              ...operationResult.failedMachines
            ]
            
            // Clear validations after a delay to allow UI to show results
            setTimeout(() => {
              store.dispatch(clearStaleValidations(0)) // Clear all stale validations
            }, 2000)
          }
          break
          
        case 'machineAssignment/startBulkOperation':
          // Could add analytics tracking here
          console.log('Bulk operation started:', action.payload)
          break
          
        case 'machineAssignment/setSelectedMachines':
        case 'machineAssignment/addSelectedMachines':
          // Could trigger validation for newly selected machines
          // This would be done by dispatching an async thunk
          break
      }
      
      return result
    }
  }

// Middleware for persisting selection across page refreshes (optional)
export const machineSelectionPersistenceMiddleware: Middleware<{}, RootState> = 
  (store) => (next) => (action) => {
    const result = next(action)
    
    // Persist selection to sessionStorage
    if (
      action.type === 'machineAssignment/setSelectedMachines' ||
      action.type === 'machineAssignment/addSelectedMachines' ||
      action.type === 'machineAssignment/removeSelectedMachines' ||
      action.type === 'machineAssignment/clearSelection' ||
      action.type === 'machineAssignment/toggleMachineSelection'
    ) {
      const state = store.getState()
      const selectedMachines = state.machineAssignment.selectedMachines
      
      try {
        sessionStorage.setItem('machineSelection', JSON.stringify(selectedMachines))
      } catch (error) {
        console.warn('Failed to persist machine selection:', error)
      }
    }
    
    return result
  }

// Middleware for logging operations (development only)
export const machineAssignmentLoggingMiddleware: Middleware<{}, RootState> = 
  (store) => (next) => (action) => {
    if (process.env.NODE_ENV === 'development') {
      if (action.type.startsWith('machineAssignment/')) {
        console.group(`🔧 Machine Assignment: ${action.type}`)
        console.log('Action:', action)
        console.log('State before:', store.getState().machineAssignment)
      }
    }
    
    const result = next(action)
    
    if (process.env.NODE_ENV === 'development') {
      if (action.type.startsWith('machineAssignment/')) {
        console.log('State after:', store.getState().machineAssignment)
        console.groupEnd()
      }
    }
    
    return result
  }

// Utility function to restore persisted selection
export const restorePersistedSelection = () => {
  try {
    const persisted = sessionStorage.getItem('machineSelection')
    if (persisted) {
      return JSON.parse(persisted) as string[]
    }
  } catch (error) {
    console.warn('Failed to restore machine selection:', error)
  }
  return null
}

// Async thunk for validating selected machines
import { createAsyncThunk } from '@reduxjs/toolkit'
import { MachineValidationService } from '@/features/distributed-storage'
import type { Machine } from '@/types'
import { setMultipleValidationResults } from './machineAssignmentSlice'

export const validateSelectedMachines = createAsyncThunk<
  void,
  {
    machines: Machine[]
    targetType: 'cluster' | 'image' | 'clone'
  },
  { state: RootState }
>(
  'machineAssignment/validateSelectedMachines',
  async ({ machines, targetType }, { dispatch, getState }) => {
    const state = getState()
    const selectedMachines = state.machineAssignment.selectedMachines
    
    // Filter to only validate selected machines
    const machinesToValidate = machines.filter(m => 
      selectedMachines.includes(m.machineName)
    )
    
    // Perform validation
    const validationResult = MachineValidationService.validateBulkAssignment(
      machinesToValidate,
      targetType
    )
    
    // Convert to validation results format
    const results = machinesToValidate.map(machine => {
      const isValid = validationResult.validMachines.some(
        vm => vm.machineName === machine.machineName
      )
      
      const errors = validationResult.errors[machine.machineName] || []
      const warnings = validationResult.warnings[machine.machineName] || []
      
      return {
        machineName: machine.machineName,
        result: {
          isValid,
          errors,
          warnings
        }
      }
    })
    
    // Dispatch validation results
    dispatch(setMultipleValidationResults(results))
  }
)