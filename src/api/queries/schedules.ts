import { useQuery } from '@tanstack/react-query'
import apiClient from '../client'
import { createResourceMutation, createVaultUpdateMutation, createMutation } from '@/api/utils/mutationFactory'

export interface Schedule {
  scheduleName: string
  teamName: string
  vaultContent?: string
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
      
      const response = await apiClient.get('/GetTeamSchedules', params)
      const data = response.resultSets?.[1]?.data || []
      const schedules = Array.isArray(data) ? data : []
      return schedules
        .filter((schedule: any) => schedule && schedule.scheduleName)
        .map((schedule: any) => ({
          scheduleName: schedule.scheduleName,
          teamName: schedule.teamName,
          vaultVersion: schedule.vaultVersion || 1,
          vaultContent: schedule.vaultContent || '{}',
        }))
    },
    enabled: !!teamFilter && (!Array.isArray(teamFilter) || teamFilter.length > 0),
    staleTime: 30 * 1000, // 30 seconds
  })
}

// Create schedule
export const useCreateSchedule = createMutation<CreateScheduleRequest>({
  endpoint: '/CreateSchedule',
  method: 'post',
  invalidateKeys: ['schedules', 'teams'],
  successMessage: (vars) => `Schedule "${vars.scheduleName}" created successfully`,
  errorMessage: 'Failed to create schedule',
  transformData: (data) => ({
    ...data,
    scheduleVault: data.scheduleVault || '{}'
  })
})

// Delete schedule
export const useDeleteSchedule = createResourceMutation<{
  teamName: string
  scheduleName: string
}>(
  'Schedule',
  'delete',
  '/DeleteSchedule',
  'scheduleName',
  ['teams']
)

// Update schedule name
export const useUpdateScheduleName = createMutation<{
  teamName: string
  currentScheduleName: string
  newScheduleName: string
}>({
  endpoint: '/UpdateScheduleName',
  method: 'put',
  invalidateKeys: ['schedules'],
  successMessage: (vars) => `Schedule renamed to "${vars.newScheduleName}"`,
  errorMessage: 'Failed to update schedule name'
})

// Update schedule vault
export const useUpdateScheduleVault = createVaultUpdateMutation<UpdateScheduleVaultRequest>(
  'Schedule',
  '/UpdateScheduleVault',
  'scheduleName',
  'scheduleVault'
)