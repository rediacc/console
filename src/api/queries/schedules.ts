import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '../client'
import toast from 'react-hot-toast'

export interface Schedule {
  scheduleName: string
  scheduleVault: string
  vaultVersion: number
  description: string
  isActive: boolean
  cronExpression: string
  nextRunTime: string
  lastRunTime: string
  queueCount: number
  createdAt: string
  updatedAt: string
}

export interface CreateScheduleRequest {
  scheduleName: string
  scheduleVault: string
  description?: string
  cronExpression: string
  isActive?: boolean
}

export interface UpdateScheduleVaultRequest {
  scheduleName: string
  scheduleVault: string
  vaultVersion: number
}

export interface UpdateScheduleStatusRequest {
  scheduleName: string
  isActive: boolean
}

// Get all schedules
export const useSchedules = () => {
  return useQuery({
    queryKey: ['schedules'],
    queryFn: async () => {
      const response = await apiClient.get<Schedule>('/GetSchedules')
      return response.tables?.[0]?.data || []
    },
  })
}

// Create schedule
export const useCreateSchedule = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: CreateScheduleRequest) => {
      const response = await apiClient.post('/CreateSchedule', data)
      return response
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['schedules'] })
      toast.success('Schedule created successfully')
    },
    onError: (error: any) => {
      console.error('Failed to create schedule:', error)
    },
  })
}

// Delete schedule
export const useDeleteSchedule = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (scheduleName: string) => {
      const response = await apiClient.delete('/DeleteSchedule', { scheduleName })
      return response
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['schedules'] })
      toast.success('Schedule deleted successfully')
    },
    onError: (error: any) => {
      console.error('Failed to delete schedule:', error)
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['schedules'] })
      toast.success('Schedule vault updated successfully')
    },
    onError: (error: any) => {
      console.error('Failed to update schedule vault:', error)
    },
  })
}

// Update schedule status (activate/deactivate)
export const useUpdateScheduleStatus = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: UpdateScheduleStatusRequest) => {
      const response = await apiClient.put('/UpdateScheduleStatus', data)
      return response
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['schedules'] })
      toast.success(`Schedule ${variables.isActive ? 'activated' : 'deactivated'} successfully`)
    },
    onError: (error: any) => {
      console.error('Failed to update schedule status:', error)
    },
  })
}