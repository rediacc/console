import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'
import toast from 'react-hot-toast'

export interface Repository {
  repoName: string
  teamName: string
  repoSize: string
  status: string
  vaultVersion: number
}

// Get repositories for a team
export const useRepositories = (teamName?: string) => {
  return useQuery<Repository[]>({
    queryKey: ['repositories', teamName],
    queryFn: async () => {
      if (!teamName) return []
      const response = await apiClient.get<Repository[]>('/GetTeamRepositories', { teamName })
      return response.tables[1]?.data || []
    },
    enabled: !!teamName,
  })
}

// Create repository
export const useCreateRepository = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { teamName: string; repoName: string; repoVault?: string }) => {
      const response = await apiClient.post('/CreateRepository', {
        teamName: data.teamName,
        repoName: data.repoName,
        repoVault: data.repoVault || '{}',
      })
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['repositories'] })
      queryClient.invalidateQueries({ queryKey: ['teams'] })
      toast.success(`Repository "${variables.repoName}" created successfully`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to create repository')
    },
  })
}

// Update repository name
export const useUpdateRepositoryName = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { teamName: string; currentRepoName: string; newRepoName: string }) => {
      const response = await apiClient.put('/UpdateRepositoryName', data)
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['repositories'] })
      toast.success(`Repository renamed to "${variables.newRepoName}"`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to update repository name')
    },
  })
}

// Update repository vault
export const useUpdateRepositoryVault = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { teamName: string; repoName: string; repoVault: string; vaultVersion: number }) => {
      const response = await apiClient.put('/UpdateRepositoryVault', data)
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['repositories'] })
      toast.success(`Repository vault updated for "${variables.repoName}"`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to update repository vault')
    },
  })
}

// Delete repository
export const useDeleteRepository = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { teamName: string; repoName: string }) => {
      const response = await apiClient.delete('/DeleteRepository', data)
      return response
    },
    onSuccess: (_, data) => {
      queryClient.invalidateQueries({ queryKey: ['repositories'] })
      queryClient.invalidateQueries({ queryKey: ['teams'] })
      toast.success(`Repository "${data.repoName}" deleted successfully`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to delete repository')
    },
  })
}