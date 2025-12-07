import { createAsyncThunk } from '@reduxjs/toolkit';
import { MachineValidationService } from '@/features/ceph';
import type { BulkValidationResult, ValidationResult } from '@/features/ceph';
import type { RootState } from '@/store/store';
import type { Machine } from '@/types';
import { clearStaleValidations, setMultipleValidationResults } from './machineAssignmentSlice';
import type { Middleware, MiddlewareAPI, UnknownAction } from '@reduxjs/toolkit';

// Configuration
const VALIDATION_CACHE_DURATION = 5 * 60 * 1000; // 5 minutes
const VALIDATION_CLEANUP_INTERVAL = 60 * 1000; // Check every minute

// Track initialization state
let middlewareInitialized = false;

// Middleware for managing side effects
export const machineAssignmentMiddleware: Middleware =
  (store: MiddlewareAPI) => (next) => (action) => {
    // Set up periodic validation cache cleanup (only once)
    if (!middlewareInitialized) {
      middlewareInitialized = true;
      const validationCleanupInterval = setInterval(() => {
        store.dispatch(clearStaleValidations(VALIDATION_CACHE_DURATION));
      }, VALIDATION_CLEANUP_INTERVAL);

      // Clean up on unload
      if (typeof window !== 'undefined') {
        window.addEventListener('beforeunload', () => {
          clearInterval(validationCleanupInterval);
        });
      }
    }

    const result = next(action);
    const typedAction = action as UnknownAction;

    // Handle specific actions
    switch (typedAction.type) {
      case 'machineAssignment/completeBulkOperation': {
        // Clear validations for machines that were part of the operation
        const state = store.getState();
        const operationResult = state.machineAssignment.lastOperationResult;

        if (operationResult) {
          // Clear validations after a delay to allow UI to show results
          setTimeout(() => {
            store.dispatch(clearStaleValidations(0)); // Clear all stale validations
          }, 2000);
        }
        break;
      }

      case 'machineAssignment/startBulkOperation':
        // Could add analytics tracking here
        break;

      case 'machineAssignment/setSelectedMachines':
      case 'machineAssignment/addSelectedMachines':
        // Could trigger validation for newly selected machines
        // This would be done by dispatching an async thunk
        break;
    }

    return result;
  };

// Middleware for persisting selection across page refreshes (optional)
export const machineSelectionPersistenceMiddleware: Middleware =
  (store: MiddlewareAPI) => (next) => (action) => {
    const result = next(action);
    const typedAction = action as UnknownAction;

    // Persist selection to sessionStorage
    if (
      typedAction.type === 'machineAssignment/setSelectedMachines' ||
      typedAction.type === 'machineAssignment/addSelectedMachines' ||
      typedAction.type === 'machineAssignment/removeSelectedMachines' ||
      typedAction.type === 'machineAssignment/clearSelection' ||
      typedAction.type === 'machineAssignment/toggleMachineSelection'
    ) {
      const state = store.getState();
      const selectedMachines = state.machineAssignment.selectedMachines;

      try {
        sessionStorage.setItem('machineSelection', JSON.stringify(selectedMachines));
      } catch (error: unknown) {
        console.warn('Failed to persist machine selection:', error);
      }
    }

    return result;
  };

// Middleware for logging operations (development only)
export const machineAssignmentLoggingMiddleware: Middleware =
  (store: MiddlewareAPI) => (next) => (action) => {
    const typedAction = action as UnknownAction;
    if (import.meta.env.DEV && String(typedAction.type).startsWith('machineAssignment/')) {
      console.warn(`Machine Assignment action: ${typedAction.type}`, {
        action,
        stateBefore: store.getState().machineAssignment,
      });
    }

    const result = next(action);

    if (import.meta.env.DEV && String(typedAction.type).startsWith('machineAssignment/')) {
      console.warn('Machine Assignment state after:', store.getState().machineAssignment);
    }

    return result;
  };

// Utility function to restore persisted selection
export const restorePersistedSelection = () => {
  try {
    const persisted = sessionStorage.getItem('machineSelection');
    if (persisted) {
      return JSON.parse(persisted) as string[];
    }
  } catch (error: unknown) {
    console.warn('Failed to restore machine selection:', error);
  }
  return null;
};

// Async thunk for validating selected machines
export const validateSelectedMachines = createAsyncThunk<
  void,
  {
    machines: Machine[];
    targetType: 'cluster' | 'image' | 'clone';
  },
  { state: RootState }
>(
  'machineAssignment/validateSelectedMachines',
  async ({ machines, targetType }, { dispatch, getState }) => {
    const state = getState();
    const selectedMachines = state.machineAssignment.selectedMachines;

    // Filter to only validate selected machines
    const machinesToValidate = machines.filter((m) => selectedMachines.includes(m.machineName));

    // Perform validation
    const validationResult: BulkValidationResult = MachineValidationService.validateBulkAssignment(
      machinesToValidate,
      targetType
    );

    // Convert to validation results format
    const results = machinesToValidate.map(({ machineName }) => {
      const isValid = validationResult.validMachines.some((vm) => vm.machineName === machineName);

      const errors = validationResult.errors[machineName] || [];
      const warnings = validationResult.warnings[machineName] || [];

      return {
        machineName,
        result: {
          isValid,
          errors,
          warnings,
        } as ValidationResult,
      };
    });

    // Dispatch validation results
    dispatch(setMultipleValidationResults(results));
  }
);
