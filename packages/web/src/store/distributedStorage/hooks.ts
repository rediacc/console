import { useCallback } from 'react'
import { useAppDispatch, useAppSelector } from '@/store/store'
import {
  setSelectedMachines,
  addSelectedMachines,
  removeSelectedMachines,
  toggleMachineSelection,
  clearSelection,
  setSelectionMode,
  startBulkOperation,
  updateOperationProgress,
  completeBulkOperation,
  cancelBulkOperation,
  setActiveFilters,
  updateFilter,
  clearFilters,
  toggleGroupExpansion
} from './machineAssignmentSlice'
import {
  selectSelectedMachines,
  selectSelectedMachineCount,
  selectIsAnyMachineSelected,
  selectIsMachineSelected,
  selectIsOperationInProgress,
  selectOperationProgress,
  selectCurrentOperation,
  selectLastOperationResult,
  selectActiveFilters,
  selectSelectionSummary,
  selectAreAllSelectedMachinesValid,
  selectFilteredMachines
} from './machineAssignmentSelectors'
import type { Machine, MachineAssignmentType } from '@/types'
import type { BulkOperationProgress, BulkOperationResult } from '@/features/distributed-storage'
import type { MachineAssignmentState } from './machineAssignmentSlice'

// Hook for machine selection management
export const useMachineSelection = (machines: Machine[] = []) => {
  const dispatch = useAppDispatch()
  const selectedMachines = useAppSelector(selectSelectedMachines)
  const selectedCount = useAppSelector(selectSelectedMachineCount)
  const hasSelection = useAppSelector(selectIsAnyMachineSelected)
  const selectionSummary = useAppSelector(state => selectSelectionSummary(state, machines))
  
  const selectMachines = useCallback((machineNames: string[]) => {
    dispatch(addSelectedMachines(machineNames))
  }, [dispatch])
  
  const deselectMachines = useCallback((machineNames: string[]) => {
    dispatch(removeSelectedMachines(machineNames))
  }, [dispatch])
  
  const toggleSelection = useCallback((machineName: string) => {
    dispatch(toggleMachineSelection(machineName))
  }, [dispatch])
  
  const selectAll = useCallback((machines: Machine[]) => {
    dispatch(setSelectedMachines(machines.map(m => m.machineName)))
  }, [dispatch])
  
  const clearAll = useCallback(() => {
    dispatch(clearSelection())
  }, [dispatch])
  
  const setMode = useCallback((mode: 'single' | 'multiple' | null) => {
    dispatch(setSelectionMode(mode))
  }, [dispatch])
  
  const isMachineSelected = useCallback((machineName: string) => {
    return selectedMachines.includes(machineName)
  }, [selectedMachines])
  
  return {
    selectedMachines,
    selectedCount,
    hasSelection,
    selectionSummary,
    selectMachines,
    deselectMachines,
    toggleSelection,
    selectAll,
    clearSelection: clearAll,
    setSelectionMode: setMode,
    isMachineSelected
  }
}

// Hook for bulk operation management
export const useBulkOperationState = () => {
  const dispatch = useAppDispatch()
  const isOperationInProgress = useAppSelector(selectIsOperationInProgress)
  const operationProgress = useAppSelector(selectOperationProgress)
  const currentOperation = useAppSelector(selectCurrentOperation)
  const lastOperationResult = useAppSelector(selectLastOperationResult)
  
  const startOperation = useCallback((
    type: 'assign' | 'remove' | 'migrate',
    targetType: 'cluster' | 'image' | 'clone',
    targetResource: string,
    totalMachines: number
  ) => {
    dispatch(startBulkOperation({ type, targetType, targetResource, totalMachines }))
  }, [dispatch])
  
  const updateProgress = useCallback((progress: Partial<BulkOperationProgress>) => {
    dispatch(updateOperationProgress(progress))
  }, [dispatch])
  
  const completeOperation = useCallback((
    result: BulkOperationResult,
    addToHistory = true
  ) => {
    dispatch(completeBulkOperation({ result, addToHistory }))
  }, [dispatch])
  
  const cancelOperation = useCallback(() => {
    dispatch(cancelBulkOperation())
  }, [dispatch])
  
  return {
    isOperationInProgress,
    operationProgress,
    currentOperation,
    lastOperationResult,
    startOperation,
    updateProgress,
    completeOperation,
    cancelOperation
  }
}

// Hook for filter management
export const useMachineFilters = () => {
  const dispatch = useAppDispatch()
  const activeFilters = useAppSelector(selectActiveFilters)

  type MachineFilterKey = keyof MachineAssignmentState['activeFilters']
  type MachineFilterValue = MachineAssignmentState['activeFilters'][MachineFilterKey]
  
  const setFilters = useCallback((filters: {
    assignmentType?: MachineAssignmentType
    teamName?: string
    searchQuery?: string
  }) => {
    dispatch(setActiveFilters(filters))
  }, [dispatch])
  
  const updateSingleFilter = useCallback((
    key: MachineFilterKey,
    value: MachineFilterValue | undefined
  ) => {
    dispatch(updateFilter({ key, value }))
  }, [dispatch])
  
  const clearAllFilters = useCallback(() => {
    dispatch(clearFilters())
  }, [dispatch])
  
  return {
    activeFilters,
    setFilters,
    updateFilter: updateSingleFilter,
    clearFilters: clearAllFilters
  }
}

// Hook for UI state management
export const useMachineAssignmentUI = () => {
  const dispatch = useAppDispatch()

  const toggleGroup = useCallback((groupId: string) => {
    dispatch(toggleGroupExpansion(groupId))
  }, [dispatch])

  // Note: isGroupExpanded removed as it violated hooks rules
  // Users should call useAppSelector(state => selectIsGroupExpanded(state, groupId)) directly in their components

  return {
    toggleGroupExpansion: toggleGroup
  }
}

// Combined hook that provides all machine assignment functionality
export const useMachineAssignmentStore = () => {
  const selection = useMachineSelection()
  const operation = useBulkOperationState()
  const filters = useMachineFilters()
  const ui = useMachineAssignmentUI()
  const areAllSelectedValid = useAppSelector(selectAreAllSelectedMachinesValid)
  
  return {
    // Selection management
    ...selection,
    
    // Operation management
    ...operation,
    
    // Filter management
    ...filters,
    
    // UI management
    ...ui,
    
    // Validation state
    areAllSelectedValid
  }
}

// Hook to check if a specific machine is selected (for use in components)
export const useIsMachineSelected = (machineName: string) => {
  return useAppSelector(state => selectIsMachineSelected(state, machineName))
}

// Hook to get filtered machines
export const useFilteredMachines = (machines: Machine[]) => {
  return useAppSelector(state => selectFilteredMachines(state, machines))
}
