import { z } from 'zod'

// Resource name schema factory
const createResourceNameSchema = (resourceType: string) => 
  z.string()
    .min(1, `${resourceType} name is required`)
    .max(100, `${resourceType} name must be less than 100 characters`)

// Resource name schemas
const resourceTypes = ['Team', 'Region', 'Bridge', 'Machine', 'Repository', 'Storage', 'Cluster', 'Pool', 'Image', 'Snapshot', 'Clone'] as const
export const [teamNameSchema, regionNameSchema, bridgeNameSchema, machineNameSchema, repositoryNameSchema, storageNameSchema, clusterNameSchema, poolNameSchema, imageNameSchema, snapshotNameSchema, cloneNameSchema] =
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
  cluster: { clusterName: clusterNameSchema },
  pool: { teamName: teamNameSchema, clusterName: clusterNameSchema, poolName: poolNameSchema },
  image: { teamName: teamNameSchema, poolName: poolNameSchema, imageName: imageNameSchema },
  snapshot: { teamName: teamNameSchema, poolName: poolNameSchema, imageName: imageNameSchema, snapshotName: snapshotNameSchema },
  clone: { teamName: teamNameSchema, poolName: poolNameSchema, imageName: imageNameSchema, snapshotName: snapshotNameSchema, cloneName: cloneNameSchema }
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
export const createClusterSchema = withVault(resourceSchemas.cluster, 'clusterVault')
export const createPoolSchema = withVault(resourceSchemas.pool, 'poolVault')
export const createImageSchema = withVault(resourceSchemas.image, 'imageVault')
export const createSnapshotSchema = withVault(resourceSchemas.snapshot, 'snapshotVault')
export const createCloneSchema = withVault(resourceSchemas.clone, 'cloneVault')

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


export const editTeamSchema = createEditSchema(teamNameSchema, 'teamName')
export const editRegionSchema = createEditSchema(regionNameSchema, 'regionName')
export const editBridgeSchema = createEditSchema(bridgeNameSchema, 'bridgeName')
export const editMachineSchema = z.object(resourceSchemas.machine)
export const editRepositorySchema = createEditSchema(repositoryNameSchema, 'repositoryName')
export const editStorageSchema = createEditSchema(storageNameSchema, 'storageName')

// Type exports
export type CreateTeamForm = z.infer<typeof createTeamSchema>
export type CreateRegionForm = z.infer<typeof createRegionSchema>
export type CreateBridgeForm = z.infer<typeof createBridgeSchema>
export type CreateMachineForm = z.infer<typeof createMachineSchema>
export type CreateRepositoryForm = z.infer<typeof createRepositorySchema>
export type CreateStorageForm = z.infer<typeof createStorageSchema>
export type CreateClusterForm = z.infer<typeof createClusterSchema>
export type CreatePoolForm = z.infer<typeof createPoolSchema>
export type CreateImageForm = z.infer<typeof createImageSchema>
export type CreateSnapshotForm = z.infer<typeof createSnapshotSchema>
export type CreateCloneForm = z.infer<typeof createCloneSchema>
export type CreateUserForm = z.infer<typeof createUserSchema>
export type LoginForm = z.infer<typeof loginSchema>
export type QueueItemForm = z.infer<typeof queueItemSchema>
export type EditTeamForm = z.infer<typeof editTeamSchema>
export type EditRegionForm = z.infer<typeof editRegionSchema>
export type EditBridgeForm = z.infer<typeof editBridgeSchema>
export type EditMachineForm = z.infer<typeof editMachineSchema>
export type EditRepositoryForm = z.infer<typeof editRepositorySchema>
export type EditStorageForm = z.infer<typeof editStorageSchema>