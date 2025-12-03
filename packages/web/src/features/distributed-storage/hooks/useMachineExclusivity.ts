import { useState, useCallback, useMemo } from 'react'
import { useDebounce } from '../utils/useDebounce'
import {
  useCloneMachineAssignmentValidation,
  useAvailableMachinesForClone,
  type MachineAssignmentValidation,
  type AvailableMachine
} from '@/api/queries/distributedStorage'
import type { Machine, MachineAssignmentType } from '@/types'
import type { ValidationResult, ExclusivityValidation } from '../models/machine-validation.model'
import { useTranslation } from 'react-i18next'
import { MachineValidationService } from '../services'

export interface MachineAvailability {
  available: string[]
  unavailable: string[]
  conflicts: Record<string, ExclusivityValidation>
}

export interface ValidationCache {
  [key: string]: {
    result: ValidationResult
    timestamp: number
  }
}

const CACHE_DURATION = 30000 // 30 seconds

const parseAssignmentType = (value: string): MachineAssignmentType => {
  const normalized = value.toUpperCase()
  if (normalized === 'CLUSTER' || normalized === 'IMAGE' || normalized === 'CLONE') {
    return normalized as MachineAssignmentType
  }
  return 'AVAILABLE'
}

export const useMachineExclusivity = (teamName?: string) => {
  const { t: _t } = useTranslation(['machines', 'distributedStorage'])
  const [validationCache, setValidationCache] = useState<ValidationCache>({})
  const [isValidating, setIsValidating] = useState(false)
  const [pendingValidation, setPendingValidation] = useState<string[]>([])
  
  // Debounce validation requests
  const debouncedMachines = useDebounce(pendingValidation, 300)
  
  // Fetch available machines
  const { data: availableMachinesData = [], isLoading: loadingAvailable } = useAvailableMachinesForClone(
    teamName || '',
    !!teamName
  )

  // Validate machines when debounced value changes
  const { data: validationData, isLoading: loadingValidation } = useCloneMachineAssignmentValidation(
    teamName || '',
    debouncedMachines.join(','),
    !!teamName && debouncedMachines.length > 0
  )
  
  // Check availability of machines
  const checkAvailability = useCallback(async (
    machineNames: string[]
  ): Promise<MachineAvailability> => {
    if (!teamName || machineNames.length === 0) {
      return {
        available: [],
        unavailable: machineNames,
        conflicts: {}
      }
    }
    
    setIsValidating(true)
    setPendingValidation(machineNames)
    
    // Check cache first
    const now = Date.now()
    const available: string[] = []
    const unavailable: string[] = []
    const conflicts: Record<string, ExclusivityValidation> = {}
    const uncachedMachines: string[] = []
    
    machineNames.forEach(machineName => {
      const cacheKey = `${teamName}-${machineName}`
      const cached = validationCache[cacheKey]
      
      if (cached && now - cached.timestamp < CACHE_DURATION) {
        if (cached.result.isValid) {
          available.push(machineName)
        } else {
          unavailable.push(machineName)
          const exclusivityError = cached.result.errors.find(e => e.code === 'MACHINE_ALREADY_ASSIGNED')
          if (exclusivityError && exclusivityError.metadata?.conflict) {
            conflicts[machineName] = exclusivityError.metadata.conflict as ExclusivityValidation
          }
        }
      } else {
        uncachedMachines.push(machineName)
      }
    })
    
    // If all machines were cached, return immediately
    if (uncachedMachines.length === 0) {
      setIsValidating(false)
      return { available, unavailable, conflicts }
    }
    
    // Wait for validation data
    return new Promise((resolve) => {
      const checkInterval = setInterval(() => {
        if (validationData && !loadingValidation) {
          clearInterval(checkInterval)
          
          // Process validation results
          validationData.forEach((validation: MachineAssignmentValidation) => {
            const cacheKey = `${teamName}-${validation.machineName}`
            const result: ValidationResult = {
              isValid: validation.isValid,
              errors: validation.error ? [{
                code: 'MACHINE_ALREADY_ASSIGNED',
                message: validation.error,
                severity: 'error'
              }] : [],
              warnings: []
            }
            
            // Update cache
            setValidationCache(prev => ({
              ...prev,
              [cacheKey]: {
                result,
                timestamp: now
              }
            }))
            
            if (validation.isValid) {
              available.push(validation.machineName)
            } else {
              unavailable.push(validation.machineName)
              if (validation.error) {
                // Parse error message to extract conflict details
                const match = validation.error.match(/assigned to (\w+): (.+)/)
                if (match) {
                  conflicts[validation.machineName] = {
                    assignmentType: parseAssignmentType(match[1]),
                    resourceName: match[2],
                    machineName: validation.machineName,
                    isExclusive: true,
                    canOverride: false
                  }
                }
              }
            }
          })
          
          setIsValidating(false)
          resolve({ available, unavailable, conflicts })
        }
      }, 100)
      
      // Timeout after 5 seconds
      setTimeout(() => {
        clearInterval(checkInterval)
        setIsValidating(false)
        resolve({ available, unavailable: machineNames, conflicts })
      }, 5000)
    })
  }, [teamName, validationCache, validationData, loadingValidation])
  
  // Validate exclusivity for a set of machines
  const validateExclusivity = useCallback(async (
    _machines: Machine[],
    _targetType: 'cluster' | 'image' | 'clone'
  ): Promise<ValidationResult> => {
    if (!_machines || _machines.length === 0) {
      return {
        isValid: true,
        errors: [],
        warnings: []
      }
    }

    const results = _machines.map(machine =>
      MachineValidationService.validateExclusivityRule(machine, _targetType)
    )

    const allValid = results.every(result => result.isValid)
    const allErrors = results.flatMap(result => result.errors)
    const allWarnings = results.flatMap(result => result.warnings)

    return {
      isValid: allValid,
      errors: allErrors,
      warnings: allWarnings
    }
  }, [])
  
  // Get available machines with optional filtering
  const getAvailableMachines = useCallback((
    assignmentType?: 'cluster' | 'image' | 'clone'
  ): AvailableMachine[] => {
    if (!assignmentType) {
      return availableMachinesData
    }
    
    // Filter based on assignment type if needed
    return availableMachinesData.filter((machine: AvailableMachine) => {
      // All available machines can be assigned to any type
      return machine.status === 'AVAILABLE'
    })
  }, [availableMachinesData])
  
  // Suggest alternative machines when some are unavailable
  const suggestAlternatives = useCallback((
    unavailableMachines: string[],
    count: number
  ): string[] => {
    const suggestions: string[] = []
    const unavailableSet = new Set(unavailableMachines)
    
    for (const machine of availableMachinesData) {
      if (!unavailableSet.has(machine.machineName) && suggestions.length < count) {
        suggestions.push(machine.machineName)
      }
    }
    
    return suggestions
  }, [availableMachinesData])
  
  // Clear validation cache
  const clearCache = useCallback(() => {
    setValidationCache({})
  }, [])
  
  // Get cached validation result
  const getCachedValidation = useCallback((machineName: string): ValidationResult | null => {
    if (!teamName) return null
    
    const cacheKey = `${teamName}-${machineName}`
    const cached = validationCache[cacheKey]
    
    if (cached && Date.now() - cached.timestamp < CACHE_DURATION) {
      return cached.result
    }
    
    return null
  }, [teamName, validationCache])
  
  // Computed values
  const availableMachineCount = useMemo(() => 
    availableMachinesData.length,
    [availableMachinesData]
  )
  
  const validationResults = useMemo(() => {
    const results: Record<string, ValidationResult> = {}
    
    if (validationData) {
      validationData.forEach((validation: MachineAssignmentValidation) => {
        results[validation.machineName] = {
          isValid: validation.isValid,
          errors: validation.error ? [{
            code: 'MACHINE_ALREADY_ASSIGNED',
            message: validation.error,
            severity: 'error'
          }] : [],
          warnings: []
        }
      })
    }
    
    return results
  }, [validationData])
  
  return {
    // Availability checking
    checkAvailability,
    validateExclusivity,
    getAvailableMachines,
    suggestAlternatives,
    
    // Cache management
    clearCache,
    getCachedValidation,
    
    // State
    validationResults,
    isValidating: isValidating || loadingValidation,
    availableMachineCount,
    isLoadingAvailable: loadingAvailable
  }
}
