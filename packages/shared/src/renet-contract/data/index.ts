export {
  type CheckboxOption,
  FUNCTION_CATEGORIES,
  FUNCTION_DEFINITIONS,
  type FunctionCategory,
  type FunctionDefinition,
  type FunctionParameterDefinition,
  type UIType,
} from './definitions';
export { FUNCTION_REQUIREMENTS } from './functionRequirements';

// Type-safe exports from generated file
// Note: FUNCTION_VISIBILITY and FunctionVisibility removed - visibility validation
// is now handled server-side by renet. All functions in this file are public.
export {
  BRIDGE_FUNCTIONS,
  BRIDGE_FUNCTIONS_VERSION,
  type BridgeFunctionName,
  createFunctionPayload,
  type FunctionParamsMap,
  getTypedParams,
  isBridgeFunction,
  isPublicBridgeFunction,
  type QueueFunctionsType,
  queueFunctions,
  type TypedFunctionPayload,
} from './functions.generated';

// Zod validation exports from schema file
export {
  FUNCTION_SCHEMAS,
  getValidationErrors,
  isValidParams,
  safeValidateFunctionParams,
  validateFunctionParams,
} from './functions.schema';
// List types - auto-generated from renet/pkg/list/types.go
// These are the types from 'renet list all --json' for machine status
export {
  type BlockDevice,
  type ContainerInfo,
  type ContainersResult,
  type DiskInfo,
  getBlockDevices,
  getContainers,
  getHealthSummary,
  getNetworkInterfaces,
  getRepositories,
  getServices,
  getSystemContainers,
  getSystemInfo,
  type HealthInfo,
  type HealthLog,
  isListResult,
  LIST_TYPES_VERSION,
  type ListResult,
  type NetworkInfo,
  type NetworkInterface,
  type Partition,
  type PortInfo,
  type PortMapping,
  type RepositoryInfo as ListRepositoryInfo,
  type ServiceInfo,
  type ServicesResult,
  type SystemInfo,
} from './list-types.generated';
// Vault types - auto-generated from renet/pkg/bridge/vault/
export {
  assertQueueVaultV2,
  type ContextSection,
  isQueueVaultV2,
  type MachineSection,
  type QueueVaultV2,
  type RepositoryInfo,
  type SSHSection,
  type StorageSection,
  type TaskSection,
  VAULT_SCHEMA,
  VAULT_VERSION,
} from './vault.generated';
// Vault Zod schemas - auto-generated from renet/pkg/bridge/vault/
export {
  ContextSectionSchema,
  getVaultValidationErrors,
  MachineSectionSchema,
  parseQueueVault,
  QueueVaultV2Schema,
  type QueueVaultV2Type,
  RepositoryInfoSchema,
  SSHSectionSchema,
  StorageSectionSchema,
  TaskSectionSchema,
  validateQueueVault,
} from './vault.schema';
