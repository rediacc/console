import type { Machine } from '@/types';
import type {
  ValidationResult,
  ValidationError,
  ValidationWarning,
  BulkValidationResult,
  InvalidMachine,
  ValidationSummary,
  ValidationContext,
  ExclusivityValidation,
  CapacityValidation,
} from '../models/machine-validation.model';
import type { CephResource } from '../models/machine-assignment.model';

export class MachineValidationService {
  /**
   * Validate if a machine is available for assignment
   */
  static validateMachineAvailability(machine: Machine): ValidationResult {
    const errors: ValidationError[] = [];
    const warnings: ValidationWarning[] = [];

    // Check if machine exists
    if (!machine.machineName) {
      errors.push({
        code: 'MACHINE_NOT_FOUND',
        message: 'Machine not found',
        field: 'machineName',
      });
    }

    // Check machine vault status
    if (machine.vaultStatus && machine.vaultStatus !== 'SUCCESS') {
      warnings.push({
        code: 'MACHINE_VAULT_ISSUE',
        message: `Machine vault status is ${machine.vaultStatus}`,
        field: 'vaultStatus',
        severity: 'medium',
      });
    }

    // Check if machine is already assigned
    if (machine.cephClusterName) {
      warnings.push({
        code: 'MACHINE_ALREADY_ASSIGNED',
        message: `Machine is assigned to cluster: ${machine.cephClusterName}`,
        field: 'cephClusterName',
        severity: 'high',
      });
    }

    return {
      isValid: errors.length === 0,
      errors,
      warnings,
    };
  }

  /**
   * Validate exclusivity rules for machine assignment
   */
  static validateExclusivityRule(
    machine: Machine,
    targetType: CephResource['type']
  ): ValidationResult {
    const errors: ValidationError[] = [];
    const warnings: ValidationWarning[] = [];

    const exclusivity = this.checkMachineExclusivity(machine);
    const normalizedTargetType = this.normalizeTargetType(targetType);

    if (exclusivity.isExclusive) {
      // Cluster and Image assignments are mutually exclusive
      if (
        (normalizedTargetType === 'cluster' || normalizedTargetType === 'image') &&
        exclusivity.conflictType
      ) {
        errors.push({
          code: 'EXCLUSIVITY_VIOLATION',
          message: `Machine is already assigned to ${exclusivity.conflictType}: ${exclusivity.conflictResource}`,
          field: 'assignmentType',
          context: {
            currentType: exclusivity.conflictType,
            requestedType: normalizedTargetType,
            conflictResource: exclusivity.conflictResource,
          },
        });
      }

      // Clones can coexist with other assignments but show warning
      if (normalizedTargetType === 'clone' && exclusivity.conflictType) {
        warnings.push({
          code: 'CLONE_ASSIGNMENT_WARNING',
          message: `Machine is also assigned to ${exclusivity.conflictType}: ${exclusivity.conflictResource}`,
          field: 'assignmentType',
          severity: 'medium',
        });
      }
    }

    return {
      isValid: errors.length === 0,
      errors,
      warnings,
    };
  }

  /**
   * Validate a complete machine assignment operation
   */
  static validateMachineAssignment(
    machine: Machine,
    targetResource: CephResource,
    context?: ValidationContext
  ): ValidationResult {
    const errors: ValidationError[] = [];
    const warnings: ValidationWarning[] = [];

    // Validate availability
    const availabilityResult = this.validateMachineAvailability(machine);
    errors.push(...availabilityResult.errors);
    warnings.push(...availabilityResult.warnings);

    // Validate exclusivity
    const exclusivityResult = this.validateExclusivityRule(machine, targetResource.type);
    errors.push(...exclusivityResult.errors);
    warnings.push(...exclusivityResult.warnings);

    // Validate team membership
    if (context?.teamName && machine.teamName !== context.teamName) {
      errors.push({
        code: 'TEAM_MISMATCH',
        message: `Machine belongs to team ${machine.teamName}, not ${context.teamName}`,
        field: 'teamName',
        context: {
          machineTeam: machine.teamName,
          requestedTeam: context.teamName,
        },
      });
    }

    // Validate resource exists
    if (!targetResource.id || !targetResource.name) {
      errors.push({
        code: 'INVALID_TARGET_RESOURCE',
        message: 'Target resource is invalid or does not exist',
        field: 'targetResource',
      });
    }

    return {
      isValid: errors.length === 0,
      errors,
      warnings,
      context: {
        machine: machine.machineName,
        targetResource: targetResource.name,
        targetType: targetResource.type,
      },
    };
  }

  /**
   * Validate a single machine for assignment
   */
  static validateSingleMachine(
    machine: Machine,
    targetType: CephResource['type'],
    _context?: ValidationContext
  ): ValidationResult {
    const result = this.validateExclusivityRule(machine, targetType);
    const availabilityResult = this.validateMachineAvailability(machine);

    // Combine all errors and warnings
    const allErrors = [...result.errors, ...availabilityResult.errors];
    const allWarnings = [...result.warnings, ...availabilityResult.warnings];

    return {
      isValid: allErrors.length === 0,
      errors: allErrors,
      warnings: allWarnings,
      context: {
        machine: machine.machineName,
        targetType,
      },
    };
  }

  /**
   * Validate bulk machine assignment
   */
  static validateBulkAssignment(
    machines: Machine[],
    targetType: CephResource['type'],
    context?: ValidationContext
  ): BulkValidationResult {
    const validMachines: Machine[] = [];
    const invalidMachines: InvalidMachine[] = [];
    const errorTypes = new Map<string, number>();
    let warningCount = 0;
    let criticalErrors = false;

    machines.forEach((machine) => {
      const result = this.validateExclusivityRule(machine, targetType);

      if (result.isValid && result.warnings.length === 0) {
        validMachines.push(machine);
      } else {
        const canOverride = result.errors.every(
          (error) => error.code === 'EXCLUSIVITY_VIOLATION' && context?.skipWarnings
        );

        invalidMachines.push({
          machine,
          machineName: machine.machineName,
          errors: result.errors,
          canOverride,
        });

        // Track error types
        result.errors.forEach((error) => {
          errorTypes.set(error.code, (errorTypes.get(error.code) || 0) + 1);
          if (error.code === 'TEAM_MISMATCH') {
            criticalErrors = true;
          }
        });

        warningCount += result.warnings.length;
      }
    });

    const summary: ValidationSummary = {
      totalMachines: machines.length,
      validCount: validMachines.length,
      invalidCount: invalidMachines.length,
      errorTypes,
      warningCount,
      criticalErrors,
    };

    // Collect all warnings
    const allWarnings: ValidationWarning[] = [];
    machines.forEach((machine) => {
      const result = this.validateExclusivityRule(machine, targetType);
      allWarnings.push(...result.warnings);
    });

    // Convert invalidMachines to Record<string, ValidationError[]> format
    const errorsByMachine: Record<string, ValidationError[]> = {};
    invalidMachines.forEach((invalid) => {
      errorsByMachine[invalid.machineName] = invalid.errors;
    });

    // Convert warnings to Record<string, ValidationWarning[]> format
    const warningsByMachine: Record<string, ValidationWarning[]> = {};
    machines.forEach((machine) => {
      const result = this.validateExclusivityRule(machine, targetType);
      if (result.warnings.length > 0) {
        warningsByMachine[machine.machineName] = result.warnings;
      }
    });

    return {
      validMachines,
      invalidMachines,
      summary,
      canProceed: validMachines.length > 0 && !criticalErrors,
      allValid: invalidMachines.length === 0,
      errors: errorsByMachine,
      warnings: warningsByMachine,
    };
  }

  /**
   * Get all invalid machines from a list
   */
  static getInvalidMachines(
    machines: Machine[],
    targetType: CephResource['type']
  ): InvalidMachine[] {
    const result = this.validateBulkAssignment(machines, targetType);
    return result.invalidMachines;
  }

  /**
   * Generate a human-readable validation summary
   */
  static generateValidationSummary(results: ValidationResult[]): ValidationSummary {
    const errorTypes = new Map<string, number>();
    let warningCount = 0;
    let criticalErrors = false;

    results.forEach((result) => {
      warningCount += result.warnings.length;

      result.errors.forEach((error) => {
        errorTypes.set(error.code, (errorTypes.get(error.code) || 0) + 1);
        if (error.code === 'TEAM_MISMATCH') {
          criticalErrors = true;
        }
      });
    });

    return {
      totalMachines: results.length,
      validCount: results.filter((r) => r.isValid).length,
      invalidCount: results.filter((r) => !r.isValid).length,
      errorTypes,
      warningCount,
      criticalErrors,
    };
  }

  /**
   * Check if a machine has cluster exclusivity
   */
  static isClusterExclusive(machine: Machine): boolean {
    return !!machine.cephClusterName;
  }

  /**
   * Check if a machine has image exclusivity
   */
  static isImageExclusive(machine: Machine): boolean {
    // Images are tracked via the assignment status, not directly on the machine
    return machine.assignmentStatus?.assignmentType === 'IMAGE';
  }

  /**
   * Check if a machine can be assigned to multiple clones
   */
  static canAssignMultipleClones(_machine: Machine): boolean {
    // Clones don't have exclusivity restrictions
    return true;
  }

  /**
   * Normalize resource types to the assignment categories used by validation
   */
  private static normalizeTargetType(
    targetType: CephResource['type']
  ): 'cluster' | 'image' | 'clone' {
    switch (targetType) {
      case 'pool':
        return 'cluster';
      case 'snapshot':
        return 'image';
      case 'clone':
        return 'clone';
      default:
        return targetType;
    }
  }

  /**
   * Private helper to check machine exclusivity
   */
  private static checkMachineExclusivity(machine: Machine): ExclusivityValidation {
    // Check cluster assignment
    if (machine.cephClusterName) {
      return {
        isExclusive: true,
        conflictType: 'cluster',
        conflictResource: machine.cephClusterName,
        canOverride: false,
      };
    }

    // Check image assignment via status
    if (machine.assignmentStatus?.assignmentType === 'IMAGE') {
      const imageName =
        machine.assignmentStatus.assignmentDetails?.match(/Assigned to image: (.+)/)?.[1];
      return {
        isExclusive: true,
        conflictType: 'image',
        conflictResource: imageName || 'Unknown Image',
        canOverride: false,
      };
    }

    // Check clone assignment
    if (machine.assignmentStatus?.assignmentType === 'CLONE') {
      const cloneName =
        machine.assignmentStatus.assignmentDetails?.match(/Assigned to clone: (.+)/)?.[1];
      return {
        isExclusive: false, // Clones are not exclusive
        conflictType: 'clone',
        conflictResource: cloneName || 'Unknown Clone',
        canOverride: true,
      };
    }

    return {
      isExclusive: false,
      canOverride: true,
    };
  }

  /**
   * Validate machine capacity for a resource
   */
  static validateCapacity(
    currentCount: number,
    maxCount: number,
    additionalCount: number = 1
  ): CapacityValidation {
    const newCount = currentCount + additionalCount;
    const hasCapacity = newCount <= maxCount;
    const remainingCapacity = Math.max(0, maxCount - currentCount);

    return {
      hasCapacity,
      currentCount,
      maxCount,
      remainingCapacity,
    };
  }
}
