import { z } from 'zod'

// Resource name schema factory
const createResourceNameSchema = (resourceType: string) => 
  z.string()
    .min(1, `${resourceType} name is required`)
    .max(100, `${resourceType} name must be less than 100 characters`)

// Resource name schemas
const resourceTypes = ['Team', 'Region', 'Bridge', 'Machine', 'Repository', 'Storage', 'Schedule'] as const
export const [teamNameSchema, regionNameSchema, bridgeNameSchema, machineNameSchema, repositoryNameSchema, storageNameSchema, scheduleNameSchema] = 
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
  schedule: { teamName: teamNameSchema, scheduleName: scheduleNameSchema }
} as const

export const createTeamSchema = withVault(resourceSchemas.team, 'teamVault')
export const createRegionSchema = withVault(resourceSchemas.region, 'regionVault')
export const createBridgeSchema = withVault(resourceSchemas.bridge, 'bridgeVault')
export const createMachineSchema = withVault(resourceSchemas.machine, 'machineVault')
// Special schema for repository creation with machine selection
export const createRepositorySchema = withVault({
  ...resourceSchemas.repository,
  machineName: z.string().min(1, 'Machine is required'),
  size: z.string()
    .min(1, 'Size is required')
    .regex(/^\d+[GT]$/, 'Invalid size format')
    .refine((val) => {
      const match = val.match(/^(\d+)([GT])$/)
      if (!match) return false
      const num = parseInt(match[1])
      return num > 0
    }, 'Size must be greater than 0')
}, 'repositoryVault')
export const createStorageSchema = withVault(resourceSchemas.storage, 'storageVault')
export const createScheduleSchema = withVault(resourceSchemas.schedule, 'scheduleVault')

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
  ['editScheduleSchema', scheduleNameSchema, 'scheduleName']
] as const

export const editTeamSchema = createEditSchema(teamNameSchema, 'teamName')
export const editRegionSchema = createEditSchema(regionNameSchema, 'regionName')
export const editBridgeSchema = createEditSchema(bridgeNameSchema, 'bridgeName')
export const editMachineSchema = z.object(resourceSchemas.machine)
export const editRepositorySchema = createEditSchema(repositoryNameSchema, 'repositoryName')
export const editStorageSchema = createEditSchema(storageNameSchema, 'storageName')
export const editScheduleSchema = createEditSchema(scheduleNameSchema, 'scheduleName')

// Type exports
export type CreateTeamForm = z.infer<typeof createTeamSchema>
export type CreateRegionForm = z.infer<typeof createRegionSchema>
export type CreateBridgeForm = z.infer<typeof createBridgeSchema>
export type CreateMachineForm = z.infer<typeof createMachineSchema>
export type CreateRepositoryForm = z.infer<typeof createRepositorySchema>
export type CreateStorageForm = z.infer<typeof createStorageSchema>
export type CreateScheduleForm = z.infer<typeof createScheduleSchema>
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