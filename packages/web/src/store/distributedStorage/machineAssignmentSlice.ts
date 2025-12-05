import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import type {
  ValidationResult,
  BulkOperationProgress,
  BulkOperationResult,
} from '@/features/distributed-storage';
import type { MachineAssignmentType } from '@/types';

// Types
export interface OperationHistoryDetails {
  successful: number;
  failed: number;
  errorMessage?: string;
}

export interface OperationHistoryEntry {
  id: string;
  timestamp: Date;
  type: 'assign' | 'remove' | 'migrate';
  targetType: 'cluster' | 'image' | 'clone';
  targetResource: string;
  machineCount: number;
  result: 'success' | 'partial' | 'failed';
  details?: OperationHistoryDetails;
}

export interface CurrentOperation {
  type: 'assign' | 'remove' | 'migrate' | null;
  targetType: 'cluster' | 'image' | 'clone' | null;
  targetResource: string | null;
  progress: BulkOperationProgress | null;
}

export interface MachineAssignmentState {
  // Selection Management
  selectedMachines: string[];
  selectionMode: 'single' | 'multiple' | null;

  // Validation State
  assignmentValidation: Record<string, ValidationResult>;
  validationTimestamps: Record<string, number>;

  // Operation State
  bulkOperationInProgress: boolean;
  currentOperation: CurrentOperation | null;

  // Operation History
  lastOperationResult: BulkOperationResult | null;
  operationHistory: OperationHistoryEntry[];

  // UI State
  activeFilters: {
    assignmentType?: MachineAssignmentType;
    teamName?: string;
    searchQuery?: string;
  };
  expandedGroups: string[];
}

type ActiveFilterKey = keyof MachineAssignmentState['activeFilters'];
type ActiveFilterValue = MachineAssignmentState['activeFilters'][ActiveFilterKey];

const initialState: MachineAssignmentState = {
  selectedMachines: [],
  selectionMode: null,
  assignmentValidation: {},
  validationTimestamps: {},
  bulkOperationInProgress: false,
  currentOperation: null,
  lastOperationResult: null,
  operationHistory: [],
  activeFilters: {},
  expandedGroups: [],
};

const machineAssignmentSlice = createSlice({
  name: 'machineAssignment',
  initialState,
  reducers: {
    // Selection Management
    setSelectedMachines: (state, action: PayloadAction<string[]>) => {
      state.selectedMachines = action.payload;
    },

    addSelectedMachines: (state, action: PayloadAction<string[]>) => {
      const newMachines = action.payload.filter(
        (machine) => !state.selectedMachines.includes(machine)
      );
      state.selectedMachines.push(...newMachines);
    },

    removeSelectedMachines: (state, action: PayloadAction<string[]>) => {
      state.selectedMachines = state.selectedMachines.filter(
        (machine) => !action.payload.includes(machine)
      );
    },

    toggleMachineSelection: (state, action: PayloadAction<string>) => {
      const machine = action.payload;
      const index = state.selectedMachines.indexOf(machine);

      if (index > -1) {
        state.selectedMachines.splice(index, 1);
      } else {
        if (state.selectionMode === 'single') {
          state.selectedMachines = [machine];
        } else {
          state.selectedMachines.push(machine);
        }
      }
    },

    clearSelection: (state) => {
      state.selectedMachines = [];
    },

    setSelectionMode: (state, action: PayloadAction<'single' | 'multiple' | null>) => {
      state.selectionMode = action.payload;

      // If switching to single mode with multiple selections, keep only the first
      if (action.payload === 'single' && state.selectedMachines.length > 1) {
        state.selectedMachines = [state.selectedMachines[0]];
      }
    },

    // Validation Management
    setValidationResult: (
      state,
      action: PayloadAction<{
        machineName: string;
        result: ValidationResult;
      }>
    ) => {
      const { machineName, result } = action.payload;
      state.assignmentValidation[machineName] = result;
      state.validationTimestamps[machineName] = Date.now();
    },

    setMultipleValidationResults: (
      state,
      action: PayloadAction<Array<{ machineName: string; result: ValidationResult }>>
    ) => {
      const timestamp = Date.now();
      action.payload.forEach(({ machineName, result }) => {
        state.assignmentValidation[machineName] = result;
        state.validationTimestamps[machineName] = timestamp;
      });
    },

    clearStaleValidations: (state, action: PayloadAction<number>) => {
      const maxAge = action.payload; // milliseconds
      const now = Date.now();

      Object.keys(state.validationTimestamps).forEach((machineName) => {
        if (now - state.validationTimestamps[machineName] > maxAge) {
          delete state.assignmentValidation[machineName];
          delete state.validationTimestamps[machineName];
        }
      });
    },

    clearValidationForMachines: (state, action: PayloadAction<string[]>) => {
      action.payload.forEach((machineName) => {
        delete state.assignmentValidation[machineName];
        delete state.validationTimestamps[machineName];
      });
    },

    // Operation Management
    startBulkOperation: (
      state,
      action: PayloadAction<{
        type: 'assign' | 'remove' | 'migrate';
        targetType: 'cluster' | 'image' | 'clone';
        targetResource: string;
        totalMachines: number;
      }>
    ) => {
      state.bulkOperationInProgress = true;
      state.currentOperation = {
        type: action.payload.type,
        targetType: action.payload.targetType,
        targetResource: action.payload.targetResource,
        progress: {
          total: action.payload.totalMachines,
          completed: 0,
          failed: 0,
          isProcessing: true,
        },
      };
    },

    updateOperationProgress: (state, action: PayloadAction<Partial<BulkOperationProgress>>) => {
      if (state.currentOperation?.progress) {
        state.currentOperation.progress = {
          ...state.currentOperation.progress,
          ...action.payload,
        };
      }
    },

    completeBulkOperation: (
      state,
      action: PayloadAction<{
        result: BulkOperationResult;
        addToHistory?: boolean;
      }>
    ) => {
      state.bulkOperationInProgress = false;
      state.lastOperationResult = action.payload.result;

      // Add to operation history if requested
      if (action.payload.addToHistory && state.currentOperation) {
        const historyEntry: OperationHistoryEntry = {
          id: `op-${Date.now()}`,
          timestamp: new Date(),
          type: state.currentOperation.type!,
          targetType: state.currentOperation.targetType!,
          targetResource: state.currentOperation.targetResource!,
          machineCount: state.currentOperation.progress?.total || 0,
          result: action.payload.result.success
            ? 'success'
            : action.payload.result.failedMachines.length > 0 &&
                action.payload.result.successfulMachines.length > 0
              ? 'partial'
              : 'failed',
          details: {
            successful: action.payload.result.successfulMachines.length,
            failed: action.payload.result.failedMachines.length,
          },
        };

        // Add to history (keep last 20 entries)
        state.operationHistory = [historyEntry, ...state.operationHistory].slice(0, 20);
      }

      state.currentOperation = null;
    },

    cancelBulkOperation: (state) => {
      state.bulkOperationInProgress = false;
      state.currentOperation = null;
    },

    // Filter Management
    setActiveFilters: (
      state,
      action: PayloadAction<{
        assignmentType?: MachineAssignmentType;
        teamName?: string;
        searchQuery?: string;
      }>
    ) => {
      state.activeFilters = action.payload;
    },

    updateFilter: (
      state,
      action: PayloadAction<{
        key: ActiveFilterKey;
        value: ActiveFilterValue | undefined;
      }>
    ) => {
      const { key, value } = action.payload;
      if (value === undefined || value === '') {
        delete state.activeFilters[key];
      } else {
        state.activeFilters[key] = value;
      }
    },

    clearFilters: (state) => {
      state.activeFilters = {};
    },

    // UI State Management
    toggleGroupExpansion: (state, action: PayloadAction<string>) => {
      const groupId = action.payload;
      const index = state.expandedGroups.indexOf(groupId);

      if (index > -1) {
        state.expandedGroups.splice(index, 1);
      } else {
        state.expandedGroups.push(groupId);
      }
    },

    setExpandedGroups: (state, action: PayloadAction<string[]>) => {
      state.expandedGroups = action.payload;
    },

    // History Management
    clearOperationHistory: (state) => {
      state.operationHistory = [];
    },

    removeFromHistory: (state, action: PayloadAction<string>) => {
      state.operationHistory = state.operationHistory.filter(
        (entry) => entry.id !== action.payload
      );
    },
  },
});

// Export actions
export const {
  // Selection
  setSelectedMachines,
  addSelectedMachines,
  removeSelectedMachines,
  toggleMachineSelection,
  clearSelection,
  setSelectionMode,
  // Validation
  setValidationResult,
  setMultipleValidationResults,
  clearStaleValidations,
  clearValidationForMachines,
  // Operations
  startBulkOperation,
  updateOperationProgress,
  completeBulkOperation,
  cancelBulkOperation,
  // Filters
  setActiveFilters,
  updateFilter,
  clearFilters,
  // UI
  toggleGroupExpansion,
  setExpandedGroups,
  // History
  clearOperationHistory,
  removeFromHistory,
} = machineAssignmentSlice.actions;

// Export reducer
export default machineAssignmentSlice.reducer;
