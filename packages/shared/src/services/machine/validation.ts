/**
 * Machine validation service
 * Platform-agnostic validation rules for machine assignment operations
 */

import type {
  BulkValidationResult,
  CapacityValidation,
  CephResource,
  CephResourceType,
  ExclusivityValidation,
  InvalidMachine,
  MachineWithAssignmentStatus,
  ValidationContext,
  ValidationError,
  ValidationResult,
  ValidationSummary,
  ValidationWarning,
} from './types';

export class MachineValidationService {
  /**
   * Validate if a machine is available for assignment
   */
  static validateMachineAvailability(machine: MachineWithAssignmentStatus): ValidationResult {
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
    machine: MachineWithAssignmentStatus,
    targetType: CephResourceType
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
    machine: MachineWithAssignmentStatus,
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
    machine: MachineWithAssignmentStatus,
    targetType: CephResourceType,
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
    machines: MachineWithAssignmentStatus[],
    targetType: CephResourceType,
    context?: ValidationContext
  ): BulkValidationResult {
    const validMachines: MachineWithAssignmentStatus[] = [];
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
          errorTypes.set(error.code, (errorTypes.get(error.code) ?? 0) + 1);
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
      const name = invalid.machineName ?? 'Unknown';
      errorsByMachine[name] = invalid.errors;
    });

    // Convert warnings to Record<string, ValidationWarning[]> format
    const warningsByMachine: Record<string, ValidationWarning[]> = {};
    machines.forEach((machine) => {
      const result = this.validateExclusivityRule(machine, targetType);
      if (result.warnings.length > 0) {
        const name = machine.machineName ?? 'Unknown';
        warningsByMachine[name] = result.warnings;
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
    machines: MachineWithAssignmentStatus[],
    targetType: CephResourceType
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
        errorTypes.set(error.code, (errorTypes.get(error.code) ?? 0) + 1);
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
  static isClusterExclusive(machine: MachineWithAssignmentStatus): boolean {
    return !!machine.cephClusterName;
  }

  /**
   * Check if a machine has image exclusivity
   * Note: Currently only cluster assignments are tracked via assignmentStatus
   */
  static isImageExclusive(_machine: MachineWithAssignmentStatus): boolean {
    // Image exclusivity would need to be tracked separately in the future
    // Currently, assignmentStatus is a simple string ('ASSIGNED' | 'UNASSIGNED')
    return false;
  }

  /**
   * Check if a machine can be assigned to multiple clones
   */
  static canAssignMultipleClones(_machine: MachineWithAssignmentStatus): boolean {
    // Clones don't have exclusivity restrictions
    return true;
  }

  /**
   * Normalize resource types to the assignment categories used by validation
   */
  private static normalizeTargetType(targetType: CephResourceType): 'cluster' | 'image' | 'clone' {
    switch (targetType) {
      case 'pool':
        return 'cluster';
      case 'snapshot':
        return 'image';
      case 'clone':
        return 'clone';
      default:
        return targetType as 'cluster' | 'image' | 'clone';
    }
  }

  /**
   * Private helper to check machine exclusivity
   * Note: assignmentStatus is now a simple string ('ASSIGNED' | 'UNASSIGNED')
   * Only cluster assignments are currently tracked via cephClusterName
   */
  private static checkMachineExclusivity(
    machine: MachineWithAssignmentStatus
  ): ExclusivityValidation {
    // Check cluster assignment (the only type currently tracked)
    if (machine.cephClusterName) {
      return {
        isExclusive: true,
        conflictType: 'cluster',
        conflictResource: machine.cephClusterName,
        canOverride: false,
      };
    }

    // If marked as assigned but no cluster, treat as potentially assigned
    if (machine.assignmentStatus === 'ASSIGNED') {
      return {
        isExclusive: true,
        conflictType: 'cluster',
        conflictResource: 'Unknown',
        canOverride: false,
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
    additionalCount = 1
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
