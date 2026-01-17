// =============================================================================
// Queue Vault Validation
// =============================================================================
//
// Bridge function validation uses the generated functions schema.
// Vault structure validation uses the generated Zod schemas.
//

import {
  BRIDGE_FUNCTIONS_VERSION,
  type BridgeFunctionName,
  isBridgeFunction,
} from '../data/functions.generated';

// Re-export type guards from generated types
export { assertQueueVaultV2, isQueueVaultV2 } from '../data/vault.generated';
// Re-export vault validation from generated schemas
export {
  ContextSectionSchema,
  getVaultValidationErrors,
  MachineSectionSchema,
  parseQueueVault,
  QueueVaultV2Schema,
  RepositoryInfoSchema,
  SSHSectionSchema,
  StorageSectionSchema,
  TaskSectionSchema,
  validateQueueVault,
} from '../data/vault.schema';

// Re-export vault types for convenience
export type { MachineSection, QueueVaultV2, RepositoryInfo, StorageSection } from '../types';

// =============================================================================
// Bridge Function Validation
// =============================================================================

/**
 * Error codes for bridge function validation.
 * Note: INTERNAL_FUNCTION and EXPERIMENTAL_FUNCTION errors are now returned by renet,
 * not console. Console only validates that a function exists.
 */
export interface BridgeFunctionError {
  code: 'UNKNOWN_FUNCTION';
  function: string;
  protocolVersion: string;
  message: string;
}

/**
 * Validates that a function name is supported by the bridge.
 * This is MANDATORY before creating queue items - unknown functions
 * will be rejected by the bridge with a protocol error.
 *
 * @param functionName - The function name to validate
 * @returns Error object if invalid, null if valid
 */
export function validateBridgeFunction(functionName: string): BridgeFunctionError | null {
  if (!isBridgeFunction(functionName)) {
    return {
      code: 'UNKNOWN_FUNCTION',
      function: functionName,
      protocolVersion: BRIDGE_FUNCTIONS_VERSION,
      message: `Function "${functionName}" is not supported in protocol v${BRIDGE_FUNCTIONS_VERSION}`,
    };
  }
  return null;
}

/**
 * Asserts that a function name is supported, throwing if not.
 * Use this for fail-fast validation before queue operations.
 */
export function assertBridgeFunction(functionName: string): void {
  const error = validateBridgeFunction(functionName);
  if (error) {
    throw new Error(error.message);
  }
}

/**
 * Validates that a function is public (callable from console).
 * All functions in the generated schema are public.
 * Internal/experimental function validation is handled server-side by renet.
 *
 * @param functionName - The function name to validate
 * @returns Error object if not a valid function, null if valid
 */
export function validatePublicBridgeFunction(functionName: string): BridgeFunctionError | null {
  // All functions in the generated file are public
  // Visibility validation for internal/experimental is done by renet
  return validateBridgeFunction(functionName);
}

/**
 * Asserts that a function is valid and can be called from console.
 * Throws if function is unknown (not in the generated schema).
 * Note: Internal/experimental validation is handled server-side by renet.
 */
export function assertPublicBridgeFunction(
  functionName: string
): asserts functionName is BridgeFunctionName {
  const error = validatePublicBridgeFunction(functionName);
  if (error) {
    throw new Error(error.message);
  }
}

// =============================================================================
// Legacy Compatibility Types
// =============================================================================
// These types are kept for backward compatibility with existing code.

export interface QueueVaultValidationError {
  path: string;
  message: string;
}

export interface QueueVaultValidationResult {
  valid: boolean;
  errors: QueueVaultValidationError[];
}
