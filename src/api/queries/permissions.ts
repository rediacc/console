import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'
import toast from 'react-hot-toast'

export interface PermissionGroup {
  permissionGroupName: string
  userCount: number
  permissionCount: number
  permissions?: string[]
}

export interface Permission {
  permissionName: string
  description?: string
}

// Get all permission groups
export const usePermissionGroups = () => {
  return useQuery<PermissionGroup[]>({
    queryKey: ['permissionGroups'],
    queryFn: async () => {
      const response = await apiClient.get<PermissionGroup[]>('/GetCompanyPermissionGroups')
      return response.tables[1]?.data || []
    },
  })
}

// Get permission group details
export const usePermissionGroupDetails = (groupName: string) => {
  return useQuery({
    queryKey: ['permissionGroup', groupName],
    queryFn: async () => {
      const response = await apiClient.get('/GetPermissionGroupDetails', { permissionGroupName: groupName })
      return response.tables[1]?.data[0] || {}
    },
    enabled: !!groupName,
  })
}

// Create permission group
export const useCreatePermissionGroup = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { permissionGroupName: string }) => {
      const response = await apiClient.post('/CreatePermissionGroup', data)
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['permissionGroups'] })
      queryClient.invalidateQueries({ queryKey: ['dropdown-data'] })
      toast.success(`Permission group "${variables.permissionGroupName}" created successfully`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to create permission group')
    },
  })
}

// Delete permission group
export const useDeletePermissionGroup = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (permissionGroupName: string) => {
      const response = await apiClient.delete('/DeletePermissionGroup', { permissionGroupName })
      return response
    },
    onSuccess: (_, permissionGroupName) => {
      queryClient.invalidateQueries({ queryKey: ['permissionGroups'] })
      queryClient.invalidateQueries({ queryKey: ['dropdown-data'] })
      toast.success(`Permission group "${permissionGroupName}" deleted successfully`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to delete permission group')
    },
  })
}

// Add permission to group
export const useAddPermissionToGroup = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { permissionGroupName: string; permissionName: string }) => {
      const response = await apiClient.post('/CreatePermissionInGroup', data)
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['permissionGroup', variables.permissionGroupName] })
      toast.success(`Permission "${variables.permissionName}" added to group`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to add permission to group')
    },
  })
}

// Remove permission from group
export const useRemovePermissionFromGroup = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { permissionGroupName: string; permissionName: string }) => {
      const response = await apiClient.delete('/DeletePermissionFromGroup', data)
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['permissionGroup', variables.permissionGroupName] })
      toast.success(`Permission "${variables.permissionName}" removed from group`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to remove permission from group')
    },
  })
}

// Assign user to permission group
export const useAssignUserToGroup = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { userEmail: string; permissionGroupName: string }) => {
      const response = await apiClient.put('/UpdateUserAssignedPermissions', data)
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      queryClient.invalidateQueries({ queryKey: ['permissionGroup', variables.permissionGroupName] })
      toast.success(`User assigned to permission group "${variables.permissionGroupName}"`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to assign user to permission group')
    },
  })
}