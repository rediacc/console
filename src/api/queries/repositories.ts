import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'
import toast from 'react-hot-toast'

export interface Repository {
  repositoryName: string
  teamName: string
  vaultVersion: number
}

// Get repositories for a team
export const useRepositories = (teamName?: string) => {
  return useQuery<Repository[]>({
    queryKey: ['repositories', teamName],
    queryFn: async () => {
      if (!teamName) return []
      const response = await apiClient.get<any>('/GetTeamRepositories', { teamName })
      // Get data from tables with proper fallback
      const data = response.tables?.[1]?.data || response.tables?.[0]?.data || []
      // Ensure we have an array
      const repositories = Array.isArray(data) ? data : []
      // Filter out empty objects and map API response to UI format
      return repositories
        .filter((repo: any) => repo && repo.repoName)
        .map((repo: any) => ({
          repositoryName: repo.repoName,
          teamName: repo.teamName,
          vaultVersion: repo.vaultVersion || 1,
        }))
    },
    enabled: !!teamName,
  })
}

// Create repository
export const useCreateRepository = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { teamName: string; repositoryName: string; repositoryVault?: string }) => {
      const response = await apiClient.post('/CreateRepository', {
        teamName: data.teamName,
        repoName: data.repositoryName, // Map repositoryName to repoName for API
        repoVault: data.repositoryVault || '{}', // Map repositoryVault to repoVault for API
      })
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['repositories'] })
      queryClient.invalidateQueries({ queryKey: ['teams'] })
      toast.success(`Repository "${variables.repositoryName}" created successfully`)
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
    mutationFn: async (data: { teamName: string; currentRepositoryName: string; newRepositoryName: string }) => {
      const response = await apiClient.put('/UpdateRepositoryName', {
        teamName: data.teamName,
        currentRepoName: data.currentRepositoryName, // Map to API format
        newRepoName: data.newRepositoryName, // Map to API format
      })
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['repositories'] })
      toast.success(`Repository renamed to "${variables.newRepositoryName}"`)
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
    mutationFn: async (data: { teamName: string; repositoryName: string; repositoryVault: string; vaultVersion: number }) => {
      const response = await apiClient.put('/UpdateRepositoryVault', {
        teamName: data.teamName,
        repoName: data.repositoryName, // Map repositoryName to repoName for API
        repoVault: data.repositoryVault, // Map repositoryVault to repoVault for API
        vaultVersion: data.vaultVersion,
      })
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['repositories'] })
      toast.success(`Repository vault updated for "${variables.repositoryName}"`)
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
    mutationFn: async (data: { teamName: string; repositoryName: string }) => {
      const response = await apiClient.delete('/DeleteRepository', {
        teamName: data.teamName,
        repoName: data.repositoryName, // Map repositoryName to repoName for API
      })
      return response
    },
    onSuccess: (_, data) => {
      queryClient.invalidateQueries({ queryKey: ['repositories'] })
      queryClient.invalidateQueries({ queryKey: ['teams'] })
      toast.success(`Repository "${data.repositoryName}" deleted successfully`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to delete repository')
    },
  })
}