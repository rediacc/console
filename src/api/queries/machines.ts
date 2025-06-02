import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'
import toast from 'react-hot-toast'

export interface Machine {
  machineName: string
  teamName: string
  bridgeName: string
  queueCount: number
  vaultVersion: number
}

// Get machines for a team
export const useMachines = (teamName?: string) => {
  return useQuery<Machine[]>({
    queryKey: ['machines', teamName],
    queryFn: async () => {
      if (!teamName) return []
      const response = await apiClient.get<Machine[]>('/GetTeamMachines', { teamName })
      return response.tables[1]?.data || []
    },
    enabled: !!teamName,
  })
}

// Create machine
export const useCreateMachine = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { teamName: string; bridgeName: string; machineName: string; machineVault?: string }) => {
      const response = await apiClient.post('/CreateMachine', {
        teamName: data.teamName,
        bridgeName: data.bridgeName,
        machineName: data.machineName,
        machineVault: data.machineVault || '{}',
      })
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['machines'] })
      queryClient.invalidateQueries({ queryKey: ['teams'] })
      queryClient.invalidateQueries({ queryKey: ['bridges'] })
      queryClient.invalidateQueries({ queryKey: ['dropdown-data'] })
      toast.success(`Machine "${variables.machineName}" created successfully`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to create machine')
    },
  })
}

// Update machine name
export const useUpdateMachineName = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { teamName: string; currentMachineName: string; newMachineName: string }) => {
      const response = await apiClient.put('/UpdateMachineName', data)
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['machines'] })
      queryClient.invalidateQueries({ queryKey: ['dropdown-data'] })
      toast.success(`Machine renamed to "${variables.newMachineName}"`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to update machine name')
    },
  })
}

// Update machine bridge assignment
export const useUpdateMachineBridge = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { teamName: string; machineName: string; newBridgeName: string }) => {
      const response = await apiClient.put('/UpdateMachineAssignedBridge', data)
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['machines'] })
      queryClient.invalidateQueries({ queryKey: ['bridges'] })
      toast.success(`Machine "${variables.machineName}" reassigned to bridge "${variables.newBridgeName}"`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to update machine bridge')
    },
  })
}

// Update machine vault
export const useUpdateMachineVault = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { teamName: string; machineName: string; machineVault: string; vaultVersion: number }) => {
      const response = await apiClient.put('/UpdateMachineVault', data)
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['machines'] })
      toast.success(`Machine vault updated for "${variables.machineName}"`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to update machine vault')
    },
  })
}

// Delete machine
export const useDeleteMachine = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { teamName: string; machineName: string }) => {
      const response = await apiClient.delete('/DeleteMachine', data)
      return response
    },
    onSuccess: (_, data) => {
      queryClient.invalidateQueries({ queryKey: ['machines'] })
      queryClient.invalidateQueries({ queryKey: ['teams'] })
      queryClient.invalidateQueries({ queryKey: ['bridges'] })
      queryClient.invalidateQueries({ queryKey: ['dropdown-data'] })
      toast.success(`Machine "${data.machineName}" deleted successfully`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to delete machine')
    },
  })
}