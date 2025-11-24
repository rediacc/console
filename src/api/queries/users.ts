import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { extractTableData, getFirstRow } from '@/core/api/response'
import { createMutation } from '@/hooks/api/mutationFactory'
import { hashPassword } from '@/utils/auth'
import { showMessage } from '@/utils/messages'
import i18n from '@/i18n/config'
import { createErrorHandler } from '@/utils/mutationUtils'

export interface User {
  userEmail: string
  companyName: string
  activated: boolean
  lastActive?: string
  permissionGroupName?: string
}

export interface PermissionGroup {
  permissionGroupName: string
  userCount: number
  permissionCount: number
}

export interface UserRequest {
  requestId: number
  userEmail: string
  sessionName: string
  ipAddress: string | null
  userAgent: string | null
  createdAt: string
  lastActivity: string
  isActive: boolean
  parentRequestId: number | null
  permissionsName: string
  expirationTime: string | null
}

// Get all users
export const useUsers = () => {
  return useQuery({
    queryKey: ['users'],
    queryFn: async () => {
      const response = await apiClient.get('/GetCompanyUsers')
      const users = extractTableData<Record<string, unknown>[]>(response, 1, [])

      return users.map((user) => ({
        ...user,
        userEmail: (user.UserEmail ?? user.userEmail) as string,
        companyName: (user.CompanyName ?? user.companyName) as string,
        activated: Boolean(user.Activated ?? user.activated),
        permissionGroupName: (user.PermissionsName ?? user.permissionsName ?? user.permissionGroupName) as string | undefined,
        lastActive: user.lastActive as string | undefined,
      }))
    },
  })
}

// Create user
export const useCreateUser = createMutation<{ email: string; password: string }>({
  endpoint: '/CreateNewUser',
  method: 'post',
  invalidateKeys: ['users', 'dropdown-data'],
  successMessage: (vars) => i18n.t('organization:users.success.created', { email: vars.email }),
  errorMessage: i18n.t('organization:users.errors.createFailed'),
  transformData: async (data) => {
    const passwordHash = await hashPassword(data.password)
    return {
      newUserEmail: data.email,
      newUserHash: passwordHash,
      languagePreference: i18n.language || 'en',
    }
  }
})

// Activate user - Special case that uses custom apiClient method
export const useActivateUser = () => {
  const queryClient = useQueryClient()
  const activationErrorHandler = createErrorHandler(i18n.t('organization:users.errors.activateFailed'))

  return useMutation({
    mutationFn: async (data: { userEmail: string; activationCode: string; passwordHash: string }) => {
      const response = await apiClient.activateUser(data.userEmail, data.activationCode, data.passwordHash)
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      showMessage('success', i18n.t('organization:users.success.activated', { email: variables.userEmail }))
    },
    onError: activationErrorHandler,
  })
}

// Deactivate user
export const useDeactivateUser = createMutation<string>({
  endpoint: '/UpdateUserToDeactivated',
  method: 'put',
  invalidateKeys: ['users'],
  successMessage: (userEmail) => i18n.t('organization:users.success.deactivated', { email: userEmail }),
  errorMessage: i18n.t('organization:users.errors.deactivateFailed'),
  transformData: (userEmail) => ({ userEmail })
})

// Reactivate user
export const useReactivateUser = createMutation<string>({
  endpoint: '/UpdateUserToActivated',
  method: 'put',
  invalidateKeys: ['users'],
  successMessage: (userEmail) => i18n.t('organization:users.success.activated', { email: userEmail }),
  errorMessage: i18n.t('organization:users.errors.activateFailed'),
  transformData: (userEmail) => ({ userEmail })
})

// Update user email
export const useUpdateUserEmail = createMutation<{ currentUserEmail: string; newUserEmail: string }>({
  endpoint: '/UpdateUserEmail',
  method: 'put',
  invalidateKeys: ['users'],
  successMessage: (vars) => i18n.t('organization:users.success.emailUpdated', { email: vars.newUserEmail }),
  errorMessage: i18n.t('organization:users.errors.emailUpdateFailed')
})

// Update user language preference
export const useUpdateUserLanguage = createMutation<string>({
  endpoint: '/UpdateUserLanguage',
  method: 'put',
  invalidateKeys: [],
  successMessage: () => i18n.t('organization:users.success.languageSaved'),
  errorMessage: i18n.t('organization:users.errors.languageUpdateFailed'),
  transformData: (preferredLanguage) => ({ preferredLanguage })
})

// Get permission groups
export const usePermissionGroups = () => {
  return useQuery({
    queryKey: ['permission-groups'],
    queryFn: async () => {
      const response = await apiClient.get('/GetCompanyPermissionGroups')
      return extractTableData<Record<string, unknown>[]>(response, 1, [])
    },
  })
}

// Create permission group
export const useCreatePermissionGroup = createMutation<string>({
  endpoint: '/CreatePermissionGroup',
  method: 'post',
  invalidateKeys: ['permission-groups'],
  successMessage: (groupName) => i18n.t('organization:users.success.permissionGroupCreated', { groupName }),
  errorMessage: i18n.t('organization:users.errors.permissionGroupCreateFailed'),
  transformData: (permissionGroupName) => ({ permissionGroupName })
})

// Assign user to permission group
export const useAssignUserPermissions = createMutation<{ userEmail: string; permissionGroupName: string }>({
  endpoint: '/UpdateUserAssignedPermissions',
  method: 'put',
  invalidateKeys: ['users'],
  successMessage: (vars) => i18n.t('organization:users.success.permissionsAssigned', {
    email: vars.userEmail,
    group: vars.permissionGroupName
  }),
  errorMessage: i18n.t('organization:users.errors.assignPermissionsFailed')
})

// Update user password
export const useUpdateUserPassword = createMutation<{ userEmail: string; newPassword: string }>({
  endpoint: '/UpdateUserPassword',
  method: 'put',
  invalidateKeys: [],
  successMessage: () => i18n.t('organization:users.success.passwordUpdated'),
  errorMessage: i18n.t('organization:users.errors.passwordUpdateFailed'),
  transformData: async (data) => {
    const passwordHash = await hashPassword(data.newPassword)
    return {
      userNewPass: passwordHash,
    }
  }
})

// Get active user requests/sessions
export const useUserRequests = () => {
  return useQuery({
    queryKey: ['user-requests'],
    queryFn: async () => {
      const response = await apiClient.get('/GetUserRequests')
      return extractTableData<UserRequest[]>(response, 1, [])
    },
    staleTime: 10 * 1000,
    refetchInterval: 30 * 1000,
  })
}

// Delete/terminate a user request/session
export const useDeleteUserRequest = createMutation<{ requestId: number }>({
  endpoint: '/DeleteUserRequest',
  method: 'delete',
  invalidateKeys: ['user-requests'],
  successMessage: () => i18n.t('organization:users.success.sessionTerminated'),
  errorMessage: i18n.t('organization:users.errors.sessionTerminateFailed'),
  transformData: (data) => ({
    targetRequestId: data.requestId
  })
})

// Get current user's vault data
interface UserVaultResult {
  vault: string
  vaultVersion: number
  userCredential: string | null
}

interface UserVaultRow {
  vaultContent?: string
  vaultVersion?: number
  userCredential?: string | null
}

export const useUserVault = () => {
  return useQuery<UserVaultResult>({
    queryKey: ['user-vault'],
    queryFn: async () => {
      const response = await apiClient.get('/GetUserVault')
      const vaultData = getFirstRow<UserVaultRow>(response, 1)

      if (vaultData) {
        return {
          vault: vaultData.vaultContent || '{}',
          vaultVersion: vaultData.vaultVersion || 1,
          userCredential: vaultData.userCredential ?? null,
        }
      }

      return {
        vault: '{}',
        vaultVersion: 1,
        userCredential: null
      }
    },
  })
}

// Update current user's vault
export const useUpdateUserVault = createMutation<{ userVault: string; vaultVersion: number }>({
  endpoint: '/UpdateUserVault',
  method: 'post',
  invalidateKeys: ['user-vault'],
  successMessage: () => i18n.t('organization:users.success.userVaultUpdated'),
  errorMessage: i18n.t('organization:users.errors.userVaultUpdateFailed'),
  transformData: (data) => ({
    userVault: data.userVault,
    vaultVersion: data.vaultVersion
  })
})
