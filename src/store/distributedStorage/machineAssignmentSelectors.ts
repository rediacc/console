import { createSelector } from '@reduxjs/toolkit'
import type { RootState } from '@/store/store'
import type { Machine } from '@/types'
import { MachineAssignmentService } from '@/features/distributed-storage'

// Base selectors
export const selectMachineAssignmentState = (state: RootState) => 
  state.machineAssignment

export const selectSelectedMachines = (state: RootState) => 
  state.machineAssignment.selectedMachines

export const selectSelectionMode = (state: RootState) => 
  state.machineAssignment.selectionMode

export const selectAssignmentValidation = (state: RootState) => 
  state.machineAssignment.assignmentValidation

export const selectValidationTimestamps = (state: RootState) => 
  state.machineAssignment.validationTimestamps

export const selectBulkOperationInProgress = (state: RootState) => 
  state.machineAssignment.bulkOperationInProgress

export const selectCurrentOperation = (state: RootState) => 
  state.machineAssignment.currentOperation

export const selectLastOperationResult = (state: RootState) => 
  state.machineAssignment.lastOperationResult

export const selectOperationHistory = (state: RootState) => 
  state.machineAssignment.operationHistory

export const selectActiveFilters = (state: RootState) => 
  state.machineAssignment.activeFilters

export const selectExpandedGroups = (state: RootState) => 
  state.machineAssignment.expandedGroups

// Computed selectors
export const selectSelectedMachineCount = createSelector(
  [selectSelectedMachines],
  (selectedMachines) => selectedMachines.length
)

export const selectIsAnyMachineSelected = createSelector(
  [selectSelectedMachineCount],
  (count) => count > 0
)

export const selectIsMachineSelected = createSelector(
  [selectSelectedMachines, (_: RootState, machineName: string) => machineName],
  (selectedMachines, machineName) => selectedMachines.includes(machineName)
)

export const selectValidationForMachine = createSelector(
  [selectAssignmentValidation, (_: RootState, machineName: string) => machineName],
  (validation, machineName) => validation[machineName] || null
)

export const selectIsValidationStale = createSelector(
  [
    selectValidationTimestamps,
    (_: RootState, machineName: string) => machineName,
    (_: RootState, _machineName: string, maxAge: number = 300000) => maxAge // 5 minutes default
  ],
  (timestamps, machineName, maxAge) => {
    const timestamp = timestamps[machineName]
    if (!timestamp) return true
    return Date.now() - timestamp > maxAge
  }
)

export const selectOperationProgress = createSelector(
  [selectCurrentOperation],
  (operation) => operation?.progress || null
)

export const selectIsOperationInProgress = createSelector(
  [selectBulkOperationInProgress, selectOperationProgress],
  (inProgress, progress) => inProgress || (progress?.isProcessing ?? false)
)

// Filter machines based on active filters
export const selectFilteredMachines = createSelector(
  [
    (_: RootState, machines: Machine[]) => machines,
    selectActiveFilters
  ],
  (machines, filters) => {
    let filtered = [...machines]
    
    // Filter by assignment type
    if (filters.assignmentType) {
      filtered = filtered.filter(machine => 
        MachineAssignmentService.getMachineAssignmentType(machine) === filters.assignmentType
      )
    }
    
    // Filter by team name
    if (filters.teamName) {
      filtered = filtered.filter(machine => 
        machine.teamName === filters.teamName
      )
    }
    
    // Filter by search query
    if (filters.searchQuery) {
      const query = filters.searchQuery.toLowerCase()
      filtered = filtered.filter(machine =>
        machine.machineName.toLowerCase().includes(query) ||
        machine.bridgeName?.toLowerCase().includes(query) ||
        machine.regionName?.toLowerCase().includes(query)
      )
    }
    
    return filtered
  }
)

// Get validation results for selected machines
export const selectSelectedMachineValidations = createSelector(
  [selectSelectedMachines, selectAssignmentValidation],
  (selectedMachines, validations) => {
    return selectedMachines.reduce((acc, machineName) => {
      if (validations[machineName]) {
        acc[machineName] = validations[machineName]
      }
      return acc
    }, {} as Record<string, typeof validations[string]>)
  }
)

// Check if all selected machines are valid
export const selectAreAllSelectedMachinesValid = createSelector(
  [selectSelectedMachineValidations],
  (validations) => {
    const validationResults = Object.values(validations)
    if (validationResults.length === 0) return false
    return validationResults.every(result => result.isValid)
  }
)

// Get recent successful operations
export const selectRecentSuccessfulOperations = createSelector(
  [selectOperationHistory],
  (history) => history.filter(op => op.result === 'success').slice(0, 5)
)

// Get operation statistics
export const selectOperationStatistics = createSelector(
  [selectOperationHistory],
  (history) => {
    const stats = {
      total: history.length,
      successful: 0,
      partial: 0,
      failed: 0,
      byType: {
        assign: 0,
        remove: 0,
        migrate: 0
      }
    }
    
    history.forEach(op => {
      stats[op.result]++
      stats.byType[op.type]++
    })
    
    return stats
  }
)

// Check if a specific group is expanded
export const selectIsGroupExpanded = createSelector(
  [selectExpandedGroups, (_: RootState, groupId: string) => groupId],
  (expandedGroups, groupId) => expandedGroups.includes(groupId)
)

// Get machines by selection status
export const selectMachinesBySelectionStatus = createSelector(
  [
    (_: RootState, machines: Machine[]) => machines,
    selectSelectedMachines
  ],
  (machines, selectedMachines) => {
    const selectedSet = new Set(selectedMachines)
    
    return {
      selected: machines.filter(m => selectedSet.has(m.machineName)),
      unselected: machines.filter(m => !selectedSet.has(m.machineName))
    }
  }
)

// Get summary of current selection
export const selectSelectionSummary = createSelector(
  [
    selectSelectedMachines,
    selectSelectedMachineValidations,
    (_: RootState, machines: Machine[]) => machines
  ],
  (selectedMachines, validations, allMachines) => {
    const selectedMachineObjects = allMachines.filter(m => 
      selectedMachines.includes(m.machineName)
    )
    
    const summary = {
      count: selectedMachines.length,
      validated: Object.keys(validations).length,
      valid: Object.values(validations).filter(v => v.isValid).length,
      invalid: Object.values(validations).filter(v => !v.isValid).length,
      byAssignmentType: {
        AVAILABLE: 0,
        CLUSTER: 0,
        IMAGE: 0,
        CLONE: 0
      },
      byTeam: {} as Record<string, number>
    }
    
    selectedMachineObjects.forEach(machine => {
      const assignmentType = MachineAssignmentService.getMachineAssignmentType(machine)
      summary.byAssignmentType[assignmentType]++
      
      const team = machine.teamName
      summary.byTeam[team] = (summary.byTeam[team] || 0) + 1
    })
    
    return summary
  }
)