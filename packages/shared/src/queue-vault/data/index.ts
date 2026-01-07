export {
  FUNCTION_CATEGORIES,
  FUNCTION_DEFINITIONS,
  type FunctionDefinition,
  type FunctionParameterDefinition,
  type FunctionCategory,
  type CheckboxOption,
  type UIType,
} from './definitions';
export { FUNCTION_REQUIREMENTS } from './functionRequirements';

// Type-safe exports from generated file
// Note: FUNCTION_VISIBILITY and FunctionVisibility removed - visibility validation
// is now handled server-side by renet. All functions in this file are public.
export {
  BRIDGE_FUNCTIONS,
  BRIDGE_FUNCTIONS_VERSION,
  isBridgeFunction,
  isPublicBridgeFunction,
  getTypedParams,
  createFunctionPayload,
  queueFunctions,
  type BridgeFunctionName,
  type FunctionParamsMap,
  type TypedFunctionPayload,
  type QueueFunctionsType,
} from './functions.generated';

// Zod validation exports from schema file
export {
  FUNCTION_SCHEMAS,
  validateFunctionParams,
  safeValidateFunctionParams,
  getValidationErrors,
  isValidParams,
} from './functions.schema';

// Vault types - auto-generated from renet/pkg/bridge/vault/
export {
  VAULT_SCHEMA,
  VAULT_VERSION,
  type QueueVaultV2,
  type TaskSection,
  type SSHSection,
  type MachineSection,
  type StorageSection,
  type RepositoryInfo,
  type ContextSection,
  isQueueVaultV2,
  assertQueueVaultV2,
} from './vault.generated';

// Vault Zod schemas - auto-generated from renet/pkg/bridge/vault/
export {
  TaskSectionSchema,
  SSHSectionSchema,
  MachineSectionSchema,
  StorageSectionSchema,
  RepositoryInfoSchema,
  ContextSectionSchema,
  QueueVaultV2Schema,
  type QueueVaultV2Type,
  validateQueueVault,
  parseQueueVault,
  getVaultValidationErrors,
} from './vault.schema';

// List types - auto-generated from renet/pkg/list/types.go
// These are the types from 'renet list all --json' for machine status
export {
  LIST_TYPES_VERSION,
  isListResult,
  getRepositories,
  getSystemInfo,
  getContainers,
  getSystemContainers,
  getServices,
  getBlockDevices,
  getNetworkInterfaces,
  getHealthSummary,
  type ListResult,
  type SystemInfo,
  type DiskInfo,
  type NetworkInfo,
  type NetworkInterface,
  type BlockDevice,
  type Partition,
  type RepositoryInfo as ListRepositoryInfo,
  type ServicesResult,
  type ServiceInfo,
  type ContainersResult,
  type ContainerInfo,
  type PortMapping,
  type PortInfo,
  type HealthInfo,
  type HealthLog,
} from './list-types.generated';
