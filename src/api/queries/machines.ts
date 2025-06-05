import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'
import toast from 'react-hot-toast'
import type { Machine } from '@/types'

// Get machines for a team, multiple teams, or all machines
export const useMachines = (teamFilter?: string | string[], enabled: boolean = true) => {
  return useQuery<Machine[]>({
    queryKey: ['machines', teamFilter],
    queryFn: async () => {
      // Build params based on teamFilter
      let params = {}
      
      if (Array.isArray(teamFilter) && teamFilter.length > 0) {
        // Send comma-separated teams in a single request
        params = { teamName: teamFilter.join(',') }
      } else if (teamFilter && !Array.isArray(teamFilter)) {
        // Single team
        params = { teamName: teamFilter }
      }
      // If no teamFilter, params remains empty (get all machines)
      
      const response = await apiClient.get('/GetTeamMachines', params)
      const machines = response.tables?.[1]?.data || response.tables?.[0]?.data || []
      if (!Array.isArray(machines)) return []
      return machines.filter(machine => machine && machine.machineName)
    },
    enabled,
    staleTime: 30 * 1000, // 30 seconds
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