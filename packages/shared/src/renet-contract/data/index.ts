export {
  type CheckboxOption,
  FUNCTION_CATEGORIES,
  FUNCTION_DEFINITIONS,
  type FunctionCategory,
  type FunctionDefinition,
  type FunctionParameterDefinition,
  type UIType,
} from './definitions.js';
export { FUNCTION_REQUIREMENTS } from './functionRequirements.js';

// Type-safe exports from generated file
// Note: FUNCTION_VISIBILITY and FunctionVisibility removed - visibility validation
// is now handled server-side by renet. All functions in this file are public.
export {
  createFunctionPayload,
  type FunctionParamsMap,
  getTypedParams,
  isPublicRenetFunction,
  isRenetFunction,
  type QueueFunctionsType,
  queueFunctions,
  RENET_FUNCTIONS,
  RENET_FUNCTIONS_VERSION,
  type RenetFunctionName,
  type TypedFunctionPayload,
} from './functions.generated.js';

// Zod validation exports from schema file
export {
  FUNCTION_SCHEMAS,
  getValidationErrors,
  isValidParams,
  safeValidateFunctionParams,
  validateFunctionParams,
} from './functions.schema.js';
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
} from './list-types.generated.js';
// Vault types - auto-generated from renet/pkg/functions/vault/
export {
  assertRenetVault,
  type ContextSection,
  isRenetVault,
  type MachineSection,
  type RenetVault,
  type RepositoryInfo,
  type SSHSection,
  type StorageSection,
  type TaskSection,
  VAULT_SCHEMA,
  VAULT_VERSION,
} from './vault.generated.js';
// Vault Zod schemas - auto-generated from renet/pkg/functions/vault/
export {
  ContextSectionSchema,
  getVaultValidationErrors,
  MachineSectionSchema,
  parseRenetVault,
  RenetVaultSchema,
  type RenetVaultType,
  RepositoryInfoSchema,
  SSHSectionSchema,
  StorageSectionSchema,
  TaskSectionSchema,
  validateRenetVault,
} from './vault.schema.js';
