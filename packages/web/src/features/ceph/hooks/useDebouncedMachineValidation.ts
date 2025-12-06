import { useState, useCallback, useMemo } from 'react';
import { useDebouncedCallback, useDebouncedValidation } from '../utils/useDebounce';
import { MachineValidationService } from '../services';
import type { Machine } from '@/types';
import type { ValidationResult } from '../models';

export interface DebouncedValidationOptions {
  delay?: number;
  maxWait?: number;
  leading?: boolean;
  trailing?: boolean;
}

/**
 * Hook for debounced machine validation
 */
export const useDebouncedMachineValidation = (options: DebouncedValidationOptions = {}) => {
  const { delay = 300 } = options;

  const [validationResults, setValidationResults] = useState<Record<string, ValidationResult>>({});
  const [isValidating, setIsValidating] = useState(false);

  // Single machine validation with debouncing
  const validateMachine = useCallback(
    (machine: Machine, targetType: 'cluster' | 'image' | 'clone') => {
      const result = MachineValidationService.validateSingleMachine(machine, targetType);
      return result;
    },
    []
  );

  // Debounced single validation
  const [debouncedValidateMachine, cancelValidation] = useDebouncedCallback(
    async (machine: Machine, targetType: 'cluster' | 'image' | 'clone') => {
      setIsValidating(true);
      try {
        const result = validateMachine(machine, targetType);
        setValidationResults((prev) => ({
          ...prev,
          [machine.machineName]: result,
        }));
      } finally {
        setIsValidating(false);
      }
    },
    delay
  );

  // Bulk validation with debouncing
  const [debouncedValidateBulk, cancelBulkValidation] = useDebouncedCallback(
    async (machines: Machine[], targetType: 'cluster' | 'image' | 'clone') => {
      setIsValidating(true);
      try {
        const result = MachineValidationService.validateBulkAssignment(machines, targetType);

        // Store individual results
        const newResults: Record<string, ValidationResult> = {};

        result.validMachines.forEach((machine) => {
          const machineName = machine.machineName;
          newResults[machineName] = {
            isValid: true,
            errors: [],
            warnings: result.warnings[machineName] || [],
          };
        });

        result.invalidMachines.forEach((machine) => {
          const machineName = machine.machineName;
          newResults[machineName] = {
            isValid: false,
            errors: result.errors[machineName] || [],
            warnings: result.warnings[machineName] || [],
          };
        });

        setValidationResults(newResults);
      } finally {
        setIsValidating(false);
      }
    },
    delay
  );

  // Clear validation results
  const clearValidationResults = useCallback(() => {
    setValidationResults({});
    cancelValidation();
    cancelBulkValidation();
  }, [cancelValidation, cancelBulkValidation]);

  // Get validation result for a specific machine
  const getValidationResult = useCallback(
    (machineName: string): ValidationResult | undefined => {
      return validationResults[machineName];
    },
    [validationResults]
  );

  // Check if all machines are valid
  const areAllMachinesValid = useMemo(() => {
    const results = Object.values(validationResults);
    return results.length > 0 && results.every((result) => result.isValid);
  }, [validationResults]);

  return {
    // Validation functions
    validateMachine: debouncedValidateMachine,
    validateBulk: debouncedValidateBulk,

    // Validation state
    validationResults,
    isValidating,
    areAllMachinesValid,

    // Utilities
    getValidationResult,
    clearValidationResults,
    cancelValidation: () => {
      cancelValidation();
      cancelBulkValidation();
    },
  };
};

/**
 * Hook for real-time validation as user types/selects
 */
export const useRealtimeValidation = (
  machines: Machine[],
  targetType: 'cluster' | 'image' | 'clone',
  delay: number = 500
) => {
  const validator = useCallback(
    (machineList: Machine[]) => {
      if (machineList.length === 0) return true;

      const result = MachineValidationService.validateBulkAssignment(machineList, targetType);
      return result.allValid;
    },
    [targetType]
  );

  // Use the validator with proper typing - pass machines as value
  const debouncedValidate = useDebouncedValidation(machines, validator, delay);
  return debouncedValidate;
};
