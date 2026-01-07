// Types
export type { QueueVaultBuilderConfig } from './builders';

// Builders
export { QueueVaultBuilder } from './builders';

// Data
export { FUNCTION_REQUIREMENTS } from './data';

// Zod validation
export {
  safeValidateFunctionParams,
  getValidationErrors,
  isValidParams,
} from './data';

// Type exports
export type {
  // V2 Types
  ContextSection,
  MachineSection,
  QueueVaultV2,
  RepositoryInfo,
  SSHSection,
  StorageSection,
  TaskSection,
  // Request context types
  FunctionRequirements,
  QueueRequestContext,
  VaultContent,
} from './types';

// Utils
export { getParamArray, getParamValue, isBase64, minifyJSON } from './utils';

// IP/Port validation
export {
  isValidIPv4,
  isValidIPv6,
  isValidIP,
  isValidHostname,
  isValidHost,
  isValidPort,
  validateSSHConnection,
  validateMachineVault,
  // Size format validation
  parseSize,
  validateSize,
  validateSizeWithMin,
  formatSizeBytes,
  // Network ID validation
  MIN_NETWORK_ID,
  NETWORK_ID_INCREMENT,
  validateNetworkId,
  isValidNetworkId,
  // SSH key format validation
  validateSSHPrivateKey,
  isValidSSHPrivateKey,
} from './utils';
export { parseVaultContent, parseVaultContentOrEmpty } from './parsing';

// Validation
export {
  validateQueueVault,
  type QueueVaultValidationResult,
  type QueueVaultValidationError,
  isQueueVaultV2,
  assertQueueVaultV2,
  validateBridgeFunction,
  assertBridgeFunction,
  type BridgeFunctionError,
} from './validation';

// Bridge Functions (generated)
export {
  isBridgeFunction,
  BRIDGE_FUNCTIONS,
  BRIDGE_FUNCTIONS_VERSION,
  getTypedParams,
  createFunctionPayload,
  queueFunctions,
  type BridgeFunctionName,
  type FunctionParamsMap,
  type TypedFunctionPayload,
  type QueueFunctionsType,
} from './data/functions.generated';
