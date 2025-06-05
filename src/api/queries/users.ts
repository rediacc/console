import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'
import toast from 'react-hot-toast'
import { hashPassword } from '@/utils/auth'

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

// Get all users
export const useUsers = () => {
  return useQuery({
    queryKey: ['users'],
    queryFn: async () => {
      const response = await apiClient.get('/GetCompanyUsers')
      const users = response.tables[1]?.data || []
      
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
export const useCreateUser = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { email: string; password: string }) => {
      const passwordHash = await hashPassword(data.password)
      const response = await apiClient.post('/CreateNewUser', {
        newUserEmail: data.email,
        newUserHash: passwordHash,
      })
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      queryClient.invalidateQueries({ queryKey: ['dropdown-data'] })
      toast.success(`User "${variables.email}" created successfully`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to create user')
    },
  })
}

// Activate user
export const useActivateUser = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { userEmail: string; activationCode: string }) => {
      const response = await apiClient.activateUser(data.userEmail, data.activationCode)
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      toast.success(`User "${variables.userEmail}" activated`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to activate user')
    },
  })
}

// Deactivate user
export const useDeactivateUser = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (userEmail: string) => {
      const response = await apiClient.put('/UpdateUserToDeactivated', { userEmail })
      return response
    },
    onSuccess: (_, userEmail) => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      toast.success(`User "${userEmail}" deactivated`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to deactivate user')
    },
  })
}

// Update user email
export const useUpdateUserEmail = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { currentUserEmail: string; newUserEmail: string }) => {
      const response = await apiClient.put('/UpdateUserEmail', data)
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      toast.success(`Email updated to "${variables.newUserEmail}"`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to update email')
    },
  })
}

// Get permission groups
export const usePermissionGroups = () => {
  return useQuery({
    queryKey: ['permission-groups'],
    queryFn: async () => {
      const response = await apiClient.get<PermissionGroup[]>('/GetCompanyPermissionGroups')
      return response.tables[1]?.data || []
    },
  })
}

// Create permission group
export const useCreatePermissionGroup = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (permissionGroupName: string) => {
      const response = await apiClient.post('/CreatePermissionGroup', { permissionGroupName })
      return response
    },
    onSuccess: (_, groupName) => {
      queryClient.invalidateQueries({ queryKey: ['permission-groups'] })
      toast.success(`Permission group "${groupName}" created`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to create permission group')
    },
  })
}

// Assign user to permission group
export const useAssignUserPermissions = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { userEmail: string; permissionGroupName: string }) => {
      const response = await apiClient.put('/UpdateUserAssignedPermissions', data)
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      toast.success(`User "${variables.userEmail}" assigned to group "${variables.permissionGroupName}"`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to assign permissions')
    },
  })
}