import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { createMutation } from '@/api/utils/mutationFactory'
import { hashPassword } from '@/utils/auth'
import { showMessage } from '@/utils/messages'

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
  requestId: string
  userEmail: string
  sessionName: string
  ipAddress: string
  userAgent: string
  createdAt: string
  lastActivity: string
  isActive: boolean
}

// Get all users
export const useUsers = () => {
  return useQuery({
    queryKey: ['users'],
    queryFn: async () => {
      const response = await apiClient.get('/GetCompanyUsers')
      const users = response.resultSets[1]?.data || []
      
      // Map PermissionsName to permissionGroupName to match our interface
      return users.map((user: any) => ({
        ...user,
        userEmail: user.UserEmail || user.userEmail,
        companyName: user.CompanyName || user.companyName,
        activated: user.Activated !== undefined ? user.Activated : user.activated,
        permissionGroupName: user.PermissionsName || user.permissionsName || user.permissionGroupName,
        lastActive: user.lastActive
      }))
    },
  })
}

// Create user
export const useCreateUser = createMutation<{ email: string; password: string }>({
  endpoint: '/CreateNewUser',
  method: 'post',
  invalidateKeys: ['users', 'dropdown-data'],
  successMessage: (vars) => `User "${vars.email}" created successfully`,
  errorMessage: 'Failed to create user',
  transformData: async (data) => {
    const passwordHash = await hashPassword(data.password)
    return {
      newUserEmail: data.email,
      newUserHash: passwordHash,
    }
  }
})

// Activate user - Special case that uses custom apiClient method
export const useActivateUser = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: { userEmail: string; activationCode: string; passwordHash: string }) => {
      const response = await apiClient.activateUser(data.userEmail, data.activationCode, data.passwordHash)
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      showMessage('success', `User "${variables.userEmail}" activated`)
    },
    onError: (error: any) => {
      showMessage('error', error.message || 'Failed to activate user')
    },
  })
}

// Deactivate user
export const useDeactivateUser = createMutation<string>({
  endpoint: '/UpdateUserToDeactivated',
  method: 'put',
  invalidateKeys: ['users'],
  successMessage: (userEmail) => `User "${userEmail}" deactivated`,
  errorMessage: 'Failed to deactivate user',
  transformData: (userEmail) => ({ userEmail })
})

// Update user email
export const useUpdateUserEmail = createMutation<{ currentUserEmail: string; newUserEmail: string }>({
  endpoint: '/UpdateUserEmail',
  method: 'put',
  invalidateKeys: ['users'],
  successMessage: (vars) => `Email updated to "${vars.newUserEmail}"`,
  errorMessage: 'Failed to update email'
})

// Get permission groups
export const usePermissionGroups = () => {
  return useQuery({
    queryKey: ['permission-groups'],
    queryFn: async () => {
      const response = await apiClient.get('/GetCompanyPermissionGroups')
      return response.resultSets[1]?.data || []
    },
  })
}

// Create permission group
export const useCreatePermissionGroup = createMutation<string>({
  endpoint: '/CreatePermissionGroup',
  method: 'post',
  invalidateKeys: ['permission-groups'],
  successMessage: (groupName) => `Permission group "${groupName}" created`,
  errorMessage: 'Failed to create permission group',
  transformData: (permissionGroupName) => ({ permissionGroupName })
})

// Assign user to permission group
export const useAssignUserPermissions = createMutation<{ userEmail: string; permissionGroupName: string }>({
  endpoint: '/UpdateUserAssignedPermissions',
  method: 'put',
  invalidateKeys: ['users'],
  successMessage: (vars) => `User "${vars.userEmail}" assigned to group "${vars.permissionGroupName}"`,
  errorMessage: 'Failed to assign permissions'
})

// Update user password
export const useUpdateUserPassword = createMutation<{ userEmail: string; newPassword: string }>({
  endpoint: '/UpdateUserPassword',
  method: 'put',
  invalidateKeys: [],
  successMessage: () => 'Password updated successfully. Please login with your new password.',
  errorMessage: 'Failed to update password',
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
      return response.resultSets[1]?.data || []
    },
    staleTime: 10 * 1000, // 10 seconds - refresh more frequently for active sessions
    refetchInterval: 30 * 1000, // Auto-refresh every 30 seconds
  })
}

// Delete/terminate a user request/session
export const useDeleteUserRequest = createMutation<{ requestId: string }>({
  endpoint: '/DeleteUserRequest',
  method: 'delete',
  invalidateKeys: ['user-requests'],
  successMessage: () => `User session terminated successfully`,
  errorMessage: 'Failed to terminate user session',
  transformData: (data) => ({ requestId: data.requestId })
})