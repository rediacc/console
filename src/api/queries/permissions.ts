import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { extractTableData } from '@/core/api/response'
import { showMessage } from '@/utils/messages'

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
      const response = await apiClient.get('/GetCompanyPermissionGroups')
      const data = extractTableData<Record<string, unknown>[]>(response, 1, [])

      return data.map((group) => ({
        permissionGroupName: (group.PermissionGroupName ?? group.permissionGroupName) as string,
        userCount: (group.UserCount ?? group.userCount ?? 0) as number,
        permissionCount: (group.PermissionCount ?? group.permissionCount ?? 0) as number,
        permissions: typeof group.Permissions === 'string'
          ? group.Permissions.split(',').map((permission) => permission.trim()).filter(Boolean)
          : [],
      }))
    },
  })
}

// Get permission group details
export const usePermissionGroupDetails = (groupName: string) => {
  return useQuery({
    queryKey: ['permissionGroup', groupName],
    queryFn: async () => {
      const response = await apiClient.get('/GetPermissionGroupDetails', { permissionGroupName: groupName })
      const permissionRows = extractTableData<Record<string, unknown>[]>(response, 1, [])
      const permissions = permissionRows
        .map((row) => (row.PermissionName ?? row.permissionName) as string)
        .filter(Boolean)
      
      return {
        permissionGroupName: groupName,
        permissions: permissions
      }
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
      showMessage('success', `Permission group "${variables.permissionGroupName}" created successfully`)
    },
    onError: (error: any) => {
      showMessage('error', error.message || 'Failed to create permission group')
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
      showMessage('success', `Permission group "${permissionGroupName}" deleted successfully`)
    },
    onError: (error: any) => {
      showMessage('error', error.message || 'Failed to delete permission group')
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
      queryClient.invalidateQueries({ queryKey: ['permissionGroups'] }) // Update permission counts
      showMessage('success', `Permission "${variables.permissionName}" added to group`)
    },
    onError: (error: any) => {
      showMessage('error', error.message || 'Failed to add permission to group')
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
      queryClient.invalidateQueries({ queryKey: ['permissionGroups'] }) // Update permission counts
      showMessage('success', `Permission "${variables.permissionName}" removed from group`)
    },
    onError: (error: any) => {
      showMessage('error', error.message || 'Failed to remove permission from group')
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
      showMessage('success', `User assigned to permission group "${variables.permissionGroupName}"`)
    },
    onError: (error: any) => {
      showMessage('error', error.message || 'Failed to assign user to permission group')
    },
  })
}
