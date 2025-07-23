import { z } from 'zod'

// Resource name schema factory
const createResourceNameSchema = (resourceType: string) => 
  z.string()
    .min(1, `${resourceType} name is required`)
    .max(100, `${resourceType} name must be less than 100 characters`)

// Resource name schemas
const resourceTypes = ['Team', 'Region', 'Bridge', 'Machine', 'Repository', 'Storage', 'Schedule', 'DistributedStorage'] as const
export const [teamNameSchema, regionNameSchema, bridgeNameSchema, machineNameSchema, repositoryNameSchema, storageNameSchema, scheduleNameSchema, distributedStorageNameSchema] = 
  resourceTypes.map(type => createResourceNameSchema(type))

// User schemas
export const emailSchema = z.string()
  .min(1, 'Email is required')
  .email('Invalid email address')

export const passwordSchema = z.string()
  .min(8, 'Password must be at least 8 characters')
  .max(100, 'Password must be less than 100 characters')

// Vault schema
export const vaultSchema = z.string()
  .min(2, 'Vault must be valid JSON')
  .refine((val) => {
    try {
      JSON.parse(val)
      return true
    } catch {
      return false
    }
  }, 'Vault must be valid JSON')

// Form schemas factory
const withVault = (fields: Record<string, z.ZodSchema>, vaultFieldName: string) =>
  z.object({ ...fields, [vaultFieldName]: vaultSchema.optional().default('{}') })

// Create schemas using configuration
const resourceSchemas = {
  team: { teamName: teamNameSchema },
  region: { regionName: regionNameSchema },
  bridge: { regionName: regionNameSchema, bridgeName: bridgeNameSchema },
  machine: { teamName: teamNameSchema, regionName: regionNameSchema, bridgeName: bridgeNameSchema, machineName: machineNameSchema },
  repository: { teamName: teamNameSchema, repositoryName: repositoryNameSchema },
  storage: { teamName: teamNameSchema, storageName: storageNameSchema },
  schedule: { teamName: teamNameSchema, scheduleName: scheduleNameSchema },
  distributedStorage: { teamName: teamNameSchema, clusterName: distributedStorageNameSchema }
} as const

export const createTeamSchema = withVault(resourceSchemas.team, 'teamVault')
export const createRegionSchema = withVault(resourceSchemas.region, 'regionVault')
export const createBridgeSchema = withVault(resourceSchemas.bridge, 'bridgeVault')
export const createMachineSchema = withVault(resourceSchemas.machine, 'machineVault')
// Special schema for repository creation with conditional machine selection and size
export const createRepositorySchema = withVault({
  ...resourceSchemas.repository,
  machineName: z.string().optional(),  // Optional - required only when creating physical storage
  size: z.string()
    .optional()
    .refine((val) => {
      // Skip validation if empty or undefined
      if (!val || val.trim() === '') return true
      
      // Validate format
      const match = val.match(/^(\d+)([GT])$/)
      if (!match) return false
      
      const num = parseInt(match[1])
      return num > 0
    }, 'Invalid size format (e.g., 10G, 100G, 1T)'),  // Optional - required only when creating physical storage
  repositoryGuid: z.union([
    z.string().length(0),  // Allow empty string
    z.string().uuid('Invalid GUID format')  // Or valid UUID
  ]).optional()  // Optional repository GUID
}, 'repositoryVault')
  .refine((data) => {
    // If repositoryGuid is provided (credential-only mode), machine and size are not required
    // Otherwise, both machine and size must be provided for physical storage creation
    const isCredentialOnlyMode = data.repositoryGuid && data.repositoryGuid.trim() !== ''
    if (isCredentialOnlyMode) {
      return true  // No additional requirements in credential-only mode
    }
    // In normal mode, both machine and size are required
    return (data.machineName && data.machineName.trim() !== '') && 
           (data.size && data.size.trim() !== '')
  }, {
    message: 'Machine and size are required when creating new repository storage',
    path: ['machineName']  // Show error on machine field
  })
export const createStorageSchema = withVault(resourceSchemas.storage, 'storageVault')
export const createScheduleSchema = withVault(resourceSchemas.schedule, 'scheduleVault')

// Special schema for distributed storage with complex configuration
export const createDistributedStorageSchema = withVault({
  ...resourceSchemas.distributedStorage,
  nodes: z.array(z.string())
    .min(3, 'At least 3 nodes are required for distributed storage')
    .refine((nodes) => new Set(nodes).size === nodes.length, 'Duplicate nodes are not allowed'),
  poolName: z.string()
    .min(1, 'Pool name is required')
    .max(100, 'Pool name must be less than 100 characters')
    .regex(/^[a-zA-Z0-9_-]+$/, 'Pool name can only contain letters, numbers, hyphens, and underscores')
    .default('rbd'),
  poolPgNum: z.number()
    .min(1, 'Pool PG number must be at least 1')
    .max(1024, 'Pool PG number must be less than 1024')
    .default(128),
  poolSize: z.string()
    .regex(/^\d+[GT]$/, 'Invalid size format (e.g., 100G, 1T)')
    .refine((val) => {
      const match = val.match(/^(\d+)([GT])$/)
      if (!match) return false
      const num = parseInt(match[1])
      return num > 0
    }, 'Size must be greater than 0')
    .default('100G'),
  osdDevice: z.string()
    .min(1, 'OSD device is required')
    .regex(/^\/dev\/[a-zA-Z0-9_\/]+$/, 'Invalid device path (e.g., /dev/sdb)')
    .default('/dev/sdb'),
  rbdImagePrefix: z.string()
    .min(1, 'RBD image prefix is required')
    .max(50, 'RBD image prefix must be less than 50 characters')
    .regex(/^[a-zA-Z0-9_-]+$/, 'RBD image prefix can only contain letters, numbers, hyphens, and underscores')
    .default('rediacc_disk'),
  healthCheckTimeout: z.number()
    .min(60, 'Health check timeout must be at least 60 seconds')
    .max(3600, 'Health check timeout must be less than 3600 seconds (1 hour)')
    .default(1800),
}, 'distributedStorageVault')

export const createUserSchema = z.object({
  newUserEmail: emailSchema,
  newUserPassword: passwordSchema,
})

export const loginSchema = z.object({
  email: emailSchema,
  password: passwordSchema,
})

// Queue schemas
export const queueItemSchema = z.object({
  teamName: teamNameSchema,
  machineName: machineNameSchema,
  bridgeName: bridgeNameSchema,
  queueVault: vaultSchema,
  priority: z.number().min(1).max(5).optional().default(3),
})

// Edit schemas - factory function for single field schemas
const createEditSchema = <T extends z.ZodSchema>(schema: T, fieldName: string) => 
  z.object({ [fieldName]: schema })

const editSchemaConfigs = [
  ['editTeamSchema', teamNameSchema, 'teamName'],
  ['editRegionSchema', regionNameSchema, 'regionName'],
  ['editBridgeSchema', bridgeNameSchema, 'bridgeName'],
  ['editRepositorySchema', repositoryNameSchema, 'repositoryName'],
  ['editStorageSchema', storageNameSchema, 'storageName'],
  ['editScheduleSchema', scheduleNameSchema, 'scheduleName'],
  ['editDistributedStorageSchema', distributedStorageNameSchema, 'clusterName']
] as const

export const editTeamSchema = createEditSchema(teamNameSchema, 'teamName')
export const editRegionSchema = createEditSchema(regionNameSchema, 'regionName')
export const editBridgeSchema = createEditSchema(bridgeNameSchema, 'bridgeName')
export const editMachineSchema = z.object(resourceSchemas.machine)
export const editRepositorySchema = createEditSchema(repositoryNameSchema, 'repositoryName')
export const editStorageSchema = createEditSchema(storageNameSchema, 'storageName')
export const editScheduleSchema = createEditSchema(scheduleNameSchema, 'scheduleName')
export const editDistributedStorageSchema = createEditSchema(distributedStorageNameSchema, 'clusterName')

// Type exports
export type CreateTeamForm = z.infer<typeof createTeamSchema>
export type CreateRegionForm = z.infer<typeof createRegionSchema>
export type CreateBridgeForm = z.infer<typeof createBridgeSchema>
export type CreateMachineForm = z.infer<typeof createMachineSchema>
export type CreateRepositoryForm = z.infer<typeof createRepositorySchema>
export type CreateStorageForm = z.infer<typeof createStorageSchema>
export type CreateScheduleForm = z.infer<typeof createScheduleSchema>
export type CreateDistributedStorageForm = z.infer<typeof createDistributedStorageSchema>
export type CreateUserForm = z.infer<typeof createUserSchema>
export type LoginForm = z.infer<typeof loginSchema>
export type QueueItemForm = z.infer<typeof queueItemSchema>
export type EditTeamForm = z.infer<typeof editTeamSchema>
export type EditRegionForm = z.infer<typeof editRegionSchema>
export type EditBridgeForm = z.infer<typeof editBridgeSchema>
export type EditMachineForm = z.infer<typeof editMachineSchema>
export type EditRepositoryForm = z.infer<typeof editRepositorySchema>
export type EditStorageForm = z.infer<typeof editStorageSchema>
export type EditScheduleForm = z.infer<typeof editScheduleSchema>
export type EditDistributedStorageForm = z.infer<typeof editDistributedStorageSchema>