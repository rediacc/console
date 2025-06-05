import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '../client'
import toast from 'react-hot-toast'

export interface Schedule {
  scheduleName: string
  teamName: string
  scheduleVault: string
  vaultVersion: number
}

export interface CreateScheduleRequest {
  teamName: string
  scheduleName: string
  scheduleVault?: string
}

export interface UpdateScheduleVaultRequest {
  teamName: string
  scheduleName: string
  scheduleVault: string
  vaultVersion: number
}

// Get schedules for a team or multiple teams
export const useSchedules = (teamFilter?: string | string[]) => {
  return useQuery<Schedule[]>({
    queryKey: ['schedules', teamFilter],
    queryFn: async () => {
      if (!teamFilter || (Array.isArray(teamFilter) && teamFilter.length === 0)) return []
      
      // Build params based on teamFilter
      let params = {}
      
      if (Array.isArray(teamFilter)) {
        // Send comma-separated teams in a single request
        params = { teamName: teamFilter.join(',') }
      } else {
        // Single team
        params = { teamName: teamFilter }
      }
      
      const response = await apiClient.get<any>('/GetTeamSchedules', params)
      const data = response.tables?.[1]?.data || response.tables?.[0]?.data || []
      if (!Array.isArray(data)) return []
      return data.filter((schedule: any) => schedule && schedule.scheduleName)
    },
    enabled: !!teamFilter && (!Array.isArray(teamFilter) || teamFilter.length > 0),
    staleTime: 30 * 1000, // 30 seconds
  })
}

// Create schedule
export const useCreateSchedule = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: CreateScheduleRequest) => {
      const response = await apiClient.post('/CreateSchedule', {
        teamName: data.teamName,
        scheduleName: data.scheduleName,
        scheduleVault: data.scheduleVault || '{}',
      })
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['schedules'] })
      queryClient.invalidateQueries({ queryKey: ['teams'] })
      toast.success(`Schedule "${variables.scheduleName}" created successfully`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to create schedule')
    },
  })
}

// Delete schedule
export const useDeleteSchedule = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: { teamName: string; scheduleName: string }) => {
      const response = await apiClient.delete('/DeleteSchedule', data)
      return response
    },
    onSuccess: (_, data) => {
      queryClient.invalidateQueries({ queryKey: ['schedules'] })
      queryClient.invalidateQueries({ queryKey: ['teams'] })
      toast.success(`Schedule "${data.scheduleName}" deleted successfully`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to delete schedule')
    },
  })
}

// Update schedule name
export const useUpdateScheduleName = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: async (data: { teamName: string; currentScheduleName: string; newScheduleName: string }) => {
      const response = await apiClient.put('/UpdateScheduleName', data)
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['schedules'] })
      toast.success(`Schedule renamed to "${variables.newScheduleName}"`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to update schedule name')
    },
  })
}

// Update schedule vault
export const useUpdateScheduleVault = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: UpdateScheduleVaultRequest) => {
      const response = await apiClient.put('/UpdateScheduleVault', data)
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['schedules'] })
      toast.success(`Schedule vault updated for "${variables.scheduleName}"`)
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to update schedule vault')
    },
  })
}