import { z } from 'zod'

// Common patterns
const namePattern = /^[a-zA-Z0-9-_@/]+$/
const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

// Resource name schemas
export const teamNameSchema = z.string()
  .min(1, 'Team name is required')
  .max(100, 'Team name must be less than 100 characters')

export const regionNameSchema = z.string()
  .min(1, 'Region name is required')
  .max(100, 'Region name must be less than 100 characters')

export const bridgeNameSchema = z.string()
  .min(1, 'Bridge name is required')
  .max(100, 'Bridge name must be less than 100 characters')

export const machineNameSchema = z.string()
  .min(1, 'Machine name is required')
  .max(100, 'Machine name must be less than 100 characters')

export const repositoryNameSchema = z.string()
  .min(1, 'Repository name is required')
  .max(100, 'Repository name must be less than 100 characters')

export const storageNameSchema = z.string()
  .min(1, 'Storage name is required')
  .max(100, 'Storage name must be less than 100 characters')

export const scheduleNameSchema = z.string()
  .min(1, 'Schedule name is required')
  .max(100, 'Schedule name must be less than 100 characters')

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

// Form schemas
export const createTeamSchema = z.object({
  teamName: teamNameSchema,
  teamVault: vaultSchema.optional().default('{}'),
})

export const createRegionSchema = z.object({
  regionName: regionNameSchema,
  regionVault: vaultSchema.optional().default('{}'),
})

export const createBridgeSchema = z.object({
  regionName: regionNameSchema,
  bridgeName: bridgeNameSchema,
  bridgeVault: vaultSchema.optional().default('{}'),
})

export const createMachineSchema = z.object({
  teamName: teamNameSchema,
  regionName: regionNameSchema,
  bridgeName: bridgeNameSchema,
  machineName: machineNameSchema,
  machineVault: vaultSchema.optional().default('{}'),
})

export const createRepositorySchema = z.object({
  teamName: teamNameSchema,
  repositoryName: repositoryNameSchema,
  repositoryVault: vaultSchema.optional().default('{}'),
})

export const createStorageSchema = z.object({
  teamName: teamNameSchema,
  storageName: storageNameSchema,
  storageVault: vaultSchema.optional().default('{}'),
})

export const createScheduleSchema = z.object({
  teamName: teamNameSchema,
  scheduleName: scheduleNameSchema,
  scheduleVault: vaultSchema.optional().default('{}'),
})

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
})

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